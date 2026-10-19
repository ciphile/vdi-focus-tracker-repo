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


MON, FRI = "2026-10-12", "2026-10-16"


class RealWorkAndLateOtTest(TempCase):
    """Ví dụ của người dùng: hôm nay 2 giờ trong VDI, tối OT 3 giờ. OT thuộc đúng ngày nó xảy ra."""

    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))   # mặc định: giờ làm 08:00–17:00, tổng kết 17:00
        insert_run(self.db, MON, "09:00", 120)                      # thứ Hai: 2 giờ trong VDI
        insert_run(self.db, MON, "16:30", 30, vdi="minimized")
        insert_run(self.db, MON, "19:00", 180)                      # tối thứ Hai: OT 3 giờ (sau báo cáo)
        insert_run(self.db, TUE, "09:00", 60)                       # thứ Ba: 1 giờ

    def test_ot_counts_for_the_day_it_happened(self):
        mon, tue = analyze(self.db, self.cfg, MON), analyze(self.db, self.cfg, TUE)
        self.assertEqual(report.real_work_line(mon), "💼 Thực làm trong VDI: 5h 00m (trong giờ 2h 00m + OT 3h 00m)")
        self.assertEqual(report.real_work_line(tue), "💼 Thực làm trong VDI: 1h 00m (chưa có OT)")

    def test_next_day_report_repeats_last_night_ot_without_adding_it(self):
        late = report.late_ot(self.db, self.cfg, TUE)
        self.assertEqual(len(late), 1)
        self.assertEqual(late[0]["day"], MON)
        self.assertEqual(round(late[0]["late"] / 60), 180)
        text = report.summary_text(analyze(self.db, self.cfg, TUE), {}, None, late)
        self.assertIn("🌙 OT T2 12/10 sau giờ báo cáo: 3h 00m (19:00–22:00) → T2 12/10 thực làm trong VDI tổng 5h 00m",
                      text)
        self.assertIn("💼 Thực làm trong VDI: 1h 00m (chưa có OT)", text)   # hôm nay vẫn chỉ 1 giờ
        html = report_html.render_day(self.cfg, analyze(self.db, self.cfg, TUE), {}, [], {"late_ot": late})
        self.assertIn("thực làm trong VDI tổng 5h 00m", html)
        self.assertIn("không cộng vào hôm nay", html)

    def test_ot_before_report_is_not_repeated(self):
        insert_run(self.db, "2026-10-14", "09:00", 30)
        insert_run(self.db, "2026-10-14", "17:00", 0.5)             # 30 giây sau 17:00: chưa đủ 1 phút
        self.assertEqual(report.late_ot(self.db, self.cfg, "2026-10-15"), [])
        self.assertEqual(report.late_ot(self.db, self.cfg, "2026-10-14"), [])  # thứ Ba không có OT sau báo cáo

    def test_weekend_make_up_shown_on_monday(self):
        insert_run(self.db, FRI, "09:00", 60)
        insert_run(self.db, "2026-10-17", "10:00", 45)               # thứ Bảy làm bù
        late = report.late_ot(self.db, self.cfg, "2026-10-19")
        self.assertEqual([r["day"] for r in late], ["2026-10-17"])
        self.assertIn("🌙 làm bù T7 17/10", report.late_ot_texts(late)[0])
