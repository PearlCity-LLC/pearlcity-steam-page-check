import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "checker"))
from steam_check import date_score, about_tip


class DateScore(unittest.TestCase):
    def s(self, d): return date_score(d)[0]

    def test_month_beats_coming_soon(self):
        self.assertGreater(self.s("January 2027"), self.s("Coming soon"))
        self.assertGreater(self.s("Jan 2027"), self.s("To be announced"))

    def test_ordering(self):
        self.assertEqual(self.s("15 Jan, 2027"), 8)
        self.assertEqual(self.s("Jan 15, 2027"), 8)
        self.assertEqual(self.s("January 2027"), 7)
        self.assertEqual(self.s("Q1 2027"), 5)
        self.assertEqual(self.s("Spring 2027"), 5)
        self.assertEqual(self.s("2027"), 4)
        self.assertEqual(self.s("Coming soon"), 2)
        self.assertEqual(self.s(""), 0)


class AboutTip(unittest.TestCase):
    def test_low_words_only(self):
        t = about_tip(50, 3)
        self.assertIn("50 words", t)
        self.assertNotIn("GIF", t)

    def test_media_only(self):
        t = about_tip(400, 0)
        self.assertIn("GIF", t)
        self.assertNotIn("words", t)

    def test_both(self):
        t = about_tip(50, 0)
        self.assertIn("words", t); self.assertIn("GIF", t)


if __name__ == "__main__":
    unittest.main()
