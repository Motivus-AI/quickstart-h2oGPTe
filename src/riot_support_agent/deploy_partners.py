"""Publish Collections, Local MCP, and the LangGraph agent to partners.h2o.ai."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from riot_support_agent.h2o_client import DEFAULT_ADDRESS, get_api_key, get_client
from riot_support_agent.ingestion.ingest_collections import run_ingest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST = REPO_ROOT / "dist"
MCP_ZIP = DIST / "riot_player_context.zip"
AGENT_ZIP = DIST / "riot_helpdesk_agent.zip"
IDS_PATH = REPO_ROOT / "data" / "collections.json"
CHAT_URL = f"{DEFAULT_ADDRESS.rstrip('/')}/"
AGENT_ID = "c77f4f63-4237-4ba8-9389-ea27de6c4b66"
AGENT_NAME = "riot_helpdesk_agent"


def _dump(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return {"value": str(obj)}


ENVS_PATH = REPO_ROOT / "packages" / "riot_helpdesk_agent" / "envs.json"
ENVS_COLLECTION_KEYS = {
    "penalizaciones": "COLLECTION_PENALIZACIONES",
    "tecnica": "COLLECTION_TECNICA",
    "billing": "COLLECTION_BILLING",
}


def _sync_envs_json() -> None:
    """Bake collection ids into envs.json — they are identifiers, not secrets."""
    if not IDS_PATH.exists():
        return
    ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    envs = json.loads(ENVS_PATH.read_text(encoding="utf-8"))
    changed = False
    for branch, env_name in ENVS_COLLECTION_KEYS.items():
        collection_id = (ids.get(branch) or {}).get("id")
        if collection_id and envs.get(env_name) != collection_id:
            envs[env_name] = collection_id
            changed = True
    if changed:
        ENVS_PATH.write_text(json.dumps(envs, indent=2) + "\n", encoding="utf-8")
        print("Baked collection ids into envs.json")


@contextmanager
def _api_key_in_envs():
    """Assigned secrets never reach the sandbox, but envs.json defaults do.

    The key is written into the packaged copy only and reverted straight after,
    so it never lands in the working tree.
    """
    original = ENVS_PATH.read_text(encoding="utf-8")
    key = get_api_key()
    if not key:
        yield
        return
    envs = json.loads(original)
    envs["RIOT_H2OGPTE_API_KEY"] = key
    ENVS_PATH.write_text(json.dumps(envs, indent=2) + "\n", encoding="utf-8")
    try:
        yield
    finally:
        ENVS_PATH.write_text(original, encoding="utf-8")


def _pack() -> None:
    _sync_envs_json()
    script = REPO_ROOT / "scripts" / "pack.sh"
    with _api_key_in_envs():
        subprocess.run(["bash", str(script)], check=True, cwd=REPO_ROOT)


def _existing_tool_names(client) -> set[str]:
    names: set[str] = set()
    try:
        for tool in client.get_custom_agent_tools() or []:
            data = _dump(tool)
            names.add(str(data.get("tool_name") or data.get("name") or ""))
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list tools ({exc})")
    return names


def _find_agent_id(client, name: str) -> str | None:
    try:
        for agent in client.get_custom_agents() or []:
            data = _dump(agent)
            if data.get("agent_name") == name or data.get("name") == name:
                return str(data.get("id"))
    except Exception as exc:  # noqa: BLE001
        print(f"Could not list agents ({exc})")
    return None


def upload_mcp(client, replace: bool) -> list:
    if "riot-player-context" in _existing_tool_names(client) and not replace:
        print("MCP riot-player-context already exists — skip upload")
        return []
    print(f"Uploading Local MCP {MCP_ZIP} → {DEFAULT_ADDRESS}")
    return client.add_custom_agent_tool(
        tool_type="local_mcp",
        tool_args={
            "tool_name": "riot-player-context",
            "description": "Simulated Riot player context (account, ban, tickets, purchases)",
            "enable_by_default": True,
            "tool_usage_mode": ["runner", "creator"],
        },
        custom_tool_path=str(MCP_ZIP),
    )


def upload_agent(client, replace: bool) -> list:
    existing = _find_agent_id(client, AGENT_NAME)
    if existing and replace:
        print(f"Replacing agent {existing}")
        client.delete_custom_agent([existing])
        existing = None
    if existing and not replace:
        print(f"Agent {AGENT_NAME} already exists — skip upload ({existing})")
        return [existing]
    print(f"Uploading LangGraph agent {AGENT_ZIP} → {DEFAULT_ADDRESS}")
    return client.add_custom_agent(
        agent_type="langgraph",
        agent_args={
            "description": "Riot Support helpdesk: classify, route, RAG, MCP, draft",
        },
        agent_path=str(AGENT_ZIP),
        agent_name=AGENT_NAME,
    )


def _recreate_key(client, name: str, value: str, description: str) -> str | None:
    # update_agent_key() reports success but does not persist the new value, so
    # the only way to guarantee what a secret holds is to drop and rebuild it.
    stale = [
        str(_dump(key)["id"])
        for key in client.get_agent_keys() or []
        if _dump(key).get("name") == name and _dump(key).get("id")
    ]
    if stale:
        try:
            client.delete_agent_keys(stale)
            print(f"Deleted stale agent key {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"Could not delete agent key {name}: {exc}")
    created = client.add_agent_key(
        [
            {
                "name": name,
                "value": value,
                "key_type": "private",
                "description": description,
            }
        ]
    )
    if not created:
        print(f"Failed to create agent key {name}")
        return None
    first = created[0]
    data = _dump(first)
    key_id = data.get("agent_key_id") or data.get("id")
    print(f"Created agent key {name}")
    return str(key_id) if key_id else None


def _associate(client, agent_id: str, env_key_name: str, key_id: str) -> None:
    # Keys are recreated on every deploy, so any surviving row points at a key
    # id that no longer exists. Always rebuild the mapping.
    existing = client.list_custom_agent_key_associations(agent_id=agent_id) or []
    for row in existing:
        data = _dump(row)
        if data.get("env_key_name") == env_key_name and data.get("id"):
            try:
                client.delete_custom_agent_key_associations([str(data["id"])])
            except Exception as exc:  # noqa: BLE001
                print(f"Could not clear association {env_key_name}: {exc}")
    client.create_custom_agent_key_association(
        agent_id=agent_id,
        env_key_name=env_key_name,
        key_id=key_id,
    )
    print(f"Mapped {env_key_name} → key")


def associate_runtime_keys(client, agent_id: str) -> None:
    api_key = get_api_key()
    if not api_key:
        print("No H2OGPTE_API_KEY in env — skip key association")
        return
    ids = {}
    if IDS_PATH.exists():
        ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    mapping = {
        # CUSTOM_AGENT_API_KEY is reserved: h2oGPTe injects its own platform
        # token there and ignores the assigned secret, so use our own name.
        "RIOT_H2OGPTE_API_KEY": (
            "riot_h2ogpte_api_key",
            api_key,
            "Enterprise h2oGPTe API key for the Riot helpdesk agent",
        ),
        "CUSTOM_AGENT_BASE_URL": (
            "riot_h2ogpte_base_url",
            DEFAULT_ADDRESS,
            "h2oGPTe partners base URL",
        ),
        "H2OGPTE_ADDRESS": (
            "riot_h2ogpte_base_url",
            DEFAULT_ADDRESS,
            "h2oGPTe partners base URL",
        ),
        "COLLECTION_PENALIZACIONES": (
            "riot_collection_penalizaciones",
            (ids.get("penalizaciones") or {}).get("id") or os.getenv("COLLECTION_PENALIZACIONES", ""),
            "RAG collection id penalizaciones",
        ),
        "COLLECTION_TECNICA": (
            "riot_collection_tecnica",
            (ids.get("tecnica") or {}).get("id") or os.getenv("COLLECTION_TECNICA", ""),
            "RAG collection id tecnica",
        ),
        "COLLECTION_BILLING": (
            "riot_collection_billing",
            (ids.get("billing") or {}).get("id") or os.getenv("COLLECTION_BILLING", ""),
            "RAG collection id billing",
        ),
    }
    created: dict[str, str] = {}
    for env_name, (key_name, value, description) in mapping.items():
        if not value:
            print(f"Skip {env_name}: empty value")
            continue
        if key_name not in created:
            kid = _recreate_key(client, key_name, value, description)
            if not kid:
                continue
            created[key_name] = kid
        _associate(client, agent_id, env_name, created[key_name])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy Riot Support Agent to Enterprise h2oGPTe on partners.h2o.ai"
    )
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete and re-upload the LangGraph agent ZIP.",
    )
    parser.add_argument(
        "--associate-keys",
        action="store_true",
        help="Create Secret Manager keys and map them onto the custom agent.",
    )
    args = parser.parse_args()

    print(f"Production target: {DEFAULT_ADDRESS}")
    _pack()
    if not args.skip_ingest:
        run_ingest(dry_run=False)
    client = get_client()
    if not args.skip_upload:
        tool_ids = upload_mcp(client, replace=False)
        agent_ids = upload_agent(client, replace=args.replace)
        print(f"tool_ids={tool_ids}")
        print(f"agent_ids={agent_ids}")
    agent_id = _find_agent_id(client, AGENT_NAME) or AGENT_ID
    if args.associate_keys or not args.skip_upload:
        associate_runtime_keys(client, agent_id)
    print()
    print("Open Chat on partners:")
    print(f"  {CHAT_URL}")
    print("Agent Type = riot_helpdesk_agent (langgraph)")
    print("Test ticket: VAN 57 error al iniciar Valorant. player_id=abc123")


if __name__ == "__main__":
    main()
