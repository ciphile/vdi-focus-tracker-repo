"""v2.14.0: danh sách việc /viec (gom /plan, /issue, /tmrtask), hỏi cập nhật việc đầu ngày + 12:45 + 16:00 (chờ 5 phút),
báo giờ tập trung sâu + AI nhận xét 10:17, 12:45 (gộp với hỏi việc), 15:00; cảnh báo tiến độ chỉ còn 15:30."""
import datetime as dt
import threading
import time
from unittest import mock

from focus import ai_client, progress, tasks
from focus.analysis import off_day
from focus.config import DEFAULTS, ConfigError, validate
from focus.schedule import due_jobs
from focus.storage import get_note, get_pref, open_db, db_path, save_note
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, make_cfg, msg

MONDAY = "2026-11-23"
TUESDAY = "2026-11-24"
FRIDAY = "2026-11-20"
SATURDAY = "2026-11-21"
D = dt.date(2026, 11, 23)


class ParseTest(TempCase):
    def p(self, text):
        return tasks.parse(text, D)

    def test_syntax(self):
        self.assertEqual(self.p("xong 1 3"), [("done", [1, 3])])
        self.assertEqual(self.p("Xong 1-3, 5"), [("done", [1, 2, 3, 5])])
        self.assertEqual(self.p("xong 2 và 4"), [("done", [2, 4])])
        self.assertEqual(self.p("xong: spec UAT"), [("done_name", "spec UAT")])
        self.assertEqual(self.p("mới: Viết spec UAT hạn 25/11"), [("add", "Viết spec UAT", "2026-11-25")])
        self.assertEqual(self.p("thêm: a; b; c"), [("add", "a", None), ("add", "b", None), ("add", "c", None)])
        self.assertEqual(self.p("+ gọi anh Tuấn"), [("add", "gọi anh Tuấn", None)])
        self.assertEqual(self.p("hoãn 2"), [("later", [2])])
        self.assertEqual(self.p("bỏ 4"), [("drop", [4])])
        self.assertEqual(self.p("xoá 4"), [("drop", [4])])
        self.assertEqual(self.p("sửa 2: Gửi email cho SH"), [("edit", 2, "Gửi email cho SH")])
        self.assertEqual(self.p("ưu tiên 3"), [("first", [3])])
        self.assertEqual(self.p("hạn 2 25/11"), [("due", 2, "2026-11-25")])
        self.assertEqual(self.p("hạn 2 05/01"), [("due", 2, "2027-01-05")], "tháng 1 gõ cuối năm = năm sau")
        self.assertEqual(self.p("issue: VDI chậm"), [("issue", "VDI chậm", None)])
        self.assertEqual(self.p("hoàn tác"), [("undo",)])
        self.assertEqual(self.p("xong 2\nmới: test batch ABC"), [("done", [2]), ("add", "test batch ABC", None)])

    def test_not_syntax_goes_to_normal_handling(self):
        for text in ("không", "xong rồi", "bỏ qua", "mình xong việc rồi", "ok 1", "OK 1", "hôm nay làm gì",
                     "xong 2 rồi đi ăn", "mới thêm việc", "/viec", "", "giá vàng hôm nay", "bỏ qua câu này"):
            self.assertIsNone(self.p(text), text)

    def test_errors(self):
        with self.assertRaises(tasks.TaskError):
            self.p("hạn 2 31/02")
        with self.assertRaises(tasks.TaskError):
            self.p("hoàn tác\nxong 1")
        self.assertIsNone(self.p("mới: "))

    def test_noop(self):
        for text in ("không", "Ko", "ok", "bỏ qua", "không có", "giữ nguyên"):
            self.assertTrue(tasks.is_noop(text), text)
        self.assertFalse(tasks.is_noop("xong 1"))


class _Db(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)
        tasks.ensure_started(self.db, self.cfg, MONDAY, off_day)

    def apply(self, text, day=MONDAY):
        return tasks.apply(self.db, self.cfg, day, tasks.parse(text, dt.date.fromisoformat(day)), off_day)

    def names(self, day=MONDAY):
        return [t["text"] for t in tasks.open_tasks(self.db, day)]


class ApplyTest(_Db):
    def test_add_done_numbering_and_output(self):
        self.apply("mới: A; B; C")
        self.assertEqual(self.names(), ["A", "B", "C"])
        out = self.apply("xong 1 3")
        self.assertEqual(out, ["✅ Xong: A", "✅ Xong: C"], "số thứ tự tính trên danh sách TRƯỚC khi đổi")
        self.assertEqual(self.names(), ["B"])
        self.assertIn("A", get_note(self.db, MONDAY)["output"], "xong cũng ghi vào output (báo cáo, AI)")
        self.assertIn("C", get_note(self.db, MONDAY)["output"])
        self.assertIn("Đã xong hôm nay (2)", tasks.list_text(self.db, MONDAY))

    def test_bad_number_changes_nothing(self):
        self.apply("mới: A; B")
        with self.assertRaises(tasks.TaskError):
            self.apply("xong 1 5")
        self.assertEqual(self.names(), ["A", "B"], "một số sai thì không ghi gì")

    def test_later_drop_edit_first_due(self):
        self.apply("mới: A; B; C; D")
        self.apply("hoãn 1")
        self.assertEqual(self.names(), ["B", "C", "D"])
        self.assertEqual(self.names(TUESDAY), ["A", "B", "C", "D"], "hoãn = ngày làm việc kế")
        self.apply("bỏ 3")
        self.assertEqual(self.names(), ["B", "C"])
        self.apply("sửa 1: B2")
        self.apply("ưu tiên 2")
        self.assertEqual(self.names(), ["C", "B2"])
        self.apply("hạn 2 20/11")
        self.assertIn("quá hạn", tasks.list_text(self.db, MONDAY))

    def test_friday_later_goes_to_monday(self):
        self.apply("mới: A", day=FRIDAY)
        self.apply("hoãn 1", day=FRIDAY)
        self.assertEqual(self.names(FRIDAY), [])
        self.assertEqual(self.names(SATURDAY), [], "thứ Bảy là ngày nghỉ")
        self.assertEqual(self.names(MONDAY), ["A"])

    def test_undo(self):
        self.apply("mới: A; B")
        self.apply("xong 1\nmới: C\nissue: VDI chậm")
        self.assertEqual(self.names(), ["B", "C", "VDI chậm"])
        self.assertIn("VDI chậm", get_note(self.db, MONDAY)["issues"])
        self.assertIn("hoàn tác", self.apply("hoàn tác")[0])
        self.assertEqual(self.names(), ["A", "B"])
        self.assertNotIn("A", get_note(self.db, MONDAY).get("output") or "")
        self.assertFalse(get_note(self.db, MONDAY).get("issues"))
        self.assertIn("Không có gì", self.apply("hoàn tác")[0])

    def test_done_by_name(self):
        self.apply("mới: Gởi estimation UAT release cho SH; Fix job đối soát")
        self.assertEqual(self.apply("xong: estimation UAT"), ["✅ Xong: Gởi estimation UAT release cho SH"])
        with self.assertRaises(tasks.TaskError):
            self.apply("xong: họp với khách")

    def test_duplicate_open_task_not_added(self):
        self.apply("mới: A")
        self.assertIn("Đã có", self.apply("mới: a")[0])
        self.assertEqual(self.names(), ["A"])

    def test_carry_history_by_day(self):
        from focus.storage import set_pref
        set_pref(self.db, tasks.SINCE_PREF, FRIDAY)
        self.apply("mới: A; B", day=FRIDAY)
        self.apply("xong 1")  # xong thứ Hai
        self.assertEqual([t[1] for t in tasks.carry_after(self.db, self.cfg, FRIDAY, off_day)], ["A", "B"],
                         "xem lại thứ Sáu: A còn mở lúc hết ngày thứ Sáu")
        self.assertEqual([t[1] for t in tasks.carry_after(self.db, self.cfg, MONDAY, off_day)], ["B"])


class StartTest(TempCase):
    def test_old_pending_plan_and_tomorrow_are_copied_once(self):
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        save_note(db, FRIDAY, {"plan": "1. Viết spec API\n2. Fix job đối soát", "output": "- xong fix job đối soát",
                               "issues": "- thiếu quyền DB2", "tomorrow": "Gọi anh Tuấn"})
        save_note(db, MONDAY, {"plan": "Test batch ABC"})
        self.assertGreater(tasks.ensure_started(db, self.cfg, MONDAY, off_day), 0)
        names = [t["text"] for t in tasks.open_tasks(db, MONDAY)]
        self.assertEqual(names[0], "Gọi anh Tuấn", "việc hẹn sáng nay đứng đầu")
        self.assertIn("Viết spec API", names)
        self.assertIn("thiếu quyền DB2", names)
        self.assertIn("Test batch ABC", names)
        self.assertNotIn("Fix job đối soát", names, "đã có output khớp")
        self.assertEqual(tasks.ensure_started(db, self.cfg, MONDAY, off_day), 0, "chỉ chép một lần")
        self.assertEqual(get_pref(db, tasks.SINCE_PREF), MONDAY)
        self.assertIn("tồn từ T6 20/11", tasks.list_text(db, MONDAY))


class ScheduleTest(TempCase):
    def jobs(self, hhmm, morning_age=None, active=True, off=False, leave=None, **cfg):
        c = make_cfg(self.tmp, **dict({"task_checkin_enabled": True, "focus_report_enabled": True,
                                       "pace_checkpoints": ["15:30"]}, **cfg))
        return due_jobs(c, hhmm, 0, active=active, off=off, note={}, has_bot=True, leave=leave,
                        morning_age=morning_age)

    def test_defaults(self):
        self.assertEqual(DEFAULTS["pace_checkpoints"], ["15:30"])
        self.assertEqual(DEFAULTS["task_checkins"], ["12:45", "16:00"])
        self.assertEqual(DEFAULTS["focus_reports"], ["10:17", "12:45", "15:00"])
        self.assertEqual((DEFAULTS["task_reply_minutes"], DEFAULTS["task_checkin_after_morning_minutes"]), (5, 5))

    def test_morning_list_after_greeting(self):
        self.assertNotIn("tasks_am", self.jobs("08:05", morning_age=None))
        self.assertNotIn("tasks_am", self.jobs("08:05", morning_age=200))
        self.assertIn("tasks_am", self.jobs("08:05", morning_age=300))
        self.assertNotIn("plan", self.jobs("08:05", morning_age=300), "không hỏi «3 việc» nữa")
        self.assertIn("tasks_am", self.jobs("08:05", encouragement_enabled=False), "tắt lời chào: gửi ngay")
        self.assertNotIn("tasks_am", self.jobs("08:05", morning_age=300, active=False))

    def test_old_plan_question_when_tasks_off(self):
        jobs = self.jobs("08:05", morning_age=300, task_checkin_enabled=False)
        self.assertIn("plan", jobs)
        self.assertNotIn("tasks_am", jobs)

    def test_slots(self):
        self.assertIn("focus_1017", self.jobs("10:17", active=False))
        self.assertIn("focus_1017", self.jobs("11:00", active=False), "trễ dưới 60 phút vẫn gửi")
        jobs = self.jobs("12:45", active=False)
        self.assertLess(jobs.index("focus_1245"), jobs.index("tasks_1245"), "focus trước để gộp")
        self.assertIn("focus_1500", self.jobs("15:00"))
        self.assertIn("tasks_1600", self.jobs("16:05"))
        self.assertNotIn("tasks_1600", self.jobs("15:59"))
        self.assertIn("pace_1530", self.jobs("15:30"))
        self.assertFalse([j for j in self.jobs("10:30") if j.startswith("pace_")], "bỏ mốc 10:30, 14:00")

    def test_late_lunch_off_and_leave(self):
        c = dict(lunch_start="11:00", lunch_end="12:00")
        self.assertIn("focus_1017", self.jobs("11:40", **c), "phút nghỉ trưa không tính là trễ")
        self.assertEqual(self.jobs("12:45", off=True), [], "ngày nghỉ / làm bù cuối tuần: không gửi")
        self.assertNotIn("focus_1017", self.jobs("10:17", leave="am"), "nghỉ sáng: bỏ 10:17")
        self.assertIn("focus_1245", self.jobs("12:45", leave="am"))
        self.assertNotIn("tasks_1600", self.jobs("16:00", leave="pm"), "nghỉ chiều: bỏ 16:00")
        self.assertNotIn("focus_1017", self.jobs("12:40"), "trễ quá 60 phút (không tính trưa): bỏ")

    def test_switches(self):
        jobs = self.jobs("12:45", focus_report_enabled=False)
        self.assertNotIn("focus_1245", jobs)
        self.assertIn("tasks_1245", jobs)
        self.assertNotIn("tasks_1245", self.jobs("12:45", task_checkin_enabled=False))

    def test_config_validation(self):
        for key in ("task_checkins", "focus_reports"):
            with self.assertRaises(ConfigError):
                make_cfg(self.tmp, **{key: ["11:30"]})  # rơi vào nghỉ trưa mặc định 11:15–12:30
            with self.assertRaises(ConfigError):
                make_cfg(self.tmp, **{key: "12:45"})
        with self.assertRaises(ConfigError):
            make_cfg(self.tmp, task_reply_minutes=0)
        self.assertEqual(make_cfg(self.tmp, focus_reports=["15:00", "10:17", "10:17"])["focus_reports"],
                         ["10:17", "15:00"])


class _Bot(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off",
                        task_checkin_enabled=True, focus_report_enabled=True)
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "recheck": threading.Event(), "quit": threading.Event(),
                      "last": None, "perf": "", "manual": False}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.addCleanup(lambda: self.bot.db.close())
        p = mock.patch.object(TelegramBot, "today", return_value=MONDAY)
        p.start()
        self.addCleanup(p.stop)

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def names(self):
        return [t["text"] for t in tasks.open_tasks(self.bot.db, MONDAY)]


class BotTaskTest(_Bot):
    def test_checkin_waits_5_minutes_then_stops(self):
        self.say("/viec mới: A; B")
        self.api.clear()
        self.bot.send_task_checkin(MONDAY, "am")
        self.assertIn("📋 Việc cần làm hôm nay", self.api.last())
        self.assertIn("1. A", self.api.last())
        self.assertIn("mình chờ 5 phút", self.api.last())
        self.assertEqual(self.bot.convo[0], "tasks")
        self.assertEqual(self.bot.convo[3], 300)
        out = self.say("xong 1")
        self.assertIn("✅ Xong: A", out[-1])
        self.assertEqual(self.bot.convo[0], "tasks", "vẫn chờ thêm 5 phút cho lệnh kế")
        self.assertEqual(self.names(), ["B"])
        self.assertIn("OK, giữ nguyên", self.say("không")[-1])
        self.assertIsNone(self.bot.convo)
        self.say("xong 1")
        self.assertIsNone(self.bot.convo, "gõ cú pháp lúc bot không hỏi: không mở lượt chờ")

    def test_reply_no_keeps_list(self):
        self.bot.send_task_checkin(MONDAY, "12:45")
        self.assertIn("Cập nhật việc lúc 12:45", self.api.last())
        self.assertIn("OK, giữ nguyên", self.say("không")[-1])
        self.assertIsNone(self.bot.convo)

    def test_after_5_minutes_message_is_normal(self):
        self.bot.send_task_checkin(MONDAY, "am")
        with self.bot._lock:
            kind, q, start, ttl = self.bot.convo
            self.bot.convo = (kind, q, start - 301, ttl)
        self.say("không")
        self.assertNotIn("OK, giữ nguyên", self.api.last(), "hết 5 phút: không còn chờ trả lời")
        self.assertIsNone(self.bot.convo)

    def test_other_text_during_wait_is_understood_normally(self):
        self.bot.send_task_checkin(MONDAY, "am")
        self.say("/status")
        self.say("hôm nay tập trung được bao nhiêu rồi")
        self.assertIsNone(self.bot.convo, "tin khác cú pháp: thôi chờ")

    def test_plan_and_output_with_task_syntax_act_like_viec(self):
        self.say("/viec mới: A")
        out = self.say("/plan mới: check jira ticket")
        self.assertIn("➕ Thêm: check jira ticket", out[-1])
        self.assertEqual(self.names(), ["A", "check jira ticket"], "không còn chữ «mới:» trong tên việc")
        from focus.storage import get_note
        self.assertFalse(get_note(self.bot.db, MONDAY).get("plan"), "không ghi đè kế hoạch bằng cú pháp")
        out = self.say("/output xong 1")
        self.assertIn("✅ Xong: A", out[-1])
        self.assertEqual(get_note(self.bot.db, MONDAY).get("output").count("A ("), 1, "output chỉ 1 dòng")
        self.say("/plan fix job đối soát")
        self.assertIn("fix job đối soát", self.names())
        self.assertEqual(get_note(self.bot.db, MONDAY).get("plan"), "fix job đối soát")

    def test_syntax_works_any_time(self):
        self.say("mới: Viết spec")
        self.assertEqual(self.names(), ["Viết spec"])
        out = self.say("hoàn tác")
        self.assertIn("hoàn tác", out[-1])
        self.assertEqual(self.names(), [])

    def test_bad_number_message(self):
        out = self.say("xong 9")
        self.assertIn("Không có việc số 9", out[-1])

    def test_skip_checkin_right_after_late_morning_list(self):
        self.bot.send_task_checkin(MONDAY, "am")
        self.api.clear()
        self.bot.send_task_checkin(MONDAY, "12:45")
        self.assertEqual(self.api.sent(), [], "vừa gửi danh sách đầu ngày chưa tới 1 giờ")

    def test_viec_on_off(self):
        out = self.say("/viec off")
        self.assertIn("Đã TẮT", out[-1])
        self.assertFalse(self.cfg["task_checkin_enabled"])
        self.assertEqual(get_pref(self.bot.db, "task_checkin_enabled"), "0")
        self.say("/viec on")
        self.assertTrue(self.cfg["task_checkin_enabled"])
        self.assertEqual(self.names(), [], "«off» không phải lệnh bỏ việc")

    def test_viec_view_and_bad_syntax(self):
        self.assertIn("Việc cần làm hôm nay", self.say("/viec")[-1])
        out = self.say("/viec làm gì đó")[-1]
        self.assertIn("Việc cần làm hôm nay", out, "không phải cú pháp: hiện danh sách kèm cách cập nhật")
        self.assertIn("xong 1 3", out)
        self.assertEqual(self.say("danh sách việc hôm nay")[-1].count("Việc cần làm hôm nay"), 1)
        self.assertEqual(self.bot.pending, {}, "chỉ xem: không hỏi OK")

    def test_plan_issue_tomorrow_output_join_the_list(self):
        self.say("/plan 1. Viết spec API\n2. Fix job đối soát")
        self.assertEqual(self.names(), ["Viết spec API", "Fix job đối soát"])
        self.assertIn("Đã thêm 2 việc", self.api.last())
        self.say("/issue thiếu quyền DB2")
        self.assertEqual(self.names()[-1], "thiếu quyền DB2")
        self.say("/tmrtask Gọi anh Tuấn")
        self.assertNotIn("Gọi anh Tuấn", self.names())
        self.assertEqual(tasks.open_tasks(self.bot.db, TUESDAY)[0]["text"], "Gọi anh Tuấn")
        out = self.say("/output xong spec API")
        self.assertIn("gõ «xong 1»", out[-1], "gợi ý, không tự đánh xong")
        self.assertIn("Viết spec API", self.names())

    def test_review_output_answer_with_syntax(self):
        self.say("/viec mới: A; B")
        self.bot.start_convo("review", manual=True)
        self.assertIn("Việc cần làm hôm nay", self.api.last())
        self.say("xong 2")
        self.assertEqual(self.names(), ["A"])
        self.assertEqual(self.bot.convo[1][0][0], "issues", "sang câu hỏi kế")

    def test_morning_greeting_has_no_pending_block_when_list_on(self):
        self.say("/viec mới: A")
        self.bot.cfg["encouragement_enabled"] = True
        with mock.patch("focus.motivation.morning_message", return_value="Chào buổi sáng"):
            self.api.clear()
            self.bot.send_morning(MONDAY)
        self.assertNotIn("A", self.api.last().replace("Chào", ""))


class FocusReportTest(_Bot):
    def test_report_fallback_without_ai(self):
        self.bot.send_focus_report(MONDAY, "10:17")
        text = self.api.last()
        self.assertIn("Tập trung chuyên sâu hôm nay: 0m / mục tiêu 4h (0%)", text)
        self.assertIn("Nhịp cần lúc này", text)
        self.assertNotIn("🤖", text, "AI tắt: câu có sẵn")
        self.assertIsNone(self.bot.convo)

    def test_combined_with_tasks_starts_wait(self):
        self.say("/viec mới: A")
        self.bot.send_focus_report(MONDAY, "12:45", with_tasks=True)
        text = self.api.last()
        self.assertIn("Tập trung chuyên sâu", text)
        self.assertIn("Cập nhật việc lúc 12:45", text)
        self.assertEqual(self.bot.convo[0], "tasks")

    def test_combined_skips_list_right_after_late_morning_list(self):
        self.bot.send_task_checkin(MONDAY, "am")
        self.bot.end_task_convo()
        self.bot.send_focus_report(MONDAY, "12:45", with_tasks=True)
        self.assertNotIn("Cập nhật việc", self.api.last())
        self.assertIsNone(self.bot.convo)

    def test_ai_comment_prompt_and_text(self):
        self.cfg["ai_provider"] = "auto"
        self.cfg["gemini_api_key"] = "x" * 20
        with mock.patch.object(ai_client, "generate", return_value=("Đang hơi chậm, vào một khối 45 phút nhé.", "m")) as g:
            self.bot.send_focus_report(MONDAY, "10:17")
        self.assertIn("🤖 Đang hơi chậm", self.api.last())
        prompt = g.call_args[0][1]
        self.assertIn("expected_deep_hours", prompt)
        self.assertEqual(g.call_args[1]["purpose"], "progress")

    def test_facts_expected_pace(self):
        f = progress.facts(self.bot.db, self.cfg, MONDAY, "12:30")
        # 08:00–11:15 = 195 phút trên tổng 465 phút làm (08:00–17:00 trừ trưa 75 phút)
        self.assertAlmostEqual(f["expected_deep_hours"], round(4 * 195 / 465, 2))

    def test_baosau_command(self):
        self.assertIn("Tập trung chuyên sâu", self.say("/baosau")[-1])
        self.say("/baosau off")
        self.assertFalse(self.cfg["focus_report_enabled"])


class TrackerCombineTest(TempCase):
    def test_1245_sends_one_combined_message(self):
        from focus.tracker import Tracker
        from tests.test_bot_hours import FakeClock, VdiProbe
        self.cfg.update(task_checkin_enabled=True, focus_report_enabled=True)
        bot = mock.Mock()
        t = Tracker.__new__(Tracker)
        t.state = {"manual": False}
        t.cfg, t.bot, t.db, t.day, t.week_id, t.manual = self.cfg, bot, open_db(db_path(self.cfg)), MONDAY, "W", False
        self.addCleanup(t.db.close)
        t.last_vdi_work = None
        t.now = lambda: dt.datetime(2026, 11, 23, 12, 45)
        t.clock = time.time
        sent = []
        t.submit = lambda name, fn, *a: sent.append((name, a))
        t.run_jobs("12:45", False, None, {})
        names = [n for n, _ in sent]
        self.assertIn("focus_1245", names)
        self.assertNotIn("tasks_1245", names, "đã gộp vào tin báo tập trung")
        self.assertEqual(dict(sent)["focus_1245"], (MONDAY, "12:45", True))


class HtmlTasksTest(TempCase):
    def test_daily_html_shows_done_new_dropped(self):
        from focus import report
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        tasks.ensure_started(db, self.cfg, MONDAY, off_day)

        def run(text):
            tasks.apply(db, self.cfg, MONDAY, tasks.parse(text, dt.date.fromisoformat(MONDAY)), off_day)
        run("mới: A; B; C")
        run("xong 1")
        run("bỏ 2")
        path, _ = report.write_report(db, self.cfg, MONDAY)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("📋 Danh sách việc hôm nay", html)
        self.assertIn("✅ Đã xong (1)", html)
        self.assertIn("➕ Thêm mới hôm nay (3)", html)
        self.assertIn("🗑 Đã bỏ (1)", html)
        self.assertIn("Việc chưa xong trong danh sách việc", html)
        self.assertNotIn("Kế hoạch đầu ngày", html, "dùng danh sách việc, chưa ghi /plan: ẩn ô kế hoạch trống")

    def test_html_before_task_list_unchanged(self):
        from focus import report
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        path, _ = report.write_report(db, self.cfg, MONDAY)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("Danh sách việc hôm nay", html)
        self.assertIn("Kế hoạch đầu ngày", html)
