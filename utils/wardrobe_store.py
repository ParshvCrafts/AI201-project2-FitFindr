"""
Style memory (stretch): keeps the user's wardrobe in a JSON file between runs.

The file is config.WARDROBE_PATH, data/my_wardrobe.json by default. It is
gitignored, because it's someone's own clothes, not project data. It has the
same shape as every other wardrobe in this project: {"items": [...]}.

Two rules this module keeps:

  • A file that exists but can't be read raises WardrobeFileError. It is never
    quietly replaced with an empty wardrobe, because that would delete what
    the user saved.
  • Writes go to a temporary file first and are swapped in with os.replace,
    so a crash halfway through a save can't leave a half-written file.
"""

import json
import os
import re
import tempfile
from pathlib import Path

import config

CATEGORIES = ("tops", "bottoms", "outerwear", "shoes", "accessories")


class WardrobeFileError(Exception):
    """The saved wardrobe file exists but isn't a readable wardrobe."""


def _path(path=None) -> Path:
    return Path(path) if path is not None else Path(config.WARDROBE_PATH)


def has_saved_wardrobe(path=None) -> bool:
    return _path(path).is_file()


def load_saved_wardrobe(path=None) -> dict | None:
    """The saved wardrobe, or None if nothing has been saved yet."""
    p = _path(path)
    if not p.is_file():
        return None
    try:
        # utf-8-sig also reads files saved with a byte order mark, which is
        # what Notepad and PowerShell's Out-File write on Windows.
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WardrobeFileError(
            f"Couldn't read your saved wardrobe at {p} ({exc}). Fix the file, or "
            "run `python app.py wardrobe clear` to start over."
        ) from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise WardrobeFileError(
            f"{p} isn't a wardrobe. It should look like {{\"items\": [...]}}. Fix the "
            "file, or run `python app.py wardrobe clear` to start over."
        )
    return {"items": items}


def save_wardrobe(wardrobe: dict, path=None) -> None:
    """Write the wardrobe atomically: temp file first, then swap it in."""
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".wardrobe-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"items": list(wardrobe.get("items") or [])}, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def clear_saved_wardrobe(path=None) -> bool:
    """Forget the saved wardrobe. True if there was one to forget."""
    p = _path(path)
    if p.is_file():
        p.unlink()
        return True
    return False


def _next_id(items: list[dict]) -> str:
    numbers = [
        int(m.group(1)) for item in items
        if (m := re.fullmatch(r"w_(\d+)", str(item.get("id", ""))))
    ]
    return f"w_{max(numbers, default=0) + 1:03d}"


def _clean(values) -> list[str]:
    return [str(v).strip().lower() for v in (values or []) if str(v).strip()]


def add_item(name: str, category: str, colors=(), style_tags=(), notes: str | None = None,
             path=None) -> dict:
    """Add a piece the user owns. Returns the saved item, with its new id."""
    name = (name or "").strip()
    if not name:
        raise ValueError("A wardrobe item needs a name.")
    category = (category or "").strip().lower()
    if category not in CATEGORIES:
        raise ValueError(f"Category must be one of: {', '.join(CATEGORIES)}.")

    wardrobe = load_saved_wardrobe(path) or {"items": []}
    item = {
        "id": _next_id(wardrobe["items"]),
        "name": name,
        "category": category,
        "colors": _clean(colors),
        "style_tags": _clean(style_tags),
    }
    if notes and notes.strip():
        item["notes"] = notes.strip()
    wardrobe["items"].append(item)
    save_wardrobe(wardrobe, path)
    return item


def add_listing(listing: dict, path=None) -> tuple[dict, bool]:
    """
    Save a listing the agent found (`ask --keep`) as a wardrobe item.

    Returns (item, added). added is False when that listing was already saved,
    so keeping the same find twice doesn't duplicate it.
    """
    if not listing or not listing.get("id"):
        raise ValueError("There's no found item to keep.")

    wardrobe = load_saved_wardrobe(path) or {"items": []}
    for existing in wardrobe["items"]:
        if existing.get("source_listing") == listing["id"]:
            return existing, False

    price = listing.get("price")
    paid = ""
    if price is not None:
        value = float(price)
        paid = f" for ${int(value)}" if value.is_integer() else f" for ${value:.2f}"
    item = {
        "id": _next_id(wardrobe["items"]),
        "name": listing.get("title", "thrifted piece"),
        "category": listing.get("category", ""),
        "colors": list(listing.get("colors") or []),
        "style_tags": list(listing.get("style_tags") or []),
        "notes": f"Thrifted on {listing.get('platform', 'a resale app')}{paid}",
        "source_listing": listing["id"],
    }
    wardrobe["items"].append(item)
    save_wardrobe(wardrobe, path)
    return item, True


def remove_item(item_id: str, path=None) -> bool:
    """Remove one item by id. True if it was there."""
    wardrobe = load_saved_wardrobe(path)
    if not wardrobe:
        return False
    kept = [item for item in wardrobe["items"] if item.get("id") != item_id]
    if len(kept) == len(wardrobe["items"]):
        return False
    save_wardrobe({"items": kept}, path)
    return True
