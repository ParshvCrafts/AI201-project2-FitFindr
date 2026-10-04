#!/usr/bin/env python3
"""
FitFindr — command line.

    python app.py ask 'vintage graphic tee under $30, size M'
    python app.py ask                     keep asking until you quit
    python app.py ask --empty-wardrobe    run as a user with nothing saved
    python app.py ask '...' --keep        save the item it finds to your wardrobe
    python app.py wardrobe show           your saved wardrobe (style memory)
    python app.py wardrobe add 'black wide-leg jeans' --category bottoms --colors black
    python app.py wardrobe remove w_003
    python app.py wardrobe clear          forget it, go back to the example wardrobe
    python app.py listings                browse the data  (Milestone 1)
    python app.py fields                  what fields a listing has
    python app.py examples                queries worth trying, including a dud

Add --trace to any `ask` to print the loop step by step.

⚠️ Quote your query with SINGLE quotes. In PowerShell, "under $30" in double
quotes silently becomes "under " — PowerShell reads $30 as a variable and
substitutes nothing, so you search with no price ceiling and get no error
telling you why. Single quotes are literal in PowerShell, bash and zsh alike.
"""

import argparse
import sys

import config

# Every query here except the last one has something real to find in
# data/listings.json. If you add your own, check it against the data first — a
# query that finds nothing because the item doesn't exist looks exactly like a
# search tool that's broken.
EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "silk slip dress in midi length under $40",
    "platform sneakers size 8",
    "denim jacket under $50",
    "designer ballgown size XXS under $5",   # matches nothing, on purpose
]


def cmd_fields(args):
    """Milestone 1 — you can't filter on a field that isn't there."""
    from utils.data_loader import load_listings, get_example_wardrobe

    listing = load_listings()[0]
    print("A listing has these fields:\n")
    for key, value in listing.items():
        shown = str(value)
        if len(shown) > 58:
            shown = shown[:58] + "…"
        print(f"  {key:<14} {type(value).__name__:<6} {shown}")

    item = get_example_wardrobe()["items"][0]
    print("\nA wardrobe item has these fields:\n")
    for key, value in item.items():
        shown = str(value)
        if len(shown) > 58:
            shown = shown[:58] + "…"
        print(f"  {key:<14} {type(value).__name__:<6} {shown}")

    print(
        "\nThese are what search_listings can filter on. Read a few whole "
        "listings\nwith `python app.py listings` before you write it."
    )


def cmd_listings(args):
    """Milestone 1 — read the data before you write tools against it."""
    from utils.data_loader import load_listings

    listings = load_listings()

    if args.full:
        import json
        for listing in listings[: args.n]:
            print(json.dumps(listing, indent=2))
            print()
        return

    print(f"{len(listings)} listings.\n")
    print(f"{'id':<6}{'price':>8}  {'size':<22}{'platform':<11}title")
    print("-" * 92)
    for listing in listings[: args.n]:
        print(
            f"{str(listing['id']):<6}"
            f"{listing['price']:>8.2f}  "
            f"{str(listing['size']):<22}"
            f"{listing['platform']:<11}"
            f"{listing['title'][:38]}"
        )
    if len(listings) > args.n:
        print(f"\n… {len(listings) - args.n} more. Use -n {len(listings)} to see them all.")
    print("\nRead five or six all the way through: python app.py listings --full -n 6")


def cmd_examples(args):
    print("Queries worth trying:\n")
    for query in EXAMPLE_QUERIES[:-1]:
        print(f"  python app.py ask '{query}'")
    print(f"\nAnd one the data cannot match — this is the empty-search branch:\n")
    print(f"  python app.py ask '{EXAMPLE_QUERIES[-1]}'")
    print(
        "\nSingle quotes on purpose. In PowerShell a query in \"double quotes\"\n"
        "loses the $30 — it gets read as a variable — and you search with no\n"
        "price ceiling, with nothing to tell you it happened."
    )


def _ask_one(query, wardrobe, use_trace, keep=False):
    from agent import run_agent
    import trace as trace_module

    if use_trace:
        trace_module.start_trace()

    session = run_agent(query, wardrobe)

    print()
    if session["error"]:
        print(f"  {session['error']}")
    else:
        item = session["selected_item"] or {}
        print(f"  Found:    {item.get('title')} — ${item.get('price')} on {item.get('platform')}")
        if session.get("price_check"):
            print(f"  Price:    {session['price_check']['summary']}")
        print()
        print(f"  Outfit:   {session['outfit_suggestion']}")
        print()
        print(f"  Fit card: {session['fit_card']}")
        if keep:
            _keep(session["selected_item"])
    print()

    if use_trace:
        text = trace_module.get_trace()
        if not text:
            print(
                "  (--trace printed nothing. You haven't added trace.step() calls to\n"
                "   run_agent() yet — that's unit 4, Milestone 2.)\n"
            )
    return session


def _keep(item):
    from utils import wardrobe_store

    first = not wardrobe_store.has_saved_wardrobe()
    saved, added = wardrobe_store.add_listing(item)
    print()
    if added:
        print(f"  Kept:     saved \"{saved['name']}\" to your wardrobe as {saved['id']}.")
    else:
        print(f"  Kept:     \"{saved['name']}\" is already in your wardrobe as {saved['id']}.")
    if first:
        print(
            f"            Started a saved wardrobe at {config.WARDROBE_PATH.name}. From now\n"
            "            on `ask` uses it instead of the example wardrobe. Add the clothes\n"
            "            you own with `python app.py wardrobe add`."
        )


def _pick_wardrobe(args):
    """--empty-wardrobe, then the saved wardrobe if there is one, then the example."""
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
    from utils import wardrobe_store

    if args.empty_wardrobe:
        print("(running with an empty wardrobe)")
        return get_empty_wardrobe()
    saved = wardrobe_store.load_saved_wardrobe()
    if saved is not None:
        print(f"(using your saved wardrobe, {len(saved['items'])} items)")
        return saved
    return get_example_wardrobe()


def cmd_ask(args):
    from utils import wardrobe_store
    import generate

    wardrobe = _pick_wardrobe(args)

    try:
        if args.query:
            _ask_one(args.query, wardrobe, args.trace, args.keep)
        else:
            print("Ask for something, or press Enter on an empty line to quit.\n")
            while True:
                try:
                    query = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not query:
                    break
                _ask_one(query, wardrobe, args.trace, args.keep)
                if args.keep and not args.empty_wardrobe:
                    # The next question should see what was just kept.
                    wardrobe = wardrobe_store.load_saved_wardrobe() or wardrobe
    finally:
        print(generate.usage())


def cmd_wardrobe(args):
    from utils import wardrobe_store

    if args.action == "add":
        item = wardrobe_store.add_item(
            args.name, args.category,
            colors=_split(args.colors), style_tags=_split(args.tags), notes=args.notes,
        )
        print(f"Saved {item['id']}: {item['name']} ({item['category']}).")
    elif args.action == "remove":
        if wardrobe_store.remove_item(args.item_id):
            print(f"Removed {args.item_id}.")
        else:
            print(f"There's no {args.item_id} in your saved wardrobe. "
                  "`python app.py wardrobe show` lists the ids.")
    elif args.action == "clear":
        if wardrobe_store.clear_saved_wardrobe():
            print("Forgot your saved wardrobe. `ask` is back to the example wardrobe.")
        else:
            print("There was no saved wardrobe to clear.")
    else:  # show
        wardrobe = wardrobe_store.load_saved_wardrobe()
        if wardrobe is None:
            print("No saved wardrobe yet, so `ask` uses the example wardrobe.\n"
                  "Add a piece: python app.py wardrobe add 'black wide-leg jeans' "
                  "--category bottoms --colors black")
            return
        if not wardrobe["items"]:
            print("Your saved wardrobe is empty.")
            return
        print(f"Your saved wardrobe ({len(wardrobe['items'])} items):\n")
        for item in wardrobe["items"]:
            details = [item.get("category", "")] + [", ".join(item.get("colors") or [])]
            details += [", ".join(item.get("style_tags") or [])]
            print(f"  {item.get('id', '?'):6} {item.get('name', '?')}  "
                  f"({'; '.join(d for d in details if d)})")


def _split(text):
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="app.py",
        description="FitFindr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fields = sub.add_parser("fields", help="what fields the data has")
    p_fields.set_defaults(func=cmd_fields)

    p_list = sub.add_parser("listings", help="browse the listings data")
    p_list.add_argument("-n", type=int, default=15, help="how many to show")
    p_list.add_argument("--full", action="store_true", help="print whole records")
    p_list.set_defaults(func=cmd_listings)

    p_ex = sub.add_parser("examples", help="queries worth trying")
    p_ex.set_defaults(func=cmd_examples)

    p_ask = sub.add_parser("ask", help="run the agent")
    p_ask.add_argument("query", nargs="?")
    p_ask.add_argument("--trace", action="store_true", help="print the loop step by step")
    p_ask.add_argument(
        "--empty-wardrobe",
        action="store_true",
        help="run as a user with nothing saved — one of unit 4's failure modes",
    )
    p_ask.add_argument(
        "--keep",
        action="store_true",
        help="save the item it finds to your wardrobe (style memory)",
    )
    p_ask.set_defaults(func=cmd_ask)

    p_wardrobe = sub.add_parser("wardrobe", help="your saved wardrobe (style memory)")
    w_sub = p_wardrobe.add_subparsers(dest="action", required=True)
    w_add = w_sub.add_parser("add", help="add a piece you own")
    w_add.add_argument("name")
    w_add.add_argument("--category", required=True,
                       choices=("tops", "bottoms", "outerwear", "shoes", "accessories"))
    w_add.add_argument("--colors", default="", help="comma separated, e.g. black,white")
    w_add.add_argument("--tags", default="", help="comma separated style tags")
    w_add.add_argument("--notes", default=None)
    w_sub.add_parser("show", help="list what's saved")
    w_remove = w_sub.add_parser("remove", help="remove a piece by id")
    w_remove.add_argument("item_id")
    w_sub.add_parser("clear", help="forget the saved wardrobe")
    p_wardrobe.set_defaults(func=cmd_wardrobe)

    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 — students read this, not a traceback
        print(f"\n{type(exc).__name__}: {exc}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
