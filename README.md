# ShonenChat

Ask a question about a shonen anime or manga, get an answer, and get a link to the wiki page
every part of that answer came from.

## The problem

When you want to check a fact about an anime, the answer is on the wiki. But it is spread
over several pages and filed under words you would not think to type, so you either spend ten
minutes hunting or you ask a subreddit and admit you did not know.

That is not a guess. Three real questions taken from r/OnePiece, r/Naruto and r/DragonBallZ
were answered using only the relevant wiki's own search, and timed: 5, 12 and 10 minutes.
All three answers existed but were spread across several pages. Two of the three failed
because the words the reader used were not the words the wiki is indexed under. The write-up
is in `docs/decisions/0001-corpus-and-community.md`.

## What it covers

28 shonen anime and manga Fandom wikis, 65,002 content pages. The full host list is in
`notes/wiki-hosts.txt`. Counts come from each wiki's own
`action=query&meta=siteinfo&siprop=statistics`, read between 21 and 23 August 2026.

Yu-Gi-Oh is deliberately excluded even though it is larger than everything else combined.
Its pages are card stat blocks rather than prose, which is a different document shape and a
different kind of question.

## Status

Early. The only thing that works today is the fetcher: it downloads article wikitext from
one wiki and writes it to a `.jsonl` file. There is no search, no index and no chat yet.

## How to run

Needs Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:SURYAPRASATHJP/shonenchat.git
cd shonenchat
uv run shonenchat fetch --host onepiece.fandom.com --limit 100
```

That writes `data/onepiece.jsonl` and prints what it kept and what it threw away:

```
onepiece.fandom.com: examined 1717 pages of ids 1 to 1750 requested
skipped {'namespace': 40, 'missing': 1559, 'redirect': 18}
100 documents -> data/onepiece.jsonl
2,978,884 characters of wikitext, mean 29,788
```

Most page ids hold nothing. On One Piece, about 17 ids are walked for every article kept.

### `shonenchat fetch`

| Flag | Default | What it does |
|---|---|---|
| `--host` | required | Wiki host, for example `onepiece.fandom.com` |
| `--limit` | 100 | How many articles to keep |
| `--scan-ceiling` | 2000 | Highest page id to walk before giving up. Far above `--limit`, because most ids hold nothing |
| `--out` | `data/<wiki>.jsonl` | Where to write |

Articles are fetched oldest first, by ascending page id. Page ids are assigned in creation
order and never move, so a run can be resumed at a known point. Sorting by title cannot,
because a new page beginning with "A" shifts everything after it.

## Licence and attribution

Wiki text is CC-BY-SA and is indexed and shown with attribution and a link back to the source
page. **Images are not served.** Their licence status on these wikis is mixed fair use and
this project does not redistribute them.
