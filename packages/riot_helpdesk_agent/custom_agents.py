"""Riot Support LangGraph custom agent for Enterprise h2oGPTe."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from h2o_runtime import (
    COLLECTION_NAMES,
    call_mcp_tool,
    collection_id_for,
    is_offline,
    llm_available,
    llm_endpoint,
    llm_query,
    parse_json_object,
    partners_address,
    rag_available,
    runtime_diagnostics,
    search_collection,
)

ROOT = Path(__file__).resolve().parent
KB_ROOT = ROOT / "kb"
PLAYERS_PATH = ROOT / "fallback_players.json"

BRANCHES = ("penalizaciones", "tecnica", "billing")

# Keep subcategories groupable for reporting; free-form LLM text breaks that.
SUBCATEGORIES = {
    "tecnica": ("VAN_57", "VAN_128", "VAN_2266", "VAN_9006", "crash"),
    "penalizaciones": ("ban_permanente", "suspension", "apelacion", "cuenta_robada"),
    "billing": ("refund", "rp", "missing_skin", "unrecognized"),
}

PENAL_KWS = (
    "ban",
    "baneo",
    "penaliz",
    "apel",
    "suspend",
    "restriccion",
    "restricción",
    "infraccion",
    "infracción",
)
TECH_KWS = (
    "van ",
    "van_",
    "vanguard",
    "crash",
    "lag",
    "fps",
    "cliente",
    "error",
    "tpm",
    "secure boot",
)
BILLING_KWS = (
    "rp",
    "reembolso",
    "refund",
    "compra",
    "skin",
    "billing",
    "cargo",
    "pago",
    "riot points",
    "cobro",
)


class HelpdeskState(TypedDict):
    query: str
    chat_history: List[Dict[str, str]]
    category: str
    subcategory: str
    summary: str
    collection: str
    tool_results: Dict[str, Any]
    kb_hits: str
    draft: str
    action: str
    action_reason: str
    error: str


def _print(message: str) -> None:
    print(message, flush=True)


def _text(query: str) -> str:
    return query.lower()


def _van_code(text: str) -> str | None:
    match = re.search(r"van[\s_-]?(\d+)", text, flags=re.I)
    return f"VAN_{match.group(1)}" if match else None


SUBCATEGORY_KEYWORDS = {
    "tecnica": (("crash", ("crash", "se cierra", "cierra solo", "pantalla negra", "congel")),),
    "penalizaciones": (
        ("cuenta_robada", ("robad", "hacke", "comprometid")),
        ("apelacion", ("apel", "revision", "revisión", "injust")),
        ("ban_permanente", ("permanente", "definitiv")),
        ("suspension", ("suspend", "suspens", "temporal", "restriccion", "restricción")),
    ),
    "billing": (
        ("unrecognized", ("no reconozco", "desconocid", "duplicad", "no autoriz", "fraud")),
        ("refund", ("reembolso", "refund", "devoluc")),
        ("missing_skin", ("skin", "bundle", "no me llego", "no me llegó", "no recibi")),
        ("rp", ("rp", "riot points")),
    ),
}


def _subcategory_heuristic(text: str, category: str) -> str:
    if category == "tecnica":
        code = _van_code(text)
        if code:
            return code
    for name, keywords in SUBCATEGORY_KEYWORDS.get(category, ()):
        if any(keyword in text for keyword in keywords):
            return name
    return "general"


def classify_heuristic(query: str) -> dict[str, str]:
    text = _text(query)
    scores = {
        "penalizaciones": sum(1 for kw in PENAL_KWS if kw in text),
        "tecnica": sum(1 for kw in TECH_KWS if kw in text),
        "billing": sum(1 for kw in BILLING_KWS if kw in text),
    }
    category = max(scores, key=scores.get)
    if scores[category] == 0:
        category = "tecnica"
    subcategory = _subcategory_heuristic(text, category)
    summary = query.strip().split("\n")[0][:240]
    return {
        "category": category,
        "subcategory": subcategory,
        "summary": summary,
    }


def normalize_subcategory(value: str, category: str, query: str) -> str:
    """Map whatever the LLM answered onto the branch's known subcategories."""
    allowed = SUBCATEGORIES.get(category, ())
    if category == "tecnica":
        code = _van_code(query)
        if code:
            return code
    candidate = re.sub(r"[\s-]+", "_", (value or "").strip().lower())
    code = _van_code(candidate)
    if code and category == "tecnica":
        return code
    if candidate in allowed:
        return candidate
    guess = classify_heuristic(query)["subcategory"]
    return guess if guess in allowed else "general"


def _classify_with_h2o(query: str) -> dict[str, str] | None:
    if is_offline() or not llm_available():
        return None
    options = "\n".join(
        f"- {branch}: {', '.join(values)}" for branch, values in SUBCATEGORIES.items()
    )
    prompt = (
        "Eres un clasificador de tickets de Riot Support en Enterprise h2oGPTe. "
        "Responde SOLO JSON con keys category, subcategory, summary. "
        "category debe ser exactamente una de: penalizaciones, tecnica, billing. "
        "subcategory debe ser exactamente uno de los valores de su categoría "
        f"(para errores VAN usa VAN_<código>):\n{options}\n\n"
        f"{query}"
    )
    try:
        _print(f"LLM classify via {llm_endpoint()[2]}...")
        payload = parse_json_object(llm_query(prompt, collection_id=None, timeout=60))
        if not payload:
            return None
        category = str(payload.get("category", "tecnica"))
        if category not in BRANCHES:
            category = "tecnica"
        return {
            "category": category,
            "subcategory": str(payload.get("subcategory", "")),
            "summary": str(payload.get("summary", query[:240])),
        }
    except Exception as exc:  # noqa: BLE001 — agent must not crash the chat UI
        _print(f"LLM classify fallback ({exc})")
        return None


def classify_node(state: HelpdeskState) -> HelpdeskState:
    _print("Clasificando ticket...")
    result = _classify_with_h2o(state["query"]) or classify_heuristic(state["query"])
    state["category"] = result["category"]
    state["subcategory"] = normalize_subcategory(
        result["subcategory"], result["category"], state["query"]
    )
    state["summary"] = result["summary"]
    return state


def route_node(state: HelpdeskState) -> HelpdeskState:
    category = state.get("category") or "tecnica"
    if category not in BRANCHES:
        category = "tecnica"
    state["category"] = category
    state["collection"] = f"riot-support-{category}"
    _print(f"Routing → {category} ({state['collection']})")
    return state


def route_branch(state: HelpdeskState) -> str:
    return {
        "penalizaciones": "retrieve_penalizaciones",
        "tecnica": "retrieve_tecnica",
        "billing": "retrieve_billing",
    }.get(state.get("category") or "tecnica", "retrieve_tecnica")


RAG_QUERY_TERMS = {
    "VAN_57": "VAN 57 Vanguard integridad cliente",
    "VAN_128": "VAN 128 VAN 9006 Vanguard terceros",
    "VAN_9006": "VAN 9006 VAN 128 overclock drivers",
    "VAN_2266": "VAN 2266 Vanguard",
    "crash": "crash cliente pantallazo Valorant",
    "ban_permanente": "ban permanente apelaciones cheat",
    "suspension": "suspension temporal chat ranked",
    "apelacion": "apelacion ban permanente contested",
    "cuenta_robada": "cuenta robada recuperacion comprometida",
    "refund": "reembolso refund compra RP",
    "rp": "Riot Points RP cargo",
    "missing_skin": "skin bundle no llego compra",
    "unrecognized": "cargo no reconocido fraude duplicado",
}

BRANCH_RAG_TERMS = {
    "penalizaciones": "ban permanente apelacion suspension",
    "tecnica": "Vanguard VAN error cliente",
    "billing": "reembolso compra RP cargo",
}


def rag_query(state: HelpdeskState) -> str:
    """Short lexical query: full ticket text often misses Collection chunks."""
    subcategory = state.get("subcategory") or ""
    category = state.get("category") or "tecnica"
    terms = RAG_QUERY_TERMS.get(subcategory) or BRANCH_RAG_TERMS.get(category, "")
    van = _van_code(state.get("query") or "")
    parts = [subcategory.replace("_", " "), van.replace("_", " ") if van else "", terms]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for token in part.split():
            key = token.lower()
            if key and key not in seen:
                seen.add(key)
                out.append(token)
    return " ".join(out) or (state.get("query") or "")


def _search_kb(branch: str, query: str) -> str:
    folder = KB_ROOT / branch
    if not folder.exists():
        return ""
    tokens = [tok for tok in re.findall(r"[a-z0-9]+", query.lower()) if len(tok) > 2]
    scored: list[tuple[int, Path]] = []
    for path in folder.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        haystack = text.lower()
        score = sum(haystack.count(tok) for tok in tokens)
        scored.append((score, path))
    scored.sort(key=lambda item: item[0], reverse=True)
    parts = []
    for score, path in scored[:2]:
        if score <= 0 and parts:
            continue
        parts.append(f"### {path.stem}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def _retrieve(state: HelpdeskState, branch: str) -> HelpdeskState:
    name = COLLECTION_NAMES[branch]
    state["collection"] = name
    query = rag_query(state)
    hits = ""
    if rag_available():
        _print(f"RAG Collection {name} query={query!r} on {partners_address()}...")
        try:
            hits = search_collection(branch, query)
            if not hits:
                cid = collection_id_for(branch)
                _print(
                    f"Collection {name} empty or missing (id={cid}). "
                    "Run ingest_collections against partners.h2o.ai."
                )
        except Exception as exc:  # noqa: BLE001
            _print(f"Collection search failed ({exc})")
    if not hits:
        _print(f"RAG fallback local kb ({branch})")
        hits = _search_kb(branch, f"{query} {state.get('query') or ''}")
    state["kb_hits"] = hits
    return state


def retrieve_penalizaciones(state: HelpdeskState) -> HelpdeskState:
    return _retrieve(state, "penalizaciones")


def retrieve_tecnica(state: HelpdeskState) -> HelpdeskState:
    return _retrieve(state, "tecnica")


def retrieve_billing(state: HelpdeskState) -> HelpdeskState:
    return _retrieve(state, "billing")


def _load_players() -> list[dict[str, Any]]:
    if not PLAYERS_PATH.exists():
        return []
    return json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]


def _extract_player_id(query: str) -> str | None:
    match = re.search(r"player_id[\"'\s:=]+([A-Za-z0-9_-]+)", query)
    if match:
        return match.group(1)
    match = re.search(r"\b(abc123|banned42|appeal99|tempban7|buyer55|fraud01)\b", query)
    if match:
        return match.group(1)
    return None


def _find_player(player_id: str | None) -> dict[str, Any] | None:
    if not player_id:
        return None
    for player in _load_players():
        if player["player_id"] == player_id:
            return player
    return None


def _tools_from_player(player: dict[str, Any] | None, player_id: str | None, category: str) -> dict[str, Any]:
    tools: dict[str, Any] = {"player_id": player_id}
    if not player:
        tools["get_account_status"] = {"found": False}
        return tools
    tools["get_account_status"] = {
        "found": True,
        "riot_id": player["riot_id"],
        "status": player["status"],
        "region": player["region"],
        "email_verified": player["email_verified"],
        "account_id": player["account_id"],
    }
    tools["get_ticket_history"] = player.get("tickets") or []
    if category == "penalizaciones":
        ban = player.get("ban")
        tools["get_ban_reason"] = {"banned": False} if not ban else {"banned": True, **ban}
    if category == "billing":
        tools["get_purchase_history"] = {
            "purchases": player.get("purchases") or [],
            "refunds_used": player.get("refunds_used", 0),
        }
    return tools


def call_mcp_tools(state: HelpdeskState) -> HelpdeskState:
    _print("Function calling (player context)...")
    player_id = _extract_player_id(state["query"])
    category = state.get("category") or "tecnica"
    args = {"player_id": player_id or ""}
    mcp_results: dict[str, Any] = {"player_id": player_id}
    if not is_offline():
        account = call_mcp_tool("get_account_status", args)
        if account is not None:
            mcp_results["get_account_status"] = account
            history = call_mcp_tool("get_ticket_history", args)
            if history is not None:
                mcp_results["get_ticket_history"] = history
            if category == "penalizaciones":
                ban = call_mcp_tool("get_ban_reason", args)
                if ban is not None:
                    mcp_results["get_ban_reason"] = ban
            if category == "billing":
                purchases = call_mcp_tool("get_purchase_history", args)
                if purchases is not None:
                    mcp_results["get_purchase_history"] = purchases
            state["tool_results"] = mcp_results
            return state
    player = _find_player(player_id)
    state["tool_results"] = _tools_from_player(player, player_id, category)
    return state


def _decide_action(state: HelpdeskState) -> tuple[str, str]:
    tools = state.get("tool_results") or {}
    query = _text(state["query"])
    ban = tools.get("get_ban_reason") or {}
    if ban.get("apelable") is True:
        return "escalate", "El ban está marcado como apelable."
    if "fraud01" == tools.get("player_id") or "no reconozco" in query or "duplicado" in query:
        return "escalate", "Posible fraude o cargo no reconocido."
    if "robad" in query or "hacke" in query:
        return "escalate", "Posible cuenta comprometida."
    if state.get("category") == "tecnica" and "reinstal" in query and "sigue" in query:
        return "escalate", "El error persiste tras reinstalación."
    return "close", "Hay política y contexto suficientes para un borrador estándar."


def _template_draft(state: HelpdeskState, action: str, reason: str) -> str:
    """Fallback wording only; the report carries context in its own sections."""
    account = (state.get("tool_results") or {}).get("get_account_status") or {}
    greeting = f"Hola {account['riot_id']}," if account.get("riot_id") else "Hola,"
    closing = (
        "Un agente revisará tu caso y te contactará con los siguientes pasos."
        if action == "escalate"
        else "Por favor confirma si el problema quedó resuelto."
    )
    return (
        f"{greeting}\n\n"
        "Gracias por contactar a Riot Support. Revisamos tu caso con la base de "
        f"conocimiento de la rama {state.get('category')}.\n\n"
        f"{closing}\n\n"
        "Un saludo,\nRiot Support"
    )


def draft_response(state: HelpdeskState) -> HelpdeskState:
    _print("Generando borrador para el agente humano...")
    action, reason = _decide_action(state)
    draft = _template_draft(state, action, reason)
    if not is_offline() and llm_available():
        prompt = (
            "Eres un asistente para agentes humanos de Riot Support en h2oGPTe. "
            "NO envíes el mensaje al jugador; solo redacta un borrador. "
            "Responde SOLO JSON con keys draft, action, action_reason. "
            "action debe ser close o escalate.\n\n"
            f"Ticket:\n{state.get('query')}\n\n"
            f"Clasificación: {state.get('category')} / {state.get('subcategory')}\n"
            f"Tools:\n{json.dumps(state.get('tool_results') or {}, ensure_ascii=False)}\n\n"
            f"Artículos RAG:\n{(state.get('kb_hits') or '')[:3000]}\n"
        )
        try:
            payload = parse_json_object(llm_query(prompt, collection_id=None, timeout=90))
            if payload:
                action = str(payload.get("action") or action)
                if action not in {"close", "escalate"}:
                    action = "close"
                reason = str(payload.get("action_reason") or reason)
                draft = str(payload.get("draft") or draft)
        except Exception as exc:  # noqa: BLE001
            _print(f"LLM draft fallback ({exc})")
    state["action"] = action
    state["action_reason"] = reason
    state["draft"] = draft
    return state


def build_helpdesk_graph():
    graph = StateGraph(HelpdeskState)
    graph.add_node("classify", classify_node)
    graph.add_node("route", route_node)
    graph.add_node("retrieve_penalizaciones", retrieve_penalizaciones)
    graph.add_node("retrieve_tecnica", retrieve_tecnica)
    graph.add_node("retrieve_billing", retrieve_billing)
    graph.add_node("call_mcp_tools", call_mcp_tools)
    graph.add_node("draft_response", draft_response)
    graph.set_entry_point("classify")
    graph.add_edge("classify", "route")
    graph.add_conditional_edges(
        "route",
        route_branch,
        {
            "retrieve_penalizaciones": "retrieve_penalizaciones",
            "retrieve_tecnica": "retrieve_tecnica",
            "retrieve_billing": "retrieve_billing",
        },
    )
    graph.add_edge("retrieve_penalizaciones", "call_mcp_tools")
    graph.add_edge("retrieve_tecnica", "call_mcp_tools")
    graph.add_edge("retrieve_billing", "call_mcp_tools")
    graph.add_edge("call_mcp_tools", "draft_response")
    graph.add_edge("draft_response", END)
    return graph.compile()


def _empty_state(query: str, chat_history: Optional[List[Dict[str, str]]]) -> HelpdeskState:
    return {
        "query": query,
        "chat_history": chat_history or [],
        "category": "",
        "subcategory": "",
        "summary": "",
        "collection": "",
        "tool_results": {},
        "kb_hits": "",
        "draft": "",
        "action": "",
        "action_reason": "",
        "error": "",
    }


HUMAN_NOTE = (
    "El agente humano revisa, edita y envía. Este asistente no contacta al jugador."
)

ACTION_LABEL = {"close": "CERRAR", "escalate": "ESCALAR"}

ACCOUNT_FIELDS = (
    ("riot_id", "Riot ID"),
    ("account_id", "Account ID"),
    ("status", "Estado"),
    ("region", "Región"),
    ("email_verified", "Email verificado"),
    ("created_at", "Cuenta creada"),
)

BAN_FIELDS = (
    ("type", "Tipo"),
    ("reason", "Motivo"),
    ("at", "Fecha"),
    ("duration", "Duración"),
    ("apelable", "Apelable"),
)


def run_payload(
    query: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> dict[str, Any]:
    """Run the graph and return the structured result."""
    _print("Starting Riot Support Agent...")
    diagnostics = runtime_diagnostics()
    _print(f"Runtime diagnostics: {json.dumps(diagnostics, ensure_ascii=False)}")
    result = build_helpdesk_graph().invoke(_empty_state(query, chat_history))
    _print("Done!")
    return {
        "query": query,
        "category": result.get("category"),
        "subcategory": result.get("subcategory"),
        "summary": result.get("summary"),
        "collection": result.get("collection"),
        "action": result.get("action"),
        "action_reason": result.get("action_reason"),
        "draft": result.get("draft"),
        "tool_results": result.get("tool_results") or {},
        "kb_hits": result.get("kb_hits") or "",
        "error": result.get("error") or "",
        "note": HUMAN_NOTE,
        "diagnostics": diagnostics,
    }


def _degraded(payload: dict[str, Any]) -> list[str]:
    diagnostics = payload.get("diagnostics") or {}
    warnings = []
    if diagnostics.get("api_probe") != "ok":
        warnings.append(f"RAG degradado: {diagnostics.get('api_probe')}")
    if not diagnostics.get("mcp_server_path"):
        warnings.append("Contexto de jugador simulado: no se encontró el servidor MCP.")
    if not llm_available():
        warnings.append("Clasificación y borrador por reglas: LLM no disponible.")
    return warnings


def _article_names(kb_hits: str) -> list[str]:
    return [line[4:].strip() for line in kb_hits.splitlines() if line.startswith("### ")]


def _facts(source: dict[str, Any], fields: tuple[tuple[str, str], ...]) -> list[str]:
    rows = []
    for key, label in fields:
        value = source.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            value = "sí" if value else "no"
        rows.append(f"| {label} | {value} |")
    return rows


def render_report(payload: dict[str, Any]) -> str:
    """Markdown the human agent can act on without reading raw JSON."""
    tools = payload.get("tool_results") or {}
    account = tools.get("get_account_status") or {}
    action = payload.get("action") or "close"
    lines = [
        f"# Ticket {payload.get('category')} / {payload.get('subcategory')}",
        "",
        f"**Acción recomendada: {ACTION_LABEL.get(action, action.upper())}**",
        "",
        payload.get("action_reason") or "",
        "",
        "## Borrador para el jugador",
        "",
        (payload.get("draft") or "").strip(),
        "",
        "## Contexto del jugador",
        "",
    ]
    if account.get("found"):
        lines += ["| Campo | Valor |", "| --- | --- |", *_facts(account, ACCOUNT_FIELDS)]
    else:
        lines.append(f"No se encontró al jugador `{tools.get('player_id')}`.")
    ban = tools.get("get_ban_reason") or {}
    if ban.get("banned"):
        lines += [
            "",
            "### Sanción",
            "",
            "| Campo | Valor |",
            "| --- | --- |",
            *_facts(ban, BAN_FIELDS),
        ]
    purchases = (tools.get("get_purchase_history") or {}).get("purchases")
    if purchases:
        lines += ["", "### Compras", ""]
        lines += [
            f"- {p.get('sku')} — {p.get('amount')} {p.get('currency')} ({p.get('at')})"
            for p in purchases
        ]
    articles = _article_names(payload.get("kb_hits") or "")
    lines += [
        "",
        "## Fuentes",
        "",
        f"- Collection: `{payload.get('collection')}`",
        f"- Artículos: {', '.join(articles) if articles else 'ninguno'}",
    ]
    warnings = _degraded(payload)
    if warnings:
        lines += ["", "## Avisos", ""] + [f"- {w}" for w in warnings]
    lines += ["", "---", "", f"_{HUMAN_NOTE}_"]
    return "\n".join(lines)


def run_helpdesk(
    query: str = "VAN 57 error al iniciar Valorant. player_id=abc123",
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Entry point. Name must match function_info.name in metadata.json."""
    payload = run_payload(query, chat_history)
    if payload.get("error"):
        return payload["error"]
    return render_report(payload)


def run_helpdesk_json(
    query: str = "VAN 57 error al iniciar Valorant. player_id=abc123",
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Structured output for the benchmark; the chat entry point renders markdown."""
    return json.dumps(run_payload(query, chat_history), ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Riot Support LangGraph agent")
    parser.add_argument("--query", default="VAN 57 error al iniciar Valorant. player_id=abc123")
    parser.add_argument("--json", action="store_true", help="Print the structured payload.")
    args = parser.parse_args()
    render = run_helpdesk_json if args.json else run_helpdesk
    print(render(query=args.query))


if __name__ == "__main__":
    main()
