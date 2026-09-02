# 0001. Index 28 shonen wikis, and ship to the per-series subreddits

- **Date:** 2026-09-01
- **Status:** Accepted

## Context

The product needs two things chosen together and it cannot change either one cheaply
afterwards: a body of documents to index, and a named group of people to put it in front of
on Day 19. A corpus with no reachable community produces a portfolio piece nobody uses. A
community with no indexable corpus produces nothing to ship.

Four tests, set before looking at any candidate:

1. A real group searches this material today and the search is bad.
2. The group is findable and reachable by me.
3. The documents are free to download and free to index.
4. There are enough of them.

### The corpus

**28 shonen anime and manga Fandom wikis, 65,002 content pages.** Hosts are listed in
`notes/wiki-hosts.txt`. Every count is `query.statistics.articles` from
`action=query&meta=siteinfo&siprop=statistics`, read between 2026-08-21 and 2026-08-23.
That field is **content pages**, not `pages`: the second number counts redirects, talk pages
and file pages, and on One Piece it is 296,546 against 8,114 real articles. Indexing the
larger number would be true and worthless.

Size, measured rather than guessed: mean article **5,402 bytes of wikitext** across 33
random API draws, giving roughly **116,000 chunks at 500 words**. Two known weaknesses in
that estimate, both stated here because they change what the number means: bytes of wikitext
are not words of prose, and the sample weighted every wiki equally when One Piece has 8,114
articles and Demon Slayer has 973.

Licensing: the text is CC-BY-SA and can be indexed and redistributed with attribution.
**The images are fair use with mixed status and must never be served.** That is a hard
constraint on the interface, not a preference.

### The community

**r/anime for announcing, and the per-series subreddits for the actual need.** Evidence,
collected 2026-08-23:

Twenty threads read **consecutively, not cherry-picked**: the first ten posts in `new` on
r/Naruto and the first ten in `new` on r/bleach, taken in order at 07:00, nothing skipped.
**2 of 20 were factual lookups the wiki already answers, and both were asked to humans
anyway.** Both were in r/Naruto. **r/bleach produced zero** — its ten were fanart, merch,
memes, a mod notice and a dub complaint. Separately, twenty-four consecutive posts in `new`
on r/anime were almost all recommendation requests, which no wiki answers.

2 of 20 says the need is real and visible. **It does not say the need is the dominant
activity in these subreddits, and this ADR does not claim that.** What it supports is
r/anime as the place to announce and the per-series subs as the place the need lives.

**Reddit is not the corpus.** Its free Data API is 100 queries a minute, scoped to
non-commercial personal use, and the terms restrict redistribution at scale. Reddit is where
the users and the real queries come from, nothing else.

### The instrument that actually settled it

Reading threads shows that people ask. It does not show that the wiki fails them. So three
real questions taken from those subreddits were answered using only the relevant wiki's own
search, and timed:

| # | Question | Time | Why the wiki search failed |
|---|---|---|---|
| 01 | How many years off Luffy's lifespan | 5 min | spread across several pages |
| 02 | Everything Sasuke has been through | 12 min | spread across several pages, wrong vocabulary |
| 03 | Was Piccolo Gohan's best friend | 10 min | multiple pages, wrong vocabulary |

**Three of three: the answer exists but is not on one page. Two of three: the words the
reader used are not the words the wiki is indexed under.** Full write-ups, including the
search terms tried in order, are in `notes/community-threads.md`.

Those are two different failures and they name two different pieces of the system.
*Spread across pages* is a synthesis failure — wiki search returns documents, the reader
wanted an answer assembled from several. Better keyword matching does not fix it, which is
why this is retrieval plus generation and not a nicer search box. *Wrong vocabulary* is a
lexical failure — the reader describes a scene or a relationship, the wiki is indexed under
canonical names and technique terms. That is precisely the gap between keyword search and
vector search.

**These two findings are the argument for hybrid retrieval, and they were produced from
evidence before any retrieval code was written.**

The unmet need, in one sentence the community would recognise:

> When you want to check a fact about an anime, the answer is on the wiki, but it is spread
> over five pages and filed under words you would not think to type, so you either spend ten
> minutes hunting or you ask a subreddit and admit you did not know.

## Decision

Index the article wikitext of the 28 Fandom wikis listed in `notes/wiki-hosts.txt`, 65,002
content pages, and ship to r/anime and the per-series subreddits.

Ingest **wikitext**, not rendered HTML. Sourced sentences on these wikis carry a
`{{Qref|chap=|page=|ep=}}` template, so chapter, page and episode numbers are already
machine-readable and already attached to a specific claim. Rendering to HTML throws that
away. It means a citation layer exists in the source material, and it makes spoiler-bounded
retrieval possible along two axes, because `chap` and `ep` do not convert into one another.

## Alternatives considered

### arXiv cs.CL, 44,000 papers

Rejected. It was the previous corpus and it was chosen for being easy to parse. No community
was ever named for it, and test 1 was never tested: nobody was identified who searches
arXiv abstracts today and finds the search bad. That is how a plan reaches Day 19 with
nothing to send and nobody to send it to.

### r/selfhosted

Rejected on **test 2, reachability**, not on size. Two threads were read and test 1 passed
on the evidence: in both cases the answer was already published — in the project's own docs
in one case, a GitHub issue in the other — and the person could not find it. It failed
because I have no connection to that community, and Days 19 to 22 require belonging to one.
The corpus *shape* it revealed carried over and is why this ADR looks the way it does: the
facts live in wikis and docs, the questions live in the community.

### One Piece alone, 8,114 content pages

Rejected. The original reason recorded on 2026-08-21 was size, against a then-live target of
1,000,000 chunks. **That target has since been released, so the size argument no longer
stands and is not what this decision rests on.** What survives is reachability: a
single-series product has one subreddit to reach, and Gate 2 asks for ten real users who
were not asked as a favour. Twenty-eight series is twenty-eight communities to draw from.

### Yu-Gi-Oh, 141,218 content pages

Rejected despite being more than twice the size of everything else combined. The pages are
card stat blocks, not prose: a different document shape, a different chunking problem, and a
different kind of question. Including it would have more than tripled the corpus and made
every retrieval number harder to interpret. **This is the clearest case in the whole decision
of corpus size not being a score.**

## Consequences

### Good

- Both parts of test 1 are backed by timed evidence rather than an assumption.
- The `Qref` template means citations and spoiler bounds are available from day one, which
  is unusual and is a real differentiator to talk about.
- 28 independent wikis means the ingestion pipeline has to be host-parameterised from the
  start, which is why `fetch.py` already takes `--host`.
- The scope stays describable in one sentence: "shonen battle manga and anime".

### Bad

- Someone will ask about a series that is not in the 28 and get nothing useful. That is a
  visible, user-facing hole from the first day it is public.
- 28 wikis is 28 different templates, infobox conventions and editorial habits. One parser
  will not fit all of them.
- The corpus measures at roughly 116,000 chunks, not a million, so the Day 33 to 37 scale
  work has to be honest about which figures are real and which come from a synthetic
  benchmark.
- The two spoiler axes, `chap` and `ep`, do not convert, so spoiler bounding is a position
  with two coordinates rather than a toggle. **A refusal is itself a spoiler**, and this is
  a post-retrieval filter, which is the Day 37 recall-collapse problem appearing inside my
  own product.

### Unmeasured, and it matters

What fraction of the text sits inside or near a `Qref` is not known. Everything the citation
and spoiler story depends on rests on that number, and it has not been measured.

## What would make us revisit this

- The `Qref` coverage measurement comes back low enough that citations cannot be attached to
  most claims.
- Ten real users are not reachable through these subreddits by Gate 2.
- Fandom's terms or API access change in a way that stops redistribution of the text.

**Adding another shonen wiki is not a revisit.** The pipeline is host-parameterised and the
host list is data. Moving off shonen, off Fandom, or off Reddit is a revisit.
