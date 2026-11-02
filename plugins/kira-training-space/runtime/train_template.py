"""Portable text-only QLoRA runner. Install the pinned requirements in the bundle."""
import hashlib
import json
import random
from pathlib import Path

MODEL_ID = "__MODEL__"
DATA_JSON = "__DATA__"

def grouped_split(rows):
    """Only source train rows; identical payloads and groups stay together."""
    if any(r.get("split") in {"test","validation","eval"} for r in rows):
        raise ValueError("Import only training-split rows into this runner; preserve source evaluation data separately")
    groups = {}
    for row in rows:
        group = str(row.get("group_id") or hashlib.sha256(json.dumps(row["messages"],sort_keys=True).encode()).hexdigest())
        groups.setdefault(group,[]).append(row)
    keys = sorted(groups)
    if len(keys)<2: raise ValueError("Need at least two distinct groups to create a holdout")
    random.Random(42).shuffle(keys)
    holdout = set(keys[:max(1,round(len(keys)*.1))])
    train=[r for k in keys if k not in holdout for r in groups[k]]
    evaluation=[r for k in keys if k in holdout for r in groups[k]]
    train_hashes={hashlib.sha256(json.dumps(r["messages"],sort_keys=True).encode()).hexdigest() for r in train}
    eval_hashes={hashlib.sha256(json.dumps(r["messages"],sort_keys=True).encode()).hexdigest() for r in evaluation}
    if train_hashes & eval_hashes: raise ValueError("Duplicate message payload crosses the holdout boundary")
    return train,evaluation

def main():
    import subprocess
    import sys
    subprocess.check_call([sys.executable,"-m","pip","install","--quiet",
        "trl==0.23.1","transformers==4.56.2","peft==0.17.1","accelerate==1.10.1",
        "datasets==4.1.1","bitsandbytes==0.47.0"])
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer
    if not torch.cuda.is_available(): raise RuntimeError("This 4-bit QLoRA recipe requires an NVIDIA CUDA GPU")
    rows=[json.loads(line) for line in DATA_JSON.splitlines() if line.strip()]
    train,evaluation=grouped_split(rows)
    tokenizer=AutoTokenizer.from_pretrained(MODEL_ID,trust_remote_code=False)
    if not tokenizer.chat_template: raise ValueError("Choose an instruction model with a chat template")
    tokenizer.pad_token=tokenizer.pad_token or tokenizer.eos_token
    model=AutoModelForCausalLM.from_pretrained(MODEL_ID,trust_remote_code=False,device_map="auto",
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_compute_dtype=torch.float16))
    def normalized(data): return Dataset.from_list([{"messages":r["messages"]} for r in data])
    trainer=SFTTrainer(model=model,processing_class=tokenizer,train_dataset=normalized(train),eval_dataset=normalized(evaluation),
        peft_config=LoraConfig(r=8,lora_alpha=16,lora_dropout=.05,target_modules="all-linear",task_type="CAUSAL_LM"),
        args=SFTConfig(output_dir="kira-adapter",num_train_epochs=1,per_device_train_batch_size=1,
            gradient_accumulation_steps=4,learning_rate=2e-4,max_length=1024,fp16=True,bf16=False,
            logging_steps=1,save_strategy="epoch",report_to="none",seed=42,gradient_checkpointing=True))
    baseline=trainer.evaluate()
    trainer.train()
    candidate=trainer.evaluate()
    trainer.save_model("kira-adapter")
    tokenizer.save_pretrained("kira-adapter")
    Path("kira-adapter/evidence.json").write_text(json.dumps({"model":MODEL_ID,"train_rows":len(train),"holdout_rows":len(evaluation),
        "baseline":baseline,"candidate":candidate,"promotion":"unreviewed", "note":"Holdout loss alone does not establish task improvement or absence of regressions."},indent=2))
    import shutil
    shutil.make_archive("kira-adapter","zip","kira-adapter")
    print("Adapter saved to kira-adapter. Download it before releasing the runtime.")

if __name__=="__main__": main()
