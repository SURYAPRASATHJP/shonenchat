"""Fetch article wikitext from a Fandom wiki through the MediaWiki API."""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

USER_AGENT = "shonenchat/0.1 (+https://github.com/SURYAPRASATHJP/shonenchat)"

# The API caps a content request at 50 pages for an anonymous client.
BATCH_SIZE = 50
DELAY_SECONDS = 1.0

# Page ids are assigned in creation order, so ascending id is oldest first.
# They are not contiguous: deleted pages and other namespaces leave holes,
# so we scan a wider range than we need and stop once we have enough.
DEFAULT_SCAN_CEILING = 2000
DEFAULT_LIMIT = 100


class FetchError(RuntimeError):
    """The API returned something we are not willing to trust."""


@dataclass(frozen=True)
class FetchResult:
    """One run's output, kept next to what it threw away.

    "100 documents" is not an interpretable number on its own. It means
    something only beside how many ids were walked to get them and why the
    rest were rejected, so those counts travel with the documents instead
    of being printed once and lost.

    `examined` and `requested_to` are two different numbers and reporting
    one as the other is a lie. A run stops the moment it has `limit`
    articles, part way through a batch, so the rest of that batch is asked
    for and never looked at. The invariant that must always hold is
    `examined == len(documents) + sum(skipped.values())`.
    """

    host: str
    documents: list[dict]
    skipped: Counter[str]
    examined: int
    requested_to: int


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


def default_out_path(host: str) -> Path:
    """data/onepiece.jsonl from onepiece.fandom.com."""
    return Path("data") / f"{host.split('.')[0]}.jsonl"


class Wiki:
    """One Fandom wiki, and the client that talks to it.

    The host used to be a module constant, so fetching a second wiki meant
    editing this file. It lives here now, in one place. The httpx client is
    passed in rather than created here, so a test can hand over a fake one
    without a network call.
    """

    def __init__(self, host: str, client: httpx.Client) -> None:
        self.host = host
        self.api_url = f"https://{host}/api.php"
        self.client = client

    def _get(self, params: dict[str, str]) -> dict:
        """One API call, with every failure made loud."""
        response = self.client.get(self.api_url, params=params)
        response.raise_for_status()
        payload = response.json()

        # A 200 with a warnings key is how MediaWiki reports an unsupported
        # parameter. Without this check a typo returns an empty result that
        # looks exactly like success.
        if "warnings" in payload:
            raise FetchError(f"{self.host}: API warnings: {payload['warnings']}")
        if "query" not in payload:
            raise FetchError(f"{self.host}: no query in response: {payload}")

        return payload

    def fetch_pages(self, page_ids: list[int]) -> list[dict]:
        """Ask for the wikitext of up to BATCH_SIZE pages by id."""
        return self._get(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "pageids": "|".join(str(page_id) for page_id in page_ids),
                # info is here only for its `redirect` flag. Do not add
                # &redirects=1: that follows the redirect and returns the
                # target, which we already fetch under its own id, so it
                # makes duplicates rather than exclusions.
                "prop": "revisions|info",
                "rvslots": "*",
                "rvprop": "content|ids",
            }
        )["query"]["pages"]

    def to_document(self, page: dict) -> dict:
        """Turn one API page into a document.

        Only call this on a page whose `rejection_reason` is None.
        """
        revision = page["revisions"][0]
        title = page["title"]

        return {
            "page_id": page["pageid"],
            "title": title,
            # Which wiki this came from. Page ids are only unique within one
            # wiki, so from 28 of them the id alone stops being an identity.
            "wiki_host": self.host,
            "revision_id": revision["revid"],
            "wikitext": revision["slots"]["main"]["content"],
            "url": f"https://{self.host}/wiki/{quote(title.replace(' ', '_'))}",
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def fetch_oldest(
        self,
        limit: int = DEFAULT_LIMIT,
        scan_ceiling: int = DEFAULT_SCAN_CEILING,
    ) -> FetchResult:
        """Collect the oldest `limit` articles, by ascending page id."""
        documents: list[dict] = []
        skipped: Counter[str] = Counter()
        examined = 0

        # scan_ceiling is inclusive: --scan-ceiling 2000 walks id 2000.
        # Both bounds need the +1 and getting only one of them right is the
        # bug this replaced, which silently never asked for the last id.
        for start in range(1, scan_ceiling + 1, BATCH_SIZE):
            page_ids = list(range(start, min(start + BATCH_SIZE, scan_ceiling + 1)))

            for page in self.fetch_pages(page_ids):
                examined += 1
                reason = rejection_reason(page)
                if reason is not None:
                    skipped[reason] += 1
                    continue
                documents.append(self.to_document(page))
                if len(documents) == limit:
                    return FetchResult(
                        host=self.host,
                        documents=sorted(documents, key=lambda d: d["page_id"]),
                        skipped=skipped,
                        examined=examined,
                        requested_to=page_ids[-1],
                    )

            time.sleep(DELAY_SECONDS)

        raise FetchError(
            f"{self.host}: only found {len(documents)} articles below id "
            f"{scan_ceiling} (skipped {dict(skipped)}). Raise --scan-ceiling."
        )


def write_jsonl(documents: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False) + "\n")
