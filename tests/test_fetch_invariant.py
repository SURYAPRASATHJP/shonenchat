"""The invariant that has held twice by observation and never by assertion.

`FetchResult` promises `examined == len(documents) + sum(skipped.values())`
in its own docstring. It has been true on every real run, which is not the
same as being enforced. This is the enforcement.

Every test here runs the real fetch_oldest against a fake API, so it is
the counting logic under test, not a hand-built FetchResult that would
only prove I can add up.
"""

from __future__ import annotations

from typing import Any

from conftest import (
    article_page,
    namespace_page,
    no_revisions_page,
    redirect_page,
)


def _mixed_corpus() -> dict[int, dict[str, Any]]:
    """Ids 1..7: one of every reject reason, then three real articles.

    Walked oldest-first with limit=3, the run sees 1 (missing, absent from
    this dict), 2 (namespace), 3 (Alpha, kept), 4 (redirect), 5 (no
    revisions), 6 (Beta, kept), 7 (Gamma, kept -> limit reached). Seven
    pages examined, three kept, four skipped, one of each reason.
    """
    return {
        2: namespace_page(2),
        3: article_page(3, "Alpha"),
        4: redirect_page(4),
        5: no_revisions_page(5),
        6: article_page(6, "Beta"),
        7: article_page(7, "Gamma"),
    }


def test_invariant_holds_on_a_mixed_run(make_wiki: Any) -> None:
    wiki = make_wiki(_mixed_corpus())
    result = wiki.fetch_oldest(limit=3, scan_ceiling=10, progress=False)

    # The invariant itself.
    assert result.examined == len(result.documents) + sum(result.skipped.values())


def test_the_counts_are_the_expected_ones(make_wiki: Any) -> None:
    """If only the invariant were checked, examined=0/kept=0/skipped=0 would
    pass it. These assertions are what make the test fail on a real miscount.
    """
    wiki = make_wiki(_mixed_corpus())
    result = wiki.fetch_oldest(limit=3, scan_ceiling=10, progress=False)

    assert result.examined == 7
    assert len(result.documents) == 3
    assert dict(result.skipped) == {
        "missing": 1,
        "namespace": 1,
        "redirect": 1,
        "no-revisions": 1,
    }
    # Documents come back sorted by ascending page id.
    assert [d.page_id for d in result.documents] == [3, 6, 7]
    # requested_to is the last id of the batch the run stopped inside,
    # not the number of documents and not the scan ceiling.
    assert result.requested_to == 10


def test_the_invariant_cannot_catch_a_short_response() -> None:
    """The blind spot, written as a passing test so it is not forgotten.

    `examined` counts pages the API *returned*, not ids requested. If
    Fandom ever returns fewer pages than the ids asked for, the missing
    ones are never counted anywhere and the invariant still balances. So a
    green invariant does NOT prove every requested id was accounted for.
    Guarding the asked-for/looked-at gap needs a different assertion, and
    it is unbuilt because whether Fandom short-responds is unmeasured.

    This wiki's API is asked for many ids and answers with exactly two
    articles every time. The invariant passes; the dropped ids are
    invisible to it.
    """
    import httpx

    from shonenchat.fetch import Wiki

    def short_handler(request: httpx.Request) -> httpx.Response:
        pages = [article_page(3, "Alpha"), article_page(6, "Beta")]
        return httpx.Response(200, json={"query": {"pages": pages}})

    client = httpx.Client(transport=httpx.MockTransport(short_handler))
    wiki = Wiki("example.fandom.com", client)
    result = wiki.fetch_oldest(limit=2, scan_ceiling=50, progress=False)

    # Two ids came back; 48 were requested and never accounted anywhere.
    assert result.examined == 2
    # Still balanced, even though 48 requested ids vanished unrecorded.
    assert result.examined == len(result.documents) + sum(result.skipped.values())
