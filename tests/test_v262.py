"""2.6.2: báo cáo ngày cộng lại giờ làm: trong VDI + ngoài VDI + inactive + rời máy + không ghi = giờ làm chính thức."""
from focus import report, report_html
from focus.analysis import analyze, time_breakdown
from focus.storage import db_path, open_db, save_note
from tests.helpers import TempCase, insert_run, ts

TUE, SAT = "2026-10-13", "2026-10-17"


class BreakdownTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        insert_run(self.db, TUE, "08:00", 195)                      # 08:00–11:15 trong VDI
        insert_run(self.db, TUE, "12:30", 90, vdi="minimized")      # 12:30–14:00 VDI thu nhỏ, dùng Chrome
        # 14:00–14:10 không có mẫu (tạm dừng / tắt tracker)
        insert_run(self.db, TUE, "14:10", 170)                      # 14:10–17:00 trong VDI

    def test_parts_add_up_to_official_hours(self):
        b = time_breakdown(analyze(self.db, self.cfg, TUE), now=ts(TUE, "20:00"))
        self.assertEqual(b["total"], 465)                           # 08:00–17:00 trừ trưa 11:15–12:30
        self.assertEqual(b["vdi"] + b["other"] + b["idle"] + b["away"] + b["unrecorded"], b["total"])
        self.assertEqual(b["other"], 90)
        self.assertEqual(b["minimized"], 90)                        # nằm trong ngoài VDI, không cộng thêm
        self.assertEqual(b["unrecorded"], 10)
        self.assertIsNone(b["until"])

    def test_mid_day_counts_until_now(self):
        with self.db:  # /today lúc 10:00: chưa có mẫu sau 10:00
            self.db.execute("DELETE FROM samples WHERE ts > ?", (ts(TUE, "10:00"),))
        b = time_breakdown(analyze(self.db, self.cfg, TUE), now=ts(TUE, "10:00"))
        self.assertEqual(b["total"], 120)
        self.assertEqual(b["until"], "10:00")

    def test_text_and_html_show_the_sum(self):
        a = analyze(self.db, self.cfg, TUE)
        text = report.summary_text(a, {})
        self.assertIn("🧮 Cộng giờ làm: trong VDI", text)
        self.assertIn("không ghi 10m = 7h 45m", text)
        self.assertIn("giờ làm 08:00–17:00 trừ trưa 11:15–12:30", text)
        self.assertIn("thu nhỏ VDI 1h 30m đã nằm trong ngoài VDI", text)
        lines = text.splitlines()
        self.assertLess(lines.index(next(x for x in lines if x.startswith("🧮"))),
                        lines.index(next(x for x in lines if x.startswith("Bị cắt ngang"))))
        html = report_html.render_day(self.cfg, a, {}, [], {})
        self.assertIn("class='banner sum'", html)
        self.assertIn("= 7h 45m", html)

    def test_half_day_leave(self):
        save_note(self.db, TUE, {"leave_part": "am"})
        a = analyze(self.db, self.cfg, TUE)
        b = time_breakdown(a, now=ts(TUE, "20:00"))
        self.assertEqual(b["total"], 270)                           # chỉ 12:30–17:00
        self.assertIn("đã trừ trưa và phần nghỉ phép", report.breakdown_parts(a, ts(TUE, "20:00"))[1])

    def test_no_line_for_off_day_or_no_data(self):
        insert_run(self.db, SAT, "09:00", 30)
        self.assertIsNone(time_breakdown(analyze(self.db, self.cfg, SAT)))
        self.assertIsNone(time_breakdown(analyze(self.db, self.cfg, "2026-10-14")))
        self.assertIsNone(time_breakdown({"has_data": True}))       # số liệu cũ không có giờ làm: không vẽ dòng
