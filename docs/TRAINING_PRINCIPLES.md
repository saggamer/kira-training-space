# Training principles

These reviewed design principles informed Kira Training Space. They are workflow
guidance, not empirical claims that a training run improved a model.

- Inspect schemas, duplicates, chat templates and truncation before using compute.
- Evaluate instruction fulfillment and preservation separately for image editing.
- Keep evaluation group IDs and asset hashes outside training and replay.
- Compare task outcomes and retained capabilities with a baseline before promotion.
- Preserve checkpoints and evaluation evidence before stopping cloud runtimes.
- A prepared plan is not a trained model. An experience note is not a weight update.

Training Space's bundled runner supports CUDA text-chat QLoRA SFT. Optional Soup
supports local text SFT/DPO through its installed trainer and export dependencies.
The public website provides dataset discovery and a browser-local schema preview;
it does not launch GPU jobs or send uploaded examples to a server.
