#!/bin/zsh
set -euo pipefail

TARGET_PLIST="$HOME/Library/LaunchAgents/com.qiwang.tencent-lighthouse-ip-sync.plist"
LABEL="com.qiwang.tencent-lighthouse-ip-sync"

launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
rm -f "$TARGET_PLIST"

echo "Stopped and removed: $LABEL"
