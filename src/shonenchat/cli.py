"""Command line entry point for shonenchat."""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from shonenchat.fetch import (
    DEFAULT_LIMIT,
    DEFAULT_SCAN_CEILING,
    USER_AGENT,
    Wiki,
    default_out_path,
    write_jsonl,
)


def fetch_command(args: argparse.Namespace) -> int:
    """Download the oldest articles from one wiki and write them as jsonl."""
    out_path = args.out or default_out_path(args.host)

    # The client is built here, not inside Wiki, so that one connection is
    # reused across every batch and Wiki stays testable without a network.
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        result = Wiki(args.host, client).fetch_oldest(
            limit=args.limit,
            scan_ceiling=args.scan_ceiling,
        )

    write_jsonl(result.documents, out_path)

    # fetch_oldest either returns exactly `limit` documents or raises, and
    # main() rejects --limit below 1, so this cannot be empty today. The
    # guard is here anyway because both of those live somewhere else, and
    # the day fetch_oldest gains a partial-result path this line is a
    # ZeroDivisionError inside a summary print.
    total = sum(len(document.wikitext) for document in result.documents)
    mean = total // len(result.documents) if result.documents else 0
    print(
        f"{result.host}: examined {result.examined} pages "
        f"of ids 1 to {result.requested_to} requested"
    )
    print(f"skipped {dict(result.skipped)}")
    print(f"{len(result.documents)} documents -> {out_path}")
    print(f"{total:,} characters of wikitext, mean {mean:,}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shonenchat",
        description="Search shonen anime and manga wikis, and cite the source of every answer.",
    )
    # required=True so that a bare `shonenchat` prints usage and exits 2,
    # rather than succeeding silently having done nothing.
    subcommands = parser.add_subparsers(dest="command", required=True)

    fetch = subcommands.add_parser(
        "fetch",
        help="download article wikitext from one wiki",
    )
    fetch.add_argument(
        "--host",
        required=True,
        metavar="WIKI",
        help="wiki host, e.g. onepiece.fandom.com",
    )
    fetch.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"how many articles to keep (default: {DEFAULT_LIMIT})",
    )
    fetch.add_argument(
        "--scan-ceiling",
        type=int,
        default=DEFAULT_SCAN_CEILING,
        help=(
            "highest page id to walk before giving up. Most ids hold nothing, "
            f"so this is far above --limit (default: {DEFAULT_SCAN_CEILING})"
        ),
    )
    fetch.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="PATH",
        help="output file (default: data/<wiki>.jsonl)",
    )
    fetch.set_defaults(handler=fetch_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch" and args.limit < 1:
        parser.error("--limit must be at least 1")

    # argparse.Namespace.__getattr__ is typed Any, so `args.handler(args)`
    # is Any and returning it directly is an unchecked claim that main()
    # returns int. The annotated local is where the claim gets made.
    exit_code: int = args.handler(args)
    return exit_code
