"""Tests for style memory (utils/wardrobe_store.py + app.py wiring). Fully offline.

Every test works in its own temp dir. The real data/my_wardrobe.json is never
touched; setUpModule/tearDownModule verify that.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import config
from utils import wardrobe_store as ws
from utils.data_loader import get_example_wardrobe

REAL = Path(__file__).resolve().parent.parent / "data" / "my_wardrobe.json"
_before = None


def _stat(p):
    return (p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None


def setUpModule():
    global _before
    _before = _stat(REAL)


def tearDownModule():
    assert _stat(REAL) == _before, "real data/my_wardrobe.json was touched by the tests"


LISTING = {"id": "L1", "title": "Vintage Levi's 501", "category": "bottoms",
           "colors": ["blue"], "style_tags": ["vintage", "denim"], "price": 19,
           "platform": "depop"}


def fake_session(error=None, item=LISTING):
    return {"error": error, "selected_item": None if error else dict(item),
            "price_check": {"summary": "fair"}, "outfit_suggestion": "wear it",
            "fit_card": "card"}


class TmpCase(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.dir = Path(td.name)
        self.path = self.dir / "w.json"

    def raw(self):
        return json.loads(self.path.read_text(encoding="utf-8"))


class TestLoad(TmpCase):
    def test_missing_is_none(self):
        self.assertIsNone(ws.load_saved_wardrobe(self.path))

    def test_valid_only_items_key(self):
        self.path.write_text(json.dumps({"items": [{"id": "w_001"}], "extra": 1}), encoding="utf-8")
        self.assertEqual(ws.load_saved_wardrobe(self.path), {"items": [{"id": "w_001"}]})

    def test_corrupt_raises_and_file_unchanged(self):
        for blob in (b"{not json", b"[1, 2]", b'"str"', b'{"items": "x"}',
                     b'{"items": [{"a": 1}, 5]}', b'{}', b"\xff\xfe\x00bad"):
            with self.subTest(blob=blob):
                self.path.write_bytes(blob)
                with self.assertRaises(ws.WardrobeFileError):
                    ws.load_saved_wardrobe(self.path)
                self.assertEqual(self.path.read_bytes(), blob)

    def test_corrupt_not_overwritten_by_add(self):
        self.path.write_bytes(b"{oops")
        with self.assertRaises(ws.WardrobeFileError):
            ws.add_item("tee", "tops", path=self.path)
        self.assertEqual(self.path.read_bytes(), b"{oops")


class TestSave(TmpCase):
    def test_round_trip_and_parent_dirs(self):
        p = self.dir / "a" / "b" / "w.json"
        data = {"items": [{"id": "w_001", "name": "tee"}]}
        ws.save_wardrobe(data, p)
        self.assertEqual(ws.load_saved_wardrobe(p), data)

    def test_no_tmp_left_behind(self):
        ws.save_wardrobe({"items": []}, self.path)
        ws.save_wardrobe({"items": [{"id": "w_001"}]}, self.path)
        self.assertEqual([f.name for f in self.dir.iterdir()], ["w.json"])
        self.assertEqual(list(self.dir.glob(".wardrobe-*.tmp")), [])

    def test_unicode_survives(self):
        ws.save_wardrobe({"items": [{"id": "w_001", "name": "café 毛衣 ñ"}]}, self.path)
        self.assertEqual(ws.load_saved_wardrobe(self.path)["items"][0]["name"], "café 毛衣 ñ")
        self.assertIn("café", self.path.read_text(encoding="utf-8"))


class TestAddItem(TmpCase):
    def test_ids_sequential(self):
        a = ws.add_item("a", "tops", path=self.path)
        b = ws.add_item("b", "shoes", path=self.path)
        self.assertEqual((a["id"], b["id"]), ("w_001", "w_002"))
        self.assertEqual(len(self.raw()["items"]), 2)

    def test_continues_after_max_with_gaps(self):
        ws.save_wardrobe({"items": [{"id": "w_001"}, {"id": "w_005"}]}, self.path)
        self.assertEqual(ws.add_item("x", "tops", path=self.path)["id"], "w_006")

    def test_ignores_non_matching_ids(self):
        ws.save_wardrobe({"items": [{"id": "ex_9"}, {"id": "w_abc"}, {"id": "w_002x"}, {}]}, self.path)
        self.assertEqual(ws.add_item("x", "tops", path=self.path)["id"], "w_001")

    def test_cleaning(self):
        item = ws.add_item("  Tee  ", "tops", colors=[" Black ", "", "  "],
                           style_tags=("MINIMAL", " "), notes="  hi  ", path=self.path)
        self.assertEqual(item["name"], "Tee")
        self.assertEqual(item["colors"], ["black"])
        self.assertEqual(item["style_tags"], ["minimal"])
        self.assertEqual(item["notes"], "hi")

    def test_notes_optional(self):
        for n in (None, "", "   "):
            item = ws.add_item("t", "tops", notes=n, path=self.path)
            self.assertNotIn("notes", item)

    def test_bad_name(self):
        for n in ("", "   ", None):
            with self.assertRaises(ValueError):
                ws.add_item(n, "tops", path=self.path)

    def test_bad_category_and_case(self):
        with self.assertRaises(ValueError):
            ws.add_item("t", "hats", path=self.path)
        with self.assertRaises(ValueError):
            ws.add_item("t", "", path=self.path)
        self.assertEqual(ws.add_item("t", "Tops", path=self.path)["category"], "tops")

    def test_failed_add_leaves_file_untouched(self):
        ws.add_item("t", "tops", path=self.path)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            ws.add_item("", "tops", path=self.path)
        with self.assertRaises(ValueError):
            ws.add_item("x", "nope", path=self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_add_creates_no_file(self):
        with self.assertRaises(ValueError):
            ws.add_item("", "tops", path=self.path)
        self.assertFalse(self.path.exists())


class TestAddListing(TmpCase):
    def test_fields(self):
        item, added = ws.add_listing(LISTING, path=self.path)
        self.assertTrue(added)
        self.assertEqual(item["id"], "w_001")
        self.assertEqual(item["name"], LISTING["title"])
        self.assertEqual(item["category"], "bottoms")
        self.assertEqual(item["colors"], ["blue"])
        self.assertEqual(item["style_tags"], ["vintage", "denim"])
        self.assertEqual(item["notes"], "Thrifted on depop for $19")
        self.assertEqual(item["source_listing"], "L1")
        self.assertEqual(self.raw()["items"], [item])

    def test_duplicate(self):
        first, a1 = ws.add_listing(LISTING, path=self.path)
        again, a2 = ws.add_listing(LISTING, path=self.path)
        self.assertEqual((a1, a2), (True, False))
        self.assertEqual(again, first)
        self.assertEqual(len(self.raw()["items"]), 1)

    def test_invalid(self):
        for bad in (None, {}, {"title": "no id"}):
            with self.assertRaises(ValueError):
                ws.add_listing(bad, path=self.path)
        self.assertFalse(self.path.exists())

    def test_cents(self):
        item, _ = ws.add_listing({**LISTING, "price": 24.5}, path=self.path)
        self.assertTrue(item["notes"].endswith("for $24.50"), item["notes"])


class TestRemoveClear(TmpCase):
    def test_remove(self):
        ws.add_item("a", "tops", path=self.path)
        ws.add_item("b", "tops", path=self.path)
        self.assertTrue(ws.remove_item("w_001", self.path))
        self.assertEqual([i["id"] for i in self.raw()["items"]], ["w_002"])

    def test_remove_unknown_unchanged(self):
        ws.add_item("a", "tops", path=self.path)
        before = self.path.read_bytes()
        self.assertFalse(ws.remove_item("w_099", self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_remove_no_file(self):
        self.assertFalse(ws.remove_item("w_001", self.path))
        self.assertFalse(self.path.exists())

    def test_clear(self):
        ws.add_item("a", "tops", path=self.path)
        self.assertTrue(ws.has_saved_wardrobe(self.path))
        self.assertTrue(ws.clear_saved_wardrobe(self.path))
        self.assertFalse(ws.has_saved_wardrobe(self.path))
        self.assertFalse(ws.clear_saved_wardrobe(self.path))


class AppCase(TmpCase):
    def setUp(self):
        super().setUp()
        p = patch.object(config, "WARDROBE_PATH", self.path)
        p.start()
        self.addCleanup(p.stop)

    def run_cli(self, *argv, session=None):
        """Run a CLI command, return (stdout, run_agent mock)."""
        args = app.build_parser().parse_args(list(argv))
        buf = io.StringIO()
        with patch("agent.run_agent", return_value=session or fake_session()) as m, \
                patch("generate.usage", return_value="usage-line"), \
                contextlib.redirect_stdout(buf):
            args.func(args)
        return buf.getvalue(), m


class TestPickWardrobe(AppCase):
    def pick(self, empty=False):
        args = app.build_parser().parse_args(["ask", "q"] + (["--empty-wardrobe"] if empty else []))
        with contextlib.redirect_stdout(io.StringIO()):
            return app._pick_wardrobe(args)

    def test_example_when_no_file(self):
        self.assertEqual(self.pick(), get_example_wardrobe())

    def test_saved_beats_example(self):
        ws.add_item("mine", "tops", path=self.path)
        w = self.pick()
        self.assertEqual([i["name"] for i in w["items"]], ["mine"])

    def test_empty_beats_saved(self):
        ws.add_item("mine", "tops", path=self.path)
        self.assertEqual(self.pick(empty=True)["items"], [])


class TestAskKeep(AppCase):
    def test_keep_first_time(self):
        out, m = self.run_cli("ask", "levis", "--keep")
        self.assertIn("Kept:", out)
        self.assertIn("Started a saved wardrobe", out)
        self.assertEqual(self.raw()["items"][0]["source_listing"], "L1")
        self.assertEqual(m.call_args[0][1], get_example_wardrobe())

    def test_keep_second_time_no_started_note(self):
        ws.add_item("mine", "tops", path=self.path)
        out, m = self.run_cli("ask", "levis", "--keep")
        self.assertIn("Kept:", out)
        self.assertNotIn("Started a saved wardrobe", out)
        self.assertEqual(len(self.raw()["items"]), 2)
        self.assertEqual([i["name"] for i in m.call_args[0][1]["items"]], ["mine"])

    def test_keep_same_twice_reports_already(self):
        self.run_cli("ask", "levis", "--keep")
        out, _ = self.run_cli("ask", "levis", "--keep")
        self.assertIn("already in your wardrobe", out)
        self.assertEqual(len(self.raw()["items"]), 1)

    def test_keep_with_error_saves_nothing(self):
        out, _ = self.run_cli("ask", "levis", "--keep", session=fake_session(error="nothing found"))
        self.assertIn("nothing found", out)
        self.assertNotIn("Kept:", out)
        self.assertFalse(self.path.exists())

    def test_no_keep_flag_saves_nothing(self):
        out, _ = self.run_cli("ask", "levis")
        self.assertNotIn("Kept:", out)
        self.assertFalse(self.path.exists())


class TestWardrobeCommands(AppCase):
    def test_add_show_remove_clear(self):
        out, _ = self.run_cli("wardrobe", "add", "black wide-leg jeans", "--category", "bottoms",
                              "--colors", "Black, grey", "--tags", "minimal", "--notes", "fav")
        self.assertIn("Saved w_001: black wide-leg jeans (bottoms).", out)
        item = self.raw()["items"][0]
        self.assertEqual(item["colors"], ["black", "grey"])
        self.assertEqual(item["style_tags"], ["minimal"])
        self.assertEqual(item["notes"], "fav")

        out, _ = self.run_cli("wardrobe", "show")
        self.assertIn("w_001", out)
        self.assertIn("black wide-leg jeans", out)
        self.assertIn("1 items", out)

        out, _ = self.run_cli("wardrobe", "remove", "w_001")
        self.assertIn("Removed w_001.", out)
        self.assertEqual(self.raw()["items"], [])
        out, _ = self.run_cli("wardrobe", "show")
        self.assertIn("empty", out)

        out, _ = self.run_cli("wardrobe", "remove", "w_001")
        self.assertIn("There's no w_001", out)

        out, _ = self.run_cli("wardrobe", "clear")
        self.assertIn("Forgot your saved wardrobe", out)
        self.assertFalse(self.path.exists())
        out, _ = self.run_cli("wardrobe", "clear")
        self.assertIn("There was no saved wardrobe to clear.", out)

    def test_show_no_file(self):
        out, _ = self.run_cli("wardrobe", "show")
        self.assertIn("No saved wardrobe yet", out)
        self.assertIn("example wardrobe", out)
        self.assertFalse(self.path.exists())

    def test_bad_category_rejected_by_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            app.build_parser().parse_args(["wardrobe", "add", "x", "--category", "hats"])


if __name__ == "__main__":
    unittest.main()
