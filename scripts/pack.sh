#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
mkdir -p "$DIST"

(cd "$ROOT/packages" && zip -r "$DIST/riot_player_context.zip" riot_player_context \
  -x "*/__pycache__/*" "*.pyc")
(cd "$ROOT/packages" && zip -r "$DIST/riot_helpdesk_agent.zip" riot_helpdesk_agent \
  -x "*/__pycache__/*" "*.pyc" "*test_custom_agents.py" "*conftest.py")

echo "Wrote:"
ls -la "$DIST"/*.zip
