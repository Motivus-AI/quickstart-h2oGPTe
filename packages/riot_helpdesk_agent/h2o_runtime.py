"""Runtime helpers that talk only to Enterprise h2oGPTe on partners.h2o.ai."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

PARTNERS_ADDRESS = "https://h2ogpte.partners.h2o.ai"

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001 — find_dotenv() asserts when there is no caller frame
    pass

COLLECTION_NAMES = {
    "penalizaciones": "riot-support-penalizaciones",
    "tecnica": "riot-support-tecnica",
    "billing": "riot-support-billing",
}

ENV_COLLECTION = {
    "penalizaciones": "COLLECTION_PENALIZACIONES",
    "tecnica": "COLLECTION_TECNICA",
    "billing": "COLLECTION_BILLING",
}


def partners_address() -> str:
    # CUSTOM_AGENT_BASE_URL points at the platform's LLM endpoint, which is not
    # the same host as the h2oGPTe RPC API this client talks to.
    return (os.getenv("H2OGPTE_ADDRESS") or PARTNERS_ADDRESS).rstrip("/")


def api_key() -> str | None:
    # h2oGPTe reserves CUSTOM_AGENT_API_KEY and overwrites it with a platform
    # token that our assigned secret cannot override, so it is only a fallback.
    key = (
        os.getenv("RIOT_H2OGPTE_API_KEY")
        or os.getenv("H2OGPTE_API_KEY")
        or os.getenv("CUSTOM_AGENT_API_KEY")
    )
    return key.strip() if key else None


def is_offline() -> bool:
    """Global kill switch; keeps unit tests off the network."""
    return os.getenv("H2OGPTE_OFFLINE", "").strip() in {"1", "true", "yes"}


def rag_available() -> bool:
    """Collections live behind the h2oGPTe RPC API, which needs a user key."""
    return not is_offline() and bool(api_key())


def get_client():
    key = api_key()
    if not key:
        raise RuntimeError(
            "Missing CUSTOM_AGENT_API_KEY / H2OGPTE_API_KEY for "
            f"{partners_address()}"
        )
    from h2ogpte import H2OGPTE

    return H2OGPTE(address=partners_address(), api_key=key)


@lru_cache(maxsize=8)
def collection_id_for(branch: str) -> str | None:
    env_name = ENV_COLLECTION.get(branch)
    if env_name:
        forced = os.getenv(env_name, "").strip()
        if forced:
            return forced
    name = COLLECTION_NAMES[branch]
    try:
        client = get_client()
        for collection in client.list_recent_collections(0, 1000):
            if getattr(collection, "name", None) == name:
                return collection.id
    except Exception as exc:  # noqa: BLE001
        print(f"Collection lookup for {name} failed ({type(exc).__name__}: {exc})", flush=True)
        return None
    return None


def llm_endpoint() -> tuple[str, str, str] | None:
    """The OpenAI-compatible LLM that h2oGPTe hands to every custom agent."""
    base_url = os.getenv("CUSTOM_AGENT_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("CUSTOM_AGENT_API_KEY", "").strip()
    model = os.getenv("CUSTOM_AGENT_MODEL", "").strip()
    if base_url and key and model:
        return base_url, key, model
    return None


def llm_available() -> bool:
    return llm_endpoint() is not None


def llm_query(message: str, collection_id: str | None = None, timeout: int = 90) -> str:
    endpoint = llm_endpoint()
    if endpoint is None:
        raise RuntimeError("CUSTOM_AGENT_BASE_URL / API_KEY / MODEL not injected")
    base_url, key, model = endpoint
    import requests

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "temperature": 0,
            # Anthropic models behind LiteLLM reject requests without it.
            "max_tokens": 2048,
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"LLM {response.status_code}: {response.text[:300]}")
    choices = response.json().get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message", {}).get("content") or "").strip()


def parse_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def search_collection(branch: str, query: str, limit: int = 4) -> str:
    collection_id = collection_id_for(branch)
    if not collection_id:
        return ""
    client = get_client()
    chunks = client.search_chunks(
        collection_id=collection_id,
        query=query,
        topics=[],
        offset=0,
        limit=limit,
    )
    parts = []
    for chunk in chunks or []:
        text = getattr(chunk, "text", "") or ""
        name = getattr(chunk, "name", "") or ""
        if text:
            parts.append(f"### {name}\n{text}")
    return "\n\n".join(parts)


def _mcp_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.getenv("RIOT_PLAYER_CONTEXT_MCP_SERVER_PATH", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    mcp_dir = os.getenv("MCP_DIR", "").strip()
    if mcp_dir:
        base = Path(mcp_dir)
        for folder in ("riot_player_context", "riot-player-context"):
            candidates.append(base / folder / "server.py")
        candidates.append(base / "server.py")
    return candidates


def mcp_server_path() -> Path | None:
    for path in _mcp_candidates():
        if path.exists():
            return path.resolve()
    # The platform names the extracted folder for us, so fall back to a scan
    # instead of trusting the layout declared in metadata.json.
    mcp_dir = os.getenv("MCP_DIR", "").strip()
    if mcp_dir and Path(mcp_dir).is_dir():
        for found in sorted(Path(mcp_dir).glob("*/server.py")):
            return found.resolve()
        for found in sorted(Path(mcp_dir).glob("*/*/server.py")):
            return found.resolve()
    return None


def _tool_result_to_python(result: Any) -> Any:
    content = getattr(result, "content", None) or []
    texts = []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            texts.append(text)
    if not texts:
        return {"ok": True}
    raw = texts[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


async def _mcp_call_async(tool_name: str, arguments: dict[str, Any]) -> Any:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    path = mcp_server_path()
    if path is None:
        raise FileNotFoundError("MCP server.py not found")
    # MCP_DIR is relative, so args and cwd must both be absolute or the server
    # path gets appended to itself.
    path = path.resolve()
    params = StdioServerParameters(
        command=sys.executable or "python",
        args=[str(path)],
        cwd=str(path.parent),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _tool_result_to_python(result)


DIAG_ENV_KEYS = (
    "RIOT_H2OGPTE_API_KEY",
    "CUSTOM_AGENT_API_KEY",
    "CUSTOM_AGENT_MODEL",
    "CUSTOM_AGENT_BASE_URL",
    "H2OGPTE_API_KEY",
    "H2OGPTE_ADDRESS",
    "H2OGPTE_OFFLINE",
    "COLLECTION_PENALIZACIONES",
    "COLLECTION_TECNICA",
    "COLLECTION_BILLING",
    "MCP_DIR",
    "RIOT_PLAYER_CONTEXT_MCP_SERVER_PATH",
)


def _mask(name: str, value: str) -> str | None:
    if not value:
        return None
    if "KEY" not in name:
        return value
    if len(value) <= 12:
        return f"<set len={len(value)}>"
    return f"{value[:4]}...{value[-4:]} <len={len(value)}>"


def runtime_diagnostics() -> dict[str, Any]:
    """Report what the sandbox actually injected, so failures are explainable."""
    diag: dict[str, Any] = {
        "address": partners_address(),
        "offline": is_offline(),
        "env": {
            name: _mask(name, os.getenv(name, "").strip()) for name in DIAG_ENV_KEYS
        },
    }
    path = mcp_server_path()
    diag["mcp_server_path"] = str(path) if path else None
    mcp_dir = os.getenv("MCP_DIR", "").strip()
    if mcp_dir and Path(mcp_dir).is_dir():
        diag["mcp_dir_listing"] = sorted(p.name for p in Path(mcp_dir).iterdir())[:20]
    try:
        get_client().list_recent_collections(0, 1)
        diag["api_probe"] = "ok"
    except Exception as exc:  # noqa: BLE001
        diag["api_probe"] = f"{type(exc).__name__}: {exc}"
    return diag


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any | None:
    if mcp_server_path() is None:
        return None
    try:
        return asyncio.run(_mcp_call_async(tool_name, arguments))
    except Exception as exc:  # noqa: BLE001
        print(f"MCP {tool_name} failed ({exc})", flush=True)
        return None
