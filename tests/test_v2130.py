"""v2.13.0: /vang và câu hỏi "mình vừa inactive bao lâu?" (lần vắng gần nhất + các lần vắng trong ngày).
Chỉ đọc số liệu có sẵn: số liệu ngày (deep, idle, away, điểm...) phải y như trước."""
import threading
import time
from unittest import mock

from focus import absence, actions, intent
from focus.analysis import analyze
from focus.storage import db_path, open_db
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, msg, ts

THU = "2026-10-15"


class AbsenceTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)
        insert_run(self.db, THU, "08:30", 60)                       # làm 08:30–09:30
        insert_run(self.db, THU, "09:30", 8, idle_grow=True)        # ngồi yên 8 phút (09:30–09:38)
        insert_run(self.db, THU, "09:38", 30)
        insert_run(self.db, THU, "10:08", 2, idle_grow=True)        # ngồi yên 2 phút: có trong "gần nhất", không liệt kê
        insert_run(self.db, THU, "10:10", 20)
        insert_run(self.db, THU, "10:30", 24, locked=True)          # khoá máy 24 phút
        insert_run(self.db, THU, "10:54", 30)                       # quay lại tới 11:24
        self.a = analyze(self.db, self.cfg, THU)
        self.end = ts(THU, "11:24")

    def test_summary_last_and_list(self):
        info = absence.summarize(self.a, self.cfg, now=self.end + 10)
        self.assertIsNone(info["ongoing"])
        last = info["last"]
        self.assertEqual(round(last["secs"] / 60), 24)
        self.assertTrue(last["hard"])
        self.assertEqual([round(sp["secs"] / 60) for sp in info["listed"]], [8, 24], "quãng 2 phút không liệt kê")
        self.assertEqual(info["count"], 2)

    def test_view_text(self):
        text = absence.view_text(self.a, self.cfg, now=self.end + 10, day=THU)
        self.assertIn("🚶 Lần vắng gần nhất: 10:30–10:54, 24m (khoá máy / máy ngủ / tắt app).", text)
        self.assertIn("Các lần vắng từ 5 phút: 2 lần, tổng 32m", text)
        self.assertIn("  • 09:30–09:38 · 8m · rời máy, không chạm phím/chuột\n"
                      "  • 10:30–10:54 · 24m · khoá máy / máy ngủ / tắt app", text)
        self.assertNotIn("Lúc này", text)

    def test_ongoing_from_live_sample(self):
        state = {"paused": threading.Event(), "last": {"idle": 300.0, "locked": False}}
        now = self.end + 300
        info = absence.summarize(self.a, self.cfg, state, now=now)
        self.assertEqual(round(info["ongoing"]["secs"] / 60), 5)
        self.assertEqual(round(info["last"]["secs"] / 60), 24, "lần đang vắng không thay lần đã xong")
        state["paused"].set()
        self.assertIsNone(absence.summarize(self.a, self.cfg, state, now=now)["ongoing"], "/pause: không đoán")

    def test_ongoing_merges_with_db_part(self):
        insert_run(self.db, THU, "11:24", 3, idle_grow=True)  # DB đã có 3 phút ngồi yên, lúc này đã 6 phút
        a = analyze(self.db, self.cfg, THU)
        state = {"last": {"idle": 360.0, "locked": False}}
        info = absence.summarize(a, self.cfg, state, now=ts(THU, "11:30"))
        self.assertEqual(round(info["ongoing"]["secs"] / 60), 6)
        self.assertEqual(round(info["last"]["secs"] / 60), 24)

    def test_ai_facts_fixed_size(self):
        for i in range(30):  # ngày rất nhiều lần vắng: bối cảnh AI vẫn chỉ 5 lần gần nhất
            insert_run(self.db, THU, f"{12 + i // 6:02d}:{(i % 6) * 10:02d}", 6, idle_grow=True)
            insert_run(self.db, THU, f"{12 + i // 6:02d}:{(i % 6) * 10 + 6:02d}", 4)
        f = absence.ai_facts(analyze(self.db, self.cfg, THU), self.cfg, now=ts(THU, "17:10"))
        self.assertEqual(f["cac_lan_vang_tu_5_phut_hom_nay"].count("("), 5)
        self.assertTrue(f["cac_lan_vang_tu_5_phut_hom_nay"].startswith("32 lần"))
        self.assertEqual(f["may_luc_nay"], "đang có người dùng")

    def test_no_data(self):
        a = analyze(self.db, self.cfg, "2026-10-14")
        self.assertIn("Chưa có lần vắng nào", absence.view_text(a, self.cfg, day="2026-10-14"))
        self.assertEqual(absence.ai_facts(a, self.cfg)["lan_vang_gan_nhat"], "chưa có lần vắng nào từ 1 phút")

    def test_day_numbers_unchanged(self):
        a = dict(self.a)
        a.pop("inactive_spans")
        b = analyze(self.db, self.cfg, THU)
        self.assertIn("inactive_spans", b)
        for k in ("deep", "vdi", "other", "idle", "away", "away_count", "short_idle_count", "blocks", "timeline"):
            self.assertEqual(a[k], b[k], k)


class BotTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "recheck": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.addCleanup(lambda: self.bot.db.close())

    def test_command_and_natural_language(self):
        self.bot.handle(msg("/vang"))
        self.assertIn("Chưa có lần vắng nào từ 1 phút trở lên hôm nay.", self.api.last())
        self.assertFalse(self.bot.pending, "chỉ xem, không hỏi OK")
        for text in ("mình vừa inactive bao lâu?", "hôm nay mình rời máy mấy lần?"):
            self.assertEqual(intent.by_rules(text)[0].name, "xem_vang", text)

    def test_ai_question_gets_absence_facts(self):
        seen = {}
        with mock.patch("focus.ai_client.provider", return_value="gemini"), \
                mock.patch("focus.motivation.ask_ai", side_effect=lambda cfg, q, live: (seen.update(live), ("ok", True))[1]):
            self.bot.answer_question("mình vừa inactive bao lâu?")
        self.assertIn("vang_mat_hom_nay", seen)
        self.assertIn("lan_vang_gan_nhat", seen["vang_mat_hom_nay"])

    def test_listed_in_help(self):
        self.assertIn("/vang", actions.full_help(self.cfg))
