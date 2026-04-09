#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_PLIST="$SCRIPT_DIR/com.qiwang.tencent-lighthouse-ip-sync.plist"
TARGET_PLIST="$HOME/Library/LaunchAgents/com.qiwang.tencent-lighthouse-ip-sync.plist"
LABEL="com.qiwang.tencent-lighthouse-ip-sync"

if [[ ! -f "$SCRIPT_DIR/tencent_lighthouse_ip_sync.json" ]]; then
  echo "Config not found: $SCRIPT_DIR/tencent_lighthouse_ip_sync.json"
  echo "Copy tencent_lighthouse_ip_sync.example.json to tencent_lighthouse_ip_sync.json and fill it first."
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$SOURCE_PLIST" "$TARGET_PLIST"

launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET_PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started: $LABEL"
echo "Status: launchctl print gui/$(id -u)/$LABEL"
