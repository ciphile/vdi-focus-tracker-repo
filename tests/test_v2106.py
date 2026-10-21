"""v2.10.6: lọc lời AI cuối ngày: bỏ tên mục lời chúc, báo cáo HTML tô nổi tên các mục."""
import datetime as dt
import unittest
from unittest import mock

from focus import ai_client, motivation
from focus.analysis import day_facts
from focus.report_html import CSS, ai_box
from focus.review_text import drop_wish_heading, sections
from focus.storage import db_path, open_db
from tests.helpers import TempCase, insert_run

REVIEW = """Đánh giá ngày
Điểm tổng hôm nay là 71/100 (7,1/10).
Dòng thứ hai.

Việc tồn đọng
Danh sách việc cũ vẫn còn.

Khích lệ
Bờ rồ ráng lên. "Hãy trao gánh nặng ngươi cho Đức Giê-hô-va" (Thi-thiên 55:22)

Chúc buổi tối
Chúc bờ rồ có buổi tối thật ấm áp bên gia đình nhé."""


class WishHeadingTest(unittest.TestCase):
    def test_heading_removed_wish_kept(self):
        out = drop_wish_heading(REVIEW)
        self.assertNotIn("Chúc buổi tối", out)
        self.assertTrue(out.endswith("Chúc bờ rồ có buổi tối thật ấm áp bên gia đình nhé."))
        self.assertIn("Đánh giá ngày\nĐiểm tổng", out)  # các mục khác giữ nguyên
        self.assertIn("Việc tồn đọng\nDanh sách", out)

    def test_weekend_and_emoji_variants(self):
        for head in ("Chúc cuối tuần", "🌙 Chúc buổi tối", "Lời chúc cuối tuần", "chúc cuối tuần vui vẻ"):
            out = drop_wish_heading(f"Đánh giá\nTốt.\n\n{head}\nNghỉ ngơi nhé bờ rồ.")
            self.assertTrue(out.endswith("\n\nNghỉ ngơi nhé bờ rồ."), head)
            self.assertNotIn(head, out)

    def test_wish_without_heading_untouched(self):
        for t in ("Chúc bờ rồ ngủ ngon.", "Đánh giá\nTốt.\n\nChúc bờ rồ một buổi tối ấm áp, ngon giấc nhé!",
                  "", None, "Chỉ một dòng"):
            self.assertEqual(drop_wish_heading(t), t)

    def test_no_wish_returns_same_text(self):
        t = "Đánh giá ngày\nTốt.\n\nKhích lệ\nCố lên."
        self.assertIs(drop_wish_heading(t), t)

    def test_idempotent(self):
        once = drop_wish_heading(REVIEW)
        self.assertEqual(drop_wish_heading(once), once)

    def test_sections_split(self):
        s = sections(REVIEW)
        self.assertEqual([h for h, _ in s], ["Đánh giá ngày", "Việc tồn đọng", "Khích lệ", "Chúc buổi tối"])
        self.assertEqual(s[0][1], ["Điểm tổng hôm nay là 71/100 (7,1/10).", "Dòng thứ hai."])

    def test_long_first_line_is_not_heading(self):
        s = sections("Hôm nay bờ rồ làm việc rất chăm chỉ và đều đặn suốt cả ngày dài\nCố gắng nhé.")
        self.assertIsNone(s[0][0])
        s = sections("Cố lên bờ rồ!\nGiỏi lắm.")
        self.assertIsNone(s[0][0])


class AiBoxTest(unittest.TestCase):
    def test_headings_marked_wish_heading_gone(self):
        h = ai_box(REVIEW, "")
        self.assertEqual(h.count("<h3 class='aih'>"), 3)
        self.assertIn("<h3 class='aih'>Đánh giá ngày</h3>", h)
        self.assertNotIn("Chúc buổi tối", h)
        self.assertIn("Chúc bờ rồ có buổi tối thật ấm áp", h)
        self.assertIn("Điểm tổng hôm nay là 71/100 (7,1/10).<br>Dòng thứ hai.", h)

    def test_text_is_escaped(self):
        h = ai_box("Mục\n<script>alert(1)</script>", "")
        self.assertNotIn("<script>", h)

    def test_empty_shows_placeholder(self):
        self.assertIn("Chưa có lời AI", ai_box("", "Sẽ có sau."))

    def test_css_has_heading_style(self):
        self.assertIn(".aih{", CSS)


class ReviewReturnTest(TempCase):
    """Lời AI gửi Telegram (và lưu trong cache) không còn tên mục lời chúc, kể cả khi lấy lại từ cache."""

    def setUp(self):
        super().setUp()
        self.cfg["gemini_api_key"] = "k"
        self.db = open_db(db_path(self.cfg))
        self.day = dt.date.today().isoformat()
        insert_run(self.db, self.day, "09:00", 90)

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def test_daily_review_drops_wish_heading(self):
        calls = []

        def fake(cfg, prompt, system="", image=None, purpose=""):
            calls.append(purpose)
            return REVIEW, "m"
        facts = day_facts(self.db, self.cfg, self.day)
        with mock.patch.object(ai_client, "generate", fake):
            first, _ = motivation.review_day(self.cfg, self.db, facts)
            again, _ = motivation.review_day(self.cfg, self.db, facts)  # lần 2 lấy từ cache
        self.assertEqual(calls, ["daily_review"])
        for text in (first, again):
            self.assertNotIn("Chúc buổi tối", text)
            self.assertIn("Chúc bờ rồ có buổi tối thật ấm áp", text)
            self.assertIn("Việc tồn đọng\nDanh sách", text)


if __name__ == "__main__":
    unittest.main()
