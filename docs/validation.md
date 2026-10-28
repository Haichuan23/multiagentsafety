# Validation completed

Validated on the remote cluster login host `boslogin08.rc.fas.harvard.edu`.

- Conda environment `networkproject`: Python 3.11.18.
- PyTorch 2.6.0+cu124 imports successfully; compiled CUDA version 12.4.
- Transformers 4.57.6, Accelerate 1.15.0. Full installed versions: `requirements-lock.txt`.
- **26 tests passed** in 8.95 seconds. Tests cover the path-based exposure definition on
  branching DAGs, greedy selection, final-node budget accounting, rollback, audit schema
  rejection, answer isolation, Research scoring, token accounting, cached restarts, CLI
  resumption/config mismatch rejection, mixed GPU-memory keys, and the HTTP API backend
  against an actual local protocol test server.
- **10/10 offline smoke rows complete**, zero failed examples: both synthetic benchmarks,
  five Table 5 conditions, one seed. All rows explicitly carry `smoke: true` and use estimated
  fixture token usage. These scores/costs are not paper replications.
- **Two distinct real Hugging Face models loaded together and generated eight tokens each
  on CPU**: `hf-internal-testing/tiny-random-LlamaForCausalLM` and
  `hf-internal-testing/tiny-random-gpt2`. This validates model loading, per-role routing,
  generation and tokenizer-based usage, not reasoning/auditing quality.
- Both tiny models subsequently reloaded and generated again with `HF_HUB_OFFLINE=1` from
  this project's `.cache/huggingface/hub` directory. Activation overrides inherited model
  cache paths so subsequent downloads stay inside this folder.
- Model fixture revisions: Llama `9fb191250dd56d0ba7ec9785a025ed29c03d5998`, GPT-2
  `71034c5d8bde858ff824298bdedc65515b97d2b9`.
- Prepared 150 BBH examples from 6,511 upstream examples (sampling seed 42), and 100 official
  Research tasks. Checksums: `data/manifest.json`; source revisions: `vendor/provenance.json`.
- Persistent tmux setup session completed with **exit status 0**. Full log:
  `logs/networkproject-setup.log`; exit marker: `logs/networkproject-setup.exit`.

No full-scale experiments, paid external API calls, large model downloads, or GPU jobs were
run. Physical GPU execution remains unverified because this host has no visible GPU. A
small Slurm smoke job is provided in `scripts/slurm-gpu.sh`. An external API smoke config is
provided in `configs/api-smoke.yaml`; its endpoint/key must be supplied by the user.

The supplied PDF lacks the technical supplement. See `docs/methodology.md` for every
reconstruction choice and the limits on numerical reproducibility.
