# Source this file from bash. Keeps packages, models and Conda envs in this project.
BRA_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CONDA_ENVS_PATH="$BRA_PROJECT_ROOT/.conda/envs${CONDA_ENVS_PATH:+:$CONDA_ENVS_PATH}"
export CONDA_PKGS_DIRS="$BRA_PROJECT_ROOT/.conda/pkgs"
export HF_HOME="$BRA_PROJECT_ROOT/.cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export HUGGINGFACE_HUB_CACHE="$HF_HUB_CACHE"
export TORCH_HOME="$BRA_PROJECT_ROOT/.cache/torch"
unset TRANSFORMERS_CACHE PYTORCH_TRANSFORMERS_CACHE PYTORCH_PRETRAINED_BERT_CACHE
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export PIP_CACHE_DIR="$BRA_PROJECT_ROOT/.cache/pip"
source /n/sw/ncf/apps/miniconda3/py39_4.11.0/etc/profile.d/conda.sh
conda activate "$BRA_PROJECT_ROOT/.conda/envs/networkproject"
