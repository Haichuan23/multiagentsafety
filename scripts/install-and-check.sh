#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/activate.sh
# CUDA-enabled wheel runs CPU smoke tests here and supports GPU compute nodes.
python -m pip install 'torch==2.6.0' --index-url https://download.pytorch.org/whl/cu124
python -m pip install -e '.[local,dev]'
python -m pip freeze > requirements-lock.txt
bra-audit prepare-data > logs/prepare-data.log
python -m pytest -q
bra-audit run --config configs/smoke.yaml --output results/smoke --limit 1

HF_HUB_DISABLE_XET=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python scripts/hf-smoke.py
