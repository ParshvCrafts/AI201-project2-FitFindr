"""
The FitFindr planning loop.

This is the file that makes FitFindr an agent rather than a script. It decides
which tool to run next based on what the last one returned.

    python agent.py          runs both example paths below

The two branch rules, also written in the README under Planning Loop:

  1. If the query has no item words once the price and size are taken out,
     stop before searching and ask what kind of item they want.  (stretch)
  2. If search_listings returns an empty list, put a message naming what to
     change in session["error"] and stop. suggest_outfit is never called.
     Otherwise take the first result and go on.
"""

import re

import config  # noqa: F401 — MAX_ITERATIONS is read through trace.check_iterations
import trace
from tools import (
    compare_price,
    content_words,
    create_fit_card,
    find_matches,
    format_price,
    search_listings,
    size_matches,
    suggest_outfit,
)
from generate import ModelUnavailable  # noqa: F401 — handled here in unit 4
from utils.data_loader import load_listings


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """
    A fresh session for one user interaction.

    The session is the single source of truth for a run. Every tool result goes
    in here, and the next tool reads it back out.
    """
    return {
        "query": query,              # what the user typed
        "parsed": {},                # description / size / max_price pulled out of it
        "search_results": [],        # everything search_listings returned
        "selected_item": None,       # the one chosen, goes into suggest_outfit
        "price_check": None,         # what compare_price returned (stretch)
        "wardrobe": wardrobe,        # the user's wardrobe
        "outfit_suggestion": None,   # what suggest_outfit returned
        "fit_card": None,            # what create_fit_card returned
        "tool_log": [],              # {"tool", "item_id"} for every tool call, in order
        "error": None,               # set when the run ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

_AMOUNT = r"(\d+(?:\.\d{1,2})?)"

# Tried in order. The first one that matches is the price, and its words are
# cut out of the description.
_PRICE_PATTERNS = [
    re.compile(
        r"\b(?:under|below|less\s+than|cheaper\s+than|max(?:imum)?|up\s+to|"
        r"at\s+most|no\s+more\s+than|budget(?:\s+of)?)\s*:?\s*\$?\s*" + _AMOUNT +
        r"(?:\s*(?:dollars|bucks|usd)\b)?",
        re.IGNORECASE,
    ),
    re.compile(r"<=?\s*\$?\s*" + _AMOUNT),
    re.compile(r"\$\s*" + _AMOUNT + r"(?:\s+or\s+(?:less|under|below)\b|\s+max\b)?", re.IGNORECASE),
]

_LETTERS = r"(?:xxxl|xxl|xl|xxs|xs|s|m|l)"
_SIZE_WORDS = {"small": "S", "medium": "M", "large": "L", "extra large": "XL"}

_SIZE_PATTERNS = [
    # "size M", "in size M", "sz 8", "size W30", "size US 8.5", "size medium"
    re.compile(
        r"(?:\bin\s+(?:an?\s+)?)?\b(?:size|sz)\s*:?\s*("
        r"(?:us\s*)?w?\s*\d+(?:\.\d)?|one\s+size|extra\s+large|small|medium|large|"
        + _LETTERS + r")\b",
        re.IGNORECASE,
    ),
    # "in M", "in a medium"
    re.compile(
        r"\bin\s+(?:an?\s+)?(" + _LETTERS + r"|extra\s+large|small|medium|large)\b",
        re.IGNORECASE,
    ),
    # Sizes that can't be mistaken for anything else, standing alone: "XL hoodie"
    re.compile(r"\b(xxs|xs|xl|xxl|xxxl)\b", re.IGNORECASE),
]


# Openers that say "I'm searching" rather than what for. Cut so the stop
# messages quote the item, not "looking for a ...".
_FILLER_OPENER = re.compile(
    r"^(?:(?:hi|hey|please)[,!]?\s+)?(?:i'?m\s+|i\s+am\s+)?"
    r"(?:looking\s+for|searching\s+for|search\s+for|shopping\s+for|"
    r"i\s+want|i\s+need|i'?d\s+like|find\s+me|show\s+me|get\s+me)\s+"
    r"(?:an?\s+|some\s+)?",
    re.IGNORECASE,
)


def _cut(text: str, match: re.Match) -> str:
    return text[: match.start()] + " " + text[match.end():]


def _normalize_size(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw.strip().lower())
    if raw in _SIZE_WORDS:
        return _SIZE_WORDS[raw]
    if raw == "one size":
        return "One Size"
    return raw.upper().replace("W ", "W")


def parse_query(query: str) -> dict:
    """
    Pull a description, a size and a max_price out of a plain-language query.

    Regex, not the model: free, instant, the same answer every time, and
    testable. "vintage graphic tee under $30, size M" →
    {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}.
    Missing pieces come back as None. The description is whatever is left.
    """
    text = query or ""

    max_price = None
    for pattern in _PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            max_price = float(match.group(1))
            text = _cut(text, match)
            break

    size = None
    for pattern in _SIZE_PATTERNS:
        match = pattern.search(text)
        if match:
            size = _normalize_size(match.group(1))
            text = _cut(text, match)
            break

    description = re.sub(r"\s+", " ", text.replace("$", " ")).strip(" ,.;:-")
    description = _FILLER_OPENER.sub("", description).strip(" ,.;:-")
    return {"description": description, "size": size, "max_price": max_price}


# ── stop messages ─────────────────────────────────────────────────────────────

# Item words that each match at least one listing (tests check this), offered
# when the user's own words match nothing.
SUGGESTED_WORDS = ("tee", "jeans", "jacket", "blazer", "sneakers", "dress")


def _filters_text(parsed: dict) -> str:
    parts = []
    if parsed.get("size"):
        parts.append(f"in size {parsed['size']}")
    if parsed.get("max_price") is not None:
        parts.append(f"under {format_price(parsed['max_price'])}")
    return (" " + " ".join(parts)) if parts else ""


def _n_listings(n: int) -> str:
    return "1 listing" if n == 1 else f"{n} listings"


def describe_vague_query(query: str, parsed: dict) -> str:
    """The stop message for a query with no item words in it (second branch)."""
    understood = []
    if parsed.get("max_price") is not None:
        understood.append(f"a budget of {format_price(parsed['max_price'])}")
    if parsed.get("size"):
        understood.append(f"size {parsed['size']}")
    heard = (" I got " + " and ".join(understood) + ", but no item.") if understood else ""
    return (
        f"I couldn't tell what kind of item you want from \"{query.strip()}\".{heard} "
        "Add the item itself, for example 'graphic tee under $30' or "
        "'denim jacket size M'."
    )


def describe_empty_search(parsed: dict) -> str:
    """
    The stop message for an empty search. Instead of "no results", it re-runs
    the search with each filter dropped and reports what that would find, so
    the user knows which thing to change.
    """
    description = parsed.get("description", "")
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    lines = [f"Nothing matched \"{description}\"{_filters_text(parsed)}."]
    word_matches = find_matches(description)
    item_words = ", ".join(SUGGESTED_WORDS[:-1]) + f" or {SUGGESTED_WORDS[-1]}"

    # Case 1: the words themselves match nothing. Fix the words first, then
    # say whether the filters would also have ruled everything out.
    if not word_matches:
        terms = content_words(description)
        found = [t for t in terms if find_matches(t)]
        missing = [t for t in terms if t not in found]
        quoted = " or ".join(f"\"{t}\"" for t in missing)
        if found:
            lines.append(
                f"No listing mentions {quoted}. \"{found[0]}\" on its own finds "
                f"{_n_listings(len(find_matches(found[0])))}, so drop \"{missing[0]}\" "
                f"or swap it for an item word like {item_words}."
            )
        else:
            lines.append(
                f"No listing mentions {quoted}. Try a different word for the item, "
                f"like {item_words}."
            )

        everything = load_listings()
        also = []
        if max_price is not None:
            cheapest = min(float(item["price"]) for item in everything)
            if max_price < cheapest:
                also.append(
                    f"no listing costs under {format_price(max_price)} "
                    f"(the cheapest is {format_price(cheapest)})"
                )
        if size and not any(
            size_matches(size, item["size"]) and "one size" not in item["size"].lower()
            for item in everything
        ):
            also.append(f"no listing comes in size {size}, so leave the size out")
        if also:
            lines.append("Your filters are too tight as well: " + ", and ".join(also) + ".")
        return " ".join(lines)

    # Case 2: the words match, a filter removed them. Re-run without each
    # filter and report what that would find.
    without_price = find_matches(description, size, None) if max_price is not None else []
    without_size = find_matches(description, None, max_price) if size else []

    if without_price:
        cheapest = min(float(item["price"]) for item in without_price)
        in_size = f" in size {size}" if size else ""
        if len(without_price) == 1:
            lines.append(
                f"Raise your budget to {format_price(cheapest)}: that's the price "
                f"of the one listing{in_size} that matches."
            )
        else:
            lines.append(
                f"Raise your budget to at least {format_price(cheapest)}: that's the "
                f"cheapest of the {len(without_price)} listings{in_size} that match."
            )
    if without_size:
        sizes = sorted({item["size"] for item in without_size})
        under = f" under {format_price(max_price)}" if max_price is not None else ""
        lead = "Or try" if without_price else "Try"
        if len(without_size) == 1:
            lines.append(
                f"{lead} another size: the one listing{under} that matches is "
                f"size {sizes[0]}."
            )
        else:
            lines.append(
                f"{lead} another size: {len(without_size)} listings{under} match, "
                f"in sizes {', '.join(sizes[:5])}."
            )

    # Case 3: only reachable with both filters set. Each one alone still
    # leaves nothing, so say that plainly and show the closest thing there is.
    if not without_price and not without_size:
        lines.append(
            f"Changing just one filter won't help: without the size there's still "
            f"nothing under {format_price(max_price)}, and without the budget there's "
            f"still nothing in size {size}."
        )
        if len(word_matches) == 1:
            only = word_matches[0]
            lines.append(
                f"The only listing with those words is size {only['size']} at "
                f"{format_price(only['price'])}. Drop both filters to see it, or "
                "try different words."
            )
        else:
            cheapest = min(float(item["price"]) for item in word_matches)
            sizes = sorted({item["size"] for item in word_matches})
            lines.append(
                f"The {len(word_matches)} listings with those words start at "
                f"{format_price(cheapest)} and come in {', '.join(sizes[:5])}. "
                "Drop both filters to see them, or try different words."
            )
    return " ".join(lines)


# ── planning loop ─────────────────────────────────────────────────────────────

def _item_id(item) -> str | None:
    return item.get("id") if isinstance(item, dict) else None


def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the loop once and return the finished session.

    Args:
        query:    what the user asked for, in plain language
                  (e.g. "vintage graphic tee under $30, size M").
        wardrobe: a wardrobe dict, e.g. get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py.

    Returns:
        The session dict. **Check session["error"] first.** If it isn't None,
        the run ended early and the later fields are still None.

    Every tool reads its inputs back out of the session and writes its result
    into it. Nothing is passed straight from one call to the next.
    """
    session = new_session(query, wardrobe)
    steps = 0

    def next_step() -> None:
        nonlocal steps
        steps += 1
        trace.check_iterations(steps)

    # Parse.
    next_step()
    session["parsed"] = parse_query(query)

    # Branch (stretch): nothing to search for. Stop before searching.
    if not content_words(session["parsed"]["description"]):
        session["error"] = describe_vague_query(query, session["parsed"])
        return session

    # Search.
    next_step()
    parsed = session["parsed"]
    session["tool_log"].append({"tool": "search_listings", "item_id": None})
    session["search_results"] = search_listings(
        parsed["description"], parsed["size"], parsed["max_price"]
    )

    # THE BRANCH: an empty search stops here. suggest_outfit is never called
    # with nothing.
    if not session["search_results"]:
        session["error"] = describe_empty_search(session["parsed"])
        return session

    session["selected_item"] = session["search_results"][0]

    # Price check (stretch).
    next_step()
    item = session["selected_item"]
    session["tool_log"].append({"tool": "compare_price", "item_id": _item_id(item)})
    session["price_check"] = compare_price(item)

    # Outfit.
    next_step()
    item = session["selected_item"]
    session["tool_log"].append({"tool": "suggest_outfit", "item_id": _item_id(item)})
    session["outfit_suggestion"] = suggest_outfit(item, session["wardrobe"])

    # Fit card.
    next_step()
    item = session["selected_item"]
    session["tool_log"].append({"tool": "create_fit_card", "item_id": _item_id(item)})
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], item)

    return session


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:
    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(f"  fit_card is {session['fit_card']!r} — it should still be None here")
        return

    item = session["selected_item"] or {}
    print(f"  found:    {item.get('title')} — ${item.get('price')} on {item.get('platform')}")
    if session["price_check"]:
        print(f"  price:    {session['price_check']['summary']}")
    print(f"  outfit:   {session['outfit_suggestion']}")
    print(f"  fit card: {session['fit_card']}")


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== A query the data can match ===")
    _show(run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    ))

    print("\n=== A query it can't ===")
    _show(run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    ))

    print(
        "\nThe second one should stop before the fit card. If both paths look "
        "the same,\nthe branch isn't doing anything yet."
    )
