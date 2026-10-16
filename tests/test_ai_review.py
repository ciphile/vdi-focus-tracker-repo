"""AI tự đánh giá cuối ngày / cuối tuần: ngữ cảnh đầy đủ trong prompt, giọng văn, bật/tắt, /style."""
import datetime as dt
import json
import threading
from unittest import mock

from focus import ai_client, ai_context, motivation
from focus.analysis import day_facts, week_facts
from focus.config import ConfigError, validate
from focus.storage import get_pref, save_note
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, make_cfg, msg


class Calls:
    """ai_client.generate giả: ghi lại prompt/system, trả câu cố định."""

    def __init__(self, text="AI: hôm nay ổn", fail=False):
        self.calls, self.text, self.fail = [], text, fail

    def __call__(self, cfg, prompt, system="", image=None, purpose=""):
        self.calls.append({"prompt": prompt, "system": system, "purpose": purpose})
        if self.fail:
            raise ai_client.AIError("hết quota")
        return self.text, "fake-model"


class ContextTest(TempCase):
    def test_default_context_mentions_platform(self):
        sp = ai_context.system_prompt(self.cfg)
        for word in ("AS400", "IBM i", "COBOL", "Life Asia", "bảo hiểm nhân thọ", "Citrix", "không có trí nhớ",
                     "08:00–17:00", "11:15–12:30", "thu nhỏ"):
            self.assertIn(word, sp)

    def test_custom_work_context(self):
        cfg = make_cfg(self.tmp, work_context="Kế toán dùng SAP")
        sp = ai_context.system_prompt(cfg)
        self.assertIn("Kế toán dùng SAP", sp)
        self.assertNotIn("COBOL", sp)

    def test_tone_in_every_prompt(self):
        for tone, word in (("sep_kho_tinh", "60 tuổi"), ("hai_huoc", "hài hước"), ("vui_tuoi", "vui tươi"),
                           ("than_mat", "thân mật")):
            self.cfg["persona"] = dict(self.cfg["persona"], giong=tone, goi_nguoi_dung="bro", ten_sep="anh Tuấn")
            sp = ai_context.system_prompt(self.cfg)
            self.assertIn(word, sp)
            self.assertIn('"bro"', sp)
            self.assertIn("anh Tuấn", sp)
            self.assertIn(word, motivation.system_prompt(self.cfg))

    def test_glossary_only_present_keys(self):
        g = ai_context.glossary({"deep_hours": 1, "short_idle_count_1_5min": 3})
        self.assertIn("điện thoại", g)
        self.assertNotIn("as400", g)

    def test_config_validation(self):
        for bad in ({"ai_review_enabled": "yes"}, {"work_context": 5}, {"as400_enabled": 1}):
            with self.assertRaises(ConfigError):
                make_cfg(self.tmp, **bad)
        cfg = make_cfg(self.tmp, work_context="  abc  ")
        self.assertEqual(cfg["work_context"], "abc")


class ReviewTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg["gemini_api_key"] = "k"
        from focus.storage import db_path, open_db
        self.db = open_db(db_path(self.cfg))
        self.day = dt.date.today().isoformat()
        insert_run(self.db, self.day, "09:00", 90)
        insert_run(self.db, self.day, "10:30", 20, vdi="background")
        save_note(self.db, self.day, {"plan": "fix job đối soát\nviết spec", "output": "fix job đối soát",
                                      "issues": "VDI chậm", "tomorrow": "viết spec"})
        yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        save_note(self.db, yday, {"issues": "VDI chậm sáng nay"})

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def test_daily_prompt_is_complete(self):
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake):
            text, by_ai = motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
        self.assertEqual((text, by_ai), ("AI: hôm nay ổn", None))
        call = fake.calls[0]
        self.assertEqual(call["purpose"], "daily_review")
        for word in ("pending", "khắc phục", "Mất tập trung", "cải thiện", "Ý nghĩa các trường",
                     "viết spec", "VDI chậm sáng nay", "recent_issues", "tomorrow"):
            self.assertIn(word, call["prompt"])
        for word in ("AS400", "Life Asia", "không có trí nhớ", "Giọng"):
            self.assertIn(word, call["system"])

    def test_daily_payload_separates_today_from_previous_days(self):
        """Dữ liệu gửi AI: "today" chỉ có ngày đang đánh giá; ngày trước nằm riêng, có ngày rõ ràng."""
        prev = (dt.date.fromisoformat(self.day) - dt.timedelta(days=1)).isoformat()
        insert_run(self.db, prev, "12:30", 200)
        save_note(self.db, prev, {"tomorrow": "review code batch"})
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake):
            motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
        prompt = fake.calls[0]["prompt"]
        data = json.loads(prompt.split("SỐ LIỆU (JSON):\n", 1)[1])
        self.assertTrue(data["report_date"].startswith(self.day))
        today = data["today"]
        self.assertEqual(today["day"], self.day)
        for k in ("recent_days", "recent_issues", "avg_deep_hours_7d", "promised_yesterday"):
            self.assertNotIn(k, today, f"{k} là số liệu ngày trước, không được nằm trong today")
        ctx = data["previous_days_context"]
        self.assertIn("KHÔNG phải số liệu ngày " + self.day, ctx["note"])
        self.assertEqual(ctx["recent_days"][0]["date"], prev)
        self.assertEqual(ctx["recent_days"][0]["deep_hours"], 3.3)
        self.assertTrue(all(r["date"] < self.day for r in ctx["recent_days"] + ctx["recent_issues"]))
        self.assertEqual(ctx["promised_yesterday"], {"written_on": prev, "task": "review code batch"})
        self.assertLess(today["deep_hours"], 3, "giờ hôm nay không bị cộng số ngày trước")
        for word in ("CHỈ của ngày " + self.day, "TUYỆT ĐỐI không lấy số liệu ở đây làm số liệu hôm"):
            self.assertIn(word, prompt)

    def test_morning_payload_labels_previous_day(self):
        info = {"today": "2026-10-15", "weekday": "thứ Năm", "first_task": "fix job",
                "yesterday": "2026-10-14: tập trung sâu 5h10m, đạt mục tiêu"}
        data = motivation.morning_payload(info)
        self.assertEqual(data["today"], {"date": "2026-10-15", "weekday": "thứ Năm", "first_task": "fix job"})
        self.assertEqual(data["previous_workday"], {"date": "2026-10-14", "summary": "tập trung sâu 5h10m, đạt mục tiêu"})
        fake = Calls("Chào buổi sáng")
        with mock.patch.object(ai_client, "generate", fake):
            motivation.morning_message(self.cfg, self.db, info, style="motivation")
        self.assertIn("CHƯA có số liệu tập trung hôm nay", fake.calls[0]["prompt"])
        self.assertIn('"previous_workday"', fake.calls[0]["prompt"])

    def test_cache_and_tone_change(self):
        fake = Calls()
        facts = day_facts(self.db, self.cfg, self.day)
        with mock.patch.object(ai_client, "generate", fake):
            motivation.review_day(self.cfg, self.db, facts)
            motivation.review_day(self.cfg, self.db, facts)
            self.assertEqual(len(fake.calls), 1, "lần 2 dùng cache")
            self.cfg["persona"] = dict(self.cfg["persona"], giong="sep_kho_tinh")
            motivation.review_day(self.cfg, self.db, facts)
            self.assertEqual(len(fake.calls), 2, "đổi giọng thì gọi AI lại")
            self.assertIn("60 tuổi", fake.calls[1]["system"])

    def test_disabled_no_ai_call(self):
        self.cfg["ai_review_enabled"] = False
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake):
            text, by_ai = motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
            wtext, wby_ai = motivation.review_week(self.cfg, self.db, week_facts(self.db, self.cfg, self.day))
        self.assertEqual(fake.calls, [])
        self.assertEqual((text, by_ai, wtext, wby_ai), (None, None, None, None), "tắt: không có đánh giá soạn sẵn")

    def test_ai_error_returns_reason_not_canned_text(self):
        with mock.patch.object(ai_client, "generate", Calls(fail=True)):
            text, error = motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
        self.assertIsNone(text)
        self.assertIn("hết quota", error)

    def test_no_key(self):
        self.cfg["gemini_api_key"] = ""
        text, error = motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
        self.assertIsNone(text)
        self.assertIn("API key", error)

    def test_weekly_prompt(self):
        fake = Calls("AI: tuần ổn")
        with mock.patch.object(ai_client, "generate", fake):
            text, error = motivation.review_week(self.cfg, self.db, week_facts(self.db, self.cfg, self.day))
        self.assertEqual((text, error), ("AI: tuần ổn", None))
        p = fake.calls[0]["prompt"]
        for word in ("Issue lặp lại", "pending", "Mục tiêu tuần sau", "giờ vàng", "VDI chậm", "KHÔNG nhớ"):
            self.assertIn(word, p)
        self.assertIn("COBOL", fake.calls[0]["system"])

    def test_weekly_prompt_has_every_day_full_report(self):
        """AI không nhớ các ngày trước: prompt tuần phải chứa báo cáo đầy đủ từng ngày + đánh giá AI đã gửi."""
        motivation._store(self.db, f"review:{self.day}:abc", "AI hôm đó khuyên: chặn giờ vàng 9h")
        fake = Calls("AI: tuần ổn")
        with mock.patch.object(ai_client, "generate", fake):
            motivation.review_week(self.cfg, self.db, week_facts(self.db, self.cfg, self.day))
        data = json.loads(fake.calls[0]["prompt"].split("SỐ LIỆU (JSON):\n", 1)[1])
        days = {d["day"]: d for d in data["days"]}
        today = days[self.day]
        for key in ("plan", "output", "issues", "tomorrow", "focus_blocks", "top_apps_outside_vdi", "score"):
            self.assertIn(key, today)
        self.assertEqual(today["ai_daily_review"], "AI hôm đó khuyên: chặn giờ vàng 9h")
        self.assertIn("week_summary", data)
        self.assertNotIn("recent_days", today, "không lặp số liệu ngày trước trong từng ngày")

    def test_quote_hint_follows_styles(self):
        fake = Calls()
        self.cfg["encouragement_styles"] = ["motivation"]
        with mock.patch.object(ai_client, "generate", fake):
            motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
        prompt = fake.calls[0]["prompt"]
        self.assertNotIn("Truyền Thống 1926", prompt)
        self.assertIn("KHÔNG dùng Kinh Thánh", prompt)
        self.assertIn("danh nhân", prompt)
        self.assertIn("TẮT Kinh Thánh", fake.calls[0]["system"])


class BotToggleTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.day = self.bot.today()
        insert_run(self.bot.db, self.day, "09:00", 60)

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def summary(self):
        self.api.clear()
        with mock.patch.object(ai_client, "generate", Calls()):
            self.bot.send_daily_summary(self.day)
        return self.api.sent()

    def test_auto_summary_has_ai_review(self):
        out = self.summary()
        self.assertTrue(any(s.startswith("🤖 AI đánh giá cuối ngày") and "AI: hôm nay ổn" in s for s in out))

    def test_aireview_off_on_persists(self):
        out = self.say("/aireview off")
        self.assertIn("ĐANG TẮT", out[0])
        self.assertEqual(get_pref(self.bot.db, "ai_review_enabled"), "0")
        self.assertFalse(any("🤖" in s for s in self.summary()))
        # khởi động lại: vẫn tắt
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k")
        bot2 = TelegramBot(cfg2, self.state, api=self.api)
        self.assertFalse(bot2.cfg["ai_review_enabled"])
        self.assertIn("ĐANG BẬT", self.say("/aireview bật")[0])
        self.assertTrue(any("🤖" in s for s in self.summary()))
        self.assertIn("ĐANG BẬT", self.say("/aireview")[0])
        self.say("/aireview mac_dinh")
        self.assertIsNone(get_pref(self.bot.db, "ai_review_enabled"))
        self.assertIn("Chọn on", self.say("/aireview xyz")[0])

    def test_aireview_natural_language_confirms(self):
        with mock.patch.object(ai_client, "generate", Calls(fail=True)):
            out = self.say("tắt AI đánh giá tự động giúp mình")
        self.assertIn("TẮT", out[0])
        self.assertTrue(self.bot.pending, "nhắn tự nhiên phải bấm OK")
        self.assertTrue(self.bot.cfg["ai_review_enabled"])
        pid = list(self.bot.pending)[0]
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        self.assertFalse(self.bot.cfg["ai_review_enabled"])

    def test_view_status_no_confirm(self):
        with mock.patch.object(ai_client, "generate", Calls(fail=True)):
            out = self.say("AI đánh giá đang chạy không")
        self.assertFalse(self.bot.pending)
        self.assertIn("AI tự đánh giá", out[0])

    def test_style_command(self):
        self.assertIn("Giọng hiện tại", self.say("/style")[0])
        with mock.patch.object(ai_client, "generate", Calls("Ừ.")):
            out = self.say("/style sếp khó tính")
        self.assertEqual(self.bot.cfg["persona"]["giong"], "sep_kho_tinh")
        self.assertIn("60 tuổi", out[0])
        self.assertIn("60 tuổi", ai_context.system_prompt(self.bot.cfg))
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.state, api=self.api)
        self.assertEqual(cfg2["persona"]["giong"], "sep_kho_tinh", "khởi động lại vẫn giữ giọng")
        self.say("/style mac_dinh")
        self.assertEqual(self.bot.cfg["persona"]["giong"], "than_mat")
        self.assertIn("Giọng là", self.say("/style abc")[0])

    def test_style_shared_with_tracker(self):
        """Tracker dùng chung dict cfg với bot: đổi giọng thì cảnh báo của tracker cũng đổi."""
        cfg_seen_by_tracker = self.bot.cfg
        with mock.patch.object(ai_client, "generate", Calls("ok")):
            self.say("/style hai_huoc")
        self.assertEqual(cfg_seen_by_tracker["persona"]["giong"], "hai_huoc")



class RetryTest(BotToggleTest):
    def test_ai_down_then_retry_sends_later(self):
        self.api.clear()
        with mock.patch.object(ai_client, "generate", Calls(fail=True)):
            self.bot.send_daily_summary(self.day)
        out = self.api.sent()
        self.assertFalse(any("🤖" in s for s in out))
        self.assertTrue(any("AI chưa đánh giá được hôm nay" in s and "tự gửi" in s for s in out))
        self.assertTrue(self.bot._retries(), "đã hẹn gửi lại")
        self.assertFalse(self.bot.has_review_retry(), "chưa tới giờ: tracker không cần xếp việc gửi lại")
        # chưa tới giờ thử lại: không gọi AI
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake):
            self.bot.retry_ai_reviews(self.day)
        self.assertEqual(fake.calls, [])
        # tới giờ: lỗi tiếp thì im lặng, hẹn lần sau
        self.bot._set_retry("day", self.day, 0)
        self.api.clear()
        with mock.patch.object(ai_client, "generate", Calls(fail=True)):
            self.bot.retry_ai_reviews(self.day)
        self.assertEqual(self.api.sent(), [], "không báo lỗi lặp lại mỗi 15 phút")
        self.bot._set_retry("day", self.day, 0)
        with mock.patch.object(ai_client, "generate", Calls()):
            self.bot.retry_ai_reviews(self.day)
        self.assertTrue(any(s.startswith(f"🤖 AI đánh giá ngày {self.day}") for s in self.api.sent()))
        self.assertFalse(self.bot.has_review_retry())

    def test_old_retry_dropped_and_no_key_no_retry(self):
        self.bot._set_retry("day", "2000-01-01", 0)
        self.bot.retry_ai_reviews(self.day)
        self.assertFalse(self.bot.has_review_retry())
        self.cfg["gemini_api_key"] = ""
        out = self.summary()
        self.assertTrue(any("chưa có API key AI" in s for s in out))
        self.assertFalse(self.bot.has_review_retry())


class TotalScoreInPromptTest(TempCase):
    """Tổng kết ngày / tuần: prompt phải có điểm tổng, ý nghĩa, công thức, và buộc AI giải thích lại cho người dùng."""

    def setUp(self):
        super().setUp()
        from focus.storage import db_path, open_db
        self.cfg["gemini_api_key"] = "k"
        self.db = open_db(db_path(self.cfg))
        self.day = "2026-10-14"
        insert_run(self.db, self.day, "09:00", 300)

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def _data(self, prompt):
        return json.loads(prompt.split("SỐ LIỆU (JSON):\n", 1)[1])

    def test_daily_prompt_explains_total_score(self):
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake):
            motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, self.day))
        p = fake.calls[0]["prompt"]
        for word in ("ĐIỂM TỔNG LÀ GÌ", "người dùng KHÔNG biết điểm tổng là gì", "60%", "30%", "10%", "65%",
                     "100 × max(0, 1 − số lần bị cắt ngang mỗi giờ / 20)", "González", "dưới 30 kém",
                     "từ 85 xuất sắc", "Điểm tổng hôm nay (BẮT BUỘC", "biggest_loss", "how_to_raise",
                     "không phải chuẩn khoa học"):
            self.assertIn(word, p)
        today = self._data(p)["today"]
        self.assertIn("total_score", today)
        ex = today["total_score_explained"]
        self.assertIn(f"{today['total_score']}/100", ex["meaning"])
        self.assertTrue(ex["parts"][0].startswith("Điểm tập trung"))
        self.assertIn("lần/giờ", ex["parts"][1])
        self.assertIn("làm mất nhiều điểm nhất", ex["biggest_loss"])
        self.assertTrue(ex["how_to_raise"])
        self.assertIn("total_score_explained", p.split("SỐ LIỆU (JSON)", 1)[0], "có giải nghĩa trường")

    def test_weekly_prompt_explains_total_score(self):
        fake = Calls("AI: tuần ổn")
        with mock.patch.object(ai_client, "generate", fake):
            motivation.review_week(self.cfg, self.db, week_facts(self.db, self.cfg, self.day))
        p = fake.calls[0]["prompt"]
        for word in ("ĐIỂM TỔNG LÀ GÌ", "Điểm tổng của tuần (BẮT BUỘC", "avg_total_score", "by_day"):
            self.assertIn(word, p)
        ws = self._data(p)["week_summary"]
        self.assertIn("avg_total_score", ws)
        ex = ws["total_score_explained"]
        for key in ("meaning", "avg_parts", "by_day", "best_day", "worst_day", "biggest_loss"):
            self.assertIn(key, ex)
        self.assertIn("điểm tập trung", ex["avg_parts"])
