"""Tests for riot_helpdesk_agent (offline via conftest.py)."""

from __future__ import annotations

from custom_agents import classify_heuristic, rag_query, run_helpdesk, run_payload


def test_function_exists() -> None:
    assert callable(run_helpdesk)


def test_default_parameters() -> None:
    payload = run_payload("VAN 57 error al iniciar Valorant. player_id=abc123")
    assert payload["category"] == "tecnica"
    assert payload["action"] in {"close", "escalate"}
    assert "borrador" in payload["draft"].lower() or "Hola" in payload["draft"]


def test_penalizaciones_branch() -> None:
    query = (
        "Me banearon permanente y quiero apelar. player_id=appeal99"
    )
    payload = run_payload(query)
    assert payload["category"] == "penalizaciones"
    assert payload["action"] == "escalate"


def test_tecnica_branch() -> None:
    query = "VAN 57 error al iniciar Valorant. player_id=abc123"
    payload = run_payload(query)
    assert payload["category"] == "tecnica"
    assert payload["collection"] == "riot-support-tecnica"


def test_billing_branch() -> None:
    query = "Quiero un reembolso de mis Riot Points. player_id=buyer55"
    payload = run_payload(query)
    assert payload["category"] == "billing"
    assert payload["action"] == "close"


def test_report_is_markdown_without_diagnostics() -> None:
    report = run_helpdesk(query="VAN 57 error al iniciar Valorant. player_id=abc123")
    assert report.startswith("# Ticket tecnica / VAN_57")
    assert "**Acción recomendada:" in report
    assert "## Borrador para el jugador" in report
    assert "PlayerOne#NA1" in report
    assert "api_probe" not in report
    assert "diagnostics" not in report


def test_classify_heuristic_ban() -> None:
    result = classify_heuristic("ban permanente por trampas")
    assert result["category"] == "penalizaciones"


def test_rag_query_uses_subcategory_not_ticket() -> None:
    query = rag_query(
        {
            "query": "Me banearon permanentemente y no sé por qué. player_id=banned42",
            "category": "penalizaciones",
            "subcategory": "ban_permanente",
        }
    )
    assert "ban" in query.lower()
    assert "permanente" in query.lower()
    assert "player_id" not in query
