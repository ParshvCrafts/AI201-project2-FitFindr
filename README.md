# FitFindr

> ### 👋 Start here
>
> **New to this repo? Read [RUNNING.md](RUNNING.md) first** — setup, every
> command, and what to do when something breaks.
>
> Once `python test.py` passes:
>
> ```bash
> python app.py listings --full -n 6      # read the data (Milestone 1)
> python app.py fields                    # what you can filter on
> python app.py ask 'vintage graphic tee under $30'
> ```
>
> All three tools are stubs, so that last command will do nothing useful yet.
> That's the starting position.
>
> **The rest of this file is your submission.** Fill it in as you go.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     HOW TO USE THIS FILE

     This is your submission. Fill each section in as you finish the milestone
     it belongs to — don't leave it all to the end.

     Unit 3 asks for the first five sections. Unit 4 adds the five below them.
     Leave the unit 4 sections alone until then; they're here so you know
     what's coming.

     Everything is pasted as TEXT. No screenshots, no images, no video links.
     A typed block of output gets full credit; a picture of the same output
     gets none.
     ───────────────────────────────────────────────────────────────────────── -->

<!-- ═══════════════════════ UNIT 3 — THE BUILD ═══════════════════════ -->

## What This Does

You type what you're hunting for in plain words, like
`'vintage graphic tee under $30'` or `'platform sneakers size 8'`, and FitFindr
searches 40 secondhand listings from Depop, ThredUp and Poshmark for the best
match within your size and budget. For the item it picks, you get how its
price compares to similar listings, one or two outfits built from clothes you
already own, and a short caption you could actually post. If nothing fits, it
stops before styling anything and tells you which part of your search to
change (the words, the size, or the budget), with real numbers from the
listings.


---

## Tool Inventory

<!-- Four lines per tool. This is worth 2 points and it's the single most
     common place students lose them.

     "Returns a list" earns NOTHING. The description has to say what is IN
     the list.

     The empty case isn't optional either — it's the thing your loop branches
     on, and if you don't decide it here you'll discover it as a crash in
     Milestone 5. -->

### What the data holds

I read six listings end to end (`python app.py listings --full -n 6`) before
writing any of this, because the search can only filter on fields that exist.

- **A listing has 11 fields:** `id`, `title`, `description`, `category`,
  `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list),
  `brand` (str or None), `platform`.
- **40 listings.** Categories are tops, bottoms, outerwear, shoes, accessories.
  Platforms are depop, thredUp, poshmark. Prices run from $12 to $75.
- **`brand` is None on 32 of 40.** Nothing I write can assume a brand exists.
- **Sizes are messy.** There are 22 different spellings: `M`, `S/M`, `M/L`,
  `L/XL`, `XL (oversized)`, `W30 L30`, `W28`, `US 8`, `US 8.5`, `One Size`,
  `One Size (adjustable)`. A plain substring test breaks on these (`"l" in "xl"`
  is True, so is `"s" in "us 9"`).
- **`vintage` is a tag on 29 of 40 listings.** If one shared word were enough
  to count as a match, almost any query with "vintage" in it would return
  something, even when the actual item doesn't exist.
- **A wardrobe** is `{"items": [...]}`. Each item has `id`, `name`,
  `category`, `colors`, `style_tags`, and optional `notes`. An empty wardrobe
  is `{"items": []}`, same shape, nothing in the list.

### `search_listings`

- **What it does:** Filters the 40 listings by price and size, keeps the ones
  that match more than half of the description's words, and returns them best
  match first. No model call.
- **Inputs:** `description` (str), `size` (str or None, None skips the size
  filter), `max_price` (float or None, inclusive, None skips the price filter).
- **Returns:** A `list[dict]` of at most 10 listing dicts
  (`config.SEARCH_RESULT_LIMIT`), each the unchanged record from
  `data/listings.json` with all 11 fields: `id`, `title`, `description`,
  `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`,
  `platform`. Sorted by score (highest first), then price (cheapest first),
  then `id`, so the same input always gives the same order.
- **When it has nothing:** `[]`, an empty list. Never None, never an
  exception. That covers no keyword match, filters that remove everything, and
  a description with no real words in it.

How matching works, so someone else could rebuild it:

- **Words.** Lowercase, split on anything that isn't a letter or digit, drop
  one-letter pieces and filler words (`a`, `for`, `looking`, `size`, `under`
  ...), and cut a trailing `s` off words longer than three letters that don't
  end in `ss` (`jeans` becomes `jean`, `dress` stays `dress`). Listing text
  goes through the same steps, so both sides agree.
- **Majority rule.** A listing is kept only if it matches *more than half* of
  the query's words. With 2 words both must match. With 3, two must. I picked
  this over "any word" because of the `vintage` problem above: "vintage
  ballgown" should find nothing, not a pair of Levi's.
- **Score.** Each matched word counts once, at the weight of the best field it
  appears in: title 3, style tag / category / brand 2, color / description 1.
- **Size rule.** The listing's size is split into tokens on `/`, spaces, and
  parentheses. A letter size (`XS` to `XXXL`) has to equal one of the tokens,
  so `M` matches `S/M` and `M/L` but `L` never matches `XL`. A number compares
  as a number against shoe sizes and waist sizes: `8` matches `US 8` but not
  `US 8.5`, and `30` matches `W30 L30` (the `L30` is inseam, so it's ignored).
  `W30` only matches waist 30. Any listing whose size contains `One Size`
  matches every size request, because a belt or a bucket hat fits anyone.
- **Price rule.** `price <= max_price`.

### `suggest_outfit`

- **What it does:** Asks the model for one or two outfits built around the
  new item. With a wardrobe, the outfits use pieces the user owns, named the
  way the wardrobe names them. With an empty wardrobe, it asks for general
  styling ideas instead.
- **Inputs:** `new_item` (dict, a listing dict from `search_listings`),
  `wardrobe` (dict, `{"items": [...]}`, where `items` may be empty).
- **Returns:** A non-empty `str` of outfit suggestions, plain text, a few short
  lines.
- **When it has nothing:**
  - Empty wardrobe (`items` is `[]`, missing, or the wardrobe is None): still
    returns a non-empty string of general styling advice. Not an error.
  - `new_item` is None or `{}`: returns the fixed string
    `"No item was given, so there is nothing to style."` without calling the
    model.
  - The model replies with nothing: returns a short fallback built from the
    item's own fields, so the string is never empty.
  - The model can't be reached: raises `ModelUnavailable` from `generate.py`.
    The tool doesn't hide that; handling it in the loop is a unit 4 job.

### `create_fit_card`

- **What it does:** Asks the model for a short caption someone would actually
  post about the find, mentioning the price and the platform once each.
- **Inputs:** `outfit` (str, the text `suggest_outfit` returned), `new_item`
  (dict, the same listing dict).
- **Returns:** A `str` caption, two to four sentences, no hashtags. The price
  is written like `$24` (or `$24.50` when there are cents). Calls the model
  with the cache turned off (`cache=False`) so the same item gives a different
  caption each run. `TEMPERATURE` stays at 0.9.
- **When it has nothing:**
  - `outfit` is empty, whitespace, or not a string: returns the fixed string
    `"Can't write a fit card without an outfit suggestion."`, no model call.
  - `new_item` is None or `{}`: returns
    `"Can't write a fit card without an item."`, no model call.
  - The model replies with nothing: returns a two-sentence fallback caption
    built from the title, price, and platform.

### `compare_price` (stretch, fourth tool)

- **What it does:** Compares the chosen item's price with every other listing
  in the same category. No model call.
- **Inputs:** `item` (dict, a listing dict), `listings` (list[dict] or None,
  None means load all listings).
- **Returns:** A `dict` with `category` (str), `compared_with` (int, how many
  other listings in that category), `median_price` (float), `cheaper_than`
  (int, how many of those cost more than the item), `verdict` (`"below"`,
  `"at"`, or `"above"` the median), and `summary` (one readable sentence, e.g.
  `"$24 is below the $25 median for 14 other tops. It's cheaper than 8 of
  them."`).
- **When it has nothing:** No other listings in the category (or `item` is
  None / `{}`): the same dict shape with `compared_with` 0, `median_price`
  None, `cheaper_than` 0, `verdict` None, and a `summary` saying there was
  nothing to compare with. Never raises for that.

---

## Planning Loop

<!-- Your branch rule, stated as a rule — the condition AND both paths — plus
     the file and function that holds it.

     Like this:
       "If search_listings returns an empty list, put a message in the session
        and stop. Otherwise take the first result and go to suggest_outfit."
        — agent.py::run_agent

     The grader checks your code against what you claim here, so the file and
     function have to be real. -->

**Branch rule:** If `search_listings` returns an empty list, put a message in
`session["error"]` that says which filter to change (built by re-running the
search with each filter dropped, see below) and stop. `suggest_outfit` and
`create_fit_card` are never called. Otherwise take the first result as
`session["selected_item"]` and go on to `compare_price`, then
`suggest_outfit`, then `create_fit_card`.

**Second branch (stretch):** If the query has no description words left after
the price and size are pulled out (for example just `'under $30'`), put a
message in `session["error"]` asking what kind of item they want and stop
before calling `search_listings` at all. This is a different condition from
the empty search: the empty search means "we looked and nothing fits", this
one means "there was nothing to look for".

**Where it lives:** `agent.py::run_agent`. The stop messages come from
`agent.py::describe_empty_search` and `agent.py::describe_vague_query`.

**How the query is parsed:** Regex, in `agent.py::parse_query`. Price comes
from phrases like `under $30`, `below 30`, `less than $30`, `max $30`,
`up to $30`, `$30 or less`, or a bare `$30`. Size comes from `size M`,
`sz 8`, `size W30`, `in M`, or a standalone `XS` / `XL` / `XXL`. Whatever is
left is the description. I chose regex over asking the model because it's
free, it gives the same answer every time (criterion 2 asks for 5 of 5), and
I can unit test it. The cost is that odd phrasings like "nothing over thirty
bucks" won't be read as a price.

**What the empty-search message says:** It names the filters that were used
and, for each one, what dropping it would do, with real counts. For example:
if the words match listings but none are cheap enough, it says how many match
and what the cheapest one costs. If no listing has the words at all, it says
that and suggests words that do appear in the data.

**What moves through the session, in order:**

1. `query`, `wardrobe` (set by `new_session`)
2. `parsed`: `{"description", "size", "max_price"}` from `parse_query`
3. `search_results`: the list `search_listings` returned
4. `selected_item`: `search_results[0]`
5. `price_check`: the dict `compare_price` returned (stretch)
6. `outfit_suggestion`: read `selected_item` and `wardrobe` back out of the
   session, call `suggest_outfit`, store the string
7. `fit_card`: read `outfit_suggestion` and `selected_item` back out of the
   session, call `create_fit_card`, store the string
8. `tool_log`: every tool call in order, with the `id` of the item each tool
   actually received. This is how criterion 3 checks that the item search
   found is the same one the later tools got.
9. `error`: None on the happy path, the stop message on either branch.

---

## Stretch Features

I'm adding all three stretch features. I wrote them down here before building
any of them.

1. **A fourth tool, `compare_price`.** Tells you whether the item is a good
   price for its category. Spec is in the Tool Inventory above.
2. **A second branch.** A query with no item words stops before the search.
   Rule is in the Planning Loop above.
3. **Style memory.** The wardrobe is saved to `data/my_wardrobe.json` (that
   file is gitignored, it's personal data) and `ask` loads it automatically
   on the next run. Commands:
   - `python app.py wardrobe add 'black wide-leg jeans' --category bottoms --colors black --tags minimal`
   - `python app.py wardrobe show`
   - `python app.py wardrobe remove w_003`
   - `python app.py wardrobe clear` (forgets the saved wardrobe, `ask` goes
     back to the example one)
   - `python app.py ask '...' --keep` saves the item the agent found into the
     wardrobe, so the next outfit can use it.

   `ask` picks a wardrobe in this order: `--empty-wardrobe` if given, then the
   saved wardrobe if the file exists, then the example wardrobe.
   `run_eval.py` and `serve.py` are not affected, they pick their wardrobe
   explicitly.

---

## Sample Run

<!-- Two things go here.

     1. One FULL query and its output, pasted as text.
     2. Your three per-tool terminal tests — the command and what it printed. -->

**One full query**

```
$ python app.py ask 'vintage graphic tee under $30'

  Found:    Vintage Band Tee — Faded Grey — $19.0 on depop
  Price:    $19 is below the $21.50 median for 14 other tops. It's cheaper than 9 of them.

  Outfit:   Outfit 1: Vintage Band Tee — Faded Grey, Baggy straight-leg jeans, dark wash, Black combat boots, Black crossbody bag
Why it works: The boxy tee tucked into high-waisted jeans with chunky boots nails an effortless grunge streetwear look.

Outfit 2: Vintage Band Tee — Faded Grey, Wide-leg khaki trousers, Vintage black denim jacket, Chunky white sneakers
Why it works: Pairing the edgy graphic tee with clean khaki trousers and a cropped jacket creates a cool high-low balance.

  Fit card: Found this perfectly faded grey band tee and I’m obsessed with how it looks thrown on with wide-leg khaki trousers and chunky white sneakers. It’s also super sick dressed down with baggy dark wash jeans and combat boots for that effortless grunge streetwear vibe. Snagged this gem on depop for just $19 and I honestly won't be taking it off. 🎸✨

1 model calls this session, 1 served from cache, 308 prompt + 79 output tokens
```

The session behind that run, printed from `agent.py::run_agent`, shows the
same item id at every step:

```
selected: lst_033 Vintage Band Tee — Faded Grey
first result id: lst_033
tool_log: [{'tool': 'search_listings', 'item_id': None}, {'tool': 'compare_price', 'item_id': 'lst_033'}, {'tool': 'suggest_outfit', 'item_id': 'lst_033'}, {'tool': 'create_fit_card', 'item_id': 'lst_033'}]
```

The same command with a query the data can't match. It stops after the
search, and the usage line shows no model calls, so neither model tool ran:

```
$ python app.py ask 'designer ballgown size XXS under $5'

  Nothing matched "designer ballgown" in size XXS under $5. No listing mentions "designer" or "ballgown". Try a different word for the item, like tee, jeans, jacket, blazer, sneakers or dress. Your filters are too tight as well: no listing costs under $5 (the cheapest is $12), and no listing comes in size XXS, so leave the size out.

0 model calls this session
```

And the second branch, a query with no item in it. It stops before searching:

```
$ python app.py ask 'under $30'

  I couldn't tell what kind of item you want from "under $30". I got a budget of $30, but no item. Add the item itself, for example 'graphic tee under $30' or 'denim jacket size M'.

0 model calls this session
```

Style memory across two runs. The first run keeps what it found, then I add a
pair of jeans by hand, and the next query's outfits use both saved pieces
instead of the example wardrobe. (For this run I pointed `AI201_WARDROBE` at a
scratch file, `fitfindr_keep.json`, so it wouldn't touch my real wardrobe. By
default the file is `data/my_wardrobe.json`.)

```
$ python app.py ask 'platform sneakers size 8' --keep
  ...
  Kept:     saved "Platform Sneakers — White Chunky Sole" to your wardrobe as w_001.
            Started a saved wardrobe at fitfindr_keep.json. From now
            on `ask` uses it instead of the example wardrobe. Add the clothes
            you own with `python app.py wardrobe add`.

$ python app.py wardrobe add 'black wide-leg jeans' --category bottoms --colors black --tags minimal
Saved w_002: black wide-leg jeans (bottoms).

$ python app.py ask 'vintage graphic tee under $30'
(using your saved wardrobe, 2 items)

  Found:    Vintage Band Tee — Faded Grey — $19.0 on depop
  Price:    $19 is below the $21.50 median for 14 other tops. It's cheaper than 9 of them.

  Outfit:   Outfit 1: Vintage Band Tee — Faded Grey, black wide-leg jeans, Platform Sneakers — White Chunky Sole
Why it works: The boxy tee and chunky sneakers nail that effortless grunge streetwear vibe with the sleek black jeans.
  ...
```

**The three tools, tested one at a time**

`search_listings`, a match and then its empty case:

```
$ python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"
[{'id': 'lst_006', 'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'description': 'Vintage-style bootleg tee with faded graphic. Slightly boxy fit. 100% cotton, soft and worn-in.', 'category': 'tops', 'style_tags': ['graphic tee', 'vintage', 'grunge', 'streetwear', 'band tee'], 'size': 'L', 'condition': 'good', 'price': 24.0, 'colors': ['black'], 'brand': None, 'platform': 'depop'}, {'id': 'lst_002', 'title': 'Y2K Baby Tee — Butterfly Print', 'description': 'Super cute early 2000s baby tee with butterfly graphic. Fitted crop length. Tag says medium but fits like a small.', 'category': 'tops', 'style_tags': ['y2k', 'vintage', 'graphic tee', 'cottagecore'], 'size': 'S/M', 'condition': 'excellent', 'price': 18.0, 'colors': ['white', 'pink', 'purple'], 'brand': None, 'platform': 'depop'}, {'id': 'lst_033', 'title': 'Vintage Band Tee — Faded Grey', 'description': 'Faded grey band-style tee with distressed graphic. Crew neck. Fits boxy. Well-loved but no holes or major damage.', 'category': 'tops', 'style_tags': ['vintage', 'grunge', 'band tee', 'graphic tee', 'streetwear'], 'size': 'L', 'condition': 'fair', 'price': 19.0, 'colors': ['grey', 'charcoal'], 'brand': None, 'platform': 'depop'}, {'id': 'lst_017', 'title': 'Mesh Long-Sleeve Top — Black', 'description': 'Sheer black mesh long-sleeve. Great for layering under a graphic tee or over a bralette. Stretchy material, fits true to size.', 'category': 'tops', 'style_tags': ['y2k', 'grunge', 'goth', 'layering'], 'size': 'S/M', 'condition': 'excellent', 'price': 15.0, 'colors': ['black'], 'brand': None, 'platform': 'depop'}]

$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]
```

Four results, all $30 or less, the two with "graphic" and "tee" in the title
first. The mesh top is last because it only matches through its description
("great for layering under a graphic tee"), which is the lowest weight.

`suggest_outfit`, with the example wardrobe and then an empty one:

```
$ python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
Outfit 1
Vintage Levi's 501 Jeans — Medium Wash, White ribbed tank top, Vintage black denim jacket, Black combat boots, Black crossbody bag
Why it works: Double denim creates a timeless look, and the fitted tank balances the slightly cropped jacket.

Outfit 2
Vintage Levi's 501 Jeans — Medium Wash, Oversized grey crewneck sweatshirt, Chunky white sneakers, Brown leather belt, Black crossbody bag
Why it works: Tucking the classic 501s into the belt anchors the huge sweatshirt for an easy streetwear vibe.

$ python -c "from tools import suggest_outfit; from utils.data_loader import get_empty_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_empty_wardrobe()))"
Outfit one
Pieces: oversized white button-down shirt, brown leather belt, white canvas sneakers
Why it works: A crisp shirt contrasts the casual denim for an effortless, classic look.

Outfit two
Pieces: black cropped hoodie, vintage leather jacket, chunky black boots
Why it works: Layering black pieces leans into a cool streetwear vibe and highlights the medium wash.
```

`create_fit_card`, three runs on the same item, then the empty case:

```
$ python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
Nothing beats the broken-in feel of vintage Levi's, and scoring these for just $38 on depop was an absolute win. I’m styling them with crisp white sneakers for that effortlessly cool, everyday streetwear look. Can't wait to wear this combo on repeat all season. 👖👟

$ (same command again)
Just scored these vintage Levi's 501s on depop for only $38 and I am obsessed. The medium wash is chef's kiss and they fit just right. Can't wait to style them with my favorite crisp white sneakers for that effortless everyday look. 👖✨

$ (same command a third time)
I'm officially obsessed with these vintage Levi's I just scored on depop for $38. The medium wash and broken-in knees give them that effortless, I-just-raided-my-cool-uncle's-closet energy. Throwing them on with fresh white sneakers for the ultimate casual weekend fit. 👖✨

$ python -c "from tools import create_fit_card; print(repr(create_fit_card('   ', {'id':'x'})))"
"Can't write a fit card without an outfit suggestion."
```

Three different captions, each with `$38` and `depop` once. They differ
because `create_fit_card` passes `cache=False` and `TEMPERATURE` is 0.9.

**Unit tests.** `python -m unittest discover -s tests` runs the offline test
suite. The model is patched out, so it costs no quota and gives the same
result every time.

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

**Moment 1: attacking my criteria**

- *What I asked for:* I pasted my five criteria into Claude and asked: "For
  each one, tell me exactly how you would test it using only what the
  sentence says. Don't suggest improvements." I also asked it to quote any
  phrase where it had to guess what I meant.
- *What came back:* It could test most of them, but criterion 4 had three
  guesses in it. It couldn't tell if "5 of 5 tries" meant five queries or five
  runs of each query. It didn't know where the price came from. And it didn't
  know how to count `...` or `?!` as sentences. For criterion 3 it didn't know
  what a `tool_log` entry looked like, so it couldn't find the right one.
- *What I changed:* I rewrote criterion 4 so each of the five queries runs
  once and each run is one try. I also added a **How to check** line under all
  five criteria. Those lines name the session fields to read, the shape of a
  `tool_log` entry (`{"tool", "item_id"}`), and an exact sentence-counting
  rule. Criteria 1 and 2 were given to us, so I left their sentences alone and
  only added the check underneath.

**Moment 2: reading my empty-search message cold**

- *What I asked for:* I gave Claude four versions of my empty-search message,
  one per kind of failure, and asked what it would try next after reading
  each one, knowing nothing about the app. I told it to say so if the honest
  answer was "no idea", and not to rewrite them.
- *What came back:* The price-only message and the "vintage ballgown" one were
  clear. For `'platform sneakers size 6 under $20'` it said a person would
  mostly have no idea what to try. "Starting at $48" made it sound like there
  were several listings when there was one. "The size and the budget together
  rule everything out" didn't say whether changing just one would help. It
  also called "nothing in the data" developer-speak, said "Only One Size items
  would fit" was unclear, and pointed out that "drop or swap the word" never
  says what to swap it for.
- *What I changed:* I rewrote `agent.py::describe_empty_search`. The both
  filters case now says "Changing just one filter won't help" and names the
  single closest listing ("size US 8 at $48"). A single match is described as
  one listing. "The data" became "no listing costs under $5 (the cheapest is
  $12)". The missing-word case now lists real item words to swap in. I added
  `tests/test_agent_messages.py` so none of those can slip back.

**Other ways I used it.** I had Claude help draft the code from my spec, and
I made the design calls myself (majority-word matching, the token size rule,
regex parsing, the cache-off fit card). I also had it write three of the four
test files from my README spec *without* showing it my code, so the tests
check what I wrote down, not what I happened to build. All 88 tool tests
passed against the implementation on the first run, which told me the spec
and the code agreed.

<!-- ═══════════════════════ UNIT 4 — THE TEST ═══════════════════════

     Don't fill these in during unit 3.
     ═══════════════════════════════════════════════════════════════════ -->

---

## Run Log — Before

<!-- Five criteria, five tries each, in this exact format.

     Five, because your criteria are written out of five. Mark each try PASS
     or FAIL, count the passes, and read that count against your target — a
     row targeting 4 of 5 with three PASS cells is MISSED (3/5).

     `python run_eval.py --label before` runs everything and writes the table
     into results/. Paste it here and fill in the verdicts. -->

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Real output from one try**, pasted as text, naming the file and function
that produced it:

```

```

---

## Verdicts and Diagnoses

<!-- MET or MISSED per criterion against LAST UNIT's target, plus a sentence on
     how you decided.

     Then, for every miss: which of the four places it happened — a tool, the
     loop's branch, the session, or the model's output — AND the mechanism.

     Not a diagnosis:  "The fit card was bad."
     A diagnosis:      "The fit card criterion missed on 2 of 5 items. Both had
                        an empty brand field. My prompt puts the brand in the
                        first sentence, so the card opened with a blank and read
                        like a fragment. The tool worked; the prompt assumed a
                        field that isn't always there."

     Look for a pattern. Three misses on the same tool is one problem, not
     three. -->

| # | Criterion | Target | Verdict | How I decided |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

**Diagnoses**



---

## Loop Trace

<!-- One full run, printed step by step, with the MCP call visible in it.

     `python app.py ask '...' --trace` once you've added the trace.step()
     calls in Milestone 2.

     Worth pasting BOTH the happy path and the empty-search path. The empty
     one should be visibly shorter, because it stops. If your two traces are
     the same length, your branch isn't working — and this is the fastest way
     anyone will ever find that out. -->

**Happy path**

```

```

**Empty search**

```

```

**On the MCP move:** <!-- what changed in your code, and whether anything
behaved differently afterwards. If the rewire didn't work, say exactly where it
broke — the error text and the last thing that worked. That earns the point in
full. -->



---

## The Improvement

<!-- What you changed, why your diagnosis pointed at it, and the after-run in
     the same table format. One change, measured properly.

     `python run_eval.py --label after` -->

**What I changed:**

**Which failure it was meant to fix:**

### Run Log — After

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Did it help, and how do I know:**

<!-- If it made things worse, say that. Honestly reported, that earns full
     credit and is more interesting than one that worked. -->



---

## What's Still Broken

<!-- For each criterion still missed: what you'd do, and why you stopped where
     you did. "I ran out of time" is fine if it's true. Pretending nothing is
     left is not. -->



<!-- ═════════════════════════════════════════════════════════════════════

     SUBMISSION CHECKLIST — unit 3

       [ ] criteria.md has five numbered criteria, each with a target
       [ ] Each criterion has a reason underneath it
       [ ] All five unit 3 sections above have real content
       [ ] Tool Inventory: all three tools, inputs WITH TYPES, a specific
           return value, and the empty case
       [ ] Planning Loop names the branch rule and agent.py::run_agent
       [ ] Sample Run: one full query plus the three per-tool tests, as text
       [ ] At least four new commits
       [ ] Repository URL submitted — WRITE IT DOWN, you submit the same one
           next unit

     SUBMISSION CHECKLIST — unit 4

       [ ] mcp_server.py exists with one tool registered
           (or a written record of exactly where the rewire broke)
       [ ] Run Log — Before, five criteria, five tries each
       [ ] Real output pasted underneath, naming file and function
       [ ] A verdict on every criterion
       [ ] A diagnosis for every miss, naming a place AND a mechanism
       [ ] Loop Trace, with the MCP call visible in it
       [ ] All three failure modes triggered and handled
       [ ] One improvement, with Run Log — After in the same format
       [ ] What's Still Broken
       [ ] At least four new commits
       [ ] The SAME repository URL as last unit

     Do not delete and recreate this repository. Your commit history is what
     shows your criteria existed before your results did.
     ═════════════════════════════════════════════════════════════════════ -->

---

📖 **How to run this project: [RUNNING.md](RUNNING.md)**
