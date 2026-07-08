#!/usr/bin/env bash
set -euo pipefail

REMOTE="${REMOTE:-lumosbot@192.168.54.110}"
REMOTE_DIR="${REMOTE_DIR:-/home/lumosbot/thomas_ws/lumos_controller}"
IMU_A="${IMU_A:-/dev/ttyUSB_imu}"
IMU_B="${IMU_B:-/dev/ttyUSB_imu2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_LOG_DIR="${LOCAL_LOG_DIR:-${SCRIPT_DIR}/../../logs/imu}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$SCRIPT_DIR}"
DURATION_MINUTES=10
RUN_PLOT=1
WRITE_HTML=0
IMU_MODE="both"
EXISTING_LOG=""

SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/tmp/lumos_known_hosts
)

usage() {
  cat <<'USAGE'
Usage:
  ./run_imu_test.sh [-t N|--duration-minutes N] [--imu both|ttyUSB0|ttyUSB1] [--html] [--no-plot]
  ./run_imu_test.sh -log <log-file-or-rpy-stem> [--html]

Defaults:
  remote:  lumosbot@192.168.54.110
  length:  10 minutes
  imu:     both
  output:  ../../logs/imu, relative to this script
  plot:    PNG only; add --html to also generate interactive HTML

Environment overrides:
  REMOTE, REMOTE_DIR, IMU_A, IMU_B, LOCAL_LOG_DIR, ANALYSIS_DIR
USAGE
}

wait_with_progress() {
  local total="$1"
  local elapsed=0
  local remaining percent filled empty bar_width step
  bar_width=30

  while [[ "$elapsed" -le "$total" ]]; do
    remaining=$((total - elapsed))
    percent=$((elapsed * 100 / total))
    filled=$((elapsed * bar_width / total))
    empty=$((bar_width - filled))

    printf '\r[INFO] Waiting ['
    printf '%*s' "$filled" '' | tr ' ' '#'
    printf '%*s' "$empty" '' | tr ' ' '-'
    printf '] %3d%% elapsed %02d:%02d remaining %02d:%02d' \
      "$percent" \
      $((elapsed / 60)) $((elapsed % 60)) \
      $((remaining / 60)) $((remaining % 60))

    if [[ "$elapsed" -eq "$total" ]]; then
      break
    fi

    if [[ "$remaining" -gt 1 ]]; then
      step=1
    else
      step="$remaining"
    fi

    sleep "$step"
    elapsed=$((elapsed + step))
  done

  printf '\n'
}

resolve_existing_log() {
  local input="$1"
  local name stem candidate
  name="$(basename "$input")"
  stem="${name%.*}"
  stem="${stem%%_rpy*}"

  for candidate in \
      "$input" \
      "${input}.log" \
      "${ANALYSIS_DIR}/${input}" \
      "${ANALYSIS_DIR}/${input}.log" \
      "${LOCAL_LOG_DIR}/${input}" \
      "${LOCAL_LOG_DIR}/${input}.log" \
      "${LOCAL_LOG_DIR}/${stem}.log" \
      "${ANALYSIS_DIR}/${stem}.log" \
      "${ANALYSIS_DIR}/../../logs/imu/${stem}.log"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

generate_plot_for_log() {
  local local_log="$1"

  echo "[INFO] Generating RPY plot from ${local_log}"
  (
    cd "$ANALYSIS_DIR"
    plot_args=(-m imu -log "$local_log")
    [[ "$WRITE_HTML" -eq 1 ]] && plot_args+=(--html)
    zsh ./run.sh "${plot_args[@]}"
  )
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--duration-minutes)
      DURATION_MINUTES="${2:-}"
      [[ "$DURATION_MINUTES" =~ ^[0-9]+$ ]] || {
        echo "[ERROR] -t/--duration-minutes must be an integer" >&2
        exit 1
      }
      [[ "$DURATION_MINUTES" -gt 0 ]] || {
        echo "[ERROR] -t/--duration-minutes must be greater than 0" >&2
        exit 1
      }
      shift 2
      ;;
    --imu)
      IMU_MODE="${2:-}"
      [[ "$IMU_MODE" == "ttyUSB0" ]] && IMU_MODE="ttyusb0"
      [[ "$IMU_MODE" == "ttyUSB1" ]] && IMU_MODE="ttyusb1"
      case "$IMU_MODE" in
        ttyusb0|ttyusb1|both) ;;
        *)
          echo "[ERROR] --imu must be one of: both, ttyUSB0, ttyUSB1" >&2
          exit 1
          ;;
      esac
      shift 2
      ;;
    -log|--log)
      EXISTING_LOG="${2:-}"
      [[ -n "$EXISTING_LOG" ]] || { usage >&2; exit 1; }
      shift 2
      ;;
    --no-plot)
      RUN_PLOT=0
      shift
      ;;
    --html)
      WRITE_HTML=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

TAG="${DURATION_MINUTES}min"
DURATION="${DURATION_MINUTES}m"
WAIT_SECONDS=$((DURATION_MINUTES * 60 + 5))
case "$IMU_MODE" in
  ttyusb0)
    LOG_PREFIX="ttyUSB0_drift"
    ;;
  ttyusb1)
    LOG_PREFIX="ttyUSB1_drift"
    ;;
  both)
    LOG_PREFIX="daisi_imu_drift"
    ;;
esac

if [[ -n "$EXISTING_LOG" ]]; then
  local_log="$(resolve_existing_log "$EXISTING_LOG")" || {
    echo "[ERROR] IMU log not found: ${EXISTING_LOG}" >&2
    echo "[INFO] Tried direct path, .log suffix, ${LOCAL_LOG_DIR}, and _rpy stem normalization" >&2
    exit 1
  }
  generate_plot_for_log "$local_log"
  echo "[INFO] Done"
  exit 0
fi

echo "[INFO] Starting IMU drift test on ${REMOTE} (${DURATION}, imu=${IMU_MODE})"

remote_start_script="$(mktemp)"
remote_check_script="$(mktemp)"
trap 'rm -f "$remote_start_script" "$remote_check_script"' EXIT
cat > "$remote_start_script" <<'REMOTE_START'
set -euo pipefail

remote_dir="$1"
duration="$2"
tag="$3"
imu_a="$4"
imu_b="$5"
imu_mode="${6:-}"
log_prefix="${7:-}"

echo "[INFO] Remote imu_mode=${imu_mode:-<empty>}"

cd "$remote_dir"

busy="$(pgrep -af '[l]umos_main|[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true)"
if [[ -n "$busy" ]]; then
  echo "[WARN] Found possible IMU serial owner. Stopping it before restarting this test:"
  echo "$busy"
  pkill -TERM -f '[l]umos_main|[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true
  sleep 2

  busy="$(pgrep -af '[l]umos_main|[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true)"
  if [[ -n "$busy" ]]; then
    echo "[WARN] Processes still running after TERM. Sending KILL:"
    echo "$busy"
    pkill -KILL -f '[l]umos_main|[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true
    sleep 1
  fi

  busy="$(pgrep -af '[l]umos_main|[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true)"
  if [[ -n "$busy" ]]; then
    echo "[ERROR] Failed to stop IMU serial owner:"
    echo "$busy"
    exit 2
  fi
fi

case "${imu_mode:-}" in
  both)
    test_binary="./example/daisi_imu_handler_test"
    test_args=("$imu_a" "$imu_b")
    required_devices=("$imu_a" "$imu_b")
    ;;
  ttyusb0)
    test_binary="./example/imu_handler_test"
    test_args=("/dev/ttyUSB0")
    required_devices=("/dev/ttyUSB0")
    ;;
  ttyusb1)
    test_binary="./example/imu_handler_test"
    test_args=("/dev/ttyUSB1")
    required_devices=("/dev/ttyUSB1")
    ;;
  *)
    echo "[ERROR] Unsupported IMU mode: ${imu_mode:-<empty>}" >&2
    exit 3
    ;;
esac

ls -l "$imu_a" "$imu_b" /dev/serial/by-path/* 2>/dev/null || true
for dev in "${required_devices[@]}"; do
  if [[ ! -e "$dev" ]]; then
    echo "[ERROR] Required IMU device is missing: $dev" >&2
    exit 3
  fi
done

if [[ ! -x "build/${test_binary}" ]]; then
  echo "[ERROR] Test binary not found or not executable: build/${test_binary}" >&2
  exit 3
fi

mkdir -p logs
log="logs/${log_prefix}_$(date +%Y%m%d_%H%M%S)_${tag}.log"
echo "LOG=$log"

nohup bash -c '
  set +e
  remote_dir="$1"
  duration="$2"
  imu_a="$3"
  imu_b="$4"
  log="$5"
  test_binary="$6"
  shift 6

  cd "$remote_dir/build" || exit 127
  timeout "$duration" "$test_binary" "$@" > "../$log" 2>&1
  code=$?
  cd "$remote_dir" || exit 127
  echo "DONE code=$code log=$log" >> "$log"
' _ "$remote_dir" "$duration" "$imu_a" "$imu_b" "$log" "$test_binary" "${test_args[@]}" >/tmp/imu_handler_test_start.log 2>&1 &

echo "PID=$!"
REMOTE_START

start_output="$(
  ssh "${SSH_OPTS[@]}" "$REMOTE" "bash -s" -- "$REMOTE_DIR" "$DURATION" "$TAG" "$IMU_A" "$IMU_B" "$IMU_MODE" "$LOG_PREFIX" < "$remote_start_script"
)"

printf '%s\n' "$start_output"

remote_log="$(printf '%s\n' "$start_output" | awk -F= '/^LOG=/{print $2; exit}')"
if [[ -z "$remote_log" ]]; then
  echo "[ERROR] Failed to parse remote LOG path from startup output" >&2
  exit 4
fi

echo "[INFO] Remote log: ${remote_log}"
echo "[INFO] Waiting ${WAIT_SECONDS}s before checking the result"
wait_with_progress "$WAIT_SECONDS"

echo "[INFO] Checking remote test result"
cat > "$remote_check_script" <<'REMOTE_CHECK'
set -euo pipefail

remote_dir="$1"
remote_log="$2"

cd "$remote_dir"
pgrep -af '[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true
ls -lh "$remote_log"
grep -E 'DONE code=' "$remote_log" || true
tail -80 "$remote_log"
REMOTE_CHECK

ssh "${SSH_OPTS[@]}" "$REMOTE" "bash -s" -- "$REMOTE_DIR" "$remote_log" < "$remote_check_script"

mkdir -p "$LOCAL_LOG_DIR"
local_ts="$(date +%Y%m%d_%H%M%S)"
local_log="${LOCAL_LOG_DIR}/${LOG_PREFIX}_${local_ts}_${TAG}.log"

echo "[INFO] Downloading log to ${local_log}"
scp "${SSH_OPTS[@]}" "${REMOTE}:${REMOTE_DIR}/${remote_log}" "$local_log"

ls -lh "$local_log"
wc -l "$local_log"

if [[ "$RUN_PLOT" -eq 1 ]]; then
  generate_plot_for_log "$local_log"
fi

echo "[INFO] Done"
