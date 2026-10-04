# Acceptance criteria — FitFindr

Five criteria that say what "working" means for this agent, written in unit 3
**before** any results existed.

An acceptance criterion names a target: a number, a count, a rate, or something
a person could plainly observe. *"The agent handles errors"* is an opinion.
*"When search returns nothing, the agent stops before calling the second tool,
in 5 of 5 tries"* is a criterion.

Under each one, write a sentence or two on **why that target** and not a
stricter one. A reason that says something about your tools, your loop, or the
data earns credit; *"80% seemed reasonable"* does not.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

**Two are written for you. You write three.**

---

## 1. A matching query completes all three tools

Given a query that matches at least one listing, the agent completes all three
tool calls and returns a fit card — in at least 4 of 5 tries.

**Why this target:** For a fixed query my search is deterministic (regex
parse, keyword scoring, sorted with a tie-break), so it can't match on one try
and miss on the next. What can fail is one of the two live model calls: every
run makes two of them on a free tier capped at 15 a minute, and the adapter
gives up after 5 rate-limit retries. One network or quota hiccup in five tries
isn't a bug in my agent. Two would mean something in my loop is fragile, so I
didn't go lower than 4.

**How to check:** Run `python app.py ask 'vintage graphic tee under $30'` five
times (single quotes). A try passes when it prints a `Found:` line and a
non-empty `Fit card:` line, which only happens after `search_listings`,
`suggest_outfit` and `create_fit_card` have all run. In code,
`session["error"]` is None and `session["fit_card"]` is a non-empty string.

---

## 2. An impossible query stops before the second tool

Given a query that matches no listings, the agent stops before calling
`suggest_outfit` and returns a message naming what to change — 5 of 5 tries.

**Why this target:** Nothing on this path calls the model. The parse is
regex, the search is local, and the stop message is built by re-running the
local search with each filter dropped. Same input, same output, every time.
So any miss here is a bug in my branch, not bad luck, and accepting 4 of 5
would mean accepting a bug I already know about.

**How to check:** Run `python app.py ask 'designer ballgown size XXS under $5'`
five times. A try passes when `session["fit_card"]` and
`session["outfit_suggestion"]` are both None, `session["tool_log"]` has no
`suggest_outfit` entry, and the printed message names at least one specific
filter to change (the price, the size, or the words) with a number or a word
from the data, not just "no results".

---

## 3. The item search picked is the item the other tools received

For each of the 5 matching queries listed under `python app.py examples`,
`session["selected_item"]["id"]` equals `session["search_results"][0]["id"]`,
and the `item_id` that `session["tool_log"]` records for `suggest_outfit` and
for `create_fit_card` is that same id, in 5 of 5 tries (one run of each query is
one try).

**Why this target:** The item gets from search to the later tools by plain
dictionary reads out of the session, with no model in between, so there's no
randomness to forgive. If even one try styles a different item than the one
the user was shown, the agent is describing the wrong product, and that's
worse than an error. `tool_log` records the id of the argument each tool was
actually called with, not what the session says it should have been, so a
mismatch would show up instead of hiding.

**How to check:** For each query, call
`run_agent(query, get_example_wardrobe())` from `agent.py` and read the
returned session. Each `tool_log` entry is a dict
`{"tool": <tool name>, "item_id": <id or None>}`; find the entries whose
`"tool"` is `"suggest_outfit"` and `"create_fit_card"` and compare their
`item_id` with `session["selected_item"]["id"]`. The five matching queries are
the first five lines of `python app.py examples` (the sixth is the one marked
as matching nothing).

---

## 4. The fit card states the facts and stays caption-sized

Run each of the 5 matching queries listed under `python app.py examples` once
(each run is one try). A try passes when its fit card contains the selected
item's price written with a dollar sign (`$24` and `$24.00` both count),
contains the item's platform name (any capitalization), and is 2 to 4
sentences long, in at least 4 of 5 tries.

**Why this target:** The caption comes from the model at temperature 0.9 with
the cache off, so the wording changes every run, and my prompt can ask for the
price and platform but can't force them. I've seen models drop a detail or
add a fifth sentence. That's why it isn't 5 of 5. I didn't go to 3 of 5
because the prompt states all three rules plainly; if two out of five cards
break them, the problem is my prompt, not chance.

**How to check:** The price and platform are `session["selected_item"]["price"]`
and `session["selected_item"]["platform"]`. Every price in the data is a whole
number of dollars, so for a price of 24.0 the card must contain `$24`
(`$24.00` contains it too). For sentences: a run of one or more `.`, `!` or `?`
followed by a space or the end of the text ends one sentence, so `...` and
`?!` count once and the decimal point in `$24.00` counts zero. Leftover text
after the last ending counts as one more sentence if it has any letters in it.

---

## 5. A price limit is read correctly and never exceeded

For each of these 5 queries: `'vintage graphic tee under $30'`,
`'silk slip dress in midi length under $40'`, `'denim jacket under $50'`,
`'jeans under $35'`, `'sneakers below $25'`, `session["parsed"]["max_price"]`
equals the number in the query, `session["search_results"]` is not empty, and
every listing in it has `price` at most that number, in 5 of 5 tries (one run
of each query is one try).

**Why this target:** This is regex and a comparison, no model. A miss means
the parser read the wrong number (or none, like when PowerShell double quotes
silently eat `$30`) or the filter is wrong, and either one shows a user items
they said they can't afford. The last two queries are there on purpose: the
data has jeans at $36 and $38 and sneakers at $48, so they only pass if the
filter actually removes something. The "not empty" part stops an empty search
from passing by having nothing to check.

**How to check:** Call `run_agent(query, get_example_wardrobe())` for each
query and read the session. `price` and `max_price` are both numbers (floats),
so compare them as numbers: `30` and `30.0` are equal. From a shell, the query
goes in single quotes so the `$` survives.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 4 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath it, like this:

         ## 4. Something about the fit card

         The fit card is different every time.

         **Why this target:** ...

         > **Revised in unit 4:** For 5 different items, the 5 fit cards share
         > no opening sentence.
         >
         > **Why revised:** "different" wasn't checkable — two cards that
         > differed by one word still counted. The new version is something I
         > can actually score.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "I said the empty search stops it 5 of 5 times, but I got 3 of 5,
            so 3 of 5 is more realistic."

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->
