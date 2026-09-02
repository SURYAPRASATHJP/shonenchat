"""Fixtures shared across the test suite.

Lives here, not in a helpers module the tests import, for two reasons that
a plain module cannot give: pytest finds it with no import line, so there
is no import path to get wrong and no risk of a circular import between a
test and its helpers; and it is scoped by directory, so a fixture defined
here is available to every test under tests/ and nowhere else.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from shonenchat.fetch import Wiki

FAKE_HOST = "example.fandom.com"


def article_page(page_id: int, title: str, text: str = "body") -> dict[str, Any]:
    """A page shaped the way rejection_reason and to_document both accept."""
    return {
        "pageid": page_id,
        "ns": 0,
        "title": title,
        "revisions": [
            {"revid": page_id * 1000, "slots": {"main": {"content": text}}}
        ],
    }


def missing_page(page_id: int) -> dict[str, Any]:
    return {"pageid": page_id, "missing": True}


def namespace_page(page_id: int, ns: int = 14) -> dict[str, Any]:
    """ns 14 is Category. Anything but 0 is not an article."""
    return {"pageid": page_id, "ns": ns, "title": f"Category:{page_id}"}


def redirect_page(page_id: int) -> dict[str, Any]:
    """ns 0 with a revision, so only the redirect flag tells it apart."""
    return {
        "pageid": page_id,
        "ns": 0,
        "title": f"Redirect {page_id}",
        "redirect": True,
        "revisions": [{"revid": page_id * 1000, "slots": {"main": {"content": "#REDIRECT"}}}],
    }


def no_revisions_page(page_id: int) -> dict[str, Any]:
    return {"pageid": page_id, "ns": 0, "title": f"Empty {page_id}", "revisions": []}


@pytest.fixture
def make_wiki() -> Callable[[dict[int, dict[str, Any]]], Wiki]:
    """Build a Wiki backed by a fake API, keyed by page id.

    The handler answers exactly what fetch_pages asked for: it reads the
    pageids off the query string and returns those pages in that order. A
    requested id that is not in the corpus is answered as a missing page,
    which is what the real API does.

    No network. httpx.MockTransport routes every request to the handler,
    so the same Wiki class runs in the test as in production with only the
    client swapped, which is why the client is a constructor argument.
    """

    def _build(corpus: dict[int, dict[str, Any]]) -> Wiki:
        def handler(request: httpx.Request) -> httpx.Response:
            raw = request.url.params["pageids"]
            ids = [int(x) for x in raw.split("|")]
            pages = [corpus.get(i, missing_page(i)) for i in ids]
            return httpx.Response(200, json={"query": {"pages": pages}})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return Wiki(FAKE_HOST, client)

    return _build
