"""Benchmark the LangGraph agent against gold synthetic tickets."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENT_DIR = REPO_ROOT / "packages" / "riot_helpdesk_agent"
TICKETS = REPO_ROOT / "data" / "tickets" / "synthetic_tickets.jsonl"
REPORT = REPO_ROOT / "data" / "benchmark" / "report.json"

sys.path.insert(0, str(AGENT_DIR))

from custom_agents import run_payload  # noqa: E402


def load_tickets(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def overlap(left: str, right: str) -> float:
    a = {tok for tok in left.lower().split() if len(tok) > 3}
    b = {tok for tok in right.lower().split() if len(tok) > 3}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluate(tickets: list[dict]) -> dict:
    rows = []
    cat_ok = act_ok = 0
    started = time.time()
    for ticket in tickets:
        query = (
            f"{ticket['subject']}\n{ticket['body']}\nplayer_id={ticket['player_id']}"
        )
        t0 = time.time()
        payload = run_payload(query=query)
        latency = time.time() - t0
        gold_branch = ticket["routing_branch"]
        gold_action = ticket["resolution"]["action"]
        cat_match = payload.get("category") == gold_branch
        act_match = payload.get("action") == gold_action
        cat_ok += int(cat_match)
        act_ok += int(act_match)
        rows.append(
            {
                "ticket_id": ticket["ticket_id"],
                "gold_branch": gold_branch,
                "pred_branch": payload.get("category"),
                "gold_action": gold_action,
                "pred_action": payload.get("action"),
                "draft_overlap": round(
                    overlap(payload.get("draft") or "", ticket["resolution"]["response_draft"]),
                    3,
                ),
                "latency_s": round(latency, 3),
            }
        )
    n = len(tickets) or 1
    return {
        "n": len(tickets),
        "category_accuracy": round(cat_ok / n, 3),
        "action_accuracy": round(act_ok / n, 3),
        "elapsed_s": round(time.time() - started, 3),
        "rows": rows,
    }


def _load_collection_env() -> None:
    ids_path = REPO_ROOT / "data" / "collections.json"
    if not ids_path.exists():
        return
    payload = json.loads(ids_path.read_text(encoding="utf-8"))
    env_map = {
        "penalizaciones": "COLLECTION_PENALIZACIONES",
        "tecnica": "COLLECTION_TECNICA",
        "billing": "COLLECTION_BILLING",
    }
    for branch, info in payload.items():
        key = env_map.get(branch)
        if key and info.get("id"):
            os.environ.setdefault(key, info["id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets", type=Path, default=TICKETS)
    parser.add_argument("--out", type=Path, default=REPORT)
    parser.add_argument(
        "--production",
        action="store_true",
        help="Call Enterprise h2oGPTe on partners.h2o.ai (requires H2OGPTE_API_KEY).",
    )
    args = parser.parse_args()
    if args.production:
        os.environ.pop("H2OGPTE_OFFLINE", None)
        _load_collection_env()
        print("Eval production mode → https://h2ogpte.partners.h2o.ai")
    else:
        os.environ["H2OGPTE_OFFLINE"] = "1"
    tickets = load_tickets(args.tickets)
    report = evaluate(tickets)
    report["mode"] = "production" if args.production else "offline"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"n={report['n']} category_accuracy={report['category_accuracy']} "
        f"action_accuracy={report['action_accuracy']}"
    )
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
