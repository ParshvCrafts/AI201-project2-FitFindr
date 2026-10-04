"""
Tests for the wording of the two stop messages and the filler the parser cuts.

These pin down fixes made after a cold read of the empty-search message: a
reader with no context couldn't act on "Drop or swap the word" (swap for
what?), tripped on "the data", and read "starting at $48" as several listings
when there was one.
"""

import unittest

from agent import SUGGESTED_WORDS, describe_empty_search, describe_vague_query, parse_query


def message(query: str) -> str:
    return describe_empty_search(parse_query(query))


class EmptySearchWording(unittest.TestCase):
    def test_impossible_query_names_words_price_and_size(self):
        text = message("designer ballgown size XXS under $5")
        self.assertIn('"designer" or "ballgown"', text)
        self.assertIn("$12", text)                      # cheapest real listing
        self.assertIn("size XXS", text)
        self.assertNotIn("the data", text)
        self.assertNotIn("No results", text)

    def test_one_missing_word_says_drop_it_and_offers_swaps(self):
        text = message("vintage ballgown")
        self.assertIn('drop "ballgown"', text)
        self.assertIn('"vintage" on its own finds 29 listings', text)
        for word in SUGGESTED_WORDS:
            self.assertIn(word, text)

    def test_price_only_gives_the_budget_to_raise_to(self):
        self.assertIn("Raise your budget to at least $15", message("graphic tee under $10"))

    def test_single_listing_is_described_as_one(self):
        text = message("platform sneakers size 6")
        self.assertIn("the one listing that matches is size US 8", text)
        self.assertNotIn("listings", text)

    def test_both_filters_says_changing_one_is_not_enough(self):
        text = message("platform sneakers size 6 under $20")
        self.assertIn("Changing just one filter won't help", text)
        self.assertIn("The only listing with those words is size US 8 at $48", text)
        self.assertNotIn("starting at", text)

    def test_both_filters_with_several_matches_lists_their_sizes(self):
        text = message("jeans size W40 under $20")
        self.assertIn("The 3 listings with those words start at $30", text)
        self.assertIn("W28, W30 L30, W32", text)


class VagueQueryWording(unittest.TestCase):
    def test_repeats_what_was_understood(self):
        text = describe_vague_query("under $30, size M", parse_query("under $30, size M"))
        self.assertIn("a budget of $30 and size M", text)
        self.assertIn("graphic tee under $30", text)    # an example to copy

    def test_with_nothing_understood_has_no_dangling_clause(self):
        text = describe_vague_query("please", parse_query("please"))
        self.assertNotIn("I got", text)


class FillerIsCut(unittest.TestCase):
    def test_openers_do_not_end_up_in_the_description(self):
        cases = {
            "looking for a vintage graphic tee under $30, size M": "vintage graphic tee",
            "I'm looking for some boots in a medium": "boots",
            "find me a denim jacket": "denim jacket",
            "hi, i need a tee sz L": "tee",
            "90s track jacket in size M": "90s track jacket",
        }
        for query, description in cases.items():
            with self.subTest(query=query):
                self.assertEqual(parse_query(query)["description"], description)

    def test_size_words_become_letters(self):
        self.assertEqual(parse_query("tee in a medium")["size"], "M")
        self.assertEqual(parse_query("tee size extra large")["size"], "XL")

    def test_powershell_eaten_price_leaves_no_price(self):
        # "under $30" in double quotes in PowerShell arrives as "under ".
        self.assertEqual(
            parse_query("vintage graphic tee under "),
            {"description": "vintage graphic tee under", "size": None, "max_price": None},
        )


class ReviewFindings(unittest.TestCase):
    """Bugs an independent review found and reproduced. Each failed before its fix."""

    def test_words_that_each_exist_but_never_together_do_not_crash(self):
        # 'denim' and 'dress' each match listings, but no listing has both.
        for query in ("denim dress", "leather sneakers", "blue tee blazer"):
            with self.subTest(query=query):
                text = message(query)
                self.assertIn("no single listing", text)
                self.assertIn("on its own", text.lower())

    def test_run_agent_stops_with_a_message_instead_of_raising(self):
        from unittest.mock import patch
        from agent import run_agent
        from utils.data_loader import get_example_wardrobe
        with patch("tools.generate") as model:
            session = run_agent("denim dress", get_example_wardrobe())
        self.assertIsNotNone(session["error"])
        self.assertIsNone(session["fit_card"])
        model.assert_not_called()

    def test_size_word_describing_the_item_is_not_a_size(self):
        self.assertEqual(parse_query("jeans in medium wash"),
                         {"description": "jeans in medium wash", "size": None, "max_price": None})
        self.assertIsNone(parse_query("dress in small floral print")["size"])
        # At the end of the query it still is a size.
        self.assertEqual(parse_query("tee in a medium")["size"], "M")
        self.assertEqual(parse_query("hoodie in large, under $30")["size"], "L")

    def test_inseam_is_part_of_the_size_not_the_description(self):
        parsed = parse_query("jeans size W30 L32")
        self.assertEqual(parsed["description"], "jeans")
        self.assertEqual(parsed["size"], "W30 L32")
        from tools import search_listings
        self.assertEqual([x["id"] for x in search_listings("jeans", parsed["size"])], ["lst_001"])

    def test_thousands_separator_in_a_price(self):
        self.assertEqual(parse_query("jacket under $1,000"),
                         {"description": "jacket", "size": None, "max_price": 1000.0})
        self.assertEqual(parse_query("coat $1,250.50 or less")["max_price"], 1250.5)


if __name__ == "__main__":
    unittest.main()
