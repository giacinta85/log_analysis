#!/usr/bin/env bash
set -euo pipefail

REMOTE="${REMOTE:-lumosbot@192.168.54.110}"
REMOTE_DIR="${REMOTE_DIR:-/home/lumosbot/thomas_ws/lumos_controller}"
RULE_FILE="${RULE_FILE:-/etc/udev/rules.d/99-lumos-imu.rules}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SOURCE_DIR:-$SCRIPT_DIR/resource}"

# Current 3588 USB topology:
#   ttyUSB1: daisi IMU A
#   ttyUSB0: daisi IMU B, changed from the Beitong USB position
IMU_A_ID_PATH="${IMU_A_ID_PATH:-platform-fc8c0000.usb-usb-0:1:1.0-port0}"
IMU_B_ID_PATH="${IMU_B_ID_PATH:-platform-xhci-hcd.6.auto-usb-0:1:1.0-port0}"
IMU_A_LINK="${IMU_A_LINK:-ttyUSB_imu}"
IMU_B_LINK="${IMU_B_LINK:-ttyUSB_imu2}"

SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/tmp/lumos_known_hosts
)

usage() {
  cat <<'USAGE'
Usage:
  ./deploy_imu_env.sh [--check]

Installs stable IMU serial aliases on the RK3588:
  /dev/ttyUSB_imu   -> USB path platform-fc8c0000.usb-usb-0:1:1.0-port0
  /dev/ttyUSB_imu2  -> USB path platform-xhci-hcd.6.auto-usb-0:1:1.0-port0

Then uploads files from ./resource/ into the remote lumos_controller tree.
Source paths are relative to REMOTE_DIR. Example:
  resource/example/device-test/daisi_imu_handler_test.cpp
  -> /home/lumosbot/thomas_ws/lumos_controller/example/device-test/daisi_imu_handler_test.cpp

Environment overrides:
  REMOTE, REMOTE_DIR, RULE_FILE, SOURCE_DIR
  IMU_A_ID_PATH, IMU_B_ID_PATH, IMU_A_LINK, IMU_B_LINK
USAGE
}

MODE="deploy"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      MODE="check"
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

echo "[INFO] Target: ${REMOTE}"
echo "[INFO] Remote controller: ${REMOTE_DIR}"
echo "[INFO] Local upload root: ${SOURCE_DIR}"

if [[ "$MODE" == "check" ]]; then
  ssh "${SSH_OPTS[@]}" "$REMOTE" "bash -s" -- "$RULE_FILE" <<'REMOTE_CHECK'
set -euo pipefail

rule_file="$1"

echo "[INFO] Existing by-path mappings:"
ls -l /dev/serial/by-path/* 2>/dev/null || true

echo "[INFO] Existing IMU aliases:"
ls -l /dev/ttyUSB_imu /dev/ttyUSB_imu2 2>/dev/null || true

echo "[INFO] Running IMU test processes:"
pgrep -af '[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true

if [[ -f "$rule_file" ]]; then
  echo "[INFO] Current rule file: $rule_file"
  cat "$rule_file"
else
  echo "[INFO] Rule file not installed: $rule_file"
fi
REMOTE_CHECK
  exit 0
fi

ssh -t "${SSH_OPTS[@]}" "$REMOTE" "bash -s" -- \
  "$RULE_FILE" "$IMU_A_ID_PATH" "$IMU_B_ID_PATH" "$IMU_A_LINK" "$IMU_B_LINK" <<'REMOTE_DEPLOY'
set -euo pipefail

rule_file="$1"
imu_a_id_path="$2"
imu_b_id_path="$3"
imu_a_link="$4"
imu_b_link="$5"

tmp_rule="$(mktemp)"
cat > "$tmp_rule" <<EOF_RULE
# Lumos daisi IMU stable serial aliases.
# Installed by deploy_imu_env.sh.
SUBSYSTEM=="tty", ENV{ID_PATH}=="${imu_a_id_path}", SYMLINK+="${imu_a_link}", GROUP="dialout", MODE="0666"
SUBSYSTEM=="tty", ENV{ID_PATH}=="${imu_b_id_path}", SYMLINK+="${imu_b_link}", GROUP="dialout", MODE="0666"
EOF_RULE

echo "[INFO] Existing by-path mappings:"
ls -l /dev/serial/by-path/* 2>/dev/null || true

busy="$(pgrep -af '[d]aisi_imu_handler_test|[i]mu_handler_test|[t]imeout .*imu' || true)"
if [[ -n "$busy" ]]; then
  echo "[ERROR] IMU test is running. Wait for it to finish before deploying udev rules:"
  echo "$busy"
  exit 2
fi

echo "[INFO] Installing udev rule to ${rule_file}"
sudo mkdir -p "$(dirname "$rule_file")"
sudo cp "$tmp_rule" "$rule_file"
rm -f "$tmp_rule"

echo "[INFO] Reloading udev rules"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
sleep 1

echo "[INFO] Installed rule:"
cat "$rule_file"

echo "[INFO] Resulting IMU aliases:"
ls -l "/dev/${imu_a_link}" "/dev/${imu_b_link}"

a_target="$(readlink -f "/dev/${imu_a_link}")"
b_target="$(readlink -f "/dev/${imu_b_link}")"
echo "[INFO] /dev/${imu_a_link} -> ${a_target}"
echo "[INFO] /dev/${imu_b_link} -> ${b_target}"

if [[ "${a_target##*/}" != ttyUSB1 ]]; then
  echo "[ERROR] Expected /dev/${imu_a_link} to resolve to ttyUSB1" >&2
  exit 2
fi

if [[ "${b_target##*/}" != ttyUSB0 ]]; then
  echo "[ERROR] Expected /dev/${imu_b_link} to resolve to ttyUSB0" >&2
  exit 3
fi

echo "[INFO] IMU serial mapping deployed successfully"
REMOTE_DEPLOY

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "[ERROR] Local upload directory not found: $SOURCE_DIR" >&2
  exit 4
fi

source_count=0
echo "[INFO] Uploading resource files to ${REMOTE}:${REMOTE_DIR}"
while IFS= read -r local_file; do
  rel_path="${local_file#"$SOURCE_DIR"/}"
  remote_path="${REMOTE_DIR}/${rel_path}"
  remote_parent="$(dirname "$remote_path")"

  echo "[INFO] Upload ${rel_path}"
  ssh "${SSH_OPTS[@]}" "$REMOTE" "mkdir -p '$remote_parent'"
  scp "${SSH_OPTS[@]}" "$local_file" "${REMOTE}:${remote_path}"
  source_count=$((source_count + 1))
done < <(find "$SOURCE_DIR" -type f | sort)

if [[ "$source_count" -eq 0 ]]; then
  echo "[ERROR] No files found under upload directory: $SOURCE_DIR" >&2
  exit 5
fi

echo "[INFO] Uploaded source files:"
ssh "${SSH_OPTS[@]}" "$REMOTE" "bash -s" -- "$REMOTE_DIR" <<'REMOTE_LIST'
set -euo pipefail
remote_dir="$1"
find "$remote_dir/example/device-test" -maxdepth 1 -type f -name '*imu*test.cpp' -printf '%p %s bytes\n' | sort
REMOTE_LIST

echo "[INFO] Building remote IMU test binaries"
ssh "${SSH_OPTS[@]}" "$REMOTE" "bash -s" -- "$REMOTE_DIR" <<'REMOTE_BUILD'
set -euo pipefail
remote_dir="$1"
cd "$remote_dir/build"
make daisi_imu_handler_test imu_handler_test -j"$(nproc)"
ls -lh example/daisi_imu_handler_test example/imu_handler_test
REMOTE_BUILD

echo "[INFO] Deployment complete"
