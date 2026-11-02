---
name: training-space
description: Discover categorized model-training data, inspect JSONL with Soup, prepare text fine-tuning plans, and check an existing Google Colab CLI connection in Kira Training Space.
---

Use the bundled Kira Training Space MCP tools. Start with `training_catalog` to see
dataset IDs, model categories, local reports, activity history, and evidence-backed project lessons.
The local app opens with `python3 runtime/server.py` from this plugin directory.
Use `KIRA_TRAINING_WORKSPACE` to select a persistent data directory; otherwise it
uses `training-space-data` under the process working directory. Only inspect files
within that directory. Do not move unrelated private project data into it.

For public data, `dataset_download_files` resolves direct source URLs pinned to an
immutable Hub revision. Retain attribution and review dataset/underlying asset
terms. Gated sources require their own login. Kira's six-row CC0 starters are
synthetic schema examples, not production corpora or benchmark evidence.

Inspect imported data before preparing a run. Resolve invalid rows, duplicate
payloads and train/evaluation leakage. Soup tools add deeper inspection and recipes
when installed; a missing Soup dependency is an explicit setup state.

`prepare_training` writes a text-chat QLoRA script and a Colab command, without
executing it. The bundled runner cannot train image editing, speech or preference
models. Select an appropriate Soup recipe for those modalities. Explain the model,
data, compute and output destination before any separately authorized execution.
Do not report prepared plans as running or trained models.

`colab_status` reads sessions or compute usage using the official CLI's existing
authentication. When authentication is missing, guide the user to `colab --help`
and the official CLI setup; do not collect OAuth tokens in chat or manifests.

Preserve evaluation groups and asset hashes outside training/replay. Assess task
improvement and retained capabilities against the baseline before promotion.
Experience notes can inform decisions, but writing a note is not a weight update.

Activity history is persisted in the selected workspace and available in the app
with search, event-type filters and JSON export. A source-download event means a
link was opened; it is not evidence that a file transfer completed. History stores
metadata and references, not dataset message contents.

Optional full Soup backend: `prepare_soup_training` validates local text SFT or
DPO data and prepares an exact Soup configuration without starting compute.
Use `execute_soup_training` only after the user has reviewed the model, dataset,
configuration, local compute and destination and explicitly authorized that run.
Set confirmed=true only for that authorization. Soup confirmation tokens remain
in memory, expire after five minutes, are consumed once, and are invalid after a
server restart. A changed input requires a new plan. Keep this MCP process alive
between prepare and execute. `soup_training_status` retrieves run status and logs.
`soup_export` first prepares an export with confirmed=false; review its command
with the user before confirmed=true. Do not infer authorization to train from a
request to build, install, demonstrate, or inspect the plugin. Do not claim image
or audio support through this guided text SFT/DPO flow.
