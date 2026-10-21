"""2.5.0: việc tồn cộng dồn qua các ngày làm việc (việc tồn hôm qua chưa ghi xong thì thành việc tồn hôm nay)."""
import os

from focus import pending, report
from focus.analysis import day_facts, off_day
from focus.storage import db_path, open_db, save_note
from tests.helpers import TempCase

MON, TUE, WED, THU, FRI = "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"
NEXT_MON = "2026-10-19"


class CarryPendingTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))

    def prev(self, day):
        return pending.previous_pending(self.db, self.cfg, day, off_day)

    def test_yesterday_pending_without_update_becomes_today_pending(self):
        save_note(self.db, MON, {"plan": "Sửa job CL01\nViết spec API"})
        save_note(self.db, TUE, {"plan": "Review PR"})  # thứ Ba không nhắc lại 2 việc của thứ Hai, không ghi output
        last, items = self.prev(WED)
        self.assertEqual(last, TUE)
        self.assertEqual(items, [("plan", "Sửa job CL01", MON), ("plan", "Viết spec API", MON), ("plan", "Review PR", TUE)])
        text = pending.pending_text(last, items)
        self.assertIn("cộng dồn", text)
        self.assertIn("• Sửa job CL01 (tồn từ T2 12/10)", text)
        self.assertIn("• Review PR\n", text, "việc của chính ngày làm việc trước không cần ghi ngày")

    def test_done_on_a_later_day_drops_the_item(self):
        save_note(self.db, MON, {"plan": "Sửa job CL01\nViết spec API", "issues": "thiếu quyền PRDLIB"})
        save_note(self.db, TUE, {"output": "đã sửa xong job CL01 (10:00)\nđã có quyền PRDLIB"})
        last, items = self.prev(WED)
        self.assertEqual(items, [("plan", "Viết spec API", MON)])

    def test_day_without_any_note_keeps_items(self):
        save_note(self.db, MON, {"plan": "Viết spec API"})
        last, items = self.prev(THU)  # thứ Ba, thứ Tư không ghi gì
        self.assertEqual((last, items), (MON, [("plan", "Viết spec API", MON)]))
        self.assertTrue(pending.pending_text(last, items).startswith("📌 Việc còn tồn từ thứ Hai 12/10"))

    def test_weekend_is_skipped_and_old_items_expire(self):
        save_note(self.db, FRI, {"plan": "Gửi estimation"})
        self.assertEqual(self.prev(NEXT_MON)[1], [("plan", "Gửi estimation", FRI)])
        self.assertEqual(self.prev("2026-10-30")[1], [("plan", "Gửi estimation", FRI)])  # thứ Sáu là ngày thứ 10
        self.assertEqual(self.prev("2026-11-02"), (None, []), "quá 10 ngày làm việc thì thôi nhắc")

    def test_no_duplicates_when_plan_repeats(self):
        save_note(self.db, MON, {"plan": "Viết spec API"})
        save_note(self.db, TUE, {"plan": "viết spec api"})
        self.assertEqual(self.prev(WED)[1], [("plan", "Viết spec API", MON)])

    def test_more_items_than_shown(self):
        save_note(self.db, MON, {"plan": "\n".join(f"việc số {i} khác nhau x{i}" for i in range(13))})
        text = pending.pending_text(*self.prev(TUE))
        self.assertIn("… và 3 việc nữa", text)

    def test_pending_after_includes_the_day_itself(self):
        save_note(self.db, MON, {"plan": "Viết spec API"})
        save_note(self.db, TUE, {"plan": "Review PR", "output": "review PR xong"})
        self.assertEqual(pending.pending_after(self.db, self.cfg, TUE, off_day), [("plan", "Viết spec API", MON)])
        facts = day_facts(self.db, self.cfg, TUE)
        self.assertEqual(facts["pending_carry"], ["Viết spec API (tồn từ T2 12/10)"])

    def test_html_report_shows_carried_items(self):
        save_note(self.db, MON, {"plan": "Viết spec API", "issues": "VDI chậm"})
        path, _ = report.write_report(self.db, self.cfg, TUE)
        html = open(path, encoding="utf-8").read()
        self.assertIn("📌 Việc tồn sang ngày mai", html)
        self.assertIn("Viết spec API <small class='mut'>· tồn từ T2 12/10", html)
        self.assertIn("⚠️ issue: VDI chậm", html)

    def test_html_report_without_pending(self):
        path, _ = report.write_report(self.db, self.cfg, TUE)
        self.assertIn("không còn việc tồn", open(path, encoding="utf-8").read())


class ReportCardsTest(TempCase):
    """Báo cáo HTML: thẻ lớn cho chỉ số phụ, TB mỗi lần, OT = 0 không hiện thẻ, chú thích màu trắng, khung lời AI."""
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))

    def html(self, day=TUE):
        path, _ = report.write_report(self.db, self.cfg, day)
        return open(path, encoding="utf-8").read()

    def test_cards_without_ot(self):
        from tests.helpers import insert_run
        insert_run(self.db, TUE, "09:00", 60)
        h = self.html()
        for label in ("Điểm tập trung", "Khối tập trung dài nhất", "Lần bị cắt ngang mỗi giờ",
                      "Inactive / rời máy ≥ 10 phút", "Chuỗi ngày đạt mục tiêu", "VDI bị đóng / tự ngắt"):
            self.assertIn(f"<div class='k'>{label}", h)
        self.assertNotIn("<div class='k'>Làm ngoài giờ trong VDI (OT)", h, "OT = 0 thì không hiện thẻ OT")
        self.assertIn("<div class='v num'>0 lần</div><div class='k'>VDI bị đóng", h, "thẻ khác = 0 vẫn hiện")
        self.assertNotIn("class='chips'", h, "chỉ số phụ nằm trong thẻ lớn, không còn chip nhỏ")
        self.assertEqual(h.count("TB mỗi lần"), 4, "ngoài VDI, thu nhỏ, inactive, rời máy: ghi TB mỗi lần")
        self.assertIn("Trắng: không ghi", h)
        self.assertIn("Nghỉ trưa 11:15–12:30 (không tính)", h)
        self.assertIn("<h2>Lời khuyên của AI</h2><div class='card mut'>Chưa có lời AI", h)

    def test_ot_card_when_ot(self):
        from tests.helpers import insert_run
        insert_run(self.db, TUE, "09:00", 30)
        insert_run(self.db, TUE, "17:30", 20)
        h = self.html()
        self.assertIn("<div class='k'>Làm ngoài giờ trong VDI (OT)</div><div class='s'>17:30–17:50", h)

    def test_ai_review_shown(self):
        from tests.helpers import insert_run
        insert_run(self.db, TUE, "09:00", 30)
        self.db.execute("INSERT INTO ai_cache VALUES (?,?,?)", (f"review:{TUE}:x", 1.0, "Lời AI thật"))
        self.assertIn("<div class='ai'><div class='aisec'><p>Lời AI thật</p></div></div>", self.html())

    def test_demo_has_sample_ai_reviews(self):
        import contextlib
        import io
        from focus.demo import make_demo
        with contextlib.redirect_stdout(io.StringIO()):
            path = make_demo(self.cfg)
        h = open(path, encoding="utf-8").read()
        self.assertIn("Lời AI MẪU", h)
        week = [f for f in os.listdir(os.path.dirname(path)) if f.startswith("focus-week-")][0]
        self.assertIn("Lời AI MẪU", open(os.path.join(os.path.dirname(path), week), encoding="utf-8").read())
