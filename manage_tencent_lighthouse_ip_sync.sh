#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.qiwang.tencent-lighthouse-ip-sync"
PLIST_NAME="$LABEL.plist"
SOURCE_PLIST="$SCRIPT_DIR/$PLIST_NAME"
TARGET_PLIST="$HOME/Library/LaunchAgents/$PLIST_NAME"
PYTHON_SCRIPT="$SCRIPT_DIR/tencent_lighthouse_ip_sync.py"
CONFIG_FILE="$SCRIPT_DIR/tencent_lighthouse_ip_sync.json"

ensure_config() {
  if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Config not found: $CONFIG_FILE"
    exit 1
  fi
}

start_job() {
  ensure_config
  mkdir -p "$HOME/Library/LaunchAgents"
  cp "$SOURCE_PLIST" "$TARGET_PLIST"
  launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$TARGET_PLIST"
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
  echo "Started: $LABEL"
}

stop_job() {
  launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
  rm -f "$TARGET_PLIST"
  echo "Stopped: $LABEL"
}

status_job() {
  launchctl print "gui/$(id -u)/$LABEL"
}

run_once() {
  ensure_config
  env \
    -u http_proxy \
    -u https_proxy \
    -u HTTP_PROXY \
    -u HTTPS_PROXY \
    -u ALL_PROXY \
    -u all_proxy \
    /usr/bin/python3 "$PYTHON_SCRIPT" --config "$CONFIG_FILE" "$@"
}

usage() {
  cat <<'EOF'
Usage:
  ./manage_tencent_lighthouse_ip_sync.sh start
  ./manage_tencent_lighthouse_ip_sync.sh stop
  ./manage_tencent_lighthouse_ip_sync.sh restart
  ./manage_tencent_lighthouse_ip_sync.sh status
  ./manage_tencent_lighthouse_ip_sync.sh run [--dry-run|--force]
EOF
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  start)
    start_job
    ;;
  stop)
    stop_job
    ;;
  restart)
    stop_job
    start_job
    ;;
  status)
    status_job
    ;;
  run)
    run_once "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
