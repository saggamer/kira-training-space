import collections
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import threading
import uuid
import zipfile
from urllib.request import Request, urlopen
from urllib.parse import quote

from catalog import CATEGORIES, LESSONS, catalog, starter_rows
from integrations import colab_call, colab_command, soup_call, soup_command, redact

MAX_DATA = 20 * 1024 * 1024

def now(): return datetime.now(timezone.utc).isoformat()

def inspect_text(content):
    if not isinstance(content, str) or len(content.encode()) > MAX_DATA:
        raise ValueError("Dataset must be UTF-8 JSON/JSONL, at most 20 MB")
    errors, rows = [], []
    if content.lstrip().startswith("["):
        try:
            rows = json.loads(content)
            if not isinstance(rows, list): raise ValueError("Expected a JSON array")
        except json.JSONDecodeError as exc: errors.append({"row": 1, "message": str(exc)})
    else:
        for line_no, line in enumerate(content.splitlines(), 1):
            if not line.strip(): continue
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: errors.append({"row":line_no, "message":"Invalid JSON"})
    hashes, groups, lengths, splits = [], {}, [], collections.Counter()
    valid = 0
    schema_counts = collections.Counter()
    pii_rows = 0
    for i,row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append({"row":i,"message":"Expected an object"}); continue
        encoded = json.dumps(row, sort_keys=True, ensure_ascii=False)
        # Exclude bookkeeping fields from duplicate detection.
        payload = {k:v for k,v in row.items() if k not in {"split","group_id","provenance","id"}}
        digest = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        hashes.append(digest); lengths.append(len(encoded))
        split = str(row.get("split", "unspecified")); splits[split] += 1
        group = str(row.get("group_id", digest))
        groups.setdefault(group, set()).add(split)
        groups.setdefault("hash:"+digest, set()).add(split)
        if re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{3}[- .]\d{3}[- .]\d{4}\b', encoded): pii_rows += 1
        kind = None
        if isinstance(row.get("messages"), list) and row["messages"]:
            msgs = row["messages"]
            if all(isinstance(m,dict) and m.get("role") in {"system","user","assistant","tool"} and isinstance(m.get("content"),str) for m in msgs) and any(m["role"]=="assistant" and m["content"].strip() for m in msgs): kind="chat"
        elif all(isinstance(row.get(k),str) and row[k].strip() for k in ("prompt","chosen","rejected")):
            if row["chosen"] != row["rejected"]: kind="dpo"
        elif all(isinstance(row.get(k),str) and row[k].strip() for k in ("instruction","output")): kind="alpaca"
        if kind: valid += 1; schema_counts[kind] += 1
        else: errors.append({"row":i,"message":"Expected nonempty chat messages, instruction/output, or distinct prompt/chosen/rejected strings"})
    leakage = [g for g,s in groups.items() if len(s)>1 and "train" in s and (s & {"test","validation","eval"})]
    duplicates = len(hashes) - len(set(hashes))
    warnings = []
    if duplicates: warnings.append(f"{duplicates} duplicate payloads; deduplicate before training.")
    if pii_rows: warnings.append(f"{pii_rows} rows match simple PII patterns; manually review. This is not a complete privacy scan.")
    if len(schema_counts)>1: warnings.append("Mixed schemas; normalize to a single trainer format.")
    if splits.get("unspecified"): warnings.append("Split metadata missing; create held-out evaluation data before training.")
    if len(rows)<100: warnings.append("Very small sample; useful for workflow checks, not evidence of model quality.")
    if lengths and max(lengths)>12000: warnings.append("Long examples detected; use a tokenizer-aware truncation check in Soup.")
    return {"rows":len(rows),"valid_rows":valid,"invalid_rows":len(errors),"duplicates":duplicates,
            "schema":next(iter(schema_counts)) if len(schema_counts)==1 else "mixed/unknown", "splits":dict(splits),
            "leakage":leakage, "pii_pattern_rows":pii_rows,"warnings":warnings,"errors":errors[:100],
            "length_chars":{"min":min(lengths,default=0),"max":max(lengths,default=0),"mean":round(sum(lengths)/len(lengths)) if lengths else 0},
            "ready":bool(rows) and not errors and not leakage and not duplicates and len(schema_counts)==1,
            "preview":rows[:3], "sha256":hashlib.sha256(content.encode()).hexdigest()}

class Space:
    def __init__(self, workspace, project=None):
        self.workspace = Path(workspace).resolve()
        self.project = Path(project or self.workspace.parent).resolve()
        self.workspace.mkdir(parents=True,exist_ok=True)
        (self.workspace/"datasets").mkdir(exist_ok=True)
        (self.workspace/"plans").mkdir(exist_ok=True)
        self.jobs_lock=threading.Lock()
        self.active_jobs=set()
        from soup_training import SoupTraining
        self.soup_training=SoupTraining(self)
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,name TEXT,category TEXT,path TEXT,report TEXT,created TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,body TEXT,created TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY,title TEXT,body TEXT,evidence TEXT,created TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY,kind TEXT,title TEXT,entity_id TEXT,details TEXT,created TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS history_created ON history(created DESC)")
            # Carry existing saved work into history using its original creation time.
            for identifier,name,category,report,created in db.execute("SELECT id,name,category,report,created FROM datasets").fetchall():
                self.record_event("datasets","Dataset added: "+name,identifier,{"category":category,"rows":json.loads(report)["rows"]},db=db,event_id="dataset-"+identifier,created=created)
            for identifier,body,created in db.execute("SELECT id,body,created FROM plans").fetchall():
                plan=json.loads(body)
                self.record_event("training","Training plan prepared: "+plan["name"],identifier,{"model":plan["model"],"gpu":plan["gpu"],"status":"prepared"},db=db,event_id="plan-"+identifier,created=created)

    def record_event(self,kind,title,entity_id="",details=None,db=None,event_id=None,created=None):
        values=(event_id or uuid.uuid4().hex,kind,title,entity_id,json.dumps(details or {},ensure_ascii=False),created or now())
        if db is not None:
            db.execute("INSERT OR IGNORE INTO history VALUES(?,?,?,?,?,?)",values)
        else:
            with self.db() as connection: connection.execute("INSERT OR IGNORE INTO history VALUES(?,?,?,?,?,?)",values)

    def history(self,limit=500):
        limit=max(1,min(int(limit),5000))
        with self.db() as db:
            rows=db.execute("SELECT id,kind,title,entity_id,details,created FROM history ORDER BY created DESC,rowid DESC LIMIT ?",(limit,)).fetchall()
        return [{"id":i,"kind":k,"title":t,"entity_id":e,"details":json.loads(d),"created":c} for i,k,t,e,d,c in rows]

    def record_source_download(self,identifier,filename):
        item=self.item(identifier)
        if item["kind"]!="public" or not isinstance(filename,str) or not filename or len(filename)>1000:
            raise ValueError("Choose a public dataset file")
        self.record_event("downloads","Source download opened: "+item["name"],identifier,{"repo":item["repo"],"file":filename,"status":"opened at source; completion not tracked"})
        return {"saved":True}

    @contextmanager
    def db(self):
        connection=sqlite3.connect(self.workspace/"space.sqlite3",timeout=15)
        try:
            with connection: yield connection
        finally: connection.close()

    def state(self):
        with self.db() as db:
            datasets=[{"id":i,"name":n,"category":c,"report":json.loads(r),"created":t} for i,n,c,r,t in db.execute("SELECT id,name,category,report,created FROM datasets ORDER BY created DESC")]
            plans=[json.loads(r[0]) for r in db.execute("SELECT body FROM plans ORDER BY created DESC")]
            lessons=[{"title":t,"body":b,"source":e,"created":c} for t,b,e,c in db.execute("SELECT title,body,evidence,created FROM lessons ORDER BY created DESC")]
        for plan in plans:
            if plan.get("backend")!="soup" and plan["status"] in {"starting","running"} and plan["id"] not in self.active_jobs:
                plan["status"]="connection_lost"
                plan["log"]="The app restarted during this run. Its Colab runtime may still be active. Check sessions and stop unused compute."
        return {"categories":CATEGORIES,"catalog":catalog(),"datasets":datasets,"plans":plans,"lessons":LESSONS+lessons,"history":self.history(),
                "connections":{"codex":{"installed":any((Path.home()/".codex/plugins/cache/kira-training-local/kira-training-space").glob("*/.codex-plugin/plugin.json"))},"kira":{"enabled":self.kira_plugin_enabled()},"soup":{"installed":bool(soup_command()),"mode":"Inspection + optional full local SFT/DPO training"},
                               "colab":{"installed":bool(colab_command(self.project)),"mode":"Official Google Colab CLI; authentication checked on refresh"}}}

    def kira_plugin_enabled(self):
        try:
            conf=json.loads((self.project/"kira_plugins/plugin_state.json").read_text())
            return bool(conf.get("enabled",{}).get("kira-training-space"))
        except (OSError,ValueError):return False

    def item(self, identifier):
        for item in catalog():
            if item["id"] == identifier: return item
        raise ValueError("Unknown catalog dataset")

    def content(self, identifier):
        if identifier.startswith("starter-"):
            item=self.item(identifier)
            return "\n".join(json.dumps(r,ensure_ascii=False) for r in starter_rows(item["category"]))+"\n"
        with self.db() as db:
            result=db.execute("SELECT path FROM datasets WHERE id=?",(identifier,)).fetchone()
        if not result: raise ValueError("Unknown local dataset")
        path=(self.workspace/result[0]).resolve()
        if not path.is_relative_to(self.workspace/"datasets"): raise ValueError("Invalid dataset path")
        return path.read_text()

    def import_data(self, name, category, content):
        if category not in {c["id"] for c in CATEGORIES}: raise ValueError("Unknown category")
        name=str(name).strip()[:160]
        if not name: raise ValueError("A dataset name is required")
        report=inspect_text(content)
        identifier=uuid.uuid4().hex
        path="datasets/"+identifier+".jsonl"
        (self.workspace/path).write_text(content)
        with self.db() as db:
            db.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?)",(identifier,name,category,path,json.dumps(report),now()))
            self.record_event("datasets","Dataset added: "+name,identifier,{"category":category,"rows":report["rows"],"schema":report["schema"],"structure_checks_passed":report["ready"]},db=db,event_id="dataset-"+identifier)
        return {"id":identifier,"name":name,"category":category,"report":report}

    def hub_files(self, identifier):
        item=self.item(identifier)
        if item["kind"] != "public": raise ValueError("Select a public dataset")
        repo=item["repo"]
        # Resolve immutable commit before listing files and constructing download URLs.
        url="https://huggingface.co/api/datasets/"+repo
        with urlopen(Request(url,headers={"User-Agent":"KiraTrainingSpace/0.1"}),timeout=20) as response:
            data=json.load(response)
        sha=data.get("sha","")
        if not re.fullmatch(r"[a-f0-9]{40,64}",sha): raise ValueError("Hub did not return an immutable dataset revision")
        files=[]
        for sibling in data.get("siblings",[]):
            name=sibling.get("rfilename","")
            if name.lower().endswith((".parquet",".jsonl",".json",".csv",".zip",".tar.gz",".arrow")):
                hint="evaluation" if re.search(r"(^|[/_.-])(test|dev|validation|eval)([/_.-]|$)",name.lower()) else "training" if re.search(r"(^|[/_.-])train([/_.-]|$)",name.lower()) else "check source split"
                files.append({"name":name,"split_hint":hint,"url":f"https://huggingface.co/datasets/{repo}/resolve/{sha}/{quote(name,safe='/')}?download=true"})
        files.sort(key=lambda f:(f["split_hint"]!="training",f["split_hint"]=="evaluation",f["name"]))
        return {"repo":repo,"revision":sha,"files":files,"license":item["license"],"source_url":item["source_url"],
                "note":"Downloads go directly from the source to your browser. Gated sources may require source-site login; Kira does not bypass access restrictions."}

    def soup(self, action, dataset_id=None, recipe=None):
        if action in {"data_inspect","data_validate","data_score","advise"}:
            content=self.content(dataset_id)
            if dataset_id.startswith("starter-"):
                item=self.item(dataset_id)
                local=self.import_data(item["name"],item["category"],content)
                dataset_id=local["id"]
            path=str(self.workspace/"datasets"/(dataset_id+".jsonl"))
            result=soup_call(self.workspace,action,{"data":path})
            self.record_event("inspection","Soup "+action.replace("_"," "),dataset_id,{"tool":action,"status":"failed" if result.get("isError") else "completed"})
            return result
        if action in {"recipes_search","recipes_show"}:
            value=recipe or ("lora" if action=="recipes_search" else "qwen2.5-0.5b-sft")
            result=soup_call(self.workspace,action,{"query" if action=="recipes_search" else "name":value})
            self.record_event("inspection","Soup recipe "+("search" if action=="recipes_search" else "opened"),details={"recipe":value,"status":"failed" if result.get("isError") else "completed"})
            return result
        raise ValueError("Unsupported inspection action")

    def create_plan(self, dataset_id, model, name, gpu="T4"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",model): raise ValueError("Use a Hub model ID such as Qwen/Qwen2.5-0.5B-Instruct")
        if gpu not in {"T4","L4","A100","H100"}: raise ValueError("Unsupported GPU")
        content=self.content(dataset_id)
        report=inspect_text(content)
        category=self.item(dataset_id)["category"] if dataset_id.startswith("starter-") else None
        if not category:
            with self.db() as db: category=db.execute("SELECT category FROM datasets WHERE id=?",(dataset_id,)).fetchone()[0]
        if not report["ready"]: raise ValueError("Resolve invalid rows, duplicate payloads, or split leakage before preparing a run")
        if category in {"image","preference"} or report["schema"]=="dpo":
            raise ValueError("This category needs a dedicated image or DPO trainer. Use Soup recipes to choose one; the bundled runner supports text chat SFT only.")
        if report["schema"]!="chat": raise ValueError("The bundled SFT runner requires chat messages; normalize the dataset first")
        from train_template import grouped_split
        grouped_split([json.loads(line) for line in content.splitlines() if line.strip()] if not content.lstrip().startswith("[") else json.loads(content))
        # Normalize JSON-array imports into JSONL for the portable script.
        if content.lstrip().startswith("["):
            content="\n".join(json.dumps(row,ensure_ascii=False) for row in json.loads(content))+"\n"
        identifier=uuid.uuid4().hex
        directory=self.workspace/"plans"/identifier
        directory.mkdir()
        (directory/"train.jsonl").write_text(content)
        # A runnable, portable script with embedded reviewed data; never uploads unrelated project files.
        template=Path(__file__).with_name("train_template.py").read_text()
        template=template.replace('MODEL_ID = "__MODEL__"',"MODEL_ID = "+repr(model))
        template=template.replace('DATA_JSON = "__DATA__"',"DATA_JSON = "+repr(content))
        (directory/"train.py").write_text(template)
        run_cmd=(colab_command(self.project) or ["colab"])+["run","--gpu",gpu,"--keep","--timeout","7200","-s","kira-"+identifier[:12],str(directory/"train.py")]
        plan={"id":identifier,"name":str(name or "My first fine-tune")[:160],"dataset_id":dataset_id,"model":model,
              "gpu":gpu,"status":"prepared","created":now(),"report":report,"category":category,
              "command":shlex.join(run_cmd),"directory":str(directory),"training":"Text-only QLoRA SFT",
              "checks":["Source train split only", "Grouped holdout created by runner", "Review data rights and privacy", "Evaluate candidate against baseline before promotion"],
              "note":"Prepared, not executed. Colab can use paid compute. The runtime stays allocated after training so you can download artifacts; stop it when finished."}
        with self.db() as db:
            db.execute("INSERT INTO plans VALUES(?,?,?)",(identifier,json.dumps(plan),now()))
            self.record_event("training","Training plan prepared: "+plan["name"],identifier,{"model":model,"gpu":gpu,"status":"prepared"},db=db,event_id="plan-"+identifier)
        return plan

    def get_plan(self, identifier):
        with self.db() as db: result=db.execute("SELECT body FROM plans WHERE id=?",(identifier,)).fetchone()
        if not result: raise ValueError("Plan not found")
        return json.loads(result[0])

    def save_plan(self, plan):
        with self.db() as db: db.execute("UPDATE plans SET body=? WHERE id=?",(json.dumps(plan),plan["id"]))

    def start_plan(self, identifier, confirmed=False):
        if confirmed is not True: raise ValueError("Review and confirm cloud compute before starting")
        command=colab_command(self.project)
        if not command: raise ValueError("Install and authenticate Google Colab CLI before starting")
        with self.jobs_lock:
            plan=self.get_plan(identifier)
            if plan["status"]!="prepared": raise ValueError("This plan has already been submitted; prepare a new plan for another attempt")
            plan.update(status="starting",session="kira-"+identifier[:12],started=now(),log="Submitting to Colab…")
            self.save_plan(plan)
            self.record_event("training","Colab run submitted: "+plan["name"],identifier,{"status":"submitted","gpu":plan["gpu"],"session":plan["session"]})
            self.active_jobs.add(identifier)
        def run():
            try:
                plan["status"]="running";self.save_plan(plan)
                args=command+["run","--gpu",plan["gpu"],"--keep","--timeout","7200","-s",plan["session"],str(self.workspace/"plans"/identifier/"train.py")]
                # Bound execution. Log complete output only after redaction; no raw logs persist.
                result=subprocess.run(args,capture_output=True,text=True,stdin=subprocess.DEVNULL,timeout=7500,cwd=self.workspace/"plans"/identifier)
                plan["status"]="completed" if result.returncode==0 else "failed"
                plan["log"]=redact(result.stdout)[-16000:] if result.returncode==0 else "Colab training did not complete. Check the session in the official CLI; the runtime may still be allocated."
            except Exception:
                plan["status"]="failed";plan["log"]="Training connection failed or timed out. Check Colab sessions and stop unused compute."
            finally:
                plan["finished"]=now()
                if self.get_plan(identifier).get("runtime_stopped"): plan["runtime_stopped"]=True
                self.save_plan(plan)
                self.record_event("training","Colab run "+plan["status"]+": "+plan["name"],identifier,{"status":plan["status"],"session":plan["session"]})
                with self.jobs_lock: self.active_jobs.discard(identifier)
        threading.Thread(target=run,daemon=True).start()
        return plan

    def stop_plan(self,identifier,confirmed=False):
        if confirmed is not True: raise ValueError("Confirm stopping the runtime; unsaved files will be lost")
        plan=self.get_plan(identifier)
        if not plan.get("session"): raise ValueError("No session was submitted for this plan")
        result=colab_call(self.project,["stop","-s",plan["session"]])
        if result["ok"]:
            plan["runtime_stopped"]=True; self.save_plan(plan)
            self.record_event("training","Colab runtime stopped: "+plan["name"],identifier,{"session":plan["session"]})
        return result

    def download_artifact(self,identifier):
        plan=self.get_plan(identifier)
        if plan["status"]!="completed": raise ValueError("Artifacts are available after a successful run")
        dest=self.workspace/"plans"/identifier/"kira-adapter.zip"
        result=colab_call(self.project,["download","-s",plan["session"],"/content/kira-adapter.zip",str(dest)],timeout=120)
        if not result["ok"]: raise ValueError(result["message"])
        if not dest.is_file(): raise ValueError("Colab did not return the adapter archive")
        self.record_event("downloads","Adapter archive retrieved: "+plan["name"],identifier,{"file":"kira-adapter.zip"})
        return dest.read_bytes()

    def plan_bundle(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{32}",identifier): raise ValueError("Invalid plan ID")
        directory=self.workspace/"plans"/identifier
        if not directory.is_dir(): raise ValueError("Plan not found")
        out=io.BytesIO()
        if (directory/"soup.json").is_file():
            with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
                cfg=json.loads((directory/"soup.json").read_text());cfg["data"]["train"]="./train.jsonl";cfg["output"]="./adapter"
                archive.writestr("soup.json",json.dumps(cfg,indent=2))
                archive.write(directory/"train.jsonl","train.jsonl")
                archive.writestr("README.txt","Install compatible Soup training dependencies. Review soup.json, then run soup train --config soup.json only after authorizing compute.\n")
            return out.getvalue()
        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as archive:
            for name in (["soup.json","train.jsonl"] if (directory/"soup.json").is_file() else ["train.py","train.jsonl"]): archive.write(directory/name,name)
            archive.writestr("requirements.txt","trl==0.23.1\ntransformers==4.56.2\npeft==0.17.1\naccelerate==1.10.1\ndatasets==4.1.1\nbitsandbytes==0.47.0\n")
            archive.writestr("README.txt","Install requirements in a CUDA environment, then run python train.py.\nThe script saves an adapter, tokenizer and evaluation metrics to kira-adapter.\nIt does not claim improvement or promote a model automatically.\n")
        return out.getvalue()

    def add_lesson(self,title,body,evidence):
        if not all(isinstance(s,str) and s.strip() for s in (title,body,evidence)): raise ValueError("Title, lesson and evidence reference are required")
        if max(len(title),len(body),len(evidence))>4000: raise ValueError("Lesson fields are too long")
        with self.db() as db:
            identifier=uuid.uuid4().hex
            db.execute("INSERT INTO lessons VALUES(?,?,?,?,?)",(identifier,title,body,evidence,now()))
            self.record_event("notes","Experience note saved: "+title,identifier,{"evidence":evidence},db=db)
        return {"saved":True,"note":"Saved as a user-reviewed note; this does not update model weights."}
