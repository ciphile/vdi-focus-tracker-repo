"""Hỏi AI (/ask), tra web cho câu hỏi cần số liệu mới, hồ sơ người dùng trong prompt, /status, đếm từ AI."""
import json
import threading
from unittest import mock

from focus import ai_client, ai_context, intent
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, make_cfg, msg


class Calls:
    def __init__(self, text="Giá vàng SJC hôm nay ... (nguồn: sjc.com.vn, 09:00)", fail=False):
        self.calls, self.text, self.fail = [], text, fail

    def __call__(self, cfg, prompt, system="", image=None, purpose="", web=False):
        self.calls.append({"prompt": prompt, "system": system, "purpose": purpose, "web": web})
        if self.fail:
            raise ai_client.AIError("mất mạng")
        return self.text, "m"


class AskTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k")
        self.cfg["persona"] = dict(self.cfg["persona"], tuoi="38", noi_song="TP.HCM")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)

    def say(self, text, fake=None, **kw):
        self.api.clear()
        fake = fake or Calls()
        with mock.patch.object(ai_client, "generate", fake):
            self.bot.handle(msg(text, **kw))
        return fake, self.api.sent()

    def test_one_shot_question_has_full_context_and_web(self):
        fake, out = self.say("/ask giá vàng hôm nay bao nhiêu", **{"from": {"first_name": "Khoa"}})
        call = fake.calls[0]
        self.assertTrue(call["web"], "câu hỏi được phép tra web")
        self.assertEqual(call["purpose"], "ask")
        self.assertIn("giá vàng hôm nay", call["prompt"])
        self.assertIn("không bịa số", call["prompt"].lower().replace("tuyệt đối ", ""))
        for word in ("Khoa", "38", "TP.HCM", "AS400", "Life Asia", "COBOL", "không có trí nhớ"):
            self.assertIn(word, call["system"])
        self.assertIn("luc_nay", call["prompt"])
        self.assertIn("SJC", out[-1])

    def test_ask_mode_routes_plain_text(self):
        self.assertIn("ĐANG TẮT", self.say("/ask")[1][0])
        self.assertIn("BẬT", self.say("/ask on")[1][0])
        fake, out = self.say("làm sao để kiếm thêm thu nhập")
        self.assertEqual(fake.calls[-1]["purpose"], "ask")
        self.assertIn("/ask off", out[-1])
        fake, out = self.say("việc ngày mai là gửi spec")  # đang hỏi AI: không thành thao tác ghi
        self.assertEqual(fake.calls[-1]["purpose"], "ask")
        self.assertFalse(self.bot.pending)
        _, out = self.say("/tmrtask gửi spec")  # lệnh vẫn chạy
        self.assertIn("Sáng mai", out[0])
        # khởi động lại vẫn giữ chế độ
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        self.assertTrue(TelegramBot(cfg2, self.state, api=self.api).ask_mode())
        self.assertIn("TẮT", self.say("/ask off")[1][0])
        fake, _ = self.say("việc ngày mai là gửi spec", Calls(fail=True))
        self.assertTrue(self.bot.pending, "tắt hỏi AI: lại thành thao tác ghi, chờ OK")

    def test_ai_error_reported(self):
        fake, out = self.say("/ask thời tiết", Calls(fail=True))
        self.assertIn("AI chưa trả lời được", out[-1])

    def test_no_key(self):
        self.cfg["gemini_api_key"] = ""
        _, out = self.say("/ask hello")
        self.assertIn("Chưa có API key", out[-1])

    def test_question_without_ask_mode_goes_to_ai(self):
        self.assertEqual(intent.by_rules("giá vàng hôm nay bao nhiêu?")[0].name, "hoi_ai")
        self.assertEqual(intent.by_rules("làm sao cải thiện sự tập trung")[0].name, "hoi_ai")
        self.assertEqual(intent.by_rules("chán quá")[0].name, "tro_chuyen")
        self.assertEqual(intent.by_rules("VDI chậm")[0].name, "ghi_issue")

    def test_tg_name_only_when_persona_empty(self):
        self.say("/ask x", **{"from": {"first_name": "Khoa"}})
        self.assertIn("Khoa", ai_context.system_prompt(self.cfg))
        self.cfg["persona"] = dict(self.cfg["persona"], ten="Minh")
        sp = ai_context.system_prompt(self.cfg)
        self.assertIn("Minh", sp)
        self.assertNotIn("Khoa", sp)


class WebAndUsageTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg["gemini_api_key"] = "k"

    def test_gemini_web_tool_and_fallback(self):
        bodies = []

        def fake_http(cfg, method, url, headers, payload=None):
            if method == "GET":
                return {"models": []}
            bodies.append(json.loads(json.dumps(payload)))
            if payload.get("tools"):
                raise ai_client.HTTPStatusError(400, "tools not supported")
            return {"candidates": [{"content": {"parts": [{"text": "ok ba bốn"}]}}]}
        with mock.patch.object(ai_client, "_http", fake_http):
            text, _ = ai_client.generate(self.cfg, "hai từ", "sys", purpose="ask", web=True)
        self.assertEqual(text, "ok ba bốn")
        self.assertEqual(bodies[0]["tools"], [{"google_search": {}}])
        self.assertNotIn("tools", bodies[1])
        u = ai_client.usage_summary(self.cfg)
        from focus import ai_context
        ctx = len(ai_context.ensure_context(self.cfg, "sys").split())
        self.assertEqual((u["calls_today"], u["words_in_today"], u["words_out_today"]), (1, 2 + ctx, 3))
        self.assertEqual(u["purposes_today"], {"ask": 1})

    def test_no_web_by_default(self):
        bodies = []

        def fake_http(cfg, method, url, headers, payload=None):
            if method == "GET":
                return {"models": []}
            bodies.append(payload)
            return {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}
        with mock.patch.object(ai_client, "_http", fake_http):
            ai_client.generate(self.cfg, "p", purpose="daily_review")
        self.assertNotIn("tools", bodies[0])

    def test_claude_web_tool(self):
        cfg = make_cfg(self.tmp, ai_provider="claude", anthropic_api_key="a")
        bodies = []

        def fake_http(cfg, method, url, headers, payload=None):
            bodies.append(payload)
            return {"content": [{"type": "server_tool_use"}, {"type": "text", "text": "Giá "},
                                {"type": "text", "text": "vàng"}], "model": "c"}
        with mock.patch.object(ai_client, "_http", fake_http):
            text, _ = ai_client.generate(cfg, "q", purpose="ask", web=True)
        self.assertEqual(text, "Giá vàng")
        self.assertEqual(bodies[0]["tools"][0]["name"], "web_search")

    def test_status_shows_words_and_budget(self):
        self.cfg["ai_daily_call_budget"] = 50
        ai_client._count_usage(self.cfg, "m", "ask", 120, 80)
        ai_client._count_usage(self.cfg, "m", "morning:bible", 30, 20)
        st = ai_client.status_text(self.cfg)
        self.assertIn("2 lượt, gửi 150 từ, nhận 100 từ", st)
        self.assertIn("còn 48 lượt", st)
        self.assertIn("hỏi AI 1", st)
        self.assertIn("chào sáng 1", st)


class StatusTest(TempCase):
    def test_full_status(self):
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k")
        api = FakeTelegramAPI()
        state = {"paused": threading.Event(), "last": {"idle": 3, "locked": False, "vdi_state": "minimized",
                                                         "fg_proc": "chrome.exe", "fg_title": "", "vdi_full": None},
                 "perf": "CPU 0.01%, RAM 30 MB"}
        bot = TelegramBot(self.cfg, state, api=api)
        insert_run(bot.db, bot.today(), "09:00", 30)
        api.clear()
        bot.handle(msg("/status"))
        text = api.sent()[0]
        for word in ("VDI đang thu nhỏ", "Hôm nay", "AI", "lượt", "Khích lệ", "Giọng", "Hỏi AI", "CPU"):
            self.assertIn(word, text)


class HelpTest(TempCase):
    def test_help_lists_every_command_with_examples(self):
        from focus.actions import ACTIONS, full_help
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42")
        api = FakeTelegramAPI()
        bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=api)
        for cmd in ("/help", "/start"):
            api.clear()
            bot.handle(msg(cmd))
            text = "\n".join(api.sent())
            for a in ACTIONS:
                for c in a.commands:
                    self.assertIn(c, text)
            for word in ("BOT TỰ LÀM", "Ví dụ", "11:15–12:30", "/ask on", "/encourage bible", "✅ OK"):
                self.assertIn(word, text)
            self.assertTrue(all(len(m) <= 4096 for m in api.sent()))
        self.cfg["as400_enabled"] = False
        self.assertNotIn("/as400", full_help(self.cfg))


class ModelChainTest(TempCase):
    def test_pro_models_never_used_and_status_per_model(self):
        self.cfg["gemini_api_key"] = "k"
        posted = []

        def fake_http(cfg, method, url, headers, payload=None):
            if method == "GET":
                return {"models": [{"name": "models/gemini-9.9-pro", "supportedGenerationMethods": ["generateContent"]}]}
            posted.append(url.split("/models/")[1].split(":")[0])
            raise ai_client.HTTPStatusError(429, "quota GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        with mock.patch.object(ai_client, "_http", fake_http):
            with self.assertRaises(ai_client.AIError):
                ai_client.generate(self.cfg, "x")
        self.assertNotIn("gemini-9.9-pro", posted)
        self.assertEqual(posted[0], "gemini-flash-lite-latest")
        self.assertEqual(posted[:3], ["gemini-flash-lite-latest"] + ai_client.FLASH_LITE_EXTRAS)
        st = ai_client.status_text(self.cfg)
        self.assertIn("gemini-flash-lite-latest: 1/20 (hết)", st)
