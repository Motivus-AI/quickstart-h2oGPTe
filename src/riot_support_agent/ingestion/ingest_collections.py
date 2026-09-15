"""Create or reuse h2oGPTe collections and ingest local knowledge-base files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from riot_support_agent.h2o_client import (
    BRANCH_FOLDERS,
    COLLECTION_NAMES,
    get_client,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
KB_ROOT = REPO_ROOT / "data" / "knowledge_base"
IDS_PATH = REPO_ROOT / "data" / "collections.json"


def _find_collection_id(client, name: str) -> str | None:
    for collection in client.list_recent_collections(0, 1000):
        if getattr(collection, "name", None) == name:
            return collection.id
    return None


def ingest_branch(client, branch: str, files: list[Path]) -> str:
    name = COLLECTION_NAMES[branch]
    collection_id = _find_collection_id(client, name)
    if collection_id is None:
        collection_id = client.create_collection(
            name=name,
            description=f"Riot Support knowledge base ({branch})",
        )
        print(f"Created collection {name} → {collection_id}")
    else:
        print(f"Reusing collection {name} → {collection_id}")

    upload_ids = []
    for path in files:
        with path.open("rb") as handle:
            upload_ids.append(client.upload(path.name, handle))
    if upload_ids:
        client.ingest_uploads(collection_id, upload_ids)
        print(f"Ingested {len(upload_ids)} files into {name}")
    return collection_id


def iter_files(branch: str) -> list[Path]:
    files: list[Path] = []
    for folder in BRANCH_FOLDERS[branch]:
        directory = KB_ROOT / folder
        if directory.exists():
            files.extend(sorted(directory.glob("*.md")))
    return files


def run_ingest(dry_run: bool = False) -> dict:
    ids: dict = {}
    for branch in COLLECTION_NAMES:
        files = iter_files(branch)
        print(f"{branch}: {len(files)} markdown files")
        for path in files:
            print(f"  - {path.relative_to(REPO_ROOT)}")
        if dry_run:
            continue
        client = get_client()
        collection_id = ingest_branch(client, branch, files)
        ids[branch] = {"name": COLLECTION_NAMES[branch], "id": collection_id}
    if ids:
        IDS_PATH.write_text(json.dumps(ids, indent=2), encoding="utf-8")
        print(f"Wrote collection ids → {IDS_PATH}")
        print("Set these in Assign Keys / .env for the LangGraph agent:")
        env_map = {
            "penalizaciones": "COLLECTION_PENALIZACIONES",
            "tecnica": "COLLECTION_TECNICA",
            "billing": "COLLECTION_BILLING",
        }
        for branch, payload in ids.items():
            print(f"  {env_map[branch]}={payload['id']}")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded without calling h2oGPTe.",
    )
    args = parser.parse_args()
    run_ingest(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
