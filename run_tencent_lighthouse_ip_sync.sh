#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/tencent_lighthouse_ip_sync.json"
PYTHON_SCRIPT="$SCRIPT_DIR/tencent_lighthouse_ip_sync.py"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Config not found: $CONFIG_FILE"
  echo "Copy tencent_lighthouse_ip_sync.example.json to tencent_lighthouse_ip_sync.json and fill it first."
  exit 1
fi

/usr/bin/python3 "$PYTHON_SCRIPT" --config "$CONFIG_FILE" "$@"
