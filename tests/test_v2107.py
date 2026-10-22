"""v2.10.7: hình nổ đỏ đầu báo cáo ghi mức chữ + điểm tổng."""
import unittest

from focus.report_html import header


class HeaderBurstTest(unittest.TestCase):
    def test_score_and_word_inside(self):
        for score, word in ((12, "KÉM"), (41, "CHƯA TỐT"), (63, "TRUNG BÌNH"), (71, "TỐT"), (92, "XUẤT SẮC")):
            h = header("K", "T", "S", score)
            self.assertIn(f"class='bn'>{score}</text>", h)
            self.assertIn(f">{word}</text>", h)
            self.assertIn(">/100</text>", h)
            self.assertNotIn("burst small", h)

    def test_long_word_is_squeezed_to_fit(self):
        self.assertIn("textLength='50'", header("K", "T", "S", 63))
        self.assertNotIn("textLength", header("K", "T", "S", 92))

    def test_no_score_small_empty_burst(self):
        h = header("K", "T", "S")
        self.assertIn("burst small", h)
        self.assertNotIn("class='bn'", h)
