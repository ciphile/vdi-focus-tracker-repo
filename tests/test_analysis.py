import datetime as dt

from focus import analysis
from focus.analysis import analyze, daily_stats, focus_score, golden_hours, in_golden, streak, week_facts
from focus.storage import open_db, db_path, save_note
from tests.helpers import TempCase, insert_run, ts

DAY = "2026-10-14"  # thứ Tư


class AnalysisTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))

    def a(self, day=DAY):
        return analyze(self.db, self.cfg, day)

    def test_empty_day(self):
        a = self.a()
        self.assertFalse(a["has_data"])
        self.assertEqual(focus_score(a), 0)
        self.assertIsNone(daily_stats(self.db, self.cfg, DAY))

    def test_one_hour_in_vdi_is_deep_focus(self):
        insert_run(self.db, DAY, "09:00", 60)
        a = self.a()
        self.assertAlmostEqual(a["deep"], 3600, delta=6)
        self.assertAlmostEqual(a["vdi"], 3600, delta=6)
        self.assertEqual(a["other"], 0)
        self.assertEqual(len(a["blocks"]), 1)

    def test_minimized_vdi_counts_as_distraction_not_work(self):
        insert_run(self.db, DAY, "09:00", 30)
        insert_run(self.db, DAY, "09:30", 15, vdi="minimized", proc="chrome.exe")
        insert_run(self.db, DAY, "09:45", 30)
        a = self.a()
        self.assertAlmostEqual(a["minimized"], 900, delta=6)
        self.assertAlmostEqual(a["other"], 900, delta=6)
        self.assertAlmostEqual(a["vdi"], 3600, delta=10)
        self.assertEqual(a["exits"], 1)
        self.assertEqual(len(a["blocks"]), 2, "15 phút thu nhỏ làm đứt khối tập trung")

    def test_side_by_side_counts_as_distraction(self):
        insert_run(self.db, DAY, "09:00", 30, vdi="background", proc="chrome.exe")
        a = self.a()
        self.assertEqual(a["deep"], 0)
        self.assertAlmostEqual(a["background"], 1800, delta=6)

    def test_short_switch_keeps_block(self):
        insert_run(self.db, DAY, "09:00", 30)
        insert_run(self.db, DAY, "09:30", 1, vdi="background", proc="teams.exe")
        insert_run(self.db, DAY, "09:31", 30)
        a = self.a()
        self.assertEqual(len(a["blocks"]), 1)
        self.assertAlmostEqual(a["deep"], 3600, delta=10)
        self.assertEqual(a["blocks"][0]["breaks"], 1)

    def test_short_blocks_not_deep(self):
        insert_run(self.db, DAY, "09:00", 15)
        insert_run(self.db, DAY, "09:15", 5, vdi="background", proc="chrome.exe")
        insert_run(self.db, DAY, "09:20", 15)
        a = self.a()
        self.assertEqual(a["deep"], 0)
        self.assertGreater(a["vdi"], 1700)

    def test_idle_and_away(self):
        insert_run(self.db, DAY, "09:00", 30)
        insert_run(self.db, DAY, "09:30", 3, idle_grow=True)   # ngồi yên 3 phút
        insert_run(self.db, DAY, "09:33", 30)
        insert_run(self.db, DAY, "10:03", 10, idle_grow=True)  # rời máy 10 phút
        insert_run(self.db, DAY, "10:13", 30)
        a = self.a()
        self.assertAlmostEqual(a["idle"], 180, delta=65)
        self.assertAlmostEqual(a["away"], 600, delta=10)
        self.assertEqual(a["short_idle_count"], 1)
        self.assertEqual(a["away_count"], 1)

    def idle_run(self, start, idles):
        """Mẫu 5 giây ngồi yên trước VDI, idle cho sẵn từng mẫu."""
        t0 = ts(DAY, start)
        with self.db:
            self.db.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)",
                                [(t0 + 5 * (i + 1), 5, idle, 0, "foreground", "cdviewer.exe", None, 1)
                                 for i, idle in enumerate(idles)])

    def test_single_touch_mid_absence_is_one_away(self):
        # Log thật 15/10: vắng 8 phút, có đúng 1 lần chạm ở giữa. Là 1 lần rời máy, không phải 2 lần ngồi yên ngắn.
        insert_run(self.db, DAY, "09:00", 30)
        self.idle_run("09:30", range(5, 241, 5))           # tới 09:34:00
        self.idle_run("09:34", range(2, 238, 5))           # chạm lẻ lúc 09:34:03 rồi ngồi yên tiếp tới 09:38
        insert_run(self.db, DAY, "09:38", 30)
        a = self.a()
        self.assertEqual(a["short_idle_count"], 0)
        self.assertEqual(a["away_count"], 1)
        self.assertAlmostEqual(a["away"], 480, delta=10)

    def test_touch_merges_two_short_idles(self):
        insert_run(self.db, DAY, "09:00", 30)
        self.idle_run("09:30", range(5, 121, 5))           # 2 phút
        self.idle_run("09:32", range(3, 119, 5))           # chạm lẻ rồi thêm 2 phút
        insert_run(self.db, DAY, "09:34", 30)
        self.assertEqual(self.a()["short_idle_count"], 1)

    def test_real_return_between_idles_not_merged(self):
        insert_run(self.db, DAY, "09:00", 30)
        self.idle_run("09:30", range(5, 121, 5))
        insert_run(self.db, DAY, "09:32", 1)               # làm tiếp 1 phút
        self.idle_run("09:33", range(5, 121, 5))
        insert_run(self.db, DAY, "09:35", 30)
        self.assertEqual(self.a()["short_idle_count"], 2)

    def test_locked_is_away(self):
        insert_run(self.db, DAY, "09:00", 30)
        insert_run(self.db, DAY, "09:30", 2, locked=True)
        insert_run(self.db, DAY, "09:32", 30)
        a = self.a()
        self.assertAlmostEqual(a["away"], 120, delta=10)

    def test_sleep_gap_is_away(self):
        insert_run(self.db, DAY, "09:00", 30)
        last = insert_run(self.db, DAY, "11:00", 30)
        with self.db:  # mẫu đầu sau khi máy thức: dur = khoảng ngủ
            self.db.execute("UPDATE samples SET dur=? WHERE ts=?", (ts(DAY, "11:00", 5) - ts(DAY, "09:30"), ts(DAY, "11:00", 5)))
        a = self.a()
        self.assertAlmostEqual(a["away"], 5400, delta=15)
        self.assertGreater(last, 0)

    def test_extra_focus_process(self):
        self.cfg["extra_focus_processes"] = ["code.exe"]
        insert_run(self.db, DAY, "09:00", 30, vdi="background", proc="code.exe")
        self.assertAlmostEqual(self.a()["vdi"], 1800, delta=6)

    def test_windowed_time(self):
        insert_run(self.db, DAY, "09:00", 30, full=False)
        insert_run(self.db, DAY, "09:30", 30, full=True)
        a = self.a()
        self.assertAlmostEqual(a["windowed"], 1800, delta=6)
        self.assertAlmostEqual(a["deep"], 3600, delta=10)

    def test_day_boundary(self):
        insert_run(self.db, "2026-10-13", "23:50", 20)
        a = self.a()
        self.assertAlmostEqual(a["ot"], 600, delta=6, msg="23:50–24:00 là làm ngoài giờ (OT)")
        self.assertEqual(a["vdi"], 0)

    def test_memo_refreshes_with_new_samples(self):
        insert_run(self.db, DAY, "09:00", 30)
        a1 = self.a()
        self.assertIs(self.a(), a1)
        insert_run(self.db, DAY, "09:30", 30)
        self.assertGreater(self.a()["vdi"], a1["vdi"])

    def test_score(self):
        insert_run(self.db, DAY, "12:30", 240)  # buổi chiều: không chạm giờ nghỉ trưa (giờ trưa không tính)
        self.assertEqual(focus_score(self.a()), 100)

    def test_hourly_and_golden(self):
        insert_run(self.db, DAY, "09:00", 60)
        insert_run(self.db, DAY, "14:00", 30)
        a = self.a()
        self.assertAlmostEqual(a["hourly"][9]["vdi"], 3600, delta=6)
        self.assertEqual(analysis.golden_hour(a["hourly"]), "09:00–10:00")

    def test_streak_skips_weekend_and_off_days(self):
        for day in ("2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13"):  # Thu, Fri, Mon, Tue
            insert_run(self.db, day, "12:30", 250)
        save_note(self.db, "2026-10-07", {"day_off": "nghỉ phép"})
        insert_run(self.db, "2026-10-06", "12:30", 250)
        insert_run(self.db, DAY, "08:00", 60)  # hôm nay chưa đạt: không đứt chuỗi
        self.assertEqual(streak(self.db, self.cfg, DAY), 5)
        insert_run(self.db, "2026-10-05", "08:00", 30)  # thứ Hai tuần trước không đạt
        self.assertEqual(streak(self.db, self.cfg, DAY), 5)

    def test_streak_broken_by_missing_workday(self):
        insert_run(self.db, "2026-10-13", "12:30", 250)
        insert_run(self.db, "2026-10-09", "12:30", 250)  # thứ Hai 12 không có dữ liệu
        self.assertEqual(streak(self.db, self.cfg, DAY), 1)

    def test_daily_stats_persist_after_samples_deleted(self):
        insert_run(self.db, "2026-10-13", "08:00", 120)
        rec = daily_stats(self.db, self.cfg, "2026-10-13")
        with self.db:
            self.db.execute("DELETE FROM samples")
        self.assertEqual(daily_stats(self.db, self.cfg, "2026-10-13")["deep"], rec["deep"])

    def test_daily_stats_past_day_recomputes_when_newer_samples(self):
        # /today lưu số liệu lúc 09:31, tracker bị tắt ngang trước khi chốt cuối ngày.
        insert_run(self.db, "2026-10-13", "09:00", 30)
        daily_stats(self.db, self.cfg, "2026-10-13", refresh=True)
        with self.db:
            self.db.execute("UPDATE daily_stats SET updated=?", (ts("2026-10-13", "09:31"),))
        insert_run(self.db, "2026-10-13", "10:00", 60)
        rec = daily_stats(self.db, self.cfg, "2026-10-13")
        self.assertAlmostEqual(rec["deep"], 5400, delta=15)
        updated = self.db.execute("SELECT updated FROM daily_stats").fetchone()[0]
        self.assertGreater(updated, ts("2026-10-13", "11:00"), "đã chốt lại thì lần sau dùng cache")

    def test_week_facts(self):
        insert_run(self.db, "2026-10-12", "12:30", 270)
        insert_run(self.db, "2026-10-13", "14:00", 60)
        save_note(self.db, "2026-10-13", {"issues": "- VDI chậm\n- thiếu quyền DB"})
        f = week_facts(self.db, self.cfg, DAY)
        self.assertEqual(f["work_days"], 2)
        self.assertEqual(f["days_reached_goal"], 1)
        self.assertIn("Thứ 2", f["best_day"])
        self.assertEqual(len(f["issues"]), 2)

    def test_golden_hours_need_five_days(self):
        days = ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
        for d in days:
            insert_run(self.db, d, "09:00", 120)
        self.assertEqual(golden_hours(self.db, self.cfg, DAY), [])
        insert_run(self.db, "2026-10-13", "09:00", 120)
        self.assertEqual(golden_hours(self.db, self.cfg, DAY), ["09:00-10:00", "10:00-11:00"])
        self.assertTrue(in_golden(["09:00-10:00"], "09:30"))
        self.assertFalse(in_golden(["09:00-10:00"], "10:00"))
        self.cfg["golden_hours"] = ["14:00-15:00"]
        self.assertEqual(golden_hours(self.db, self.cfg, DAY), ["14:00-15:00"])


class OvertimeTest(TempCase):
    """Yêu cầu 16/10: ngoài giờ làm (trưa, sau 17:00) chỉ cộng thời gian làm trong VDI (OT), không đo sao nhãng."""

    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))

    def test_evening_ot_only_counts_vdi_work(self):
        insert_run(self.db, DAY, "15:00", 60)
        insert_run(self.db, DAY, "16:00", 30, vdi="background", proc="chrome.exe")
        insert_run(self.db, DAY, "16:30", 60)                                         # 16:30–17:30 liền mạch
        insert_run(self.db, DAY, "17:30", 30, vdi="minimized", proc="chrome.exe")      # ngoài giờ: không tính
        insert_run(self.db, DAY, "18:00", 20, idle_grow=True)                          # ngoài giờ: không tính
        insert_run(self.db, DAY, "20:00", 45)                                          # làm bù buổi tối
        insert_run(self.db, DAY, "20:45", 5, vdi="background", proc="zalo.exe")
        a = analysis.analyze(self.db, self.cfg, DAY)
        self.assertAlmostEqual(a["other"], 30 * 60, delta=6)
        self.assertEqual(a["minimized"], 0)
        self.assertEqual(a["idle"] + a["away"], 0)
        self.assertEqual([p for p, _ in a["apps"]], ["chrome.exe"])
        self.assertAlmostEqual(a["vdi"], 90 * 60, delta=6)
        self.assertAlmostEqual(a["ot"], (30 + 45) * 60, delta=6)
        # Khối 16:30–17:30 vắt qua 17:00 là một khối; khối tối 20:00–20:45 cũng tính tập trung sâu
        self.assertEqual([(analysis.fmt_t(b["start"]), analysis.fmt_t(b["end"])) for b in a["blocks"]],
                         [("15:00", "16:00"), ("16:30", "17:30"), ("20:00", "20:45")])
        self.assertEqual(a["blocks"][1]["breaks"], 0)
        self.assertAlmostEqual(a["deep"], (60 + 60 + 45) * 60, delta=6)
        self.assertAlmostEqual(a["deep_ot"], 75 * 60, delta=6)
        self.assertEqual(analysis.fmt_t(a["last"]), "20:45")
        # Điểm tập trung giữ nguyên công thức: tập trung sâu có cả giờ làm bù, tỉ lệ VDI chỉ tính trong giờ làm
        self.assertEqual(focus_score(a), round(70 * min(165 / 240, 1) + 30 * 90 / 120))
        rec = analysis.daily_stats(self.db, self.cfg, DAY, refresh=True)
        self.assertAlmostEqual(rec["ot"], 75 * 60, delta=6)

    def test_lunch_is_neither_distraction_nor_inactive(self):
        insert_run(self.db, DAY, "11:00", 15)
        insert_run(self.db, DAY, "11:15", 30, vdi="background", proc="chrome.exe")
        insert_run(self.db, DAY, "11:45", 45, locked=True, vdi="background", proc="lockapp.exe")
        insert_run(self.db, DAY, "12:30", 30)
        a = analysis.analyze(self.db, self.cfg, DAY)
        self.assertEqual((a["other"], a["away"], a["away_count"]), (0, 0, 0))
        self.assertAlmostEqual(a["vdi"], 45 * 60, delta=6)

    def test_half_day_leave_afternoon_has_no_ot(self):
        from focus.storage import save_note
        save_note(self.db, DAY, {"leave_part": "pm"})
        insert_run(self.db, DAY, "09:00", 60)
        insert_run(self.db, DAY, "14:00", 60)  # buổi nghỉ phép: mẫu bị bỏ, không phải OT
        a = analysis.analyze(self.db, self.cfg, DAY)
        self.assertEqual(a["ot"], 0)
        self.assertAlmostEqual(a["vdi"], 60 * 60, delta=6)


class StatsVersionTest(TempCase):
    def test_old_daily_stats_recomputed_after_upgrade(self):
        import json
        db = open_db(db_path(self.cfg))
        insert_run(db, DAY, "16:00", 120)  # 16:00–18:00: bản cũ tính hết là giờ làm
        with db:
            db.execute("INSERT INTO daily_stats VALUES (?,?,?)",
                       (DAY, json.dumps({"day": DAY, "deep": 7200, "vdi": 7200, "other": 0}), 9e9))
        rec = daily_stats(db, self.cfg, DAY)
        self.assertEqual(rec["v"], analysis.STATS_VERSION)
        self.assertAlmostEqual(rec["vdi"], 3600, delta=6)
        self.assertAlmostEqual(rec["ot"], 3600, delta=6)
        self.assertIn("total", rec)

    def test_old_stats_without_samples_kept_and_marked(self):
        import json
        db = open_db(db_path(self.cfg))
        with db:
            db.execute("INSERT INTO daily_stats VALUES (?,?,?)",
                       (DAY, json.dumps({"day": DAY, "deep": 100, "vdi": 200}), 1.0))
        rec = daily_stats(db, self.cfg, DAY)
        self.assertEqual((rec["deep"], rec["v"]), (100, analysis.STATS_VERSION))
        self.assertEqual(json.loads(db.execute("SELECT data FROM daily_stats").fetchone()[0])["v"], analysis.STATS_VERSION)
