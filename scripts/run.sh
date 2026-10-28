#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/activate.sh
export PYTHONUNBUFFERED=1
exec bra-audit run "$@"
