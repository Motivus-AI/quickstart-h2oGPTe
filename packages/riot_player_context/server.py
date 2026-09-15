"""Local MCP server: simulated Riot player-context APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
PLAYERS_PATH = ROOT / "players.json"

mcp = FastMCP("riot-player-context")


def _load_players() -> list[dict[str, Any]]:
    with PLAYERS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)["players"]


def _find(player_id: str | None = None, riot_id: str | None = None, account_id: str | None = None) -> dict[str, Any] | None:
    needle_pid = (player_id or "").strip()
    needle_riot = (riot_id or "").strip()
    needle_acc = (account_id or "").strip()
    for player in _load_players():
        if needle_pid and player["player_id"] == needle_pid:
            return player
        if needle_riot and player["riot_id"] == needle_riot:
            return player
        if needle_acc and player["account_id"] == needle_acc:
            return player
    return None


def _missing(identifier: str) -> dict[str, Any]:
    return {"found": False, "error": f"Player not found: {identifier}"}


@mcp.tool()
def get_account_status(riot_id: str = "", player_id: str = "") -> dict[str, Any]:
    """Return account status, region, creation date, and email verification."""
    player = _find(player_id=player_id, riot_id=riot_id)
    if not player:
        return _missing(riot_id or player_id)
    return {
        "found": True,
        "player_id": player["player_id"],
        "riot_id": player["riot_id"],
        "account_id": player["account_id"],
        "status": player["status"],
        "region": player["region"],
        "created_at": player["created_at"],
        "email_verified": player["email_verified"],
    }


@mcp.tool()
def get_ban_reason(account_id: str = "", player_id: str = "") -> dict[str, Any]:
    """Return ban type, date, reason, duration, and whether it is appealable."""
    player = _find(player_id=player_id, account_id=account_id)
    if not player:
        return _missing(account_id or player_id)
    ban = player.get("ban")
    if not ban:
        return {
            "found": True,
            "account_id": player["account_id"],
            "banned": False,
            "reason": None,
        }
    return {
        "found": True,
        "account_id": player["account_id"],
        "banned": True,
        "type": ban["type"],
        "reason": ban["reason"],
        "at": ban["at"],
        "duration": ban["duration"],
        "apelable": ban["apelable"],
    }


@mcp.tool()
def get_ticket_history(player_id: str) -> list[dict[str, Any]]:
    """Return previous tickets for the player."""
    player = _find(player_id=player_id)
    if not player:
        return [_missing(player_id)]
    return player.get("tickets") or []


@mcp.tool()
def get_purchase_history(player_id: str) -> dict[str, Any]:
    """Return recent purchases and refund usage."""
    player = _find(player_id=player_id)
    if not player:
        return _missing(player_id)
    return {
        "found": True,
        "player_id": player["player_id"],
        "purchases": player.get("purchases") or [],
        "refunds_used": player.get("refunds_used", 0),
    }


if __name__ == "__main__":
    mcp.run()
