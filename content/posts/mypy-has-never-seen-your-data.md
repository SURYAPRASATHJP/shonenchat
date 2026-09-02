---
title: The checker said my code was clean. It had never seen my data.
date: 2026-09-01
summary: I turned on a tool that finds mistakes in code. It found ten and then went quiet, and I nearly mistook that silence for proof that everything was fine.
topics: [types, pydantic, ingestion]
publish: true
---

I am building a search tool over 28 anime and manga wikis. It downloads articles, and
everything it downloads comes from someone else's server, which means I cannot assume any
of it is what I expect. Yesterday I turned on a tool that checks code for mistakes, and
learning what it does *not* do was the most useful thing I did all day.

## Two different kinds of checking

Think of a paper form.

One kind of checking asks: **does the form have the right boxes on it?** Is there a space
for a name, is the date box actually a date box. You can do that with a blank form, in an
empty room, before anyone has filled one in.

The other kind asks: **is what someone wrote in the boxes any good?** Did they leave the
name blank. Did they write "banana" where the date goes. You cannot check that without a
filled-in form in your hand.

The tool I turned on, called mypy, only does the first kind. It reads my code and reports
mistakes before the program is ever run. At the moment it runs, no article has been
downloaded and no data exists for it to look at.

It found ten mistakes. I fixed all ten and it went green. Nothing about the articles
arriving from the internet had been checked in any way, and if I had stopped there I would
have shipped a program with a clean report and an unguarded front door.

## The second check

So I added the second kind, a library called pydantic, which runs on the real data as it
arrives. One rule at the entrance: an article either has the shape I expect, or it is
rejected and I am told why. There is no third outcome and nothing gets past it half-checked.

I made it strict on purpose. If a wiki sends me a field I have never seen before, the
program stops and complains, rather than quietly ignoring it. A surprise like that does not
mean the data is broken. It means my understanding of it has gone out of date, and I would
rather find that out immediately than three weeks later.

## The trap I nearly walked into

At one point the checker complained about something that was not actually wrong. I had two
ways to silence it: fix the tool's understanding, or weaken my own rule until it stopped
complaining.

The second one is easier and it makes the report green. It also makes the program worse.
**A clean report is only worth something if you did not get it by lowering the bar**, and
that is true well beyond programming.

## The numbers

I then downloaded 1,000 articles from the One Piece wiki. To get them, the program had to
look at 5,766 pages, because most pages on an old wiki are deleted, are redirects, or are
not articles at all.

One number surprised me. The oldest block of pages needed **17.5 tries per usable article**.
The next block needed **4.5**. Same wiki, same program, one run, and the success rate
changed by nearly four times depending on where I looked.

That is the lesson I actually want to keep. If I had measured only the first block and
stopped, I would have had a confident, precise, badly wrong picture of the whole thing.
