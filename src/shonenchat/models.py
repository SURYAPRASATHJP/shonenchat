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


class Document(BaseModel):
    """One wiki article, as this project stores it.

    `extra="forbid"` because every field is passed by hand from a known
    API shape. The default, silently dropping unknown keys, is right at a
    boundary where the sender owns the schema. It is wrong here: a key
    arriving that we did not model means our reading of the API changed
    under us, and that should be loud.

    `frozen=True` because a document is a record of what a wiki returned
    at `fetched_at`. Mutating one after the fact makes the timestamp a
    lie, and the chunker and the embedder downstream both key off it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

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
    # NOT IMPLEMENTED TODAY: nothing currently rejects an empty article.
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
