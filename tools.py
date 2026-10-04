"""
The FitFindr tools.

Each one is a standalone function you can call and test on its own, before any
of them are wired into the loop.

    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)             → str
    create_fit_card(outfit, new_item)              → str
    compare_price(item, listings)                  → dict   (stretch)

The full spec for each one, including what it returns when it has nothing, is
in the README under **Tool Inventory**. The docstrings below say the same thing
in less detail.
"""

import re
import statistics

import config
from generate import generate
from utils.data_loader import load_listings


# Fixed strings for the "nothing to work with" cases. They're constants so the
# loop and the tests can compare against the exact text.
NO_ITEM_TO_STYLE = "No item was given, so there is nothing to style."
NO_OUTFIT_FOR_CARD = "Can't write a fit card without an outfit suggestion."
NO_ITEM_FOR_CARD = "Can't write a fit card without an item."


# ── Shared text helpers ───────────────────────────────────────────────────────

# Words that say nothing about the item. Dropped from both the query and the
# listings so they can't create matches on their own.
_STOPWORDS = frozenset(
    """
    a an the and or of for in on at to with without from by is it its this
    that these those i im me my mine we our you your
    want wanted need needs needed looking look find finding get got buy show
    search some something any anything thing things item items piece pieces
    please would like love really very just
    size sized sz under below less than max maximum up most no more over
    budget price priced cost costs around about cheap dollar dollars buck
    bucks usd
    """.split()
)


def _stem(word: str) -> str:
    """'jeans' → 'jean', 'sneakers' → 'sneaker'. Leaves 'dress' and '90s' alone."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text) -> list[str]:
    """Lowercase, split on anything that isn't a letter or digit, drop filler."""
    out = []
    for word in re.findall(r"[a-z0-9]+", str(text).lower()):
        if len(word) < 2 or word in _STOPWORDS:
            continue
        out.append(_stem(word))
    return out


def content_words(text: str) -> list[str]:
    """The words search actually matches on, de-duplicated, in order."""
    return list(dict.fromkeys(_words(text or "")))


def format_price(price) -> str:
    """24.0 → '$24', 24.5 → '$24.50'."""
    value = float(price)
    return f"${int(value)}" if value.is_integer() else f"${value:.2f}"


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


# ── Size matching ─────────────────────────────────────────────────────────────

_LETTER_SIZES = frozenset({"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL"})
_SIZE_NOISE = frozenset({"US", "EU", "UK", "SIZE", "SZ"})
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WAIST = re.compile(r"W(\d+(?:\.\d+)?)")
_INSEAM = re.compile(r"L\d+(?:\.\d+)?")


def _size_tokens(size: str) -> list[str]:
    """'XL (fits oversized)' → ['XL', 'FITS', 'OVERSIZED']; 'US 8.5' → ['US', '8.5']."""
    return [t.strip(".") for t in re.findall(r"[A-Z0-9.]+", size.upper()) if t.strip(".")]


def size_matches(requested: str | None, listing_size: str) -> bool:
    """
    The size rule from the README. Token equality, never substring:
    'M' fits 'S/M', 'L' does not fit 'XL', '8' fits 'US 8' but not 'US 8.5',
    '30' and 'W30' fit 'W30 L30'. Anything labelled One Size fits every request.
    """
    if requested is None or not str(requested).strip():
        return True
    if re.search(r"one\s*size", listing_size or "", re.IGNORECASE):
        return True

    listing_tokens = _size_tokens(listing_size or "")
    letters = {t for t in listing_tokens if t in _LETTER_SIZES}
    numbers = {float(t) for t in listing_tokens if _NUMBER.fullmatch(t)}
    waists = {float(m.group(1)) for t in listing_tokens if (m := _WAIST.fullmatch(t))}

    wanted = [
        t for t in _size_tokens(str(requested))
        if t not in _SIZE_NOISE and not _INSEAM.fullmatch(t)
    ]
    if not wanted:
        # Nothing we know how to read, like a bare "US". Fall back to an exact
        # comparison rather than letting everything through.
        return str(requested).strip().upper() == (listing_size or "").strip().upper()

    for token in wanted:
        if token in _LETTER_SIZES:
            if token in letters:
                return True
        elif _NUMBER.fullmatch(token):
            if float(token) in numbers or float(token) in waists:
                return True
        elif m := _WAIST.fullmatch(token):
            if float(m.group(1)) in waists:
                return True
        elif token in listing_tokens:
            return True
    return False


# ── Tool 1: search_listings ───────────────────────────────────────────────────

# Where a matched word was found decides how much it counts.
_FIELD_WEIGHTS = (
    ("title", 3),
    ("style_tags", 2),
    ("category", 2),
    ("brand", 2),
    ("colors", 1),
    ("description", 1),
)


def _score(terms: list[str], listing: dict) -> tuple[int, int]:
    """(how many query words matched, weighted score)."""
    fields = {name: set(_words(_as_text(listing.get(name)))) for name, _ in _FIELD_WEIGHTS}
    matched, score = 0, 0
    for term in terms:
        best = max((w for name, w in _FIELD_WEIGHTS if term in fields[name]), default=0)
        if best:
            matched += 1
            score += best
    return matched, score


def find_matches(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Every listing that passes the filters and the majority rule, best first,
    with no length limit. search_listings() is this, cut to the result limit.
    The loop also uses it to count what each filter removed.
    """
    terms = content_words(description)
    if not terms:
        return []

    scored = []
    for listing in load_listings():
        if max_price is not None and float(listing["price"]) > float(max_price):
            continue
        if not size_matches(size, listing.get("size", "")):
            continue
        matched, score = _score(terms, listing)
        if matched * 2 > len(terms):          # more than half the words
            scored.append((score, listing))

    scored.sort(key=lambda pair: (-pair[0], float(pair[1]["price"]), pair[1]["id"]))
    return [listing for _, listing in scored]


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the listings for items matching a description, and optionally a size
    and a price ceiling.

    Args:
        description: keywords describing what the user wants ("vintage graphic tee").
        size:        a size like "M", "8", "W30", or None to skip the size filter.
        max_price:   maximum price, inclusive, or None to skip the price filter.

    Returns:
        Up to config.SEARCH_RESULT_LIMIT listing dicts, best match first, each
        the unchanged record with all 11 fields. **An empty list when nothing
        matches**, never None and never an exception. The loop branches on it.

        python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"
    """
    return find_matches(description, size, max_price)[: config.SEARCH_RESULT_LIMIT]


# ── Prompt helpers ────────────────────────────────────────────────────────────

_STYLIST = (
    "You are a friendly personal stylist who works with thrifted clothes. "
    "Be concrete and brief. Plain text only: no markdown, no headings, no bold."
)


def _describe_item(item: dict) -> str:
    """The item as prompt lines. Leaves out anything missing, brand especially."""
    lines = [f"Title: {item.get('title', 'unknown item')}"]
    if item.get("brand"):
        lines.append(f"Brand: {item['brand']}")
    for label, key in (("Category", "category"), ("Size", "size"), ("Condition", "condition")):
        if item.get(key):
            lines.append(f"{label}: {item[key]}")
    if item.get("colors"):
        lines.append(f"Colors: {', '.join(item['colors'])}")
    if item.get("style_tags"):
        lines.append(f"Style: {', '.join(item['style_tags'])}")
    if item.get("price") is not None:
        lines.append(f"Price: {format_price(item['price'])}")
    if item.get("platform"):
        lines.append(f"Platform: {item['platform']}")
    if item.get("description"):
        lines.append(f"Seller's description: {item['description']}")
    return "\n".join(lines)


def _describe_wardrobe_item(piece: dict) -> str:
    details = [str(piece.get("category") or "")]
    if piece.get("colors"):
        details.append("colors: " + ", ".join(piece["colors"]))
    if piece.get("style_tags"):
        details.append("style: " + ", ".join(piece["style_tags"]))
    if piece.get("notes"):
        details.append("notes: " + str(piece["notes"]))
    return f"- {piece.get('name', 'unnamed piece')} ({'; '.join(d for d in details if d)})"


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Suggest one or two outfits built around a thrifted item.

    Args:
        new_item: a listing dict, the item the user is considering.
        wardrobe: {"items": [...]}. The list may be empty, the key may be
                  missing, the wardrobe may be None.

    Returns:
        A non-empty string. With wardrobe items, the outfits name pieces the
        user owns. With none, it's general styling advice. If new_item is
        empty, the fixed NO_ITEM_TO_STYLE string, without a model call. Raises
        ModelUnavailable if the model can't be reached.

        python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
    """
    if not new_item:
        return NO_ITEM_TO_STYLE

    pieces = [p for p in ((wardrobe or {}).get("items") or []) if isinstance(p, dict)]
    item_text = _describe_item(new_item)

    if pieces:
        owned = "\n".join(_describe_wardrobe_item(p) for p in pieces)
        prompt = (
            f"The user is thinking about buying this thrifted item:\n{item_text}\n\n"
            f"Clothes they already own:\n{owned}\n\n"
            "Suggest 2 outfits that pair the new item with pieces they own. "
            "Only use pieces from that list plus the new item, and name each "
            "piece exactly as it is written in the list. For each outfit, write "
            "one line listing the pieces and one short line on why it works. "
            "Keep the whole answer under 120 words."
        )
    else:
        prompt = (
            f"The user is thinking about buying this thrifted item:\n{item_text}\n\n"
            "They haven't told us what clothes they own yet. Suggest 2 general "
            "outfits built around this item using common pieces most people "
            "could find (name the kind of piece, like 'straight-leg dark jeans'). "
            "For each outfit, write one line listing the pieces and one short "
            "line on why it works. Keep the whole answer under 120 words."
        )

    text = (generate(prompt, system=_STYLIST) or "").strip()
    return text or _fallback_outfit(new_item)


def _fallback_outfit(item: dict) -> str:
    """Used only when the model sends back nothing, so the loop still has text."""
    colors = item.get("colors") or []
    color = f" in {colors[0]}" if colors else ""
    return (
        f"Wear the {item.get('title', 'piece')} as the focus of the outfit. "
        f"Keep everything else simple: plain basics{color} or neutral tones, "
        "and shoes you already wear every day."
    )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Write a short caption someone would actually post about the find.

    Args:
        outfit:   the outfit text suggest_outfit() returned.
        new_item: the listing dict for the item.

    Returns:
        A 2 to 4 sentence caption that mentions the price ($24 style) and the
        platform once each. Calls the model with cache=False so the same item
        gets a different caption each run. Fixed strings, with no model call,
        when the outfit is empty or not a string (NO_OUTFIT_FOR_CARD) or the
        item is empty (NO_ITEM_FOR_CARD).

        python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
    """
    if not isinstance(outfit, str) or not outfit.strip():
        return NO_OUTFIT_FOR_CARD
    if not new_item:
        return NO_ITEM_FOR_CARD

    price = format_price(new_item["price"]) if new_item.get("price") is not None else None
    platform = new_item.get("platform")
    facts = []
    if price:
        facts.append(f"- Mention the price exactly as {price}, once.")
    if platform:
        facts.append(f'- Mention the platform name "{platform}", once.')

    prompt = (
        "Write a caption for a social media post about a thrift find.\n\n"
        f"The item:\n{_describe_item(new_item)}\n\n"
        f"How they plan to wear it:\n{outfit.strip()}\n\n"
        "Rules:\n"
        "- 2 to 4 sentences, first person, casual, like a real person posting.\n"
        + ("\n".join(facts) + "\n" if facts else "")
        + "- Be specific about the vibe of the outfit. Don't write a product description.\n"
        "- No hashtags. At most two emoji.\n"
        "- Reply with the caption only."
    )

    text = (generate(prompt, cache=False) or "").strip()
    return text or _fallback_caption(new_item, price, platform)


def _fallback_caption(item: dict, price: str | None, platform: str | None) -> str:
    """Used only when the model sends back nothing."""
    where = f" on {platform}" if platform else ""
    cost = f" for {price}" if price else ""
    return (
        f"Found this {item.get('title', 'piece')}{where}{cost}. "
        "Already planning the first outfit around it."
    )


# ── Tool 4 (stretch): compare_price ───────────────────────────────────────────

def compare_price(item: dict, listings: list[dict] | None = None) -> dict:
    """
    Compare an item's price with every other listing in the same category.

    Args:
        item:     a listing dict.
        listings: the listings to compare against, or None to load them all.

    Returns:
        {"category", "compared_with", "median_price", "cheaper_than",
         "verdict", "summary"}. verdict is "below", "at" or "above" the median.
        With nothing to compare (no other listings in the category, or no
        item), compared_with is 0, median_price and verdict are None, and the
        summary says so. Never raises for that.
    """
    item = item or {}
    category = item.get("category")
    price = item.get("price")

    others = []
    if category and price is not None:
        pool = load_listings() if listings is None else listings
        others = [
            float(other["price"]) for other in pool
            if other.get("category") == category
            and other.get("id") != item.get("id")
            and other.get("price") is not None
        ]

    if not others:
        return {
            "category": category,
            "compared_with": 0,
            "median_price": None,
            "cheaper_than": 0,
            "verdict": None,
            "summary": (
                f"There were no other {category} listings to compare this price with."
                if category else "There was no item to compare."
            ),
        }

    price = float(price)
    median = float(statistics.median(others))
    cheaper_than = sum(1 for other in others if other > price)
    if price < median:
        verdict, position = "below", "below the"
    elif price > median:
        verdict, position = "above", "above the"
    else:
        verdict, position = "at", "right at the"

    return {
        "category": category,
        "compared_with": len(others),
        "median_price": median,
        "cheaper_than": cheaper_than,
        "verdict": verdict,
        "summary": (
            f"{format_price(price)} is {position} {format_price(median)} median for "
            f"{len(others)} other {category}. It's cheaper than {cheaper_than} of them."
        ),
    }
