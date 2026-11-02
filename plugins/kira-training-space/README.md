# Kira Training Space

Your model. Your way. A local data studio and Codex plugin for fine-tuning workflows.

[Website](https://kira-training-space.bluelily129.chatgpt.site) · [Watch the demo](website/dist/assets/kira-training-space-ad.mp4)

## Start locally

Requires Python 3.11+. The app and MCP server use Python's standard library.

```sh
git clone https://github.com/saggamer/kira-training-space.git
cd kira-training-space
python3 plugins/kira-training-space/runtime/server.py --workspace ./training-space-data --project .
```

Open http://127.0.0.1:8765. On macOS you can also use `RUN_TRAINING_SPACE.command`.
The app binds to loopback. Imported data, plans, history and reviewed experience
notes are saved in the selected local workspace, which is ignored by Git.

## Install in Codex

```sh
codex plugin marketplace add ./kira-training-space
codex plugin add kira-training-space@kira-training
```

Run these from the parent of your checkout, or pass the checkout's absolute path.
Open a fresh Codex chat after installation. Example:

> Use Kira Training Space to inspect my dataset and prepare a Soup fine-tuning plan for review. Do not start training yet.

Set `KIRA_TRAINING_WORKSPACE` before launching the MCP server to choose its data
folder. Keep the same MCP process alive between preparing and confirming Soup
operations. The plugin has ten tools for catalog access, scoped inspection,
download discovery, Colab status/plans and optional Soup training/export.

## What you can do

- Browse six model categories, six small synthetic starters and seven attributed
  public dataset catalogs, with immutable-revision source download URLs.
- Import JSON/JSONL and inspect chat, instruction/output or DPO rows. Check
  duplicates, explicit split leakage, schema errors and heuristic privacy flags.
- Prepare a bundled CUDA text-chat QLoRA SFT runner with a grouped holdout and
  baseline/candidate loss metrics. Authorize Colab compute through a review step,
  retrieve adapters, and stop the runtime after saving your files.
- Optionally let **Soup handle the full local text SFT/DPO training workflow**:
  inspect, validate, review a configuration, train, track the run, then export.
  Export format support depends on the selected model and Soup dependencies.
- Keep searchable activity history and evidence-linked experience notes locally.

Training depends on the selected backend, compatible dependencies, model access
and suitable hardware. Neither installation nor website browsing starts training.
Image/audio sources are cataloged, but require dedicated training recipes and
binary-data tooling; they are not supported by this guided text training flow.
Six-row CC0 starters demonstrate schemas, not model quality.

## Soup and Colab setup

Install a compatible Soup environment, then expose its MCP executable:

```sh
export KIRA_SOUP_COMMAND='["/absolute/path/to/venv/bin/soup","mcp","serve"]'
```

Inspection uses read-only tools. Choosing Soup training opens a separate scoped
stdio session with `--allow-execute`. Preparation creates a five-minute, one-use
confirmation. Review the model, data, configuration and local compute before
execution. Changed inputs or a server restart require a new plan. Training and
export remain explicit actions. The app never runs arbitrary shell strings.

For Colab, install and authenticate the [official CLI](https://github.com/googlecolab/google-colab-cli).
Set `KIRA_COLAB_PYTHON` to its Python interpreter if it is not detected. Credentials
stay in the CLI; do not put them in manifests. The runtime stays allocated until
you stop it, and compute can be billed by your provider.

## Kira Superapp

Training Space is integrated with Kira Superapp's plugin screen in the development
workspace. For this standalone release, run the local app or install the Codex
plugin above. A portable Superapp installer is not included in this release.

## Verify

```sh
python3 -m unittest discover -s training_space_tests -v
```

28 unit tests cover data integrity, path boundaries, history, plan lifecycle,
confirmation/replay gates, grouped-data restrictions and export review. Browser
checks and real Soup SFT/DPO preflights passed during development. Full GPU training
was not run for the release demonstration. Review task-level results before
promoting a model. See [training principles](docs/TRAINING_PRINCIPLES.md).

## Public website

`website/dist/` is a buildless static website with dataset filters, starter
downloads, source file discovery, a browser-local data check and the product ad.
Serve it with `python3 -m http.server --directory website/dist 8080`.
No accounts or training credentials are needed to browse it.

## Data and credits

Kira's synthetic starters are CC0-1.0. Public dataset cards retain their own license
and access terms; inspect underlying asset rights and official train/test splits.
The ad uses local Kokoro-82M neural narration. It depicts a prepared workflow,
not a successful model training run. No third-party font files are distributed.


## Portable ZIP

After extracting the plugin ZIP, use `codex plugin marketplace add
/absolute/path/to/extracted/marketplace.json`, then `codex plugin add
kira-training-space@kira-training-local`. The ZIP marketplace uses the local name
`kira-training-local`; the source repository uses `kira-training`.
To launch the extracted plugin without Codex, enter its `kira-training-space/`
folder and run `python3 runtime/server.py`.
