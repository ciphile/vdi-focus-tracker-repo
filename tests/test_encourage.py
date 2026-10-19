"""Lời khích lệ tự động đầu ngày: luôn tích cực, đủ ngữ cảnh cho AI, bật/tắt, chọn danh ngôn / Kinh Thánh."""
import datetime as dt
import threading
from unittest import mock

from focus import ai_client, motivation
from focus.schedule import due_jobs
from focus.storage import get_pref, save_note
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, make_cfg, msg


class Calls:
    def __init__(self, text="Chào buổi sáng!\n\"Câu\" (Phi-líp 4:13)", fail=False):
        self.calls, self.text, self.fail = [], text, fail

    def __call__(self, cfg, prompt, system="", image=None, purpose=""):
        self.calls.append({"prompt": prompt, "system": system, "purpose": purpose})
        if self.fail:
            raise ai_client.AIError("mất mạng")
        return self.text, "m"


class EncourageTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k")
        self.api = FakeTelegramAPI()
        self.bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=self.api)
        self.day = self.bot.today()

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def morning(self, fake=None):
        self.api.clear()
        fake = fake or Calls()
        with mock.patch.object(ai_client, "generate", fake):
            self.bot.send_morning(self.day)
        return fake, self.api.sent()

    # --- lịch -----------------------------------------------------------------
    def test_morning_job_schedule(self):
        kw = dict(active=True, off=False, note={}, has_bot=True)
        self.assertIn("morning", due_jobs(self.cfg, "08:05", 1, **kw))
        self.assertEqual(due_jobs(self.cfg, "08:05", 1, **kw)[:2], ["morning", "plan"], "chào trước, hỏi kế hoạch sau")
        self.assertNotIn("morning", due_jobs(self.cfg, "07:30", 1, **kw), "trước giờ làm")
        self.assertNotIn("morning", due_jobs(self.cfg, "11:30", 1, **kw), "giờ trưa")
        self.assertNotIn("morning", due_jobs(self.cfg, "08:05", 1, **dict(kw, active=False)), "chưa ngồi máy")
        self.assertEqual(due_jobs(self.cfg, "08:05", 1, **dict(kw, off=True)), [], "ngày nghỉ")
        self.cfg["encouragement_enabled"] = False
        jobs = due_jobs(self.cfg, "15:00", 1, **kw)
        self.assertNotIn("morning", jobs)
        self.assertNotIn("boost", jobs)

    # --- nội dung -------------------------------------------------------------
    def test_morning_prompt_full_context_and_positive(self):
        yday = (dt.date.fromisoformat(self.day) - dt.timedelta(days=1))
        while yday.weekday() >= 5:
            yday -= dt.timedelta(days=1)
        save_note(self.bot.db, yday.isoformat(), {"tomorrow": "viết spec API"})
        insert_run(self.bot.db, yday.isoformat(), "09:00", 60)
        fake, out = self.morning()
        call = fake.calls[0]
        self.assertTrue(call["purpose"].startswith("morning:"))
        for word in ("tích cực", "chào buổi sáng", "viết spec API", "first_task"):
            self.assertIn(word, call["prompt"])
        for word in ("AS400", "Life Asia", "COBOL", "không có trí nhớ", "Giọng"):
            self.assertIn(word, call["system"])
        self.assertIn("Phi-líp", out[0])
        self.assertTrue(any("MORNING_SENT" in l for l in self.audit_lines()))

    def test_morning_reminds_previous_day_pending(self):
        """Yêu cầu 16/10: sáng nay bot không nhắc việc còn tồn hôm qua (plan chưa có trong output, issue)."""
        yday = (dt.date.fromisoformat(self.day) - dt.timedelta(days=1))
        while yday.weekday() >= 5:
            yday -= dt.timedelta(days=1)
        save_note(self.bot.db, yday.isoformat(), {
            "plan": "1. Gởi estimation uat release cho SH\n2. Uat check premium vóm\n3. Xin nghỉ phép\n4. Tạo wu",
            "output": "- đã gửi estimation UAT release cho SH (10:20)\n- tạo xong WU (15:00)",
            "issues": "- VDI chậm lúc build (14:10)"})
        fake, out = self.morning()
        prompt = fake.calls[0]["prompt"]
        self.assertIn("pending_from_previous_workday", prompt)
        self.assertIn("Uat check premium vóm", prompt)
        self.assertIn("issue: VDI chậm lúc build", prompt)
        self.assertIn("KHÔNG chép lại danh sách", prompt)
        msg_text = out[0]
        self.assertIn("📌 Việc còn tồn từ", msg_text)
        self.assertIn("• Uat check premium vóm", msg_text)
        self.assertIn("• Xin nghỉ phép", msg_text)
        self.assertIn("• ⚠️ issue: VDI chậm lúc build", msg_text)
        self.assertNotIn("• Gởi estimation", msg_text, "đã có trong output")
        self.assertNotIn("• Tạo wu", msg_text, "đã có trong output")

    def test_morning_reports_yesterday_overtime(self):
        yday = (dt.date.fromisoformat(self.day) - dt.timedelta(days=1))
        while yday.weekday() >= 5:
            yday -= dt.timedelta(days=1)
        insert_run(self.bot.db, yday.isoformat(), "15:00", 60)
        insert_run(self.bot.db, yday.isoformat(), "20:00", 45)  # làm bù buổi tối
        fake, out = self.morning()
        self.assertIn("làm thêm ngoài giờ (OT) 45m trong VDI (20:00–20:45)", out[0])
        self.assertIn("Tổng OT 14 ngày qua: 45m trong 1 ngày", out[0])
        self.assertIn("không tính sao nhãng", out[0])
        self.assertIn("làm thêm ngoài giờ 45m", fake.calls[0]["prompt"])

    def test_morning_without_pending_has_no_block(self):
        _, out = self.morning()
        self.assertNotIn("Việc còn tồn", out[0])
        self.assertNotIn("ngoài giờ", out[0])

    def test_bible_prompt_is_protestant(self):
        self.cfg["encouragement_styles"] = ["bible"]
        fake, _ = self.morning()
        p = fake.calls[0]["prompt"]
        self.assertIn("Tin Lành", p)
        self.assertIn("Truyền Thống 1926", p)
        self.assertIn("KHÔNG dùng các sách", p)

    def test_offline_fallback_positive(self):
        self.cfg["encouragement_styles"] = ["bible"]
        fake, out = self.morning(Calls(fail=True))
        self.assertIn(out[0].splitlines()[0], motivation.MORNING_HELLO)
        self.assertTrue(any(ref in out[0] for _, ref in motivation.BIBLE))

    def test_no_key_still_sends(self):
        self.cfg["gemini_api_key"] = ""
        fake, out = self.morning()
        self.assertEqual(fake.calls, [])
        from focus import motivation
        self.assertIn(out[0].splitlines()[0], motivation.MORNING_HELLO)   # AI không có: chào bằng câu có sẵn, ngẫu nhiên

    def test_disabled_sends_nothing(self):
        self.cfg["encouragement_enabled"] = False
        fake, out = self.morning()
        self.assertEqual((fake.calls, out), ([], []))

    def test_styles_respected(self):
        for mode, allowed in (("quote", {"motivation", "family"}), ("bible", {"bible"})):
            self.cfg["encouragement_styles"] = list(motivation.MODES[mode])
            for _ in range(10):
                fake, _ = self.morning()
                self.assertIn(fake.calls[-1]["purpose"].split(":")[1], allowed)

    # --- lệnh /encourage --------------------------------------------------------
    def test_encourage_command(self):
        self.assertIn("ĐANG BẬT", self.say("/encourage")[0])
        self.say("/encourage bible")
        self.assertEqual(self.bot.cfg["encouragement_styles"], ["bible"])
        self.say("/encourage quote")
        self.assertNotIn("bible", self.bot.cfg["encouragement_styles"])
        self.say("/encourage both")
        self.assertIn("bible", self.bot.cfg["encouragement_styles"])
        self.assertIn("ĐANG TẮT", self.say("/encourage off")[0])
        self.assertFalse(self.bot.cfg["encouragement_enabled"])
        # khởi động lại vẫn giữ
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.bot.state, api=self.api)
        self.assertFalse(cfg2["encouragement_enabled"])
        self.assertIn("bible", cfg2["encouragement_styles"])
        self.say("/encourage on")
        self.assertTrue(self.bot.cfg["encouragement_enabled"])
        self.say("/encourage mac_dinh")
        self.assertIsNone(get_pref(self.bot.db, "encouragement_styles"))
        self.assertEqual(self.bot.cfg["encouragement_styles"], ["motivation", "family"],
                         "mặc định khi cài lần đầu: tắt Kinh Thánh")
        self.assertIn("Chọn một trong", self.say("/encourage xyz")[0])

    def test_kinhthanh_toggle(self):
        self.assertEqual(self.bot.cfg["encouragement_styles"], ["motivation", "family"], "cài lần đầu: tắt Kinh Thánh")
        self.assertIn("Kinh Thánh: BẬT", self.say("/kinhthanh")[0])
        out = self.say("/kinhthanh")
        self.assertIn("Kinh Thánh: TẮT", out[0], "lệnh gạch chéo chạy luôn, không hỏi lại")
        self.assertNotIn("bible", self.bot.cfg["encouragement_styles"])
        self.assertIn("motivation", self.bot.cfg["encouragement_styles"])
        self.assertIn("Kinh Thánh: BẬT", self.say("/kinhthanh")[0])
        self.assertEqual(self.bot.cfg["encouragement_styles"], ["bible"])
        self.say("/kinhthanh off")
        self.say("/kinhthanh off")
        self.assertNotIn("bible", self.bot.cfg["encouragement_styles"], "off 2 lần vẫn là tắt")
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.bot.state, api=self.api)
        self.assertNotIn("bible", cfg2["encouragement_styles"], "khởi động lại vẫn giữ")
        self.say("/kinhthanh on")
        self.assertEqual(self.bot.cfg["encouragement_styles"], ["bible"])
        self.assertIn("Chọn on", self.say("/kinhthanh xyz")[0])

    def test_encourage_natural_language(self):
        cases = {"chỉ gửi kinh thánh thôi nhé": "bible", "đừng gửi kinh thánh, chỉ khích lệ thôi": "quote",
                 "tắt tin nhắn khích lệ giúp mình": "off", "gửi lời khích lệ cả hai loại": "both"}
        for text, mode in cases.items():
            with mock.patch.object(ai_client, "generate", Calls(fail=True)):
                self.say(text)
            self.assertTrue(self.bot.pending, text)
            action, args = list(self.bot.pending.values())[0][:2]
            self.assertEqual((action.name, args.get("mode")), ("cai_khich_le", mode), text)
            self.bot.cancel_pending()

    def test_plan_convo_no_double_encouragement(self):
        with mock.patch.object(ai_client, "generate", Calls()) as fake:
            self.api.clear()
            self.bot.start_convo("plan")
        self.assertEqual(len(self.api.sent()), 1, "chỉ hỏi kế hoạch; lời chào đã gửi ở job morning")


class WeekendOvertimeTest(TempCase):
    """Làm bù cuối tuần (tự bật bot): sáng thứ Hai báo giờ làm bù; tổng kết tuần, /today ngày nghỉ có giờ làm bù."""

    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42")
        self.api = FakeTelegramAPI()
        self.bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=self.api)
        db = self.bot.db
        insert_run(db, "2026-10-16", "09:00", 60)                    # thứ Sáu trong giờ
        insert_run(db, "2026-10-17", "09:00", 50)                    # thứ Bảy làm bù trong VDI
        insert_run(db, "2026-10-17", "10:00", 30, vdi="background")  # thứ Bảy lướt web: không ghi
        insert_run(db, "2026-10-18", "20:00", 25)                    # Chủ nhật tối làm bù

    def test_monday_morning_lists_weekend_overtime(self):
        text = self.bot.overtime_line("2026-10-19")
        lines = text.splitlines()
        self.assertEqual(len(lines), 3, text)
        self.assertIn("Thứ bảy 17/10 (cuối tuần) bạn bật bot làm bù 50m trong VDI (09:00–09:50)", lines[0])
        self.assertIn("Chủ nhật 18/10 (cuối tuần) bạn bật bot làm bù 25m trong VDI (20:00–20:25)", lines[1])
        self.assertIn("Tổng OT 14 ngày qua: 1h 15m trong 2 ngày", lines[2])
        self.assertIn("không tính sao nhãng", text)

    def test_week_facts_and_today_for_off_day(self):
        from focus.analysis import analyze, week_facts
        from focus.report import summary_text, week_text
        f = week_facts(self.bot.db, self.cfg, "2026-10-18")
        self.assertEqual(len(f["off_day_overtime"]), 2)
        self.assertIn("làm bù trong VDI 0.8h", f["off_day_overtime"][0])
        self.assertAlmostEqual(f["overtime_hours"], round((50 + 25) / 60, 1))
        self.assertIn("Làm bù ngày nghỉ", week_text(f))
        a = analyze(self.bot.db, self.cfg, "2026-10-17")
        out = summary_text(a, {})
        self.assertIn("ngày nghỉ (cuối tuần)", out)
        self.assertIn("Làm bù trong VDI: 50m", out)
        self.assertNotIn("Điểm tổng", out)
        self.assertEqual(a["other"], 0)
