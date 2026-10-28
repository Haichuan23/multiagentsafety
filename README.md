# BRA-Audit — Table 5 experiment environment

An independent, runnable reconstruction of the supplied paper's audit-budget ablation.
It supports BBH and MultiAgentBench-Research, local Hugging Face models on GPU(s),
OpenAI-compatible API endpoints, or a mixture with per-agent model routing.

**Exact paper numbers cannot be guaranteed:** the paper omits its supplement, prompts,
workflow, sample IDs and recovery protocol. Read [methodology](docs/methodology.md) before
interpreting results. No full-scale study is launched by setup or default commands.

Completed checks and remaining hardware/API limits: [validation report](docs/validation.md).

## Activate and check

From this directory:

```bash
source scripts/activate.sh
# The prompt should show networkproject.
python -m pytest -q
bra-audit run --config configs/smoke.yaml --output results/smoke --limit 1
```

The Conda environment lives at `.conda/envs/networkproject`; packages and model caches
stay within this folder. `source scripts/activate.sh` also makes `conda activate networkproject`
resolve the project environment in that shell. To rebuild, run `scripts/bootstrap.sh`.
`requirements-lock.txt` records the installed package versions.

The offline smoke run processes one artificial example for each benchmark in all five
conditions, one repetition. It exercises attacks, auditing, recovery and reporting with a
fixture model; its scores are not experimental evidence. `scripts/hf-smoke.py` separately
checks real loading/generation with two tiny random CPU models, without benchmark scores.

## API mode

For a small paid test, copy `configs/api-smoke.yaml` to `configs/my-api.yaml`.
For the full matrix later, copy `configs/table5-api.yaml` to a separate config. Set `base_url` to your provider's `/v1` endpoint
and `model` to its exact Qwen3-235B-A22B-Instruct-2507 model identifier. Then set your key:

```bash
read -rs -p 'API key: ' BRA_API_KEY; export BRA_API_KEY; echo
# api-smoke.yaml already selects one seed, one round and one condition.
scripts/run.sh --config configs/my-api.yaml --output results/api-check --benchmark bbh --limit 1
```

No paid API calls are made during setup. API servers must implement `/chat/completions` and
return `usage.prompt_tokens` / `usage.completion_tokens`. Compatible vLLM or other local HTTP
servers work too (`require_key: false` if authentication is disabled). Native vendor APIs need
an OpenAI-compatible gateway. `token_parameter`, `extra_body`, timeouts, retries and seed
sending can be adjusted per model. Do not put credentials in YAML.

## Local GPU mode and multiple models

Use `configs/table5-local.yaml` for a shared smaller backbone, or `configs/multi-gpu.yaml`
for a 4B worker on GPU 0 and an 8B auditor/judge on GPU 1. You can route each `agent_0` through
`agent_4`, `auditor` and `judge` to any named model. API and HF models can coexist in one config.
Identical model specs share one resident model; distinct specs load independently.
These are separate logical agents with separate inputs, even when weights are shared.
Models execute serially in dependency order; multi-GPU routing is not parallel scheduling.

```bash
source scripts/activate.sh
bra-audit download-models --config configs/multi-gpu.yaml
# Run on an allocated GPU compute node, not the cluster login node:
CUDA_VISIBLE_DEVICES=0,1 scripts/run.sh --config configs/multi-gpu.yaml \
  --output results/local-check --benchmark bbh --limit 1
```

`device_map: auto` may shard a single model over visible GPUs (and offload if needed).
Use `max_memory: {0: 20GiB, 1: 20GiB, cpu: 40GiB}` to control sharding. Explicit maps such as
`device_map: {"": 1}` pin one model to one GPU. Match `dtype` to hardware (`bfloat16`,
`float16`, `float32`). Context overflows fail explicitly; text is not silently truncated.
Local model downloads happen on first use or via `download-models`; the paper's 235B model
requires substantial multi-GPU resources. The smaller examples do not replicate that backbone.

A one-example GPU smoke job template is provided. Fill in your cluster account/partition:

```bash
sbatch --account=YOUR_ACCOUNT --partition=YOUR_GPU_PARTITION scripts/slurm-gpu.sh
```

It uses Qwen3-0.6B, one round/seed/condition, and has not been submitted during setup.

## Run Table 5 when ready

Prepared data: `data/bbh150.jsonl` (150 reproducibly sampled BBH tasks) and
`data/research100.jsonl` (100 official Research tasks with original profiles).
All five rows, both benchmarks and three repetitions are configured in the table5 YAMLs.
That is **3,750 example executions**, potentially many model calls. The default limit is one
example per benchmark, but still uses every configured condition and seed. Reduce config
conditions/seeds first if you want a minimal paid test.

Only this explicit command selects the complete study:

```bash
scripts/run.sh --config configs/my-api.yaml --output results/table5-api --limit 0
```

Outputs include `table5.csv`, `summary.json`, `manifest.json`, per-example results,
full model-call `traces/`, `cache/`, and `failures/`. Audit/Rollback/Total are mean K tokens.
Research judge cost is tracked separately. Reference values from the paper are in
`data/table5_reference.csv`. Rerun the exact same command to resume; completed examples are
skipped. Use a new output directory after changing config, selected data or source code.

```bash
bra-audit summarize results/table5-api
```

## Survive a disconnected laptop

Run remote commands inside tmux. The helper captures a log and exit status:

```bash
scripts/detached.sh bra-check scripts/check.sh
# For an intentionally launched experiment, replace scripts/check.sh with scripts/run.sh and args.
tail -f logs/bra-check.log
cat logs/bra-check.exit
# On the SAME remote host while the command runs:
tmux -L networkproject attach -t bra-check
# Detach without stopping it: Ctrl-b, then d
```

Closing the laptop/SSH session does not stop a tmux server on the remote host. Use Slurm for
GPU experiments and long compute jobs; Slurm also survives disconnection. tmux cannot survive
a host reboot, termination, or cluster time limit. Resume using the same output directory.
This keeps launched shell jobs alive; it does not itself keep the interactive coding chat
running after the client disconnects.
