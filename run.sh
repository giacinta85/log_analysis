#!/usr/bin/env zsh
# run.sh – one-click setup and launch for Lumos Log Analyzer
# Usage: zsh run.sh   OR   bash run.sh
#   --rebuild   force remove and recreate the conda environment

set -e

ENV_NAME="lumos_log"
SCRIPT_DIR="${${0:a}:h}"   # zsh: absolute dir of this script (works as bash too)
REBUILD=0
[[ "${1:-}" == "--rebuild" ]] && REBUILD=1

# ── Locate conda init script ─────────────────────────────────────────────────
_init_conda() {
  for candidate in \
      "/opt/miniconda3" \
      "$HOME/miniconda3" \
      "$HOME/anaconda3" \
      "/opt/homebrew/Caskroom/miniconda/base" \
      "/usr/local/anaconda3"; do
    if [[ -f "${candidate}/etc/profile.d/conda.sh" ]]; then
      source "${candidate}/etc/profile.d/conda.sh"
      return 0
    fi
  done
  return 1
}

if ! command -v conda &>/dev/null; then
  _init_conda || { echo "[ERROR] conda not found. Install Miniconda/Anaconda first."; exit 1; }
fi

echo "[INFO] conda $(conda --version)"

# ── Rebuild if requested ──────────────────────────────────────────────────────
if [[ $REBUILD -eq 1 ]]; then
  if conda env list | grep -q "^${ENV_NAME}[[:space:]]"; then
    echo "[INFO] Removing existing environment '${ENV_NAME}'..."
    conda env remove -n "${ENV_NAME}" -y
  fi
fi

# ── Create if missing ────────────────────────────────────────────────────────
if ! conda env list | grep -q "^${ENV_NAME}[[:space:]]"; then
  echo "[INFO] Creating conda environment '${ENV_NAME}' (this may take a minute)..."
  conda env create -f "${SCRIPT_DIR}/environment.yml"
  echo "[INFO] Environment '${ENV_NAME}' created."
else
  echo "[INFO] Environment '${ENV_NAME}' already exists. Use --rebuild to recreate."
fi

# ── Activate and launch ──────────────────────────────────────────────────────
echo "[INFO] Launching Lumos Log Analyzer..."
PYTHON_BIN="$(conda info --base)/envs/${ENV_NAME}/bin/python"
"${PYTHON_BIN}" "${SCRIPT_DIR}/app.py"
