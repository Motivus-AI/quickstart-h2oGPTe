"""Download public Riot Help Center articles via the Zendesk API."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[3]
KB_ROOT = REPO_ROOT / "data" / "knowledge_base"

FOLDER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("vanguard_errors", ("vanguard", "van 57", "van 9006", "van 128", "van 2266")),
    ("bans_penalties", ("ban", "penalty", "penaliz", "suspend", "appeal")),
    ("account_support", ("account", "cuenta", "email", "password", "hack")),
    ("purchases", ("purchase", "refund", "rp", "riot point", "billing", "skin")),
    ("technical", ("crash", "lag", "client", "install", "tecn")),
]


def _classify(title: str, body: str) -> str:
    haystack = f"{title}\n{body}".lower()
    for folder, keywords in FOLDER_RULES:
        if any(kw in haystack for kw in keywords):
            return folder
    return "technical"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:80] or "article"


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    return soup.get_text("\n", strip=True)


def fetch_articles(base_url: str, locale: str, max_pages: int) -> list[dict]:
    articles: list[dict] = []
    url = f"{base_url.rstrip('/')}/api/v2/help_center/{locale}/articles.json"
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for _ in range(max_pages):
            response = client.get(url, params={"per_page": 30})
            response.raise_for_status()
            payload = response.json()
            articles.extend(payload.get("articles") or [])
            url = payload.get("next_page")
            if not url:
                break
    return articles


def save_articles(articles: list[dict]) -> int:
    written = 0
    for article in articles:
        title = article.get("title") or "untitled"
        body = _html_to_text(article.get("body") or "")
        folder = _classify(title, body)
        target_dir = KB_ROOT / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f"scraped_{article.get('id', 'x')}_{_slug(title)}.md"
        path = target_dir / name
        path.write_text(
            f"# {title}\n\n"
            f"Source: {article.get('html_url', '')}\n\n"
            f"{body}\n",
            encoding="utf-8",
        )
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=3)
    args = parser.parse_args()
    locale = os.getenv("ZENDESK_LOCALE", "es")
    base_url = os.getenv("ZENDESK_BASE_URL", "https://support.riotgames.com")
    print(f"Fetching Help Center articles locale={locale} ...")
    articles = fetch_articles(base_url, locale, args.max_pages)
    count = save_articles(articles)
    print(f"Wrote {count} articles under {KB_ROOT}")


if __name__ == "__main__":
    main()
