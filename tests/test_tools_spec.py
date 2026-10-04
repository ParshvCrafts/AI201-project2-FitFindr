"""Black-box tests written from the README tool spec. Fully offline."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from generate import ModelUnavailable
from tools import compare_price, create_fit_card, search_listings, suggest_outfit

ROOT = Path(__file__).resolve().parent.parent
LISTINGS = json.loads((ROOT / "data" / "listings.json").read_text(encoding="utf-8"))
BY_ID = {l["id"]: l for l in LISTINGS}
WARDROBE = json.loads((ROOT / "data" / "wardrobe_schema.json").read_text(encoding="utf-8"))[
    "example_wardrobe"
]
FIELDS = {"id", "title", "description", "category", "style_tags", "size",
          "condition", "price", "colors", "brand", "platform"}

NO_ITEM_OUTFIT = "No item was given, so there is nothing to style."
NO_OUTFIT_CARD = "Can't write a fit card without an outfit suggestion."
NO_ITEM_CARD = "Can't write a fit card without an item."


def ids(results):
    return [r["id"] for r in results]


def prompt_of(mock):
    """All text passed to the mocked generate call (args and kwargs)."""
    a, k = mock.call_args
    return " ".join([str(x) for x in a] + [str(v) for v in k.values()])


class SearchShapeTests(unittest.TestCase):
    def test_returns_list_of_dicts_with_all_11_fields(self):
        res = search_listings("jeans")
        self.assertIsInstance(res, list)
        self.assertTrue(res)
        for r in res:
            self.assertIsInstance(r, dict)
            self.assertEqual(set(r), FIELDS)

    def test_results_are_unchanged_records(self):
        for r in search_listings("jeans"):
            self.assertEqual(r, BY_ID[r["id"]])

    def test_no_keyword_match_returns_empty_list(self):
        self.assertEqual(search_listings("zzzqqq"), [])

    def test_filters_removing_everything_returns_empty_list(self):
        self.assertEqual(search_listings("jeans", max_price=5), [])
        self.assertEqual(search_listings("jeans", size="XL"), [])

    def test_only_filler_words_returns_empty_list(self):
        self.assertEqual(search_listings("a for the looking size under"), [])

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(search_listings(""), [])

    def test_whitespace_only_returns_empty_list(self):
        self.assertEqual(search_listings("   "), [])

    def test_result_limit_is_ten(self):
        self.assertEqual(config.SEARCH_RESULT_LIMIT, 10)
        self.assertEqual(len(search_listings("vintage")), 10)

    def test_same_input_same_output(self):
        self.assertEqual(search_listings("vintage"), search_listings("vintage"))


class SearchMatchingTests(unittest.TestCase):
    def test_majority_rule_vintage_ballgown_is_empty(self):
        self.assertEqual(search_listings("vintage ballgown"), [])

    def test_two_words_both_must_match(self):
        res = search_listings("vintage jeans")
        self.assertEqual(set(ids(res)), {"lst_001", "lst_037", "lst_031"})

    def test_order_score_desc_then_price_asc(self):
        # lst_016/038/007 have 'denim' in the title (3); 037/001 only as a tag (2).
        res = search_listings("denim")
        self.assertEqual(ids(res), ["lst_016", "lst_038", "lst_007", "lst_037", "lst_001"])

    def test_equal_score_orders_by_price_ascending(self):
        # all three have 'jeans' in the title
        self.assertEqual(ids(search_listings("jeans")), ["lst_037", "lst_031", "lst_001"])

    def test_plural_stripping_jeans_equals_jean(self):
        self.assertEqual(search_listings("jeans"), search_listings("jean"))

    def test_dress_not_stripped(self):
        self.assertEqual(ids(search_listings("dress")), ["lst_013"])

    def test_case_insensitive_description(self):
        self.assertEqual(search_listings("JEANS"), search_listings("jeans"))


class SearchPriceTests(unittest.TestCase):
    def test_price_equal_to_max_is_included(self):
        self.assertEqual(ids(search_listings("jeans", max_price=30)), ["lst_037"])

    def test_one_cent_below_is_excluded(self):
        self.assertEqual(search_listings("jeans", max_price=29.99), [])

    def test_boots_boundary_44(self):
        self.assertEqual(ids(search_listings("boots", max_price=44)), ["lst_028"])
        self.assertEqual(search_listings("boots", max_price=43.99), [])

    def test_max_price_none_skips_filter(self):
        self.assertEqual(len(search_listings("jeans", max_price=None)), 3)

    def test_prices_all_within_limit(self):
        for r in search_listings("vintage", max_price=20):
            self.assertLessEqual(r["price"], 20)


class SearchSizeTests(unittest.TestCase):
    def test_m_matches_plain_m_and_m_l(self):
        self.assertEqual(set(ids(search_listings("shirt", size="M"))), {"lst_024", "lst_032"})

    def test_m_matches_s_slash_m(self):
        self.assertIn("lst_017", ids(search_listings("top", size="M")))

    def test_s_matches_s_slash_m(self):
        self.assertIn("lst_017", ids(search_listings("top", size="S")))

    def test_m_matches_m_l_blazer(self):
        self.assertEqual(ids(search_listings("blazer", size="M")), ["lst_018"])

    def test_l_matches_m_l_blazer(self):
        self.assertEqual(ids(search_listings("blazer", size="L")), ["lst_018"])

    def test_l_does_not_match_xl(self):
        self.assertEqual(search_listings("tee", size="XL"), [])
        self.assertEqual(set(ids(search_listings("tee", size="L"))), {"lst_033", "lst_006"})

    def test_l_does_not_match_xl_oversized(self):
        self.assertEqual(search_listings("sweatshirt", size="L"), [])
        self.assertEqual(ids(search_listings("sweatshirt", size="XL")), ["lst_012"])

    def test_xl_matches_plain_xl_and_xl_oversized(self):
        self.assertEqual(set(ids(search_listings("crewneck", size="XL"))), {"lst_012", "lst_027"})

    def test_size_case_insensitive(self):
        self.assertEqual(search_listings("crewneck", size="xl"),
                         search_listings("crewneck", size="XL"))
        self.assertEqual(search_listings("blazer", size="m"), search_listings("blazer", size="M"))

    def test_8_matches_us_8_not_us_8_5(self):
        self.assertEqual(ids(search_listings("sneakers", size="8")), ["lst_019"])
        self.assertEqual(search_listings("boots", size="8"), [])

    def test_8_5_matches_us_8_5_only(self):
        self.assertEqual(ids(search_listings("boots", size="8.5")), ["lst_028"])
        self.assertEqual(search_listings("sneakers", size="8.5"), [])

    def test_30_matches_w30_l30(self):
        self.assertEqual(ids(search_listings("jeans", size="30")), ["lst_001"])

    def test_30_matches_w30(self):
        self.assertEqual(ids(search_listings("trousers", size="30")), ["lst_021"])

    def test_w30_matches_waist_30(self):
        self.assertEqual(ids(search_listings("jeans", size="W30")), ["lst_001"])
        self.assertEqual(ids(search_listings("trousers", size="W30")), ["lst_021"])

    def test_28_matches_w28(self):
        self.assertEqual(ids(search_listings("jeans", size="28")), ["lst_037"])

    def test_w_size_does_not_match_shoe_size(self):
        self.assertEqual(search_listings("sneakers", size="W8"), [])

    def test_one_size_matches_any_request(self):
        for size in ("XS", "M", "XL"):
            self.assertEqual(ids(search_listings("belt", size=size)), ["lst_014"])
        self.assertEqual(ids(search_listings("hat", size="M")), ["lst_034"])
        self.assertEqual(ids(search_listings("bag", size="S")), ["lst_039"])

    def test_one_size_oversized_matches_any_request(self):
        self.assertEqual(ids(search_listings("cardigan", size="XS")), ["lst_008"])

    def test_size_none_skips_filter(self):
        self.assertEqual(len(search_listings("jeans", size=None)), 3)


class SearchExampleQueryTests(unittest.TestCase):
    def test_graphic_tee_under_30(self):
        res = search_listings("graphic tee", max_price=30)
        self.assertTrue({"lst_006", "lst_002", "lst_033"} <= set(ids(res)))
        self.assertTrue(all(r["price"] <= 30 for r in res))

    def test_vintage_graphic_tee_under_30_best_first(self):
        res = ids(search_listings("vintage graphic tee", max_price=30))
        self.assertEqual(res[:3], ["lst_033", "lst_006", "lst_002"])

    def test_track_jacket_size_m(self):
        res = ids(search_listings("90s track jacket", size="M"))
        self.assertEqual(res[0], "lst_004")
        self.assertTrue(all(BY_ID[i]["size"] != "XL" for i in res))

    def test_silk_slip_dress_under_40(self):
        res = ids(search_listings("silk slip dress midi length", size="M", max_price=40))
        self.assertEqual(res, ["lst_013"])

    def test_platform_sneakers_size_8(self):
        self.assertEqual(ids(search_listings("platform sneakers", size="8")), ["lst_019"])

    def test_denim_jacket_under_50(self):
        res = ids(search_listings("denim jacket", max_price=50))
        self.assertEqual(res[0], "lst_007")

    def test_designer_ballgown_matches_nothing(self):
        self.assertEqual(search_listings("designer ballgown", size="XXS", max_price=5), [])

    def test_ballgown_query_with_words_in_sentence(self):
        self.assertEqual(search_listings("designer ballgown size XXS under $5"), [])


class SuggestOutfitTests(unittest.TestCase):
    ITEM = BY_ID["lst_001"]

    @patch("tools.generate", return_value="Wear it with a tee.")
    def test_empty_wardrobe_calls_model_and_returns_text(self, g):
        out = suggest_outfit(self.ITEM, {"items": []})
        self.assertTrue(g.called)
        self.assertIsInstance(out, str)
        self.assertTrue(out.strip())

    @patch("tools.generate", return_value="General ideas.")
    def test_missing_items_key(self, g):
        out = suggest_outfit(self.ITEM, {})
        self.assertTrue(g.called)
        self.assertTrue(out.strip())

    @patch("tools.generate", return_value="General ideas.")
    def test_none_wardrobe(self, g):
        out = suggest_outfit(self.ITEM, None)
        self.assertTrue(g.called)
        self.assertTrue(out.strip())

    @patch("tools.generate", return_value="ok")
    def test_wardrobe_item_names_in_prompt(self, g):
        suggest_outfit(self.ITEM, WARDROBE)
        p = prompt_of(g)
        for item in WARDROBE["items"][:3]:
            self.assertIn(item["name"], p)

    @patch("tools.generate", return_value="ok")
    def test_new_item_title_in_prompt(self, g):
        suggest_outfit(self.ITEM, WARDROBE)
        self.assertIn("Levi", prompt_of(g))

    @patch("tools.generate")
    def test_none_item_fixed_string_no_model(self, g):
        self.assertEqual(suggest_outfit(None, WARDROBE), NO_ITEM_OUTFIT)
        g.assert_not_called()

    @patch("tools.generate")
    def test_empty_dict_item_fixed_string_no_model(self, g):
        self.assertEqual(suggest_outfit({}, WARDROBE), NO_ITEM_OUTFIT)
        g.assert_not_called()

    @patch("tools.generate", return_value="")
    def test_model_empty_gives_nonempty_fallback(self, g):
        out = suggest_outfit(self.ITEM, WARDROBE)
        self.assertIsInstance(out, str)
        self.assertTrue(out.strip())

    @patch("tools.generate", return_value="")
    def test_model_empty_with_empty_wardrobe_fallback(self, g):
        self.assertTrue(suggest_outfit(self.ITEM, {"items": []}).strip())

    @patch("tools.generate", side_effect=ModelUnavailable("down"))
    def test_model_unavailable_propagates(self, g):
        with self.assertRaises(ModelUnavailable):
            suggest_outfit(self.ITEM, WARDROBE)


class CreateFitCardTests(unittest.TestCase):
    ITEM = BY_ID["lst_006"]   # $24, depop, brand None
    OUTFIT = "Pair with baggy jeans and boots."

    @patch("tools.generate")
    def test_empty_outfit_fixed_string(self, g):
        self.assertEqual(create_fit_card("", self.ITEM), NO_OUTFIT_CARD)
        g.assert_not_called()

    @patch("tools.generate")
    def test_whitespace_outfit_fixed_string(self, g):
        self.assertEqual(create_fit_card("  \n\t ", self.ITEM), NO_OUTFIT_CARD)
        g.assert_not_called()

    @patch("tools.generate")
    def test_non_string_outfit_fixed_string(self, g):
        for bad in (None, 5, ["a"], {"a": 1}):
            self.assertEqual(create_fit_card(bad, self.ITEM), NO_OUTFIT_CARD)
        g.assert_not_called()

    @patch("tools.generate")
    def test_none_item_fixed_string(self, g):
        self.assertEqual(create_fit_card(self.OUTFIT, None), NO_ITEM_CARD)
        g.assert_not_called()

    @patch("tools.generate")
    def test_empty_dict_item_fixed_string(self, g):
        self.assertEqual(create_fit_card(self.OUTFIT, {}), NO_ITEM_CARD)
        g.assert_not_called()

    @patch("tools.generate", return_value="Cute caption.")
    def test_returns_model_text(self, g):
        self.assertEqual(create_fit_card(self.OUTFIT, self.ITEM).strip(), "Cute caption.")

    @patch("tools.generate", return_value="Cute caption.")
    def test_cache_false_passed(self, g):
        create_fit_card(self.OUTFIT, self.ITEM)
        self.assertIs(g.call_args.kwargs.get("cache"), False)

    @patch("tools.generate", return_value="x")
    def test_price_formatted_whole_dollars(self, g):
        create_fit_card(self.OUTFIT, self.ITEM)
        p = prompt_of(g)
        self.assertIn("$24", p)
        self.assertNotIn("$24.0", p)

    @patch("tools.generate", return_value="x")
    def test_price_with_cents(self, g):
        item = dict(self.ITEM, price=24.5)
        create_fit_card(self.OUTFIT, item)
        self.assertIn("$24.50", prompt_of(g))

    @patch("tools.generate", return_value="x")
    def test_platform_in_prompt(self, g):
        create_fit_card(self.OUTFIT, self.ITEM)
        self.assertIn("depop", prompt_of(g))

    @patch("tools.generate", return_value="x")
    def test_brand_none_not_in_prompt(self, g):
        self.assertIsNone(self.ITEM["brand"])
        create_fit_card(self.OUTFIT, self.ITEM)
        self.assertNotIn("None", prompt_of(g))

    @patch("tools.generate", return_value="x")
    def test_outfit_text_in_prompt(self, g):
        create_fit_card(self.OUTFIT, self.ITEM)
        self.assertIn("baggy jeans", prompt_of(g))

    @patch("tools.generate", return_value="")
    def test_model_empty_fallback_has_price_and_platform(self, g):
        out = create_fit_card(self.OUTFIT, self.ITEM)
        self.assertTrue(out.strip())
        self.assertIn("$24", out)
        self.assertIn("depop", out)

    @patch("tools.generate", return_value="   ")
    def test_model_whitespace_fallback(self, g):
        out = create_fit_card(self.OUTFIT, self.ITEM)
        self.assertTrue(out.strip())

    @patch("tools.generate", side_effect=ModelUnavailable("down"))
    def test_model_unavailable_propagates(self, g):
        with self.assertRaises(ModelUnavailable):
            create_fit_card(self.OUTFIT, self.ITEM)


class ComparePriceTests(unittest.TestCase):
    KEYS = {"category", "compared_with", "median_price", "cheaper_than", "verdict", "summary"}

    @patch("tools.generate")
    def test_no_model_call(self, g):
        compare_price(BY_ID["lst_017"])
        g.assert_not_called()

    def test_dict_keys_exactly_as_spec(self):
        self.assertEqual(set(compare_price(BY_ID["lst_017"])), self.KEYS)

    def test_excludes_item_itself(self):
        r = compare_price(BY_ID["lst_017"])
        self.assertEqual(r["category"], "tops")
        self.assertEqual(r["compared_with"], 14)   # 15 tops minus itself

    def test_cheapest_top_is_below_and_cheaper_than_all(self):
        r = compare_price(BY_ID["lst_017"])        # $15
        self.assertAlmostEqual(r["median_price"], 21.5)
        self.assertEqual(r["cheaper_than"], 14)
        self.assertEqual(r["verdict"], "below")
        self.assertIsInstance(r["summary"], str)
        self.assertTrue(r["summary"])

    def test_mid_item_cheaper_than_count(self):
        r = compare_price(BY_ID["lst_020"])        # $16
        self.assertEqual(r["cheaper_than"], 13)
        self.assertEqual(r["verdict"], "below")

    def test_priciest_top_is_above(self):
        r = compare_price(BY_ID["lst_008"])        # $35
        self.assertAlmostEqual(r["median_price"], 20.5)
        self.assertEqual(r["cheaper_than"], 0)
        self.assertEqual(r["verdict"], "above")

    def test_bottoms_above_median(self):
        r = compare_price(BY_ID["lst_001"])        # $38
        self.assertEqual(r["compared_with"], 9)
        self.assertAlmostEqual(r["median_price"], 30.0)
        self.assertEqual(r["cheaper_than"], 0)
        self.assertEqual(r["verdict"], "above")

    def test_shoes_small_category(self):
        r = compare_price(BY_ID["lst_009"])        # $55
        self.assertEqual(r["compared_with"], 3)
        self.assertAlmostEqual(r["median_price"], 44.0)
        self.assertEqual(r["verdict"], "above")

    def test_summary_mentions_price(self):
        self.assertIn("$15", compare_price(BY_ID["lst_017"])["summary"])

    def test_custom_listings_at_median(self):
        item = {"id": "x", "category": "tops", "price": 20.0}
        listings = [
            item,
            {"id": "a", "category": "tops", "price": 10.0},
            {"id": "b", "category": "tops", "price": 20.0},
            {"id": "c", "category": "tops", "price": 30.0},
            {"id": "d", "category": "shoes", "price": 1.0},
        ]
        r = compare_price(item, listings)
        self.assertEqual(r["compared_with"], 3)
        self.assertAlmostEqual(r["median_price"], 20.0)
        self.assertEqual(r["cheaper_than"], 1)
        self.assertEqual(r["verdict"], "at")

    def test_custom_listings_ignore_real_data(self):
        item = {"id": "x", "category": "tops", "price": 5.0}
        listings = [{"id": "a", "category": "tops", "price": 50.0}]
        r = compare_price(item, listings)
        self.assertEqual(r["compared_with"], 1)
        self.assertEqual(r["verdict"], "below")
        self.assertEqual(r["cheaper_than"], 1)

    def test_empty_category_shape(self):
        item = {"id": "x", "category": "tops", "price": 5.0}
        r = compare_price(item, [item, {"id": "a", "category": "shoes", "price": 9.0}])
        self.assertEqual(set(r), self.KEYS)
        self.assertEqual(r["compared_with"], 0)
        self.assertIsNone(r["median_price"])
        self.assertEqual(r["cheaper_than"], 0)
        self.assertIsNone(r["verdict"])
        self.assertTrue(r["summary"])

    def test_none_item_shape(self):
        r = compare_price(None)
        self.assertEqual(set(r), self.KEYS)
        self.assertEqual(r["compared_with"], 0)
        self.assertIsNone(r["median_price"])
        self.assertIsNone(r["verdict"])
        self.assertTrue(r["summary"])

    def test_empty_dict_item_shape(self):
        r = compare_price({})
        self.assertEqual(set(r), self.KEYS)
        self.assertEqual(r["compared_with"], 0)
        self.assertIsNone(r["verdict"])

    def test_empty_listings_list(self):
        item = {"id": "x", "category": "tops", "price": 5.0}
        r = compare_price(item, [])
        self.assertEqual(r["compared_with"], 0)
        self.assertIsNone(r["verdict"])


if __name__ == "__main__":
    unittest.main()
