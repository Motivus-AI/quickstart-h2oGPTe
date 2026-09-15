from __future__ import annotations

from server import (
    get_account_status,
    get_ban_reason,
    get_purchase_history,
    get_ticket_history,
)


def test_account_status_known_player() -> None:
    result = get_account_status(player_id="abc123")
    assert result["found"] is True
    assert result["region"] == "NA"


def test_ban_reason_permanent_not_appealable() -> None:
    result = get_ban_reason(player_id="banned42")
    assert result["banned"] is True
    assert result["apelable"] is False


def test_ban_reason_appealable() -> None:
    result = get_ban_reason(player_id="appeal99")
    assert result["apelable"] is True


def test_purchase_history_refunds() -> None:
    result = get_purchase_history("buyer55")
    assert result["refunds_used"] == 1
    assert len(result["purchases"]) == 2


def test_missing_player() -> None:
    result = get_account_status(player_id="nope")
    assert result["found"] is False
