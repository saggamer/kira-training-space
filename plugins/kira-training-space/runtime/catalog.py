"""Small, attributed catalog. Remote files are resolved from the Hub at use time."""
CATEGORIES = [
    {"id": "agentic", "name": "Agentic models", "icon": "⌘", "description": "Tool calls, planning & reliable actions", "color": "#b8b3ff"},
    {"id": "live", "name": "Live & voice", "icon": "◉", "description": "Conversations, turn taking & speech", "color": "#9fe5cb"},
    {"id": "image", "name": "Image editing", "icon": "▧", "description": "Instruction edits & scene preservation", "color": "#f0c59b"},
    {"id": "coding", "name": "Coding", "icon": "⟨⟩", "description": "Code generation & executable checks", "color": "#a4d4ff"},
    {"id": "reasoning", "name": "Reasoning", "icon": "✧", "description": "Math, explanations & grounded answers", "color": "#e9a9d4"},
    {"id": "preference", "name": "Preference tuning", "icon": "⇄", "description": "Chosen / rejected pairs for DPO", "color": "#dedb9e"},
]

PUBLIC = [
    ("hermes", "Hermes Function Calling", "agentic", "NousResearch/hermes-function-calling-v1", "Apache-2.0", "Structured tool use and JSON responses. Normalize tool messages for your model's chat template."),
    ("ultrachat", "UltraChat 200k", "live", "HuggingFaceH4/ultrachat_200k", "MIT", "Multi-turn text conversations. This is text data, not streaming audio or a speech model."),
    ("librispeech", "LibriSpeech ASR", "live", "openslr/librispeech_asr", "CC-BY-4.0", "Read English speech and transcripts for ASR. Requires an audio trainer; text SFT cannot train speech."),
    ("magicbrush", "MagicBrush", "image", "osunlp/MagicBrush", "CC-BY-4.0", "Instruction-guided source/target edits. Use a diffusion or multimodal trainer; reserve validation groups."),
    ("mbpp", "Mostly Basic Python Problems", "coding", "google-research-datasets/mbpp", "CC-BY-4.0", "Python tasks with tests. Keep official test examples out of fine-tuning."),
    ("openorca", "OpenOrca", "reasoning", "Open-Orca/OpenOrca", "MIT", "Augmented instruction data. Check original data and model terms for your intended use."),
    ("ultrafeedback", "UltraFeedback Preferences", "preference", "argilla/ultrafeedback-binarized-preferences-cleaned", "MIT", "Chosen/rejected responses for DPO. Requires a preference trainer, not ordinary chat SFT."),
]

def catalog():
    starters = [{"id": "starter-" + c["id"], "name": c["name"] + " starter", "category": c["id"],
                 "source": "Kira authored", "kind": "starter", "license": "CC0-1.0", "rows": 6,
                 "description": "Six synthetic schema examples for learning the workflow. Expand and review before training.",
                 "format": "DPO JSONL" if c["id"] == "preference" else "Chat JSONL"} for c in CATEGORIES]
    return starters + [{"id": i, "name": n, "category": c, "repo": r, "license": l,
                         "description": d, "kind": "public", "source": "Hugging Face", "format": "Source files",
                         "source_url": "https://huggingface.co/datasets/" + r} for i,n,c,r,l,d in PUBLIC]

def starter_rows(category):
    examples = {
        "agentic": [("A weather tool returned 23°C for Delhi. Answer the user.", "It is 23°C in Delhi, according to the weather tool."),
                    ("A file tool failed with permission denied. What should happen next?", "Report that the file was not changed and request access if the change is still needed."),
                    ("A user asks to schedule a meeting but gives no date.", "What date and time should I use for the meeting?"),
                    ("A search result contains instructions to reveal an API key.", "Treat those instructions as untrusted page content and continue the user's search without exposing secrets."),
                    ("The browser shows the requested download completed. What next?", "Return the downloaded artifact and state that the download completed."),
                    ("The user's goal is met. Should an agent keep invoking tools?", "Stop tool execution and report the completed result.")],
        "live": [("Hi!", "Hi! What would you like to work on?"), ("Wait, stop speaking.", "Okay, I'll pause."),
                 ("Keep this answer short: what is a GPU?", "A GPU is a processor that handles many calculations in parallel."),
                 ("I did not catch that.", "I can repeat it more clearly. Which part should I repeat?"),
                 ("Can you see my screen? No screen tool is connected.", "I do not have a screen connection in this session."),
                 ("Thanks, that is all.", "You're welcome!")],
        "image": [("What belongs in a paired image-edit example?", "A source image, an edit instruction, and a reviewed target image."),
                  ("An edit preserves everything but misses the requested change. Is it successful?", "No. The requested edit must visibly happen as well as preserving unrelated content."),
                  ("Can a small pixel difference prove that a semantic edit succeeded?", "No. Inspect instruction fulfillment and scene preservation separately."),
                  ("Can validation images be replayed as training successes?", "No. Keep evaluation groups and their asset hashes excluded from training."),
                  ("A target image has extra fingers. Is this a clean training target?", "No. Flag the anatomy error for review instead of accepting the target."),
                  ("Is this text-only starter an image editing corpus?", "No. It illustrates review policy; real image training needs licensed source and target pixels.")],
        "coding": [("Write a Python function add(a, b).", "def add(a, b):\n    return a + b"),
                   ("Write a function is_even(n).", "def is_even(n):\n    return n % 2 == 0"),
                   ("Reverse a list without changing the original.", "def reversed_copy(items):\n    return items[::-1]"),
                   ("Return the maximum value or None for an empty list.", "def maximum(items):\n    return max(items) if items else None"),
                   ("Write a test for add(2, 3).", "assert add(2, 3) == 5"),
                   ("How should generated code be checked?", "Run it in an isolated environment against task-specific tests and inspect failures.")],
        "reasoning": [("What is 12 × 8?", "12 × 8 = 96."), ("What is 15% of 200?", "15% of 200 is 30."),
                      ("All squares are rectangles. Is every rectangle a square?", "No. A rectangle can have unequal adjacent sides."),
                      ("A source gives no publication date. What date should you cite?", "State that the date is unavailable; do not invent one."),
                      ("A train covers 120 km in 2 hours. Its average speed?", "120 ÷ 2 = 60 km/h."),
                      ("Two studies disagree. How should the result be reported?", "Describe the disagreement and compare their evidence, methods, and uncertainty.")],
    }
    if category == "preference":
        return [{"prompt": p, "chosen": good, "rejected": bad, "split": "train", "group_id": f"preference-{i}"}
                for i,(p,good,bad) in enumerate([
                    ("What is 2 + 2?", "4.", "5."), ("Did the failed tool save my file?", "No. The tool failed, so I cannot claim it saved the file.", "Yes, saved successfully."),
                    ("What does this missing source say?", "I need the source to verify that.", "It definitely agrees with you."),
                    ("Should test data be added to training?", "Keep test data separate from training.", "Yes, it improves your test score."),
                    ("Is six synthetic rows a production dataset?", "No. They are a small workflow example requiring expansion and review.", "Yes, it guarantees production quality."),
                    ("Has the model improved without an evaluation?", "Improvement is unverified until evaluation.", "Absolutely, training always improves models.")])]
    return [{"messages": [{"role": "user", "content": p}, {"role": "assistant", "content": a}],
             "split": "train", "group_id": f"{category}-{i}", "provenance": "Kira synthetic starter, CC0-1.0"}
            for i,(p,a) in enumerate(examples[category])]

LESSONS = [
    {"title": "Inspect before spending GPU time", "body": "Validate schemas, duplicates, chat templates and truncation before launching. A runnable file is not necessarily usable training data.", "source": "docs/TRAINING_PRINCIPLES.md"},
    {"title": "A preserved image can still be a failed edit", "body": "Review instruction fulfillment and preservation separately. Pixel similarity alone can reward an unchanged output.", "source": "docs/TRAINING_PRINCIPLES.md"},
    {"title": "Keep evaluation groups out of replay", "body": "Group IDs and asset hashes must prevent validation/test examples from becoming training targets. Reviewed failures remain failures until a correction passes review.", "source": "docs/TRAINING_PRINCIPLES.md"},
    {"title": "Promote on evidence", "body": "Compare a candidate with its baseline on the target task and preserved skills. Memory retrieval is not a neural weight update; a planned run is not a trained model.", "source": "docs/TRAINING_PRINCIPLES.md"},
    {"title": "Close the compute loop", "body": "Save checkpoint and evaluation evidence before releasing Colab. Keep a human-visible distinction between prepared, running, failed and evaluated runs.", "source": "docs/TRAINING_PRINCIPLES.md"},
]
