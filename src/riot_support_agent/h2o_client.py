"""Shared h2oGPTe client for ingest and evaluation."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_ADDRESS = "https://h2ogpte.partners.h2o.ai"

COLLECTION_NAMES = {
    "penalizaciones": "riot-support-penalizaciones",
    "tecnica": "riot-support-tecnica",
    "billing": "riot-support-billing",
}

BRANCH_FOLDERS = {
    "penalizaciones": ("bans_penalties", "account_support"),
    "tecnica": ("vanguard_errors", "technical"),
    "billing": ("purchases",),
}


def get_address() -> str:
    return os.getenv("CUSTOM_AGENT_BASE_URL") or os.getenv(
        "H2OGPTE_ADDRESS", DEFAULT_ADDRESS
    )


def get_api_key() -> str | None:
    return os.getenv("H2OGPTE_API_KEY") or os.getenv("CUSTOM_AGENT_API_KEY")


def get_client():
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Set H2OGPTE_API_KEY (or CUSTOM_AGENT_API_KEY) in .env. "
            "Create a key in Enterprise h2oGPTe on partners.h2o.ai."
        )
    from h2ogpte import H2OGPTE

    return H2OGPTE(address=get_address(), api_key=api_key)


def collection_env_id(branch: str) -> str | None:
    mapping = {
        "penalizaciones": "COLLECTION_PENALIZACIONES",
        "tecnica": "COLLECTION_TECNICA",
        "billing": "COLLECTION_BILLING",
    }
    value = os.getenv(mapping[branch], "").strip()
    return value or None
