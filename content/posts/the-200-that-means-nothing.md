---
title: The 200 that means nothing
date: 2026-09-01
summary: Two APIs in one week returned a successful response to a request that had already failed. Neither error path ever ran.
topics: [ingestion, apis, mediawiki]
publish: true
---

Fandom's MediaWiki API returned HTTP 200 for every request I made. `batchcomplete: true`.
A valid `pages` array with the right page ids in it. It also returned no article text at
all, and it would have kept doing that for all 65,002 pages I was about to ask for.

## The parameter that is not there

I was using `prop=extracts`, which is how you get the plain-text lead of an article. It is
part of the TextExtracts extension. Fandom does not run TextExtracts.

MediaWiki's response to a `prop` value it does not recognise is not a 400. It is a 200,
with the pages you asked for, minus the field you asked about, plus a `warnings` key you
have to already be looking for:

```json
{
  "batchcomplete": true,
  "warnings": { "main": { "*": "Unrecognized value for parameter \"prop\"..." } },
  "query": { "pages": [ { "pageid": 1444, "ns": 0, "title": "Monkey D. Luffy" } ] }
}
```

Every assertion I would naturally have written passes. Status is 200. `query` exists.
`pages` is a non-empty list. The titles are correct. The only thing that is wrong is that
the field carrying the entire point of the request is silently absent.

Article text on Fandom comes from `prop=revisions&rvslots=*&rvprop=content` instead.

## The same shape, four days earlier

This is the second time in a week I have hit it.

The arXiv API documents an `http://` endpoint. On `http://`, a valid query and a malformed
one both return **301**, because the request is redirected before it ever reaches the
search logic. Move to `https://` and the behaviour separates: a valid query is 200 and a
malformed one is 400. The 400 body is an Atom feed with `totalResults` of **1** and a
single `<entry>` whose title is "Error".

I had written an error check for that: zero results and no entry tag. It is inverted on
both halves. A broken query returns one result and does have an entry, so the check passes
and a document titled "Error" gets written into the corpus as though it were a paper.

## What these have in common

In both cases the transport succeeded, so the error path never ran. There was no exception
to catch and no status code to branch on. The response was well-formed, correctly shaped,
and empty of the thing I came for.

The check I now write first, before any client code, is not "did this fail". It is
**"does the response contain the field I asked for"**, asserted positively, and an
unexpected `warnings` key treated as a failure rather than a log line.

The general version, which is the part I want to remember: read the error response by hand
before you write the client. Not the success response, the error one. You will guess the
success shape correctly most of the time. Nobody guesses the failure shape.

## One number from the same run

While proving this out, I walked the first 1,750 page ids on the One Piece wiki to collect
100 articles.

```
skipped {'missing': 1559, 'namespace': 40, 'redirect': 18}
100 documents, 2,978,884 characters of wikitext
```

**1,559 of the first 1,750 ids hold nothing.** About 17 ids walked per article kept. I had
predicted that non-article namespaces would dominate, on the reasoning that a wiki is
mostly file and template pages. They were 40. It is deletion: the delete log runs from
2006 to last month, and the ids of deleted pages are never reused.

Which also means the 100 articles I got are not a sample. They are the oldest surviving
pages on a twenty-year-old wiki, so they are the central ones, and they average 29,788
characters against a corpus mean of 5,402. Nothing I measure on that batch is a corpus
number.
