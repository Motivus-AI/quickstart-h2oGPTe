from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_metadata_framework_is_langgraph() -> None:
    payload = json.loads(
        (ROOT / "packages" / "riot_helpdesk_agent" / "metadata.json").read_text()
    )
    assert payload["agent_info"]["framework"] == "langgraph"
    assert payload["function_info"]["name"] == "run_helpdesk"
    assert "riot-player-context" in payload["mcp_servers"]
