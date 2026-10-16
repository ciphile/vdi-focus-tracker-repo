"""Nghỉ phép (/leave sáng | chiều | cả ngày) và ngày lễ: lệnh, nhắn tự nhiên, lịch việc, số liệu, tracker.

Đảm bảo: ngày lễ / nghỉ bù / nghỉ cả ngày tracker thoát ngay (không ghi mẫu, không cảnh báo, không việc theo giờ),
báo 1 câu/ngày; nghỉ nửa ngày thì phần nghỉ không theo dõi, mục tiêu còn một nửa.
"""
import datetime as dt
import threading
from unittest import mock

from focus import holidays, intent, tracker
from focus.actions import BY_NAME, parse_command_args, validate
from focus.analysis import analyze, daily_stats, streak
from focus.schedule import due_jobs, in_leave, is_work_time, job_times
from focus.storage import db_path, get_note, open_db, save_note
from focus.telegram_bot import TelegramBot
from tests import test_tracker as T
from tests.helpers import FakeTelegramAPI, TempCase, insert_run, msg

FRIDAY = T.FRIDAY  # 2026-10-16


# ------------------------------------------------------------ lệnh + nhắn tự nhiên

class LeaveBotTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg["telegram_bot_token"] = "T"
        self.cfg["telegram_chat_id"] = "42"
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "recheck": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.today = self.bot.today()
        self.tomorrow = (dt.date.fromisoformat(self.today) + dt.timedelta(days=1)).isoformat()

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def press_ok(self):
        markups = [p for m, p, f in self.api.calls if m == "sendMessage" and p.get("reply_markup")]
        cb = markups[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.api.clear()
        self.bot.handle_callback({"id": "cb", "data": cb, "message": {"chat": {"id": 42}, "message_id": 5}})
        return self.api.sent()

    def note(self, day=None):
        return get_note(self.bot.db, day or self.today)

    def test_leave_commands(self):
        out = self.say("/leave sang")
        self.assertEqual((self.note()["leave_part"], self.note()["day_off"]), ("am", None))
        self.assertIn("nghỉ phép buổi sáng", out[0])
        self.assertIn("2h", out[0], "mục tiêu còn một nửa")
        self.assertTrue(self.state["recheck"].is_set(), "báo tracker đọc lại ngay")
        self.say("/nghiphep chieu mai đi khám")
        self.assertEqual(self.note(self.tomorrow)["leave_part"], "pm")
        self.say("/leave afternoon 2026-12-23")
        self.assertEqual(get_note(self.bot.db, "2026-12-23")["leave_part"], "pm")
        self.say("/leave ca ngay 2026-12-24")
        n = get_note(self.bot.db, "2026-12-24")
        self.assertEqual((n["day_off"], n["leave_part"]), ("nghỉ phép", None))
        self.say("/leave")  # mặc định: cả ngày hôm nay
        self.assertEqual((self.note()["day_off"], self.note()["leave_part"]), ("nghỉ phép", None))
        self.assertIn("sáng hay buổi chiều", self.say("/leave nửa ngày")[0])

    def test_on_cancels_half_and_full(self):
        self.say("/leave chieu")
        out = self.say("/on")
        self.assertEqual((self.note()["leave_part"], self.note()["day_off"]), (None, None))
        self.assertIn("Đã huỷ nghỉ phép buổi chiều", out[0])
        self.say("/off")
        self.say("/on")
        self.assertIsNone(self.note()["day_off"])

    def test_off_clears_half_day(self):
        self.say("/leave sang")
        self.say("/off")
        self.assertEqual((self.note()["day_off"], self.note()["leave_part"]), ("nghỉ", None))

    def test_natural_language_needs_ok(self):
        out = self.say("chiều nay nghỉ phép")
        self.assertIn("nghỉ phép buổi chiều", out[0])
        self.assertFalse(self.note().get("leave_part"), "chưa bấm OK thì chưa ghi")
        self.press_ok()
        self.assertEqual(self.note()["leave_part"], "pm")
        self.say("mai nghỉ phép cả ngày")
        self.press_ok()
        self.assertEqual(self.note(self.tomorrow)["day_off"], "nghỉ phép")
        self.say("huỷ nghỉ chiều nay")
        self.press_ok()
        self.assertIsNone(self.note()["leave_part"])

    def test_status_today_report_mention_leave(self):
        self.say("/leave sang")
        self.assertIn("nghỉ phép buổi sáng", self.say("/status")[0])
        insert_run(self.bot.db, self.today, "13:00", 30)
        self.assertIn("Nghỉ phép buổi sáng", self.say("/today")[0])
        self.assertIn("Lịch lễ", self.say("/status")[0])

    def test_help_lists_leave(self):
        text = "\n".join(self.say("/help"))  # trợ giúp dài, bot cắt thành nhiều tin
        self.assertIn("/leave /nghiphep", text)
        self.assertIn("chiều nay nghỉ phép", text)


class LeaveParseTest(TempCase):
    TODAY = "2026-10-14"  # thứ Tư

    def rule(self, text):
        found = intent.by_rules(text, self.TODAY)
        return (found[0].name, found[1]) if found else (None, {})

    def test_rules(self):
        cases = {
            "hôm nay mình nghỉ nửa ngày sáng": ("nghi_phep", {"part": "am", "day": "2026-10-14"}),
            "chiều nay nghỉ phép": ("nghi_phep", {"part": "pm"}),
            "mai nghỉ phép cả ngày": ("nghi_phep", {"part": "full", "day": "2026-10-15"}),
            "thứ 6 nghỉ buổi chiều": ("nghi_phep", {"part": "pm", "day": "2026-10-16"}),
            "chiều mai mình nghỉ phép về quê": ("nghi_phep", {"part": "pm", "day": "2026-10-15", "reason": "về quê"}),
            "ngày mai mình xin nghỉ phép": ("bao_nghi", {"day": "2026-10-15"}),  # không nói buổi: như /off
            "huỷ nghỉ buổi chiều mai": ("bao_di_lam", {"day": "2026-10-15"}),
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.rule(text), want)

    def test_half_without_part_asks(self):
        action, args = intent.by_rules("hôm nay nghỉ nửa ngày", self.TODAY)
        self.assertEqual(action.name, "nghi_phep")
        self.assertIn("sáng hay buổi chiều", validate(action, args)[1])

    def test_command_args(self):
        a = BY_NAME["nghi_phep"]
        p = lambda t: parse_command_args(a, t, self.TODAY)
        self.assertEqual(p("sang"), {"part": "am"})
        self.assertEqual(p("morning"), {"part": "am"})
        self.assertEqual(p("pm 20/10 về quê"), {"part": "pm", "day": "2026-10-20", "reason": "về quê"})
        self.assertEqual(p("chiều nay đưa con đi học sáng"), {"part": "pm", "reason": "đưa con đi học sáng"})
        self.assertEqual(validate(a, {"part": "chiều"})[0], {"part": "pm"})
        self.assertIsNotNone(validate(a, {"part": "tối"})[1])

    def test_ai_catalog_describes_leave(self):
        from focus.actions import catalog
        item = [c for c in catalog() if c["action"] == "nghi_phep"][0]
        self.assertIn("am", item["tham_so"]["part"])
        self.assertIn("pm", item["tham_so"]["part"])
        self.assertIn("nửa ngày", item["mo_ta"])


# ------------------------------------------------------------ lịch việc + số liệu

class LeaveScheduleTest(TempCase):
    def jobs(self, hhmm, leave, weekday=2, active=True, note=None):
        return due_jobs(self.cfg, hhmm, weekday, active=active, off=None, note=note or {}, has_bot=True, leave=leave)

    def test_leave_windows(self):
        c = self.cfg  # 08:00–17:00, trưa 11:15–12:30
        self.assertTrue(in_leave(c, "07:00", "am"))
        self.assertTrue(in_leave(c, "12:29", "am"))
        self.assertFalse(in_leave(c, "12:30", "am"))
        self.assertFalse(in_leave(c, "11:14", "pm"))
        self.assertTrue(in_leave(c, "11:15", "pm"))
        self.assertFalse(in_leave(c, "09:00", None))
        self.assertFalse(is_work_time(c, "09:00", leave="am"))
        self.assertTrue(is_work_time(c, "13:00", leave="am"))
        self.assertTrue(is_work_time(c, "09:00", leave="pm"))
        self.assertFalse(is_work_time(c, "13:00", leave="pm"))

    def test_am_leave_jobs(self):
        self.assertEqual(self.jobs("09:00", "am"), [])
        self.assertEqual(self.jobs("12:30", "am")[:2], ["morning", "plan"], "chào + kế hoạch khi bắt đầu buổi chiều")
        self.assertIn("review", self.jobs("16:45", "am"))
        self.assertIn("summary", self.jobs("17:00", "am", active=False))

    def test_pm_leave_jobs(self):
        t = job_times(self.cfg, "pm")
        self.assertEqual((t["review"], t["summary"], t["weekly"], t["boost"]), ("11:00", "11:15", "11:15", ""))
        self.assertIn("review", self.jobs("11:00", "pm"))
        self.assertNotIn("summary", self.jobs("11:14", "pm"))
        self.assertIn("summary", self.jobs("11:15", "pm", active=False))
        self.assertIn("weekly", self.jobs("11:15", "pm", weekday=4, active=False))
        self.assertNotIn("review", self.jobs("13:00", "pm"), "đang nghỉ thì không hỏi")
        self.assertNotIn("boost", self.jobs("14:30", "pm"))

    def test_off_day_and_holidays_no_jobs(self):
        for reason in ("Christmas Day", "nghỉ bù National Day", "nghỉ phép"):
            for hhmm in ("08:00", "11:00", "14:30", "16:45", "17:00", "20:00"):
                self.assertEqual(due_jobs(self.cfg, hhmm, 4, active=True, off=reason, note={}, has_bot=True), [])


class LeaveAnalysisTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)

    def test_goal_halved_and_leave_samples_ignored(self):
        day = "2026-10-14"
        insert_run(self.db, day, "09:00", 60)   # buổi sáng
        insert_run(self.db, day, "13:00", 120)  # buổi chiều
        full = analyze(self.db, self.cfg, day)
        self.assertEqual(full["goal_h"], 4)
        save_note(self.db, day, {"leave_part": "am"})  # báo nghỉ sáng muộn: mẫu buổi sáng không tính
        a = analyze(self.db, self.cfg, day)
        self.assertEqual((a["goal_h"], a["leave"]), (2, "am"))
        self.assertAlmostEqual(a["deep"], 120 * 60, delta=10)
        self.assertGreater(a["first"], T.hms(day, "12:30:00"))
        save_note(self.db, day, {"leave_part": "pm"})
        a = analyze(self.db, self.cfg, day)
        self.assertAlmostEqual(a["deep"], 60 * 60, delta=10)
        rec = daily_stats(self.db, self.cfg, day, refresh=True)
        self.assertEqual((rec["goal_h"], rec["leave"]), (2, "pm"))

    def test_streak_uses_half_goal(self):
        # Thứ Hai 12/10 đủ 4h, thứ Ba 13/10 nghỉ sáng làm 2h5m: chuỗi vẫn 2 ngày.
        insert_run(self.db, "2026-10-12", "12:30", 245)
        insert_run(self.db, "2026-10-13", "13:00", 125)
        self.assertEqual(streak(self.db, self.cfg, "2026-10-13"), 1)
        save_note(self.db, "2026-10-13", {"leave_part": "am"})
        self.assertEqual(streak(self.db, self.cfg, "2026-10-13"), 2)


# ------------------------------------------------------------ tracker

class TrackerLeaveTest(T._Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(holidays, "_download", side_effect=AssertionError("test không được gọi mạng"))
        p.start()
        self.addCleanup(p.stop)

    def set_note(self, day, values):
        db = open_db(db_path(self.cfg))
        try:
            save_note(db, day, values)
        finally:
            db.close()

    def sample_ts(self):
        return [r[0] for r in self.samples()]

    def test_am_leave_full_day(self):
        self.set_note(FRIDAY, {"leave_part": "am"})
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, FRIDAY, "07:00:00", T.DAY_SCRIPT)
        self.assertEqual(tr.run(), "window_end")
        rows = self.sample_ts()
        self.assertTrue(rows)
        self.assertGreaterEqual(min(rows), T.hms(FRIDAY, "12:30:00"), "sáng nghỉ phép: không ghi mẫu")
        got = T.labels(nt, FRIDAY)
        self.assertTrue(all(t >= "12:30:00" for t, lb in got if lb != "leave_notice"), got)
        self.assertEqual(got[0][1], "leave_notice")
        self.assertIn(("12:30:00", "morning"), got)
        self.assertIn(("12:30:00", "plan"), got)
        self.assertIn(("17:00:00", "summary"), got)
        self.assertEqual(sum("Sáng nay bạn nghỉ phép" in t for t, _ in bot.sent), 1)
        self.assertIn("LEAVE_RESUME", self.audit_text())
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertEqual(analyze(db, self.cfg, FRIDAY)["goal_h"], 2)

    def test_pm_leave_summary_before_leaving(self):
        self.set_note(FRIDAY, {"leave_part": "pm"})
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, FRIDAY, "07:00:00", T.DAY_SCRIPT)
        self.assertEqual(tr.run(), "window_end")
        self.assertLess(max(self.sample_ts()), T.hms(FRIDAY, "11:15:00"), "chiều nghỉ phép: không ghi mẫu")
        got = T.labels(nt, FRIDAY)
        alerts = {"out_of_vdi", "away", "back", "break", "phone", "not_fullscreen", "boost"}
        self.assertFalse([x for x in got if x[1] in alerts and x[0] >= "11:15:00"], got)
        when = {lb: t for t, lb in got}
        self.assertTrue("11:00:00" <= when["review"] < "11:01:00", got)
        self.assertTrue("11:15:00" <= when["summary"] < "11:16:00", got)
        self.assertTrue("11:15:00" <= when["weekly"] < "11:16:00", got)
        self.assertNotIn("boost", when)
        self.assertEqual(sum("Chiều nay bạn nghỉ phép" in t for t, _ in bot.sent), 1)

    def test_off_set_while_running_stops_within_one_tick(self):
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, FRIDAY, "08:00:00", T.DAY_SCRIPT)
        stop_at = T.hms(FRIDAY, "10:00:02")
        st = {"done": False}

        def hook(c):
            if not st["done"] and c.t >= stop_at:  # bot nhận /off giữa 2 vòng lấy mẫu
                st["done"] = True
                self.set_note(FRIDAY, {"day_off": "nghỉ ốm"})
                tr.state["recheck"].set()
        fc.hook = hook
        self.assertEqual(tr.run(), "off_day")
        self.assertLess(max(self.sample_ts()), stop_at)
        self.assertLess(fc.t, stop_at + 6, "dừng ngay vòng kế tiếp")
        texts = [t for t, _ in bot.sent]
        self.assertTrue(any("Hôm nay bạn nghỉ (nghỉ ốm), mình tắt" in t for t in texts), texts)
        self.assertEqual(bot.stopped, 1)

    def test_off_set_without_signal_stops_within_a_minute(self):
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, FRIDAY, "08:00:00", T.DAY_SCRIPT)
        stop_at = T.hms(FRIDAY, "10:00:02")
        st = {"done": False}

        def hook(c):
            if not st["done"] and c.t >= stop_at:
                st["done"] = True
                self.set_note(FRIDAY, {"day_off": "nghỉ"})
        fc.hook = hook
        self.assertEqual(tr.run(), "off_day")
        self.assertLess(fc.t, stop_at + 61)

    def test_half_day_set_while_running_pauses_now(self):
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, FRIDAY, "08:00:00", T.DAY_SCRIPT)
        mark = T.hms(FRIDAY, "09:30:02")
        st = {"done": False}

        def hook(c):
            if not st["done"] and c.t >= mark:
                st["done"] = True
                self.set_note(FRIDAY, {"leave_part": "am"})
                tr.state["recheck"].set()
            if c.t >= T.hms(FRIDAY, "13:00:00"):
                self.cfg["auto_stop_at"] = "13:00"
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end")
        rows = self.sample_ts()
        self.assertFalse([t for t in rows if mark <= t < T.hms(FRIDAY, "12:30:00")])
        self.assertTrue([t for t in rows if t >= T.hms(FRIDAY, "12:30:00")], "chiều theo dõi lại")


class HolidayTrackerTest(T._Base):
    """100%: mọi ngày lễ Singapore 2026 (bảng có sẵn) + ngày nghỉ bù: tracker thoát ngay, không mẫu, không cảnh báo."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(holidays, "_download", side_effect=AssertionError("test không được gọi mạng"))
        p.start()
        self.addCleanup(p.stop)

    def run_day(self, day, start="08:00:00"):
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, day, start, T.DAY_SCRIPT)
        result = tr.run()
        bot.stop()
        return result, probe, bot, nt

    def test_every_2026_holiday_and_observed_day(self):
        days = sorted(holidays.BUILTIN[2026]) + ["2026-06-01", "2026-08-10", "2026-11-09"]
        for day in days:
            with self.subTest(day=day):
                weekday = dt.date.fromisoformat(day).weekday()
                for start in ("07:00:00", "08:30:00", "16:50:00"):
                    result, probe, bot, nt = self.run_day(day, start)
                    self.assertEqual(result, "off_day")
                    self.assertEqual(probe.calls, [], "không đọc trạng thái máy")
                    self.assertEqual(nt.jobs, [], "không việc nền, không cảnh báo")
                    if start == "07:00:00" and weekday < 5:
                        self.assertEqual(len(bot.sent), 1, bot.sent)
                        self.assertRegex(bot.sent[0][0], r"ngày lễ|nghỉ bù")
                        self.assertIn("mình tắt", bot.sent[0][0])
                    else:  # cuối tuần: im lặng; lần khởi động sau trong ngày: không báo lại
                        self.assertEqual(bot.sent, [])
                    off = holidays.off_reason(self.cfg, day)
                    for hhmm in ("08:00", "12:30", "16:45", "17:00"):
                        self.assertEqual(due_jobs(self.cfg, hhmm, weekday, active=True, off=off, note={},
                                                  has_bot=True), [])
        self.assertEqual(self.samples(), [], "không một mẫu nào được ghi")

    def test_notice_text(self):
        result, probe, bot, nt = self.run_day("2026-12-25")
        self.assertEqual(bot.sent[0][0], "🌴 Hôm nay là ngày lễ Christmas Day, mình tắt, bật lại Thứ 2 28/12.")
        result, probe, bot, nt = self.run_day("2026-08-10")
        self.assertEqual(bot.sent[0][0], "🌴 Hôm nay là ngày nghỉ bù National Day (lễ rơi Chủ nhật), mình tắt, mai bật lại.")

    def test_full_day_leave_notice_once(self):
        db = open_db(db_path(self.cfg))
        save_note(db, FRIDAY, {"day_off": "nghỉ phép"})
        db.close()
        _, _, bot, _ = self.run_day(FRIDAY)
        self.assertIn("Hôm nay bạn nghỉ (nghỉ phép), mình tắt, bật lại Thứ 2 19/10", bot.sent[0][0])
        _, _, bot, _ = self.run_day(FRIDAY, "09:00:00")
        self.assertEqual(bot.sent, [])

    def test_run_on_off_days_still_honoured(self):
        self.cfg["run_on_off_days"] = True
        self.cfg["auto_stop_at"] = "08:10"
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, "2026-12-25", "08:00:00", [("08:00:00", "chrome")])
        self.assertEqual(tr.run(), "window_end")
        self.assertEqual(nt.jobs, [])
        self.assertTrue(probe.calls)

    def test_overnight_into_holiday_stops(self):
        """Máy để qua đêm 24/12 -> 25/12 (Christmas) trong khung giờ: sang ngày lễ thì thôi theo dõi và thoát."""
        eve, xmas = "2026-12-24", "2026-12-25"
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, eve, "23:57:00", [("00:00:00", "vdi")])
        with mock.patch.object(tracker, "in_run_window", lambda cfg, hhmm: hhmm >= "23:57" or hhmm < "00:10"):
            self.assertEqual(tr.run(), "off_day")
        self.assertLess(fc.t, T.hms(xmas, "00:00:10"))
        self.assertFalse([r for r in self.samples() if r[0] > T.hms(xmas, "00:00:00")])
        self.assertTrue(any("Christmas Day" in t for t, _ in bot.sent))
        self.assertFalse([lb for lb, t in nt.jobs if t >= T.hms(xmas, "00:00:00")])

    def test_holiday_in_next_year_fetched_at_start_when_unknown(self):
        """Năm chưa có lịch nào: lúc khởi động tải MOM (giả) rồi mới quyết định có chạy không."""
        rows = "".join(f"<tr><td>H{i}</td><td>{d} Jan 2031</td><td>x</td></tr>" for i, d in enumerate(range(1, 10)))
        html = f"<h2>2031</h2><table><tr><th>Holiday</th><th>Date</th><th>Day</th></tr>{rows}</table>"
        with mock.patch.object(holidays, "_download", return_value=html) as dl:
            result, probe, bot, nt = self.run_day("2031-01-02")  # thứ Năm
        self.assertEqual(result, "off_day")
        self.assertEqual(dl.call_count, 1)
        self.assertIn("H1", bot.sent[0][0])
