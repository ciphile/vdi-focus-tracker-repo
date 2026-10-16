"""Gọi AI qua HTTPS: chọn model, 404/429/5xx, lỗi key, dò danh sách model, đếm lượt, cache, Claude, ảnh."""
import base64
import datetime as dt
import io
import json
import os
import threading
import time
import urllib.error
from unittest import mock

from focus import ai_client, ai_context
from focus.ai_client import AIError, HTTPStatusError
from tests.helpers import TempCase, make_cfg

LITE, FLASH = ai_client.PRIMARY_GEMINI, ai_client.FALLBACK_GEMINI
KEY = "AIzaSECRET-KEY-123"
# 429 thật của Gemini: hết quota NGÀY và giới hạn theo PHÚT (khác nhau ở quotaId).
DAY429 = (429, '{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"violations": '
               '[{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
MIN429 = (429, '{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"violations": '
               '[{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}')


def ok_text(text="xin chào"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class FakeHTTP:
    """_http giả. script: model -> danh sách kết quả lần lượt (dict = trả về, int = HTTPStatusError mã đó,
    (mã, body) = HTTPStatusError kèm body).
    models: danh sách model trả cho GET /models (một trang)."""

    def __init__(self, script=None, models=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.models = models if models is not None else []
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, cfg, method, url, headers, payload=None):
        with self.lock:
            self.calls.append({"method": method, "url": url, "headers": dict(headers),
                               "payload": json.loads(json.dumps(payload)) if payload is not None else None})
        if method == "GET":
            return {"models": [{"name": "models/" + m, "supportedGenerationMethods": ["generateContent"]}
                               for m in self.models]}
        model = url.rsplit("/models/", 1)[-1].split(":")[0] if "/models/" in url else "claude"
        seq = self.script.get(model)
        res = seq.pop(0) if seq and len(seq) > 1 else (seq[0] if seq else 404)
        if isinstance(res, int):
            raise HTTPStatusError(res, "body")
        if isinstance(res, tuple):
            raise HTTPStatusError(*res)
        return res

    def posts(self):
        return [c for c in self.calls if c["method"] == "POST"]

    def posted_models(self):
        return [c["url"].rsplit("/models/", 1)[-1].split(":")[0] for c in self.posts()]


class AIBase(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg = make_cfg(self.tmp, gemini_api_key=KEY)
        p = mock.patch.object(ai_client, "RETRY_WAIT_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)

    def use(self, fake):
        p = mock.patch.object(ai_client, "_http", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def cache(self):
        with open(os.path.join(self.cfg["data_dir"], "ai_model.json"), encoding="utf-8") as f:
            return json.load(f)

    def usage(self):
        with open(os.path.join(self.cfg["data_dir"], "ai_usage.json"), encoding="utf-8") as f:
            return json.load(f)


class GeminiFallbackTest(AIBase):
    def test_ok_first_model(self):
        fake = self.use(FakeHTTP({LITE: [ok_text("chào bạn")]}))
        text, model = ai_client.generate(self.cfg, "hi", system="sys", purpose="t")
        self.assertEqual((text, model), ("chào bạn", LITE))
        self.assertEqual(self.cache()["model"], LITE)
        body = fake.posts()[0]["payload"]
        sys_text = body["systemInstruction"]["parts"][0]["text"]
        self.assertTrue(sys_text.startswith("BỐI CẢNH (bạn không có trí nhớ"), "luôn kèm bối cảnh đầy đủ")
        self.assertTrue(sys_text.endswith("\n\nsys"), "dặn riêng của nơi gọi nằm sau bối cảnh")
        self.assertEqual(body["contents"][0]["parts"], [{"text": "hi"}])
        self.assertEqual(fake.posts()[0]["headers"]["x-goog-api-key"], KEY)
        self.assertNotIn(KEY, fake.posts()[0]["url"])  # key nằm trong header, không trong URL

    def test_404_falls_to_next_model(self):
        fake = self.use(FakeHTTP({LITE: [404], FLASH: [ok_text("từ flash")]}))
        text, model = ai_client.generate(self.cfg, "hi")
        self.assertEqual((text, model), ("từ flash", FLASH))
        # 404 không retry; như bot timesheet: dùng hết các bản lite rồi mới tới flash
        self.assertEqual(fake.posted_models(), [LITE] + ai_client.FLASH_LITE_EXTRAS + [FLASH])
        self.assertNotIn(LITE, ai_client.exhausted_today(self.cache()))  # 404 không phải hết quota

    def test_404_model_remembered_and_skipped_30_days(self):
        fake = self.use(FakeHTTP({LITE: [ok_text("lite")]}))
        fake.script = {LITE: [MIN429], FLASH: [ok_text("flash")]}
        ai_client.generate(self.cfg, "hi")  # 2 bản lite phụ trả 404 (mặc định của FakeHTTP)
        self.assertEqual(sorted(ai_client.gone_models(self.cache())), sorted(ai_client.FLASH_LITE_EXTRAS))
        self.assertIn("404", ai_client.status_text(self.cfg))
        fake.calls.clear()
        ai_client.generate(self.cfg, "hi")
        self.assertEqual(fake.posted_models(), [LITE, FLASH])  # không gọi lại model 404
        later = time.time() + (ai_client.GONE_DAYS + 1) * 86400
        with mock.patch.object(ai_client, "_now", return_value=later):
            self.assertEqual(ai_client.gone_models(ai_client._model_cache(self.cfg)), [])  # hết hạn thì thử lại

    def test_web_429_retries_same_model_without_web(self):
        """Gói free: quota tra Google riêng (Gemini 3.x = 0) -> 429 dù gọi thường còn quota. Log thật 15/10."""
        fake = self.use(FakeHTTP({LITE: [MIN429, ok_text("không tra web")]}))
        text, model = ai_client.generate(self.cfg, "giá bitcoin?", purpose="ask", web=True)
        self.assertEqual((text, model), ("không tra web", LITE))
        first, second = fake.posts()
        self.assertEqual(first["payload"]["tools"], [{"google_search": {}}])
        self.assertNotIn("tools", second["payload"])
        self.assertIn("KHÔNG tra web", second["payload"]["contents"][0]["parts"][-1]["text"])
        self.assertTrue(second["payload"]["contents"][0]["parts"][-1]["text"].startswith("giá bitcoin?"))
        self.assertEqual(self.cache()["quota_exhausted"], [])  # quota tra web không phải quota gọi thường

    def test_web_429_daily_also_not_marked_exhausted(self):
        self.use(FakeHTTP({LITE: [DAY429, ok_text("ok")]}))
        self.assertEqual(ai_client.generate(self.cfg, "x", web=True)[0], "ok")
        self.assertEqual(self.cache()["quota_exhausted"], [])

    def test_web_429_then_minute_429_moves_to_next_model_without_web(self):
        fake = self.use(FakeHTTP({LITE: [MIN429], FLASH: [ok_text("flash")]}))
        self.assertEqual(ai_client.generate(self.cfg, "x", web=True)[1], FLASH)
        self.assertNotIn("tools", fake.posts()[-1]["payload"])
        self.assertEqual(fake.posts()[-1]["payload"]["contents"][0]["parts"][-1]["text"].count("KHÔNG tra web"), 1)

    def test_429_marks_exhausted_and_skips_next_time(self):
        fake = self.use(FakeHTTP({LITE: [DAY429], FLASH: [ok_text()]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi")[1], FLASH)
        self.assertEqual(fake.posted_models(), [LITE] + ai_client.FLASH_LITE_EXTRAS + [FLASH])
        self.assertEqual([(e["model"], e["date"]) for e in self.cache()["quota_exhausted"]], [(LITE, ai_client._today())])
        self.assertTrue(any("AI_QUOTA_EXHAUSTED" in l and LITE in l for l in self.audit_lines()))
        fake.calls.clear()
        self.assertEqual(ai_client.generate(self.cfg, "hi")[1], FLASH)
        self.assertNotIn(LITE, fake.posted_models())  # model hết quota hôm nay bị bỏ qua

    def test_all_429_goes_offline_3h_then_fails_fast(self):
        fake = self.use(FakeHTTP({}, models=["gemini-2.5-flash"]))
        fake.script = {LITE: [DAY429], FLASH: [DAY429], "gemini-2.5-flash": [DAY429]}
        before = time.time()
        with self.assertRaises(AIError) as cm:
            ai_client.generate(self.cfg, "hi")
        self.assertIn("hết quota", str(cm.exception))
        until = self.cache()["offline_until"]
        self.assertAlmostEqual(until - before, 3 * 3600, delta=60)
        self.assertIn("tạm nghỉ", ai_client.status_text(self.cfg))
        fake.calls.clear()
        with self.assertRaises(AIError) as cm:
            ai_client.generate(self.cfg, "hi")
        self.assertIn("tạm không dùng được", str(cm.exception))
        self.assertEqual(fake.calls, [])  # không gọi HTTP khi đang nghỉ

    def test_new_day_resets_quota_and_offline(self):
        fake = self.use(FakeHTTP({LITE: [DAY429], FLASH: [DAY429]}))
        with mock.patch.object(ai_client, "_today", return_value="2026-10-13"):
            with self.assertRaises(AIError):
                ai_client.generate(self.cfg, "hi")
        fake.script = {LITE: [ok_text("ngày mới")]}
        fake.calls.clear()
        later = ai_client.quota_reset_after(time.time()) + 60  # đã qua mốc reset quota của Google
        with mock.patch.object(ai_client, "_today", return_value="2026-10-14"), \
                mock.patch.object(ai_client, "_now", return_value=later):
            self.assertEqual(ai_client.generate(self.cfg, "hi"), ("ngày mới", LITE))
            self.assertEqual(self.cache()["quota_exhausted"], [])

    def test_minute_429_moves_on_without_marking(self):
        fake = self.use(FakeHTTP({LITE: [MIN429], FLASH: [ok_text("flash")]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi"), ("flash", FLASH))
        self.assertEqual(self.cache()["quota_exhausted"], [])
        fake.calls.clear()
        fake.script = {LITE: [ok_text("lite lại được")]}
        self.assertEqual(ai_client.generate(self.cfg, "hi"), ("lite lại được", LITE))  # lần sau vẫn thử lite

    def test_all_minute_429_does_not_go_offline(self):
        self.use(FakeHTTP({LITE: [MIN429], FLASH: [DAY429]}))
        with self.assertRaises(AIError) as cm:
            ai_client.generate(self.cfg, "hi")
        self.assertFalse(cm.exception.daily_quota)
        self.assertEqual(self.cache().get("offline_until", 0), 0)
        self.assertIsNone(self.cache().get("rule_parser_mode"))

    def test_quota_expires_at_pacific_midnight_not_vn_midnight(self):
        # Hết quota lúc 20:00 VN (13:00 UTC): sang 0h VN vẫn còn hết, tới 08:00 UTC hôm sau mới dùng lại.
        at = dt.datetime(2026, 10, 13, 13, 0, tzinfo=dt.timezone.utc).timestamp()
        reset = dt.datetime(2026, 10, 14, 8, 0, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(ai_client.quota_reset_after(at), reset)
        self.assertEqual(ai_client.quota_reset_after(reset), reset + 86400)
        with mock.patch.object(ai_client, "_now", return_value=at):
            ai_client._update_cache(self.cfg, add_exhausted=LITE)
        for now, gone in ((reset - 3600, True), (reset + 1, False)):
            with mock.patch.object(ai_client, "_now", return_value=now):
                self.assertEqual(LITE in ai_client.exhausted_today(ai_client._model_cache(self.cfg)), gone, now)

    def test_old_cache_entries_still_read(self):
        today = ai_client._today()
        ai_client._update_cache(self.cfg, quota_exhausted=[{"model": LITE, "date": today}, {"model": FLASH,
                                "date": "2000-01-01"}, "rác"])
        start = dt.datetime.strptime(today, "%Y-%m-%d").timestamp()
        with mock.patch.object(ai_client, "_now", return_value=start + 60):
            self.assertEqual(ai_client.exhausted_today(ai_client._model_cache(self.cfg)), [LITE])
        with mock.patch.object(ai_client, "_now", return_value=ai_client.quota_reset_after(start) + 1):
            self.assertEqual(ai_client.exhausted_today(ai_client._model_cache(self.cfg)), [])

    def test_no_thinking_config_is_sent(self):
        """Giống bot timesheet: không gửi thinkingConfig, dùng mặc định của model (Gemini 3.x từng trả 400 vì nó)."""
        fake = self.use(FakeHTTP({LITE: [ok_text("ok")]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi")[0], "ok")
        gen = fake.posts()[0]["payload"]["generationConfig"]
        self.assertNotIn("thinkingConfig", gen)
        self.assertGreaterEqual(gen["maxOutputTokens"], 8192)
        self.assertFalse(hasattr(ai_client, "_no_thinking"))

    def test_thought_parts_are_dropped_from_answer(self):
        res = {"candidates": [{"content": {"parts": [{"text": "đang nghĩ...", "thought": True}, {"text": "trả lời"}]}}]}
        self.use(FakeHTTP({LITE: [res]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi")[0], "trả lời")

    def test_generic_400_tries_next_model_then_reports_google_message(self):
        generic = (400, '{"error": {"code": 400, "message": "Request contains an invalid argument."}}')
        fake = self.use(FakeHTTP({LITE: [generic], "gemini-2.5-flash-lite": [ok_text("từ model kế")]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi"), ("từ model kế", "gemini-2.5-flash-lite"))
        fake = self.use(FakeHTTP({m: [generic] for m in [LITE] + ai_client.FLASH_LITE_EXTRAS + [FLASH]}))
        with self.assertRaises(AIError) as cm:
            ai_client.generate(self.cfg, "hi")
        self.assertIn("invalid argument", str(cm.exception))   # lời của Google được giữ lại để biết lỗi gì
        self.assertEqual(len(set(fake.posted_models())), ai_client.MAX_BAD_REQUEST_MODELS)

    def test_truncated_and_empty_finish_reasons(self):
        self.use(FakeHTTP({LITE: [{"candidates": [{"content": {"parts": [{"text": "cụt"}]},
                                                    "finishReason": "MAX_TOKENS"}]}]}))
        with self.assertLogs("focus", "WARNING") as cm:
            self.assertEqual(ai_client.generate(self.cfg, "hi")[0], "cụt")
        self.assertTrue(any("MAX_TOKENS" in l for l in cm.output))
        for reason, word in (("SAFETY", "an toàn"), ("RECITATION", "bản quyền"), ("MAX_TOKENS", "độ dài")):
            self.use(FakeHTTP({LITE: [{"candidates": [{"content": {"parts": []}, "finishReason": reason}]}]}))
            with self.assertRaisesRegex(AIError, word):
                ai_client.generate(self.cfg, "hi")

    def test_permanent_errors(self):
        for code, body, perm in ((401, "body", True), (403, "body", True),
                                 (400, '{"error": {"message": "API key not valid. Please pass a valid API key."}}', True),
                                 (400, '{"error": {"message": "Request contains an invalid argument."}}', False),
                                 (418, "body", False)):
            self.use(FakeHTTP({LITE: [(code, body)]}))
            with self.assertRaises(AIError) as cm:
                ai_client.generate(self.cfg, "hi")
            self.assertEqual(cm.exception.permanent, perm, (code, body))
        cfg = make_cfg(self.tmp, ai_provider="off")
        with self.assertRaises(AIError) as cm:
            ai_client.generate(cfg, "hi")
        self.assertTrue(cm.exception.permanent)
        self.assertFalse(AIError("x").permanent)

    def test_call_logged_without_key(self):
        self.use(FakeHTTP({LITE: [(400, '{"error": {"message": "API key not valid: %s"}}' % KEY)]}))
        with self.assertRaises(AIError) as cm:
            ai_client.generate(self.cfg, "hi", purpose="ask")
        self.assertNotIn(KEY, str(cm.exception))
        self.use(FakeHTTP({LITE: [ok_text("chào")]}))
        ai_client.generate(self.cfg, "hai từ", purpose="ask")
        with open(os.path.join(self.cfg["data_dir"], "logs", "focus.log"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn(KEY, text)
        ctx_words = len(ai_context.system_prompt(self.cfg).split())
        self.assertIn("AI ok provider=gemini model=%s purpose=ask web=False in=%d out=1" % (LITE, 2 + ctx_words), text)
        self.assertIn("AI fail provider=gemini purpose=ask", text)

    def test_5xx_retries_then_other_family(self):
        fake = self.use(FakeHTTP({LITE: [503, 503, 503], FLASH: [ok_text("flash ok")]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi"), ("flash ok", FLASH))
        self.assertEqual(fake.posted_models(), [LITE] * ai_client.RETRY_ATTEMPTS + [FLASH])

    def test_5xx_recovers_on_retry(self):
        fake = self.use(FakeHTTP({LITE: [500, ok_text("lần 2")]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi"), ("lần 2", LITE))
        self.assertEqual(fake.posted_models(), [LITE, LITE])

    def test_5xx_everywhere_gives_up_without_offline(self):
        fake = self.use(FakeHTTP({}, models=["gemini-2.0-flash-lite", "gemini-2.5-pro"]))
        fake.script = {LITE: [504], FLASH: [503], "gemini-2.0-flash-lite": [ok_text()], "gemini-2.5-pro": [ok_text()]}
        with self.assertRaises(AIError) as cm:
            ai_client.generate(self.cfg, "hi")
        self.assertIn("quá tải", str(cm.exception))
        self.assertEqual(fake.posted_models(), [LITE] * 3 + [FLASH] * 3)  # chỉ thử 2 model khác hệ rồi thôi
        self.assertEqual(self.cache().get("offline_until", 0), 0)  # nghẽn không phải hết quota

    def test_same_family_skipped_after_busy(self):
        fake = self.use(FakeHTTP({}, models=["gemini-2.0-flash-lite"]))
        fake.script = {LITE: [503], FLASH: [404], "gemini-2.0-flash-lite": [ok_text("không được gọi")]}
        with self.assertRaises(AIError):
            ai_client.generate(self.cfg, "hi")
        self.assertNotIn("gemini-2.0-flash-lite", fake.posted_models())

    def test_key_errors_are_friendly(self):
        for code, body in ((400, '{"error": {"message": "API key not valid. Please pass a valid API key."}}'),
                           (401, "body"), (403, "body")):
            fake = self.use(FakeHTTP({LITE: [(code, body)], FLASH: [ok_text()]}))
            with self.assertRaises(AIError) as cm:
                ai_client.generate(self.cfg, "hi")
            self.assertIn("GEMINI_API_KEY", str(cm.exception))
            self.assertNotIn(f"HTTP {code}", str(cm.exception))  # câu dễ hiểu, không phải mã lỗi
            self.assertNotIn(KEY, str(cm.exception))
            self.assertEqual(fake.posted_models(), [LITE])  # lỗi key: không thử model khác

    def test_unknown_error_and_unexpected_exception(self):
        self.use(FakeHTTP({LITE: [418]}))
        with self.assertRaisesRegex(AIError, "418"):
            ai_client.generate(self.cfg, "hi")

        def boom(*a, **k):
            raise OSError("mạng rớt")
        self.use(boom)
        with self.assertRaisesRegex(AIError, "OSError"):
            ai_client.generate(self.cfg, "hi")

    def test_empty_and_blocked_responses(self):
        self.use(FakeHTTP({LITE: [{"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}]}))
        with self.assertRaisesRegex(AIError, "từ chối"):
            ai_client.generate(self.cfg, "hi")
        self.use(FakeHTTP({LITE: [{"candidates": [{"content": {"parts": [
            {"text": "nghĩ thầm", "thought": True}, {"text": "  "}]}}]}]}))
        with self.assertRaisesRegex(AIError, "rỗng"):
            ai_client.generate(self.cfg, "hi")

    def test_thought_parts_dropped(self):
        self.use(FakeHTTP({LITE: [{"candidates": [{"content": {"parts": [
            {"text": "nghĩ thầm", "thought": True}, {"text": "trả lời "}, {"text": "thật"}]}}]}]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi")[0], "trả lời thật")

    def test_configured_model_tried_first(self):
        cfg = make_cfg(self.tmp, gemini_api_key=KEY, gemini_model="gemini-9-custom")
        fake = self.use(FakeHTTP({"gemini-9-custom": [ok_text()]}))
        self.assertEqual(ai_client.generate(cfg, "hi")[1], "gemini-9-custom")
        self.assertEqual(fake.posted_models(), ["gemini-9-custom"])

    def test_image_request_shape(self):
        fake = self.use(FakeHTTP({LITE: [ok_text('{"start": "08:10"}')]}))
        ai_client.generate(self.cfg, "đọc ảnh", image=b"\xff\xd8jpeg", purpose="as400_photo")
        parts = fake.posts()[0]["payload"]["contents"][0]["parts"]
        self.assertEqual(parts[0]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(base64.b64decode(parts[0]["inline_data"]["data"]), b"\xff\xd8jpeg")
        self.assertEqual(parts[1], {"text": "đọc ảnh"})


class ModelListTest(AIBase):
    def test_paging_and_filtering(self):
        pages = {
            "": {"models": [
                {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
                {"name": "models/gemini-embedding-exp", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemma-3-27b-it", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.0-flash-lite", "supportedGenerationMethods": ["generateContent"]},
            ], "nextPageToken": "P2"},
            "P2": {"models": [
                {"name": "models/gemini-2.5-flash-preview-tts", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.5-flash-preview-05-20", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
                {"name": "models/gemini-2.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.5-flash-image", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-2.5-pro"},
            ]},
        }
        urls = []

        def http(cfg, method, url, headers, payload=None):
            urls.append(url)
            self.assertEqual(method, "GET")
            self.assertEqual(headers, {"x-goog-api-key": KEY})
            token = url.split("pageToken=")[1] if "pageToken=" in url else ""
            return pages[token]
        self.use(http)
        names = ai_client.list_gemini_models(self.cfg)
        self.assertEqual(len(urls), 2)
        self.assertIn("pageToken=P2", urls[1])
        self.assertEqual(names, ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.5-flash",
                                 "gemini-2.5-flash-preview-05-20", "gemini-2.5-pro"])

    def test_list_cached_for_ttl(self):
        fake = self.use(FakeHTTP({LITE: [404], FLASH: [404], "gemini-2.5-flash": [ok_text()]},
                                 models=["gemini-2.5-flash"]))
        self.assertEqual(ai_client.generate(self.cfg, "hi")[1], "gemini-2.5-flash")
        self.assertEqual(self.cache()["candidates"], ["gemini-2.5-flash"])
        self.assertTrue(self.cache()["resolved_at"])
        gets = lambda: [c for c in fake.calls if c["method"] == "GET"]
        self.assertEqual(len(gets()), 1)
        ai_client.generate(self.cfg, "hi")
        self.assertEqual(len(gets()), 1)  # còn hạn: không dò lại
        ai_client._update_cache(self.cfg, resolved_at="2000-01-01T00:00:00")
        ai_client.generate(self.cfg, "hi")
        self.assertEqual(len(gets()), 2)  # quá 30 ngày: dò lại

    def test_list_failure_does_not_break(self):
        def http(cfg, method, url, headers, payload=None):
            if method == "GET":
                raise HTTPStatusError(500, "x")
            return ok_text("vẫn chạy")
        self.use(http)
        self.assertEqual(ai_client.generate(self.cfg, "hi"), ("vẫn chạy", LITE))

    def test_max_models_tried(self):
        many = [f"gemini-1.{i}-pro" for i in range(6)]
        fake = self.use(FakeHTTP({}, models=many))
        with self.assertRaises(AIError):
            ai_client.generate(self.cfg, "hi")
        self.assertEqual(len(fake.posted_models()), ai_client.MAX_MODELS_TRIED)


class UsageAndCacheTest(AIBase):
    def test_usage_counting(self):
        self.use(FakeHTTP({LITE: [ok_text()]}))
        for _ in range(3):
            ai_client.generate(self.cfg, "hi")
        u = self.usage()
        today = ai_client._today()
        self.assertEqual(u["month"], today[:7])
        self.assertEqual(u["month_count"], 3)
        self.assertEqual(u["days"][today], 3)
        self.assertEqual(u["models"], {LITE: 3})
        self.assertIn("Hôm nay: 3 lượt", ai_client.status_text(self.cfg))

    def test_usage_resets_new_month_and_keeps_31_days(self):
        days = {f"2026-09-{d:02d}": 1 for d in range(1, 31)}
        with open(os.path.join(self.cfg["data_dir"], "ai_usage.json"), "w", encoding="utf-8") as f:
            json.dump({"month": "2026-09", "month_count": 30, "days": days, "models": {"x": 30}}, f)
        with mock.patch.object(ai_client, "_today", return_value="2026-10-01"):
            ai_client._count_usage(self.cfg, LITE)
        u = self.usage()
        self.assertEqual((u["month"], u["month_count"], u["models"]), ("2026-10", 1, {LITE: 1}))
        self.assertEqual(u["days"], {"2026-10-01": 1})
        with mock.patch.object(ai_client, "_today", return_value="2026-10-01"):
            u["days"] = {f"2026-08-{d:02d}": 1 for d in range(1, 32)}
            with open(os.path.join(self.cfg["data_dir"], "ai_usage.json"), "w", encoding="utf-8") as f:
                json.dump(u, f)
            ai_client._count_usage(self.cfg, LITE)
        self.assertEqual(len(self.usage()["days"]), 31)
        self.assertIn("2026-10-01", self.usage()["days"])

    def test_concurrent_saves_keep_valid_json(self):
        errors = []

        def worker(i):
            try:
                for j in range(20):
                    ai_client._count_usage(self.cfg, f"m{i % 3}")
                    ai_client._update_cache(self.cfg, model=f"m{i}", add_exhausted=f"x{j % 4}")
                    ai_client._load(self.cfg, "ai_model.json")
            except Exception as e:  # pragma: no cover - chỉ để báo lỗi
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.usage()["month_count"], 160)  # không mất lượt đếm nào
        self.assertEqual(sorted(ai_client.exhausted_today(self.cache())), ["x0", "x1", "x2", "x3"])
        leftovers = [f for f in os.listdir(self.cfg["data_dir"]) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_save_is_atomic_on_write_error(self):
        ai_client._update_cache(self.cfg, model="cũ")
        real_replace = os.replace

        def fail_replace(src, dst):
            raise PermissionError("file đang bị khoá")
        with mock.patch.object(ai_client.os, "replace", fail_replace):
            ai_client._update_cache(self.cfg, model="mới")  # không raise
        self.assertIs(os.replace, real_replace)
        self.assertEqual(self.cache()["model"], "cũ")  # file cũ còn nguyên, không bị ghi dở
        self.assertEqual([f for f in os.listdir(self.cfg["data_dir"]) if f.endswith(".tmp")], [])

    def test_corrupt_cache_tolerated(self):
        with open(os.path.join(self.cfg["data_dir"], "ai_model.json"), "w", encoding="utf-8") as f:
            f.write("{hỏng")
        self.use(FakeHTTP({LITE: [ok_text()]}))
        self.assertEqual(ai_client.generate(self.cfg, "hi")[1], LITE)
        self.assertEqual(self.cache()["model"], LITE)

    def test_files_live_in_data_dir(self):
        self.use(FakeHTTP({LITE: [ok_text()]}))
        ai_client.generate(self.cfg, "hi")
        for name in ("ai_model.json", "ai_usage.json"):
            self.assertTrue(os.path.exists(os.path.join(self.cfg["data_dir"], name)))

    def test_clear_cache(self):
        self.use(FakeHTTP({LITE: [DAY429], FLASH: [ok_text()]}))
        ai_client.generate(self.cfg, "hi")
        self.assertTrue(ai_client.clear_cache(self.cfg))
        self.assertFalse(os.path.exists(os.path.join(self.cfg["data_dir"], "ai_model.json")))
        self.assertTrue(os.path.exists(os.path.join(self.cfg["data_dir"], "ai_usage.json")))  # giữ bộ đếm
        self.assertFalse(ai_client.clear_cache(self.cfg))  # xoá lần 2: không có gì để xoá

    def test_status_text(self):
        off = make_cfg(self.tmp, ai_provider="off", gemini_api_key=KEY)
        self.assertIn("chưa cấu hình", ai_client.status_text(off))
        self.use(FakeHTTP({LITE: [DAY429], FLASH: [ok_text()]}))
        ai_client.generate(self.cfg, "hi")
        s = ai_client.status_text(self.cfg)
        self.assertIn("AI: gemini", s)
        self.assertIn(FLASH, s)
        self.assertIn("Hết quota hôm nay: " + LITE, s)
        self.assertNotIn(KEY, s)
        self.assertNotIn("SECRET", s)
        claude = make_cfg(self.tmp, ai_provider="claude", anthropic_api_key="sk-ant-SECRET")
        self.assertNotIn("sk-ant", ai_client.status_text(claude))


class ProviderTest(AIBase):
    def test_provider_selection(self):
        cases = [
            ({"ai_provider": "auto", "gemini_api_key": "g", "anthropic_api_key": "a"}, "gemini"),
            ({"ai_provider": "auto", "gemini_api_key": "", "anthropic_api_key": "a"}, "claude"),
            ({"ai_provider": "auto", "gemini_api_key": "", "anthropic_api_key": ""}, None),
            ({"ai_provider": "gemini", "gemini_api_key": "", "anthropic_api_key": "a"}, None),
            ({"ai_provider": "claude", "gemini_api_key": "g", "anthropic_api_key": "a"}, "claude"),
            ({"ai_provider": "claude", "gemini_api_key": "g", "anthropic_api_key": ""}, None),
            ({"ai_provider": "off", "gemini_api_key": "g", "anthropic_api_key": "a"}, None),
            ({"ai_provider": "OFF", "gemini_api_key": "g"}, None),
            ({"ai_provider": "Gemini", "gemini_api_key": "g"}, "gemini"),
            ({"ai_provider": "", "gemini_api_key": "g"}, "gemini"),
        ]
        for cfg, want in cases:
            self.assertEqual(ai_client.provider(cfg), want, cfg)

    def test_off_never_calls_http(self):
        fake = self.use(FakeHTTP({LITE: [ok_text()]}))
        cfg = make_cfg(self.tmp, ai_provider="off", gemini_api_key=KEY)
        with self.assertRaisesRegex(AIError, "Chưa cấu hình"):
            ai_client.generate(cfg, "hi")
        self.assertEqual(fake.calls, [])


class ClaudeTest(AIBase):
    def setUp(self):
        super().setUp()
        self.cfg = make_cfg(self.tmp, ai_provider="claude", anthropic_api_key="sk-ant-xyz", gemini_api_key=KEY)

    def test_headers_body_and_text(self):
        fake = self.use(FakeHTTP({"claude": [{"model": "claude-opus-5-5-20260101", "stop_reason": "end_turn",
                                              "content": [{"type": "thinking", "thinking": "..."},
                                                          {"type": "text", "text": "Chào "},
                                                          {"type": "text", "text": "bạn"}]}]}))
        text, model = ai_client.generate(self.cfg, "hỏi", system="dặn", purpose="t")
        self.assertEqual((text, model), ("Chào bạn", "claude-opus-5-5-20260101"))
        call = fake.calls[0]
        self.assertEqual(call["url"], ai_client.CLAUDE_URL)
        self.assertEqual(call["headers"], {"x-api-key": "sk-ant-xyz", "anthropic-version": "2023-06-01"})
        body = call["payload"]
        self.assertEqual(body["model"], self.cfg["claude_model"])
        self.assertTrue(body["system"].startswith("BỐI CẢNH") and body["system"].endswith("\n\ndặn"))
        self.assertEqual(body["messages"], [{"role": "user", "content": [{"type": "text", "text": "hỏi"}]}])
        self.assertGreater(body["max_tokens"], 0)
        self.assertEqual(self.usage()["models"], {"claude-opus-5-5-20260101": 1})

    def test_image_block(self):
        fake = self.use(FakeHTTP({"claude": [{"content": [{"type": "text", "text": "ok"}]}]}))
        text, model = ai_client.generate(self.cfg, "đọc ảnh", image=b"img")
        self.assertEqual(model, self.cfg["claude_model"])  # không có model trong trả lời: dùng model đã gửi
        content = fake.calls[0]["payload"]["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")
        self.assertEqual(base64.b64decode(content[0]["source"]["data"]), b"img")
        self.assertEqual(content[1], {"type": "text", "text": "đọc ảnh"})
        self.assertIn("BỐI CẢNH", fake.calls[0]["payload"]["system"], "đọc ảnh cũng kèm bối cảnh")

    def test_errors(self):
        for code, word in ((429, "giới hạn"), (401, "ANTHROPIC_API_KEY"), (403, "ANTHROPIC_API_KEY"), (529, "máy chủ")):
            self.use(FakeHTTP({"claude": [code]}))
            with self.assertRaises(AIError) as cm:
                ai_client.generate(self.cfg, "hi")
            self.assertIn(word, str(cm.exception))
            self.assertNotIn("sk-ant", str(cm.exception))
        self.use(FakeHTTP({"claude": [{"stop_reason": "refusal", "content": []}]}))
        with self.assertRaisesRegex(AIError, "từ chối"):
            ai_client.generate(self.cfg, "hi")
        self.use(FakeHTTP({"claude": [{"content": [{"type": "text", "text": "  "}]}]}))
        with self.assertRaisesRegex(AIError, "rỗng"):
            ai_client.generate(self.cfg, "hi")
        self.use(FakeHTTP({"claude": [{"stop_reason": "max_tokens", "content": []}]}))
        with self.assertRaisesRegex(AIError, "MAX_TOKENS"):
            ai_client.generate(self.cfg, "hi")
        self.use(FakeHTTP({"claude": [{"stop_reason": "max_tokens", "content": [{"type": "text", "text": "cụt"}]}]}))
        with self.assertLogs("focus", "WARNING"):
            self.assertEqual(ai_client.generate(self.cfg, "hi")[0], "cụt")
        for code in (401, 403):
            self.use(FakeHTTP({"claude": [code]}))
            with self.assertRaises(AIError) as cm:
                ai_client.generate(self.cfg, "hi")
            self.assertTrue(cm.exception.permanent)


class RawHTTPTest(AIBase):
    """_http thật nhưng urlopen giả: không ra mạng."""

    def test_http_error_becomes_status_error(self):
        err = urllib.error.HTTPError("https://x", 429, "Too Many", {}, io.BytesIO(b'{"error": "quota"}'))
        with mock.patch.object(ai_client.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(HTTPStatusError) as cm:
                ai_client._http(self.cfg, "POST", "https://x", {"k": "v"}, {"a": 1})
        self.assertEqual(cm.exception.code, 429)
        self.assertIn("quota", cm.exception.body)

    def test_request_built_with_json_and_timeout(self):
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout, **kw):
            seen.update(req=req, timeout=timeout)
            return Resp(json.dumps({"ok": "đúng"}).encode())
        cfg = make_cfg(self.tmp, ai_timeout_seconds=7)
        with mock.patch.object(ai_client.urllib.request, "urlopen", urlopen):
            self.assertEqual(ai_client._http(cfg, "POST", "https://x", {"x-api-key": "k"}, {"a": 1}), {"ok": "đúng"})
            ai_client._http(cfg, "GET", "https://y", {"x-goog-api-key": "k"})
        req = seen["req"]
        self.assertEqual(seen["timeout"], 7.0)
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        self.assertNotIn("Content-type", req.headers)
