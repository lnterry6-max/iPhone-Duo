#!/bin/bash
# Install stock watcher as a user's LaunchAgent. Mac must be awake and online.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
if [ ! -f "$REPO/.env" ]; then
  echo "Create .env from .env.example and set NTFY_TOPIC first." >&2
  exit 1
fi
python3 - "$REPO" <<'PY'
import os, plistlib, sys
from pathlib import Path
repo = Path(sys.argv[1])
python = sys.executable
uid = os.getuid()
label = 'com.duostockscout.monitor'
logs = Path.home() / 'Library' / 'Logs'
logs.mkdir(parents=True, exist_ok=True)
plist = {
  'Label': label,
  'ProgramArguments': [python, str(repo / 'duo_monitor.py'), 'watch', '--env', str(repo / '.env')],
  'WorkingDirectory': str(repo),
  'RunAtLoad': True,
  'KeepAlive': True,
  'StandardOutPath': str(logs / 'duo-stock-scout.log'),
  'StandardErrorPath': str(logs / 'duo-stock-scout.error.log'),
}
out = Path.home() / 'Library' / 'LaunchAgents' / (label + '.plist')
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('wb') as fp:
  plistlib.dump(plist, fp)
print(out)
PY
PLIST="$HOME/Library/LaunchAgents/com.duostockscout.monitor.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Watcher installed and started. View log: tail -f ~/Library/Logs/duo-stock-scout.error.log"
