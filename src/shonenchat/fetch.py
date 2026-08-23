"""Fetch article wikitext from a Fandom wiki through the MediaWiki API."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

WIKI_HOST = "onepiece.fandom.com"
API_URL = f"https://{WIKI_HOST}/api.php"
USER_AGENT = "shonenchat/0.1 (+https://github.com/SURYAPRASATHJP/shonenchat)"

# The API caps a content request at 50 pages for an anonymous client.
BATCH_SIZE = 50
DELAY_SECONDS = 1.0

# Page ids are assigned in creation order, so ascending id is oldest first.
# They are not contiguous: deleted pages and other namespaces leave holes,
# so we scan a wider range than we need and stop once we have enough.
SCAN_CEILING = 2000

OUT_PATH = Path("data/onepiece.jsonl")


class FetchError(RuntimeError):
    """The API returned something we are not willing to trust."""


def _get(client: httpx.Client, params: dict[str, str]) -> dict:
    """One API call, with every failure made loud."""
    response = client.get(API_URL, params=params)
    response.raise_for_status()
    payload = response.json()

    # A 200 with a warnings key is how MediaWiki reports an unsupported
    # parameter. Without this check a typo returns an empty result that
    # looks exactly like success.
    if "warnings" in payload:
        raise FetchError(f"API warnings: {payload['warnings']}")
    if "query" not in payload:
        raise FetchError(f"No query in response: {payload}")

    return payload


def fetch_pages(client: httpx.Client, page_ids: list[int]) -> list[dict]:
    """Ask for the wikitext of up to BATCH_SIZE pages by id."""
    return _get(
        client,
        {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "pageids": "|".join(str(page_id) for page_id in page_ids),
            # info is here only for its `redirect` flag. Do not add
            # &redirects=1: that follows the redirect and returns the target,
            # which we already fetch under its own id, so it makes duplicates.
            "prop": "revisions|info",
            "rvslots": "*",
            "rvprop": "content|ids",
        },
    )["query"]["pages"]


def rejection_reason(page: dict) -> str | None:
    """Why this page is not an article, or None if it is one.

    Four different things send a page id to the skip pile and they mean
    different things about the wiki. Returning which one lets the caller
    count them separately instead of reporting one opaque total.

    A redirect is namespace 0 and has a revision, so only the `redirect`
    flag from prop=info distinguishes it from a real article. Its whole
    body is one #REDIRECT line pointing at a page we already fetched.
    """
    if page.get("missing"):
        return "missing"
    if page.get("ns") != 0:
        return "namespace"
    if "redirect" in page:
        return "redirect"
    if not page.get("revisions"):
        return "no-revisions"
    return None


def to_document(page: dict) -> dict:
    """Turn one API page into a document.

    Only call this on a page whose `rejection_reason` is None.
    """
    revision = page["revisions"][0]
    title = page["title"]

    return {
        "page_id": page["pageid"],
        "title": title,
        "revision_id": revision["revid"],
        "wikitext": revision["slots"]["main"]["content"],
        "url": f"https://{WIKI_HOST}/wiki/{quote(title.replace(' ', '_'))}",
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def fetch_oldest(limit: int = 100) -> list[dict]:
    """Collect the oldest `limit` articles, by ascending page id."""
    documents: list[dict] = []
    skipped: Counter[str] = Counter()

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        for start in range(1, SCAN_CEILING, BATCH_SIZE):
            page_ids = list(range(start, min(start + BATCH_SIZE, SCAN_CEILING)))

            for page in fetch_pages(client, page_ids):
                reason = rejection_reason(page)
                if reason is not None:
                    skipped[reason] += 1
                    continue
                documents.append(to_document(page))
                if len(documents) == limit:
                    print(f"scanned up to id {page_ids[-1]}, skipped {dict(skipped)}")
                    return sorted(documents, key=lambda d: d["page_id"])

            time.sleep(DELAY_SECONDS)

    raise FetchError(
        f"Only found {len(documents)} articles below id {SCAN_CEILING} "
        f"(skipped {dict(skipped)}). Raise SCAN_CEILING."
    )


def write_jsonl(documents: list[dict], path: Path = OUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")


def main() -> None:
    documents = fetch_oldest()
    write_jsonl(documents)
    total_bytes = sum(len(d["wikitext"]) for d in documents)
    print(f"{len(documents)} documents -> {OUT_PATH}")
    print(f"{total_bytes:,} characters of wikitext, mean {total_bytes // len(documents):,}")


if __name__ == "__main__":
    main()
