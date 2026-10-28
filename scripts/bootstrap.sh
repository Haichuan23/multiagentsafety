#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export CONDA_ENVS_PATH="$PWD/.conda/envs"
export CONDA_PKGS_DIRS="$PWD/.conda/pkgs"
export PIP_CACHE_DIR="$PWD/.cache/pip"
if [[ ! -x .conda/envs/networkproject/bin/python ]]; then
  conda create -y -n networkproject python=3.11 pip
fi
exec scripts/install-and-check.sh
