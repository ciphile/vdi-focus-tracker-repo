"""Xem lại kế hoạch, năng lượng và ngày đã qua (2.0.1): /today [ngày], /report [ngày], /plan hiện kế hoạch đã lưu,
/energy giữa ngày không làm mất câu hỏi tổng kết, từ khoá "xem kế hoạch"."""
import datetime as dt
import threading

from focus import intent
from focus.actions import parse_past_day
from focus.report import summary_text
from focus.schedule import due_jobs
from focus.storage import get_note, mark_sent, save_note
from focus.telegram_bot import REVIEW_QUESTIONS, TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, msg

TODAY = dt.date(2026, 10, 15)  # thứ Năm


class ParsePastDayTest(TempCase):
    def check(self, text, want):
        self.assertEqual(parse_past_day(text, TODAY)[0], want, text)

    def test_relative_words(self):
        self.check("hôm qua", "2026-10-14")
        self.check("hom qua", "2026-10-14")
        self.check("hôm kia", "2026-10-13")
        self.check("hôm nay", "2026-10-15")
        self.assertEqual(parse_past_day("xem hôm qua nhé", TODAY), ("2026-10-14", "xem  nhé"))

    def test_weekday_is_most_recent_past(self):
        self.check("thứ 2", "2026-10-12")
        self.check("t4", "2026-10-14")
        self.check("thứ 5", "2026-10-15")  # hôm nay là thứ 5
        self.check("thứ 6", "2026-10-09")

    def test_yearless_date_in_future_is_last_year(self):
        self.check("14/10", "2026-10-14")
        self.check("20/10", "2025-10-20")
        self.check("14 tháng 10", "2026-10-14")
        self.assertEqual(parse_past_day("05/01", dt.date(2026, 12, 20))[0], "2026-01-05")

    def test_future_with_year_or_tomorrow_kept(self):
        self.check("20/10/2026", "2026-10-20")
        self.check("2026-10-20", "2026-10-20")
        self.check("mai", "2026-10-16")
        self.assertEqual(parse_past_day("", TODAY), (None, ""))


class SummaryNotesTest(TempCase):
    def a(self, has_data=True):
        t0 = dt.datetime(2026, 10, 15, 9).timestamp()
        return {"has_data": has_data, "day": "2026-10-15", "first": t0, "last": t0 + 3600, "deep": 3600, "goal_h": 4,
                "vdi": 3600, "other": 0, "exits": 0, "minimized": 0, "idle": 0, "away": 0, "away_count": 0,
                "blocks": [], "active": 3600, "score_vdi": 1}

    def test_plan_and_energy_shown(self):
        note = {"plan": "1. Fix job A\n2. Spec B", "energy": 4, "output": "xong A"}
        text = summary_text(self.a(), note)
        self.assertIn("Năng lượng tự chấm: 4/5", text)
        self.assertIn("Kế hoạch đầu ngày:", text)
        self.assertIn("1. Fix job A", text)
        self.assertLess(text.index("Kế hoạch đầu ngày"), text.index("Output"))

    def test_no_data_day_still_shows_notes(self):
        text = summary_text(self.a(has_data=False), {"plan": "Fix job A", "energy": 2})
        self.assertIn("chưa có dữ liệu", text)
        self.assertIn("Fix job A", text)
        self.assertIn("2/5", text)

    def test_nothing_written_no_extra_lines(self):
        text = summary_text(self.a(), {})
        self.assertNotIn("Kế hoạch", text)
        self.assertNotIn("Năng lượng", text)


class ViewDayBotTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="")
        self.api = FakeTelegramAPI()
        self.bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=self.api)
        self.day = self.bot.today()
        self.yesterday = (dt.date.fromisoformat(self.day) - dt.timedelta(days=1)).isoformat()

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def test_today_shows_plan_and_energy(self):
        save_note(self.bot.db, self.day, {"plan": "1. Fix job đối soát", "energy": 4})
        out = "\n".join(self.say("/today"))
        self.assertIn("Fix job đối soát", out)
        self.assertIn("4/5", out)

    def test_today_past_day(self):
        insert_run(self.bot.db, self.yesterday, "09:00", 30)
        save_note(self.bot.db, self.yesterday, {"plan": "kế hoạch hôm qua", "energy": 3})
        save_note(self.bot.db, self.day, {"plan": "kế hoạch hôm nay"})
        out = "\n".join(self.say("/today hôm qua"))
        self.assertIn(self.yesterday, out)
        self.assertIn("kế hoạch hôm qua", out)
        self.assertNotIn("kế hoạch hôm nay", out)

    def test_today_future_day_refused(self):
        out = self.say("/today mai")
        self.assertIn("chưa tới", out[0])
        self.assertIn("/today hôm qua", out[0])

    def test_report_past_day(self):
        insert_run(self.bot.db, self.yesterday, "09:00", 30)
        self.say("/report hôm qua")
        docs = [(p, f) for m, p, f in self.api.calls if m == "sendDocument"]
        self.assertEqual(len(docs), 1)
        self.assertIn(self.yesterday, docs[0][0]["caption"])

    def test_plan_without_text_shows_saved_plan(self):
        save_note(self.bot.db, self.day, {"plan": "Fix job A"})
        out = self.say("/plan")
        self.assertIn("Kế hoạch đã lưu hôm nay", out[0])
        self.assertIn("Fix job A", out[0])
        self.assertIn("/cancel", out[0])
        self.say("/cancel")
        self.assertEqual(get_note(self.bot.db, self.day)["plan"], "Fix job A", "/cancel giữ nguyên kế hoạch")

    def test_plan_without_saved_plan_just_asks(self):
        out = self.say("/plan")
        self.assertNotIn("Kế hoạch đã lưu", out[0])
        self.assertIn("3 việc quan trọng nhất", out[0])

    def test_finished_manual_review_marks_review_sent(self):
        self.say("/review")
        for _ in REVIEW_QUESTIONS:
            self.say("bỏ qua")
        self.assertIsNone(self.bot.convo)
        self.assertFalse(mark_sent(self.bot.db, self.day, "review"), "lịch 16:45 không hỏi lại")

    def test_energy_midday_does_not_mark_review(self):
        self.say("/energy 4")
        self.assertTrue(mark_sent(self.bot.db, self.day, "review"), "câu hỏi tổng kết vẫn còn")


class ReviewJobTest(TempCase):
    def test_energy_does_not_cancel_review(self):
        jobs = due_jobs(self.cfg, "16:50", 3, active=True, off=False, note={"energy": 3}, has_bot=True)
        self.assertIn("review", jobs)


class ViewIntentTest(TempCase):
    def rule(self, text):
        found = intent.by_rules(text, TODAY.isoformat())
        return (found[0].name, found[1]) if found else (None, {})

    def test_view_plan_and_energy(self):
        self.assertEqual(self.rule("xem kế hoạch hôm nay"), ("xem_hom_nay", {"day": "2026-10-15"}))
        self.assertEqual(self.rule("xem kế hoạch")[0], "xem_hom_nay")
        self.assertEqual(self.rule("kế hoạch hôm nay là gì")[0], "xem_hom_nay")
        self.assertEqual(self.rule("xem năng lượng hôm qua"), ("xem_hom_nay", {"day": "2026-10-14"}))
        self.assertEqual(self.rule("hôm qua tập trung thế nào"), ("xem_hom_nay", {"day": "2026-10-14"}))
        self.assertEqual(self.rule("báo cáo hôm qua"), ("gui_bao_cao", {"day": "2026-10-14"}))

    def test_writes_still_win_without_view_word(self):
        self.assertEqual(self.rule("kế hoạch hôm nay: fix job A")[0], "ghi_ke_hoach")
        self.assertEqual(self.rule("năng lượng hôm nay 4"), ("ghi_nang_luong", {"energy": 4}))
        self.assertEqual(self.rule("đã xong xem xét hồ sơ A")[0], "ghi_output", "xem xét không phải xem")
        self.assertEqual(self.rule("hôm qua giá vàng bao nhiêu")[0], "hoi_ai")
