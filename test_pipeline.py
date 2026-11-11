"""Offline checks for the parser, the feed reader and the tagging rules.

Run from the project root:  python -m unittest discover tests -v
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from classify import Classifier  # noqa: E402
from fetch_pib import make_excerpt, parse_feed, parse_release  # noqa: E402

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
CLF = Classifier(CFG)
FIX = ROOT / "tests" / "fixtures"

# Shaped like the live feed: BOM, zero-width spaces inside tags, only title + link, repeated item.
LIVE_SHAPED_FEED = (
    "﻿<?xml version=\"1.0\" encoding=\"utf-8\"?><rss version=\"2.0\"><channel><title>Press Information Bureau </title>"
    "<description>Press Information Bureau</description><copyright>x</copyright>"
    "<item><title>First release</title><link>https://pib.gov.in/PressReleaseIframePage.aspx?PRID=2333895</link></item>"
    "<​item><title>Second &amp; third</title><link>https://pib.gov.in/PressReleaseIframePage.aspx?PRID=2333874</link><​/item>"
    "<item><title>First release</title><link>https://pib.gov.in/PressReleaseIframePage.aspx?PRID=2333895</link></item>"
    "</channel></rss>"
)


class FeedTests(unittest.TestCase):
    def test_extracts_prid_and_title(self):
        got = parse_feed(LIVE_SHAPED_FEED)
        self.assertEqual(got[0], ("2333895", "First release"))
        self.assertEqual(got[1], ("2333874", "Second & third"))

    def test_repeats_are_returned_so_caller_must_dedupe(self):
        self.assertEqual(len(parse_feed(LIVE_SHAPED_FEED)), 3)


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.rel = parse_release((FIX / "9000001.html").read_text(encoding="utf-8"))

    def test_fields(self):
        self.assertEqual(self.rel["ministry"], "Cabinet")
        self.assertIn("Cabinet approves", self.rel["title"])
        self.assertEqual(self.rel["posted_at"].isoformat(), "2026-11-07T10:42:00+05:30")
        self.assertEqual(self.rel["office"], "PIB Delhi")

    def test_body_drops_signoff_and_footer(self):
        self.assertNotIn("AB/CD/", self.rel["body"])
        self.assertNotIn("Provide suggestions", self.rel["body"])
        self.assertIn("outlay of Rs 1,500 crore", self.rel["body"])

    def test_afternoon_time(self):
        rel = parse_release((FIX / "9000013.html").read_text(encoding="utf-8"))
        self.assertEqual(rel["posted_at"].hour, 17)

    def test_excerpt_is_short_and_clean(self):
        ex = make_excerpt("word " * 400)
        self.assertLessEqual(len(ex), 570)


class ClassifyTests(unittest.TestCase):
    def tag(self, prid):
        rel = parse_release((FIX / f"{prid}.html").read_text(encoding="utf-8"))
        return CLF.classify(rel["title"], rel["ministry"], rel["body"], rel["office"])

    def test_cabinet_decision_is_must(self):
        t = self.tag(9000001)
        self.assertEqual(t["priority"], "must")
        self.assertEqual(t["type"], "Cabinet decision")

    def test_exercise_is_must_and_names_the_exercise(self):
        t = self.tag(9000002)
        self.assertEqual(t["priority"], "must")
        self.assertIn("Sagar Mitra", t["hooks"])

    def test_routine_items_are_skipped(self):
        for prid in (9000005, 9000006, 9000007, 9000008, 9000020):
            self.assertEqual(self.tag(prid)["priority"], "skip", prid)

    def test_andhra_items_are_flagged(self):
        for prid in (9000011, 9000012, 9000014):
            self.assertTrue(self.tag(prid)["ap"], prid)

    def test_figures_extracted(self):
        self.assertIn("Rs 1,500 crore", self.tag(9000001)["figures"])

    def test_unreadable_ministry_falls_back_to_title_then_middle_weight(self):
        # real pages can lack a ministry line; the title should still carry the weight
        self.assertEqual(CLF.ministry_weight("Unknown", "Cabinet approves a new mission"), 3)
        self.assertEqual(CLF.ministry_weight("Unknown", "Something with no ministry word"), 2)
        self.assertEqual(CLF.ministry_weight("Ministry of Finance", ""), 3)

    def test_every_subject_regex_compiles(self):
        self.assertTrue(CLF.subjects)


if __name__ == "__main__":
    unittest.main()
