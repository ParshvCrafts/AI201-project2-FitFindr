"""Black-box tests written from README "Planning Loop" / "Stretch Features" and criteria.md 1-5.
Fully offline: tools.generate is patched."""
import unittest
from unittest.mock import patch, MagicMock

import agent
import tools
from agent import (SUGGESTED_WORDS, describe_empty_search, describe_vague_query,
                   new_session, parse_query, run_agent)
from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe

MATCHING = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "silk slip dress in midi length under $40",
    "platform sneakers size 8",
    "denim jacket under $50",
]
IMPOSSIBLE = "designer ballgown size XXS under $5"
FOUR = ["search_listings", "compare_price", "suggest_outfit", "create_fit_card"]


class ParseQueryTests(unittest.TestCase):
    def price(self, q):
        return parse_query(q)["max_price"]

    def test_price_phrasings(self):
        for q in ["jeans under $30", "jeans below 30", "jeans less than $30",
                  "jeans max $30", "jeans up to $30", "jeans $30 or less", "jeans $30"]:
            with self.subTest(q=q):
                self.assertEqual(self.price(q), 30.0)
                self.assertIsInstance(self.price(q), float)

    def test_size_phrasings(self):
        cases = {"jacket size M": "M", "sneakers sz 8": "8", "pants size W30": "W30",
                 "jacket in M": "M", "tee XS": "XS", "tee XL": "XL", "tee XXL": "XXL"}
        for q, s in cases.items():
            with self.subTest(q=q):
                self.assertEqual((parse_query(q)["size"] or "").upper(), s)

    def test_examples(self):
        p = parse_query("vintage graphic tee under $30")
        self.assertEqual((p["max_price"], p["size"]), (30.0, None))
        self.assertIn("graphic", p["description"])
        self.assertIn("tee", p["description"])
        p = parse_query("90s track jacket in size M")
        self.assertEqual((p["max_price"], p["size"].upper()), (None, "M"))
        self.assertIn("90s", p["description"])
        p = parse_query("silk slip dress in midi length under $40")
        self.assertEqual((p["max_price"], p["size"]), (40.0, None))
        self.assertIn("midi", p["description"])
        p = parse_query("platform sneakers size 8")
        self.assertEqual((p["max_price"], p["size"]), (None, "8"))
        p = parse_query("denim jacket under $50")
        self.assertEqual((p["max_price"], p["size"]), (50.0, None))
        p = parse_query(IMPOSSIBLE)
        self.assertEqual((p["max_price"], p["size"].upper()), (5.0, "XXS"))
        self.assertIn("ballgown", p["description"])

    def test_missing_pieces_none(self):
        p = parse_query("jeans")
        self.assertIsNone(p["max_price"])
        self.assertIsNone(p["size"])
        self.assertIn("jeans", p["description"])

    def test_description_excludes_price_and_size(self):
        d = parse_query("jeans size M under $30")["description"]
        self.assertNotIn("$", d)
        self.assertNotIn("30", d)


def mocked_run(query, wardrobe=None, outfit="Wear it with the black jeans."):
    wardrobe = get_example_wardrobe() if wardrobe is None else wardrobe
    with patch("tools.generate", return_value=outfit) as gen, \
            patch("agent.suggest_outfit", wraps=suggest_outfit) as so, \
            patch("agent.create_fit_card", wraps=create_fit_card) as fc:
        s = run_agent(query, wardrobe)
    return s, gen, so, fc


class HappyPathTests(unittest.TestCase):
    def test_happy_path_each_query(self):
        for q in MATCHING:
            with self.subTest(q=q):
                outfit = "OUTFIT-TEXT for " + q
                s, gen, so, fc = mocked_run(q, outfit=outfit)
                self.assertIsNone(s["error"])
                self.assertTrue(s["fit_card"] and s["fit_card"].strip())
                self.assertTrue(s["search_results"])
                self.assertEqual(s["selected_item"]["id"], s["search_results"][0]["id"])
                self.assertEqual([e["tool"] for e in s["tool_log"]], FOUR)
                sid = s["selected_item"]["id"]
                for e in s["tool_log"][1:]:
                    self.assertEqual(e["item_id"], sid)
                so.assert_called_once()
                fc.assert_called_once()
                self.assertIn(sid, [a.get("id") for a in
                                    list(so.call_args.args) + list(so.call_args.kwargs.values())
                                    if isinstance(a, dict)])
                fc_dicts = [a.get("id") for a in
                            list(fc.call_args.args) + list(fc.call_args.kwargs.values())
                            if isinstance(a, dict)]
                self.assertIn(sid, fc_dicts)
                fc_args = list(fc.call_args.args) + list(fc.call_args.kwargs.values())
                self.assertIn(s["outfit_suggestion"], fc_args)
                self.assertEqual(s["outfit_suggestion"], outfit)

    def test_empty_wardrobe_completes(self):
        s, *_ = mocked_run("vintage graphic tee under $30", wardrobe=get_empty_wardrobe())
        self.assertIsNone(s["error"])
        self.assertTrue(s["fit_card"])
        self.assertEqual([e["tool"] for e in s["tool_log"]], FOUR)


class EmptySearchTests(unittest.TestCase):
    def test_impossible_query_branch(self):
        s, gen, so, fc = mocked_run(IMPOSSIBLE)
        self.assertTrue(s["error"])
        self.assertIsNone(s["outfit_suggestion"])
        self.assertIsNone(s["fit_card"])
        self.assertIsNone(s["selected_item"])
        self.assertEqual([e["tool"] for e in s["tool_log"]], ["search_listings"])
        so.assert_not_called()
        fc.assert_not_called()
        gen.assert_not_called()
        msg = s["error"]
        self.assertNotIn(msg.strip().lower().rstrip("."), ("no results", "no results found"))
        self.assertTrue(any(w in msg.lower() for w in SUGGESTED_WORDS) or "$" in msg
                        or "XXS" in msg, msg)

    def msg(self, q):
        s, *_ = mocked_run(q)
        self.assertTrue(s["error"])
        self.assertIsNone(s["fit_card"])
        return s["error"]

    def test_price_only_empty(self):
        m = self.msg("graphic tee under $10")
        self.assertIn("$15", m)  # cheapest real graphic tee
        self.assertTrue("budget" in m.lower() or "price" in m.lower() or "raise" in m.lower(), m)

    def test_size_only_empty(self):
        m = self.msg("platform sneakers size 6")
        self.assertIn("US 8", m)

    def test_both_filters_empty(self):
        m = self.msg("platform sneakers size 6 under $10")
        self.assertTrue("US 8" in m or "$48" in m, m)

    def test_describe_empty_search_direct(self):
        m = describe_empty_search(parse_query(IMPOSSIBLE))
        self.assertIsInstance(m, str)
        self.assertTrue(m)

    def test_suggested_words_all_return_results(self):
        for w in SUGGESTED_WORDS:
            with self.subTest(w=w):
                self.assertTrue(search_listings(w))

    def test_deterministic(self):
        msgs = {mocked_run(IMPOSSIBLE)[0]["error"] for _ in range(5)}
        self.assertEqual(len(msgs), 1)


class VagueQueryTests(unittest.TestCase):
    def test_vague_stops_before_search(self):
        for q, token in [("under $30", "$30"), ("size M", "M")]:
            with self.subTest(q=q):
                with patch("agent.search_listings", wraps=search_listings) as sl:
                    s, gen, so, fc = mocked_run(q)
                self.assertEqual(s["tool_log"], [])
                self.assertEqual(s["search_results"], [])
                self.assertTrue(s["error"])
                self.assertIn(token, s["error"])
                self.assertTrue(any(w in s["error"].lower() for w in
                                    ("item", "what", "looking", "kind", "type")), s["error"])
                gen.assert_not_called()
                self.assertIsNone(s["fit_card"])

    def test_describe_vague_direct(self):
        m = describe_vague_query("under $30", parse_query("under $30"))
        self.assertIn("$30", m)


class Criterion5Tests(unittest.TestCase):
    def test_price_limit(self):
        cases = [("vintage graphic tee under $30", 30), ("silk slip dress in midi length under $40", 40),
                 ("denim jacket under $50", 50), ("jeans under $35", 35), ("sneakers below $25", 25)]
        for q, n in cases:
            with self.subTest(q=q):
                s, *_ = mocked_run(q)
                self.assertEqual(s["parsed"]["max_price"], n)
                self.assertTrue(s["search_results"])
                for r in s["search_results"]:
                    self.assertLessEqual(r["price"], n)


class SessionTests(unittest.TestCase):
    def test_new_session_keys(self):
        s = new_session("x", get_example_wardrobe())
        self.assertEqual(set(s), {"query", "parsed", "search_results", "selected_item",
                                  "price_check", "wardrobe", "outfit_suggestion",
                                  "fit_card", "tool_log", "error"})
        self.assertIsNone(s["error"])


if __name__ == "__main__":
    unittest.main()
