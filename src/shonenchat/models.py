"""The shapes this system is willing to trust.

A type hint is a claim about the code, checked before anything runs. It
never sees a byte that came off the network. `response.json()` is typed
`Any`, and `Any` means "stop checking", so from that call to the file on
disk nothing was verified at all.

This module is where that stops. Everything above it is untrusted input
in a `dict[str, Any]`. Everything below it holds a `Document` that either
has the shape declared here or was never constructed.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# Bump this whenever a change to `Document` makes an already-written row
# mean something different: a field removed, renamed, retyped, or given
# a new meaning. Do NOT bump it for a new optional field, because an old
# row is still a correct row under the new model.
#
# The number is on every row rather than in a file header. A header
# would be read once and would break the one-Document-per-line contract
# that lets two runs be concatenated with `cat`, and a row that leaves
# its file stops being self-describing the moment it does.
SCHEMA_VERSION = 1


class SchemaVersionError(RuntimeError):
    """A stored row was written by a different version of `Document`."""


class Document(BaseModel):
    """One wiki article, as this project stores it.

    `extra="forbid"` guards the *internal* boundary, not the external one.
    Nothing from Fandom can reach this constructor: `to_document` plucks
    seven named fields by hand and the payload never passes through. If
    Fandom adds `lastrevid` tomorrow, every fetch still succeeds and this
    setting never fires. **It is not upstream-drift detection and an
    earlier version of this docstring claimed it was.**

    What it does catch is us. The day someone passes `Document(...,
    is_locked=True)` without declaring `is_locked` here, the mismatch is
    an error instead of a silently dropped field.

    Upstream drift is therefore *unguarded*, deliberately and for now.
    Being liberal in what we accept is what stops a harmless new key
    waking anyone at 3 a.m.; the cost is that a genuinely useful new key,
    an `is_deleted` flag say, arrives and we never notice the API just
    offered us a filter. Revisit with an API-page model when a second source lands.

    `frozen=True` because a document is a record of what a wiki returned
    at `fetched_at`. Mutating one after the fact makes the timestamp a
    lie, and the chunker and the embedder downstream both key off it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # First field so it is the first key on every line and `head -c 30`
    # on the file answers "what wrote this".
    #
    # A default, not a required argument: `to_document` must not be able
    # to stamp a row with a version other than the one the running code
    # implements, and passing it by hand at the call site is exactly how
    # that happens.
    schema_version: int = Field(default=SCHEMA_VERSION, gt=0)

    # gt=0 rather than plain int: MediaWiki page and revision ids start at
    # 1, so 0 or a negative is a parsing mistake on our side, not data.
    page_id: int = Field(gt=0)
    revision_id: int = Field(gt=0)

    title: str = Field(min_length=1)

    # Page ids are only unique within one wiki. Across 28 of them the id
    # alone stops being an identity, so the host is part of the key.
    wiki_host: str = Field(min_length=1)

    # Deliberately unconstrained. An article whose wikitext is empty is a
    # real possibility on a wiki and it is not a malformed document, it is
    # a worthless one. That is a filter question for `rejection_reason`,
    # not a validation question, and the two are different jobs.
    # NOT YET: nothing currently rejects an empty article.
    wikitext: str

    url: HttpUrl
    fetched_at: datetime

    @field_validator("title", "wiki_host")
    @classmethod
    def not_only_whitespace(cls, value: str) -> str:
        """`min_length=1` accepts " ". This does not.

        The distinction is the whole reason field validators exist:
        a constraint expresses what the type cannot, and a validator
        expresses what the constraint cannot.
        """
        if not value.strip():
            raise ValueError("must not be blank or whitespace only")
        return value
