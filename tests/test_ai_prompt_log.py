"""Mọi lần gọi AI: luôn kèm BỐI CẢNH đầy đủ, ghi nguyên văn prompt + trả lời ra data/logs/ai-prompts-*.log
(có dọn dẹp), quota ước tính chỉ để báo cáo, không bao giờ chặn AI."""
import glob
import os
import time
from unittest import mock

from focus import ai_client, ai_context, housekeeping
from focus.ai_client import AIError
from tests.test_ai_client import KEY, LITE, AIBase, FakeHTTP, ok_text


class PromptLogTest(AIBase):
    def logs(self):
        files = glob.glob(os.path.join(self.cfg["data_dir"], "logs", "ai-prompts-*.log"))
        return "".join(open(f, encoding="utf-8").read() for f in files), files

    def test_prompt_and_answer_logged_verbatim(self):
        self.use(FakeHTTP({LITE: [ok_text("Chào Minh")]}))
        ai_client.generate(self.cfg, "Số liệu hôm nay: deep_hours 3.5", "dặn riêng", purpose="daily_review")
        text, files = self.logs()
        self.assertEqual(len(files), 1)
        self.assertIn("purpose=daily_review", text)
        self.assertIn(f"model={LITE}", text)
        self.assertIn("--- SYSTEM ---\nBỐI CẢNH (bạn không có trí nhớ", text)
        self.assertIn(self.cfg["work_context"][:60], text)
        self.assertIn("dặn riêng", text)
        self.assertIn("--- PROMPT ---\nSố liệu hôm nay: deep_hours 3.5", text)
        self.assertIn("--- TRẢ LỜI ---\nChào Minh", text)
        self.assertNotIn(KEY, text)

    def test_error_logged_without_key(self):
        self.use(FakeHTTP({LITE: [(400, '{"error": {"message": "API key not valid: %s"}}' % KEY)]}))
        with self.assertRaises(AIError):
            ai_client.generate(self.cfg, "hỏi", purpose="ask")
        text, _ = self.logs()
        self.assertIn("LỖI", text)
        self.assertIn("--- LỖI ---", text)
        self.assertNotIn(KEY, text)

    def test_image_not_stored(self):
        self.use(FakeHTTP({LITE: [ok_text("08:10 17:35")]}))
        ai_client.generate(self.cfg, "đọc ảnh", image=b"\xff\xd8" + b"x" * 500, purpose="as400_photo")
        text, _ = self.logs()
        self.assertIn("không lưu ảnh, 502 byte", text)
        self.assertNotIn("xxxxxxxx", text)

    def test_disabled(self):
        self.cfg["ai_prompt_log_days"] = 0
        self.use(FakeHTTP({LITE: [ok_text("ok")]}))
        ai_client.generate(self.cfg, "hỏi", purpose="ask")
        self.assertEqual(self.logs()[1], [])

    def test_housekeeping_deletes_old_prompt_logs(self):
        folder = os.path.join(self.cfg["data_dir"], "logs")
        os.makedirs(folder, exist_ok=True)
        old, new = os.path.join(folder, "ai-prompts-2026-09-01.log"), os.path.join(folder, "ai-prompts-2026-10-13.log")
        for p in (old, new):
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
        os.utime(old, (time.time() - 15 * 86400,) * 2)
        out = housekeeping.trim_text_logs(self.cfg)
        self.assertIn("ai-prompts-2026-09-01.log", out["deleted"])
        self.assertTrue(os.path.exists(new))
        self.cfg["ai_prompt_log_days"] = 30
        os.utime(new, (time.time() - 20 * 86400,) * 2)
        self.assertNotIn("ai-prompts-2026-10-13.log", housekeeping.trim_text_logs(self.cfg)["deleted"])


class ContextAlwaysSentTest(AIBase):
    """Không nơi gọi nào gửi AI thiếu bối cảnh, kể cả khi quên truyền system."""

    def test_every_purpose_gets_full_context(self):
        seen = []

        def fake_call(cfg, prompt, system, image, web=False):
            seen.append(system)
            return "ok", LITE

        with mock.patch.object(ai_client, "_gemini_call", fake_call):
            ai_client.generate(self.cfg, "x", purpose="as400_photo", image=b"img")   # không truyền system
            ai_client.generate(self.cfg, "x", "", purpose="test")
            ai_client.generate(self.cfg, "x", ai_context.system_prompt(self.cfg, "dặn"), purpose="daily_review")
        for s in seen:
            self.assertEqual(s.count(ai_context.CONTEXT_MARK), 1, "bối cảnh có đúng 1 lần")
            for part in ("Focus Tracker", "Citrix Desktop Viewer", "Luật tính tập trung", "Tập trung sâu",
                         "Công việc của người dùng", self.cfg["work_context"][:40], "Giờ làm 08:00–17:00",
                         "nghỉ trưa 11:15–12:30", "Mục tiêu tập trung sâu: 4 giờ/ngày", "CÁCH NÓI"):
                self.assertIn(part, s)

    def test_fingerprint_covers_every_context_setting(self):
        base = ai_context.fingerprint(self.cfg)
        for key, value in (("work_context", self.cfg["work_context"] + " thêm ở cuối"), ("work_end", "18:00"),
                           ("daily_focus_goal_hours", 5), ("lunch_start", "11:30")):
            cfg = dict(self.cfg, **{key: value})
            self.assertNotEqual(ai_context.fingerprint(cfg), base, key)
        cfg = dict(self.cfg, persona=dict(ai_context.persona_of(self.cfg), ten_sep="Anh Tuấn"))
        self.assertNotEqual(ai_context.fingerprint(cfg), base, "tên sếp")


class QuotaNeverBlocksTest(AIBase):
    def test_estimate_over_budget_still_calls(self):
        self.cfg.update(ai_daily_call_budget=1, gemini_free_calls_per_model=1)
        fake = self.use(FakeHTTP({LITE: [ok_text("1"), ok_text("2"), ok_text("3")]}))
        for i in range(3):
            self.assertEqual(ai_client.generate(self.cfg, "hỏi", purpose="ask")[0], str(i + 1))
        self.assertEqual(len(fake.posts()), 3, "vượt số ước tính vẫn gọi Google bình thường")
        self.assertIn("ước tính", ai_client.status_text(self.cfg))
