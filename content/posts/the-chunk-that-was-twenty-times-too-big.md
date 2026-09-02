---
title: My chunker broke its own rule on one paragraph
date: 2026-09-02
summary: I gave the chunker one job and one limit. A single 10,000-word paragraph made it return a chunk twenty times too big, and a two-line test is what caught it.
topics: [rag, chunking, testing]
publish: true
---

I am building a search tool over 28 anime and manga wikis. Before you can search text,
you have to cut it into small pieces called chunks. My chunker had one rule: no chunk
larger than 500 words. It cuts on the blank lines between paragraphs, then groups
paragraphs together until the next one would go over the limit.

Then I fed it a wiki article with a single paragraph that was about 10,000 words long,
with no blank line anywhere inside it.

The chunker returned one chunk. Ten thousand words. Twenty times over its own limit.

The reason is obvious once you see it. If the only place you are allowed to cut is a
blank line, and there is no blank line, you cannot cut at all. The rule and the input
disagreed, and the input won.

A test found it before I did. It checked one thing: that no chunk is bigger than the
limit. On that paragraph it failed with `assert 10000 <= 500`, which is about as clear
as a failing test gets.

## The fix

When a single paragraph is over the limit, I stop trying to cut on boundaries that are
not there and use a sliding window instead: 500-word windows that overlap by 50 words.
The 10,000-word paragraph becomes 23 chunks. None of them over 500.

The overlap is the part worth explaining. Without it, a sentence that lands right on a
cut gets split in half, and neither half reads as a whole thought. With a 50-word
overlap, that sentence appears complete in one of the two chunks that share the seam, so
a search for it still finds a chunk where it makes sense.

It is not free. The overlapping words get stored twice, so a heavily windowed document
costs a bit more to store and embed. For this corpus that case is rare, so I wrote the
number down and moved on instead of guessing at a cost I have not measured.

One habit this keeps proving to me: a test is only worth having if it fails when the
code is wrong. This one did, on the exact input I would never have thought to try by
hand.
