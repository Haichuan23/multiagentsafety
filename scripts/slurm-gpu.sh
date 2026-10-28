#!/usr/bin/env bash
#SBATCH --job-name=bra-audit
#SBATCH --output=logs/slurm-%j.log
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --gres=gpu:1
# Submit from project root, adding your cluster account and GPU partition:
# sbatch --account=ACCOUNT --partition=GPU_PARTITION scripts/slurm-gpu.sh
# This template runs ONE example, ONE seed, ONE condition; it is a smoke test.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit using sbatch from the project root}"
source scripts/activate.sh
python - <<'PY'
import torch
assert torch.cuda.is_available(), 'GPU job has no visible CUDA device'
print(torch.cuda.get_device_name(0))
PY
exec bra-audit run --config configs/gpu-smoke.yaml --output "results/gpu-smoke-${SLURM_JOB_ID}" --benchmark bbh --limit 1
