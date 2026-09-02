"""Cut extracted prose into chunks that carry where they came from.

A chunk is the unit everything downstream retrieves, embeds and scores, so
two things matter about it from Day 3: it is a sensible size, and it knows
its source. A chunk that has lost its page id can be embedded but never
cited, and an answer this project cannot cite is the one thing the whole
product exists to avoid.

Size is counted in whitespace-separated words, not real tokens. A real
tokeniser (tiktoken) counts what an embedding model actually sees, and a
word is roughly 1.3 of those, so these counts are wrong by a predictable
factor. That is a deliberate Day 3 shortcut: the dependency and the exact
budget belong to Day 13 when the embedder is chosen. The word count is
consistent enough to group paragraphs sensibly today, which is all the
chunker needs to do.

Cutting happens on paragraph boundaries, the blank lines the extractor was
careful to keep. Paragraphs are grouped greedily up to `max_tokens`, and a
group closes once it passes `min_tokens` so chunks do not come out tiny.

The one case a paragraph boundary cannot handle is a single paragraph
longer than `max_tokens`: there is no boundary inside it. That paragraph is
cut with an overlapping sliding window instead (see `_sliding_windows`), so
every chunk still obeys the size contract and a sentence sitting on a cut
still appears whole in one of the two chunks that share the overlap. The
cost is that the overlapped words are embedded twice; the overlap size is a
Day 13 tuning knob, measured against recall then, not guessed at now.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MIN_TOKENS = 300
DEFAULT_MAX_TOKENS = 500
# Words shared between two windows of an oversized paragraph. 10% of the
# window. Small enough that the duplication cost is minor, large enough
# that a cut sentence survives in one side. Tuned on Day 13 against recall.
DEFAULT_OVERLAP_TOKENS = 50

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of one document.

    Frozen for the same reason `Document` is: a chunk is a record of how a
    document was cut, and the embedder downstream keys off it. `index` is
    the chunk's position within its document, so a document can be
    reassembled in order and two chunks from different documents never
    collide on identity.
    """

    page_id: int
    wiki_host: str
    index: int
    text: str
    token_count: int


def count_tokens(text: str) -> int:
    """Words, by whitespace. The deliberate stand-in for real tokens."""
    return len(text.split())


def split_paragraphs(text: str) -> list[str]:
    """Non-empty paragraphs, split on blank lines, each stripped."""
    parts = _PARAGRAPH_BREAK.split(text)
    return [p.strip() for p in parts if p.strip()]


def _sliding_windows(words: list[str], max_tokens: int, overlap: int) -> list[str]:
    """Overlapping windows over one oversized paragraph's words.

    Window is `max_tokens` words; the window then advances by
    `max_tokens - overlap`, so consecutive windows share `overlap` words.
    `stride` is floored at 1 so an overlap >= max_tokens cannot loop
    forever, and the last window is whatever remains, always <= max_tokens.
    """
    stride = max(1, max_tokens - overlap)
    windows: list[str] = []
    start = 0
    while start < len(words):
        windows.append(" ".join(words[start : start + max_tokens]))
        if start + max_tokens >= len(words):
            break
        start += stride
    return windows


def chunk_document(
    text: str,
    *,
    page_id: int,
    wiki_host: str,
    min_tokens: int = DEFAULT_MIN_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Group paragraphs into chunks of roughly min..max tokens.

    Greedy: paragraphs accumulate into the current chunk until adding the
    next one would pass `max_tokens`, at which point the current chunk is
    closed and the next starts a new one. A chunk is also closed as soon
    as it passes `min_tokens`, so a long document does not become one
    chunk that happens to fit.

    A paragraph that on its own exceeds `max_tokens` cannot be grouped: it
    is flushed on its own with an overlapping sliding-window split, one
    chunk per window, so the size contract holds even where no paragraph
    boundary does. Normal paragraph groups are NOT overlapped; they cut on
    real boundaries where overlap buys little, and general inter-chunk
    overlap is a Day 13 decision.
    """
    # overlap must be a real fraction of the window. At overlap == max the
    # window would advance one word at a time (stride is floored at 1 to
    # stop an outright infinite loop), producing thousands of near-identical
    # windows: it terminates, but the output is garbage. Reject it here
    # rather than let a bad config degrade silently. Found in Day 3 review.
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError(
            f"overlap_tokens must be in [0, max_tokens); "
            f"got {overlap_tokens} with max_tokens={max_tokens}"
        )

    paragraphs = split_paragraphs(text)
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    index = 0

    def emit(body: str) -> None:
        nonlocal index
        chunks.append(
            Chunk(
                page_id=page_id,
                wiki_host=wiki_host,
                index=index,
                text=body,
                token_count=count_tokens(body),
            )
        )
        index += 1

    def close() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        emit("\n\n".join(current))
        current = []
        current_tokens = 0

    for paragraph in paragraphs:
        tokens = count_tokens(paragraph)

        if tokens > max_tokens:
            # No boundary inside it. Flush what is buffered, then window it.
            close()
            for window in _sliding_windows(paragraph.split(), max_tokens, overlap_tokens):
                emit(window)
            continue

        if current and current_tokens + tokens > max_tokens:
            close()
        current.append(paragraph)
        current_tokens += tokens
        if current_tokens >= min_tokens:
            close()

    close()
    return chunks
