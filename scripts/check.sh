#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/activate.sh
python -m pytest -q
bra-audit run --config configs/smoke.yaml --output results/smoke --limit 1
