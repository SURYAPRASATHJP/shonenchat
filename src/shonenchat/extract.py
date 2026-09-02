"""Turn wikitext into plain prose the chunker can cut.

This is the crude first pass, and it is meant to be. Wikitext is not a
regular language and a regex stripper cannot parse it correctly; what it
can do is remove the markup that would otherwise become noise in a chunk,
well enough that the paragraphs underneath survive. Day 11 is where 200 of
these outputs are read by hand and the specific things this gets wrong are
written down. Until then, every shortcut here is deliberate and named.

What it removes: templates, tables, HTML comments, ref tags, file and
category links, and the wiki markup for links, bold and italic. What it
keeps: the human-readable text those constructs wrapped, and the blank
lines between paragraphs, because those blank lines are the only thing the
chunker has to cut on.
"""

from __future__ import annotations

import re

# HTML comments first: they can wrap anything, including unbalanced braces
# that would otherwise confuse the template pass.
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# <ref>...</ref> and self-closing <ref/>, plus any other tag. Citations
# are not prose and a stray <br> is not a paragraph break.
_REF_BLOCK = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

# File, image and category links are whole-line noise, not inline text, so
# they are removed entirely rather than reduced to their display text.
_MEDIA_LINK = re.compile(r"\[\[(?:File|Image|Category):[^\]]*\]\]", re.IGNORECASE)


def _strip_braced(text: str, open_str: str, close_str: str) -> str:
    """Remove every open..close span, innermost first, so nesting is safe.

    A single regex cannot match balanced nested braces. Templates nest
    ({{a|{{b}}}}), so the loop removes the innermost span (one with no
    opener inside it) and repeats until none remain. Bounded by the number
    of openers in the text, so it always terminates.
    """
    pattern = re.compile(
        re.escape(open_str) + r"(?:(?!" + re.escape(open_str) + r").)*?" + re.escape(close_str),
        re.DOTALL,
    )
    while True:
        new_text = pattern.sub("", text)
        if new_text == text:
            return new_text
        text = new_text


def _resolve_links(text: str) -> str:
    """[[target|shown]] -> shown, [[target]] -> target."""

    def _one(match: re.Match[str]) -> str:
        inner = match.group(1)
        return inner.split("|")[-1] if "|" in inner else inner

    return re.sub(r"\[\[([^\[\]]+)\]\]", _one, text)


def _resolve_external_links(text: str) -> str:
    """[https://x display text] -> display text, [https://x] -> removed."""
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    return re.sub(r"\[https?://\S+\]", "", text)


def extract_text(wikitext: str) -> str:
    """Wikitext in, plain prose out, with paragraph breaks preserved.

    Order matters: comments before templates (a comment can hide a brace),
    templates and tables before links (a template can contain a link we do
    not want), media links before ordinary links (a File link is a link).
    """
    text = _COMMENT.sub("", wikitext)
    text = _REF_BLOCK.sub("", text)
    text = _strip_braced(text, "{{", "}}")
    text = _strip_braced(text, "{|", "|}")
    text = _MEDIA_LINK.sub("", text)
    text = _resolve_links(text)
    text = _resolve_external_links(text)
    text = _TAG.sub("", text)

    # '''bold''' and ''italic'': remove the quote runs, keep the words.
    text = re.sub(r"'{2,}", "", text)

    # Heading markers == like this ==: keep the words as their own line.
    text = re.sub(r"^=+\s*(.*?)\s*=+\s*$", r"\1", text, flags=re.MULTILINE)

    # Normalise whitespace without destroying paragraph breaks. A run of
    # two or more newlines is one paragraph break; a single newline inside
    # a paragraph becomes a space; trailing spaces on a line go.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
