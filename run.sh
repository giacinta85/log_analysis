#!/usr/bin/env zsh
# run.sh – one-click setup and launch for Lumos Log Analyzer
# Usage: zsh run.sh   OR   bash run.sh
#   --rebuild   force remove and recreate the conda environment
#   -m imu -log <file>   plot IMU RPY from an IMU drift log as PNG
#   --html   also write an interactive HTML plot

set -e

ENV_NAME="lumos_log"
SCRIPT_DIR="${${0:a}:h}"   # zsh: absolute dir of this script (works as bash too)
REBUILD=0
MODE="gui"
LOG_FILE=""
WRITE_HTML=0

_usage() {
  echo "Usage:"
  echo "  ./run.sh [--rebuild]"
  echo "  ./run.sh -m imu -log <log-file> [--html] [--rebuild]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild)
      REBUILD=1
      shift
      ;;
    --html)
      WRITE_HTML=1
      shift
      ;;
    -m|--mode)
      MODE="${2:-}"
      [[ -n "$MODE" ]] || { _usage; exit 1; }
      shift 2
      ;;
    -log|--log)
      LOG_FILE="${2:-}"
      [[ -n "$LOG_FILE" ]] || { _usage; exit 1; }
      shift 2
      ;;
    -h|--help)
      _usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      _usage
      exit 1
      ;;
  esac
done

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
PYTHON_BIN="$(conda info --base)/envs/${ENV_NAME}/bin/python"

_resolve_log_file() {
  local input="$1"
  local candidate
  for candidate in \
      "$input" \
      "${SCRIPT_DIR}/${input}" \
      "${SCRIPT_DIR}/../../logs/imu/${input}"; do
    if [[ -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

case "$MODE" in
  gui)
    echo "[INFO] Launching Lumos Log Analyzer..."
    "${PYTHON_BIN}" "${SCRIPT_DIR}/app.py"
    ;;
  imu)
    [[ -n "$LOG_FILE" ]] || { echo "[ERROR] -m imu requires -log <log-file>"; _usage; exit 1; }
    RESOLVED_LOG="$(_resolve_log_file "$LOG_FILE")" || {
      echo "[ERROR] IMU log not found: ${LOG_FILE}"
      echo "[INFO] Tried current directory, ${SCRIPT_DIR}, and ${SCRIPT_DIR}/../../logs/imu"
      exit 1
    }
    OUTPUT_FILE="${SCRIPT_DIR}/outputs/${RESOLVED_LOG:t:r}_rpy.png"
    HTML_OUTPUT_FILE="${SCRIPT_DIR}/outputs/${RESOLVED_LOG:t:r}_rpy.html"
    echo "[INFO] Plotting IMU RPY: ${RESOLVED_LOG}"
    plot_args=("${RESOLVED_LOG}" -o "${OUTPUT_FILE}")
    [[ "$WRITE_HTML" -eq 1 ]] && plot_args+=(--html)
    "${PYTHON_BIN}" "${SCRIPT_DIR}/scripts/plot_imu_rpy.py" "${plot_args[@]}"
    [[ -f "$OUTPUT_FILE" ]] && echo "[INFO] Plot: ${OUTPUT_FILE}"
    if [[ "$WRITE_HTML" -eq 1 ]]; then
      [[ -f "$HTML_OUTPUT_FILE" ]] && echo "[INFO] Interactive plot: ${HTML_OUTPUT_FILE}"
    fi
    ;;
  *)
    echo "[ERROR] Unsupported mode: ${MODE}"
    _usage
    exit 1
    ;;
esac
