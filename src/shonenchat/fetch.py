"""Fetch article wikitext from a Fandom wiki through the MediaWiki API."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from shonenchat.models import SCHEMA_VERSION, Document, SchemaVersionError

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
    documents: list[Document]
    skipped: Counter[str]
    examined: int
    requested_to: int


def rejection_reason(page: dict[str, Any]) -> str | None:
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

    def _get(self, params: dict[str, str]) -> dict[str, Any]:
        """One API call, with every failure made loud.

        Callers of this class handle `FetchError` and nothing else. If an
        `httpx.TimeoutException` escapes from here, then every caller and
        every test has to know which HTTP library is in use in order to
        catch a fetch failing, which is exactly the coupling a custom
        exception exists to prevent.

        `httpx.HTTPError` is the base of the transport errors and of
        `HTTPStatusError`, so one clause covers a timeout, a refused
        connection, a DNS failure and a 503. `raise ... from error` keeps
        the original traceback: the point is to relabel the failure, not
        to hide what it was.
        """
        try:
            response = self.client.get(self.api_url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise FetchError(f"{self.host}: request failed: {error}") from error

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as error:
            # A proxy or a captive portal answers 200 with HTML. The
            # status said success and the body is not JSON at all.
            raise FetchError(
                f"{self.host}: response was not JSON: {response.text[:200]!r}"
            ) from error

        # A 200 with a warnings key is how MediaWiki reports an unsupported
        # parameter. Without this check a typo returns an empty result that
        # looks exactly like success.
        if "warnings" in payload:
            raise FetchError(f"{self.host}: API warnings: {payload['warnings']}")
        if "query" not in payload:
            raise FetchError(f"{self.host}: no query in response: {payload}")

        return payload

    def fetch_pages(self, page_ids: list[int]) -> list[dict[str, Any]]:
        """Ask for the wikitext of up to BATCH_SIZE pages by id."""
        pages: list[dict[str, Any]] = self._get(
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
        return pages

    def to_document(self, page: dict[str, Any]) -> Document:
        """Turn one API page into a `Document`. The gate.

        Above this line the page is a `dict[str, Any]`, which is to say a
        thing nothing has checked. Below it, a `Document` exists or an
        exception was raised. There is no third outcome.

        Two failures are possible here and they mean different things, so
        they are caught separately rather than as one `except Exception`:

        `KeyError` and friends mean the API's *shape* is not what we read
        it to be. `revision["slots"]["main"]["content"]` is four subscripts
        that all run before pydantic sees anything, and Fandom dropping
        `content` would otherwise raise a bare `KeyError('content')` from
        the middle of a fetch loop, naming neither the wiki nor the page.

        `ValidationError` means the shape was right and a *value* was
        rejected, e.g. a blank title. Same outcome, different cause, and a
        run that fails at 3 a.m. should say which.

        Only call this on a page whose `rejection_reason` is None.
        """
        title = page.get("title")

        try:
            revision = page["revisions"][0]
            return Document(
                page_id=page["pageid"],
                title=page["title"],
                wiki_host=self.host,
                revision_id=revision["revid"],
                wikitext=revision["slots"]["main"]["content"],
                url=f"https://{self.host}/wiki/{quote(page['title'].replace(' ', '_'))}",
                fetched_at=datetime.now(UTC),
            )
        except (KeyError, IndexError, TypeError) as error:
            raise FetchError(
                f"{self.host}: page {page.get('pageid')} ({title!r}) is not the "
                f"shape this client expects: {error!r}"
            ) from error
        except ValidationError as error:
            raise FetchError(
                f"{self.host}: page {page.get('pageid')} ({title!r}) failed "
                f"validation: {error}"
            ) from error

    def fetch_oldest(
        self,
        limit: int = DEFAULT_LIMIT,
        scan_ceiling: int = DEFAULT_SCAN_CEILING,
        progress: bool | None = None,
    ) -> FetchResult:
        """Collect the oldest `limit` articles, by ascending page id.

        `progress` exists because the first real run of this function
        printed nothing for twenty minutes. The code was correct and the
        tool was unusable: a long silent process is indistinguishable from
        a hung one, and the only way to find out was to kill it and lose
        the work. Correct and unusable is still broken.

        It is stderr, not stdout, so `... > out.txt` still captures only
        the summary. It is `\r` with no newline, so it overwrites itself
        rather than producing 400 lines of scrollback. `flush=True`
        because stderr is line-buffered when attached to a terminal but
        block-buffered when piped, and buffered progress output is no
        progress output at all.

        `progress=None` means "decide from the stream". Carriage returns
        and the erase-line escape are terminal instructions; sent to a
        pipe or a file they are literal bytes in the output. The first
        version of this defaulted to True and wrote a stray `\033[K` into
        captured output, which is the same class of mistake as the thing
        it was added to fix: correct on the machine it was written on,
        broken the moment anything else consumes it.
        """
        if progress is None:
            progress = sys.stderr.isatty()
        documents: list[Document] = []
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
                    if progress:
                        print("\r\033[K", end="", file=sys.stderr, flush=True)
                    return FetchResult(
                        host=self.host,
                        documents=sorted(documents, key=lambda d: d.page_id),
                        skipped=skipped,
                        examined=examined,
                        requested_to=page_ids[-1],
                    )

            if progress:
                print(
                    f"\r{self.host}: id {page_ids[-1]}/{scan_ceiling}  "
                    f"kept {len(documents)}/{limit}  skipped {sum(skipped.values())}",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

            time.sleep(DELAY_SECONDS)

        raise FetchError(
            f"{self.host}: only found {len(documents)} articles below id "
            f"{scan_ceiling} (skipped {dict(skipped)}). Raise --scan-ceiling."
        )


def write_jsonl(documents: list[Document], path: Path) -> None:
    """One `Document` per line, as JSON.

    `model_dump_json` rather than `json.dumps(model_dump())`: the second
    form returns a `datetime` object for `fetched_at` and an `HttpUrl` for
    `url`, neither of which `json.dumps` can serialise. Going straight to
    JSON is what converts them, and it writes UTF-8 rather than escaping
    every non-ASCII character, which matters on a corpus full of them.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(document.model_dump_json() + "\n")


def read_jsonl(path: Path) -> Iterator[Document]:
    """Read documents back, refusing rows this code cannot honestly read.

    A version stamped on write and never checked on read is decoration.
    This is the check, and it is the only reason the field earns its
    place on 1,000 lines.

    Rows are yielded one at a time rather than returned as a list. The
    corpus is 65,002 pages and the largest article measured 122,962
    characters, so the whole file must never have to fit in memory at
    once. The chunker on Day 3 consumes this.

    **A row with no `schema_version` key is read as version 1.** The
    1,000 documents already on disk were written before the field
    existed, and adding an optional field is the one change that does
    not alter what an old row means: every other field is byte for byte
    what version 1 writes today. That is a deliberate decision and not a
    default, and it is wrong for any future bump, where a missing key
    would have to mean "unreadable".

    Line number, not just path, in every error. A corpus file has
    thousands of lines and "row 4,812" is a thing you can go and look at.
    """
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                row: dict[str, Any] = json.loads(line)
            except ValueError as error:
                raise SchemaVersionError(
                    f"{path}:{line_number}: not valid JSON: {error}"
                ) from error

            version = row.get("schema_version", 1)
            if version != SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"{path}:{line_number}: written by schema version "
                    f"{version}, this code implements {SCHEMA_VERSION}. "
                    f"Re-fetch the file or write a migration."
                )

            try:
                yield Document.model_validate(row)
            except ValidationError as error:
                raise SchemaVersionError(
                    f"{path}:{line_number}: row does not validate against "
                    f"Document v{SCHEMA_VERSION}: {error}"
                ) from error
