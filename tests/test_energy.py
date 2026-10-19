"""Tự tính năng lượng lúc tổng kết khi chưa chấm (2.1.0): công thức, tin báo, lưu energy_source, /autoenergy,
câu hỏi tổng kết, /today, file HTML, dữ liệu gửi AI."""
import datetime as dt
import os
import sqlite3
import threading

from focus import energy, motivation, prefs
from focus.analysis import analyze, day_facts
from focus.config import DEFAULTS, ConfigError, validate
from focus.report import summary_text, write_report
from focus.storage import get_note, open_db, save_note
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, msg


def facts(deep_h, vdi_h, blocks_h=()):
    return {"has_data": True, "deep": deep_h * 3600, "vdi": vdi_h * 3600,
            "blocks": [{"focus": b * 3600} for b in blocks_h]}


class EstimateTest(TempCase):
    def test_no_data_no_estimate(self):
        self.assertIsNone(energy.estimate({"has_data": False}))

    def test_scale_endpoints(self):
        self.assertEqual(energy.estimate(facts(0, 0))["energy"], 5)
        self.assertEqual(energy.estimate(facts(4, 4, [1.5, 1.5, 1]))["energy"], 1, "4h tập trung sâu = cạn sức")
        self.assertEqual(energy.estimate(facts(6, 6, [2, 2, 2]))["energy"], 1, "không thấp hơn 1")

    def test_more_focus_less_energy(self):
        levels = [energy.estimate(facts(h, h, [h] if h else []))["exact"] for h in (0, 0.5, 1, 2, 3)]
        self.assertEqual(levels, sorted(levels, reverse=True))

    def test_distracted_day_keeps_more_energy(self):
        focused = energy.estimate(facts(3, 3.5, [1.5, 1.5]))
        distracted = energy.estimate(facts(0.5, 1.5, [0.5]))  # phần lớn ngày ngoài VDI / làm vụn
        self.assertGreater(distracted["energy"], focused["energy"])

    def test_formula_parts(self):
        est = energy.estimate(facts(2, 3, [2]))  # sâu 2h, vụn 1h, khối 2h quá 90 phút 30m
        self.assertAlmostEqual(est["shallow_h"], 1)
        self.assertAlmostEqual(est["long_h"], 0.5)
        self.assertAlmostEqual(est["load_h"], 2 + 0.5 + 0.25)
        self.assertEqual(est["exact"], round(5 - 4 * 2.75 / 4, 1))
        self.assertEqual(est["energy"], 2)  # 2.25 làm tròn

    def test_long_block_costs_more_than_two_short(self):
        one_long = energy.estimate(facts(3, 3, [3]))
        three_short = energy.estimate(facts(3, 3, [1, 1, 1]))
        self.assertLess(one_long["exact"], three_short["exact"])

    def test_capacity_setting(self):
        self.assertGreater(energy.estimate(facts(3, 3), capacity_h=6)["exact"],
                           energy.estimate(facts(3, 3), capacity_h=4)["exact"])

    def test_rounds_half_up(self):
        self.assertEqual(energy.estimate(facts(1, 1))["energy"], 4)  # 5 - 1 = 4.0
        self.assertEqual(energy.estimate(facts(0.5, 0.5))["energy"], 5)  # 4.5 -> 5


class MessageTest(TempCase):
    def test_message_shows_formula(self):
        text = energy.message(energy.estimate(facts(3, 4, [2, 1])))
        self.assertIn("🔋 Hôm nay bạn chưa chấm năng lượng", text)
        self.assertIn("1/5 (kiệt sức)", text)
        self.assertIn("tập trung sâu 3h 00m", text)
        self.assertIn("làm vụn trong VDI 1h 00m × 0,5", text)
        self.assertIn("làm liền quá 90 phút 30m × 0,5", text)
        self.assertIn("4h/ngày", text)
        self.assertIn("/energy", text)

    def test_zero_parts_left_out(self):
        text = energy.message(energy.estimate(facts(1, 1, [1])))
        self.assertNotIn("làm vụn", text)
        self.assertNotIn("quá 90 phút", text)

    def test_catch_up_day_label(self):
        self.assertIn("🔋 Ngày 14/10 bạn chưa chấm", energy.message(energy.estimate(facts(1, 1)), "Ngày 14/10"))


class StorageTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(os.path.join(self.cfg["data_dir"], "focus.db"))
        self.addCleanup(self.db.close)

    def test_self_rating_replaces_auto(self):
        save_note(self.db, "2026-10-15", {"energy": 2, "energy_source": "auto"})
        self.assertEqual(get_note(self.db, "2026-10-15")["energy_source"], "auto")
        save_note(self.db, "2026-10-15", {"energy": 4})
        note = get_note(self.db, "2026-10-15")
        self.assertEqual(note["energy"], 4)
        self.assertIsNone(note["energy_source"])

    def test_old_db_gets_column(self):
        path = os.path.join(self.tmp, "old.db")
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE notes (day TEXT PRIMARY KEY, plan TEXT, output TEXT, issues TEXT, "
                    "distractions TEXT, energy INTEGER, tomorrow TEXT, updated REAL)")
        old.execute("INSERT INTO notes (day, energy) VALUES ('2026-10-01', 3)")
        old.commit()
        old.close()
        db = open_db(path)
        self.addCleanup(db.close)
        note = get_note(db, "2026-10-01")
        self.assertEqual(note["energy"], 3)
        self.assertIsNone(note["energy_source"])


class ConfigTest(TempCase):
    def test_defaults(self):
        self.assertTrue(DEFAULTS["energy_auto_enabled"])
        self.assertEqual(DEFAULTS["energy_capacity_hours"], 4)

    def test_bad_values(self):
        for bad in ({"energy_capacity_hours": 0}, {"energy_capacity_hours": 13}, {"energy_capacity_hours": "4"},
                    {"energy_auto_enabled": "yes"}):
            cfg = dict(self.cfg, **bad)
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                validate(cfg)


class AutoEnergyBotTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="")
        self.api = FakeTelegramAPI()
        self.bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=self.api)
        self.day = self.bot.today()
        insert_run(self.bot.db, self.day, "08:00", 150)  # 2h30 liền trong VDI

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def note(self):
        return get_note(self.bot.db, self.day)

    def test_summary_computes_and_notifies_first(self):
        self.api.clear()
        self.bot.send_daily_summary(self.day)
        sent = self.api.sent()
        self.assertIn("🔋 Hôm nay bạn chưa chấm năng lượng", sent[0])
        self.assertIn("TỔNG KẾT", sent[1])
        self.assertIn("Năng lượng bot tự tính", sent[1])
        note = self.note()
        self.assertEqual(note["energy_source"], "auto")
        est = energy.estimate(analyze(self.bot.db, self.cfg, self.day))
        self.assertEqual(note["energy"], est["energy"])
        self.assertIn(f"{est['energy']}/5", sent[0])

    def test_self_rated_kept(self):
        self.say("/energy 4")
        self.api.clear()
        self.bot.send_daily_summary(self.day)
        self.assertFalse(any("🔋" in s for s in self.api.sent()))
        self.assertEqual(self.note()["energy"], 4)
        self.assertIsNone(self.note()["energy_source"])

    def test_disabled(self):
        self.say("/autoenergy off")
        self.assertFalse(self.cfg["energy_auto_enabled"])
        self.api.clear()
        self.bot.send_daily_summary(self.day)
        self.assertFalse(any("🔋" in s for s in self.api.sent()))
        self.assertIn(self.note().get("energy"), (None, ""))

    def test_toggle_persists_and_default(self):
        self.say("/autoenergy off")
        cfg2 = dict(self.cfg, energy_auto_enabled=True)
        prefs.apply(cfg2, self.bot.db)
        self.assertFalse(cfg2["energy_auto_enabled"])
        self.say("/autoenergy mac_dinh")
        self.assertTrue(self.cfg["energy_auto_enabled"])

    def test_view_shows_formula_and_estimate_now(self):
        out = self.say("/autoenergy")[0]
        self.assertIn("BẬT", out)
        self.assertIn("Công thức", out)
        self.assertIn("Nếu tính lúc này", out)

    def test_user_can_override_auto(self):
        self.bot.send_daily_summary(self.day)
        self.say("/energy 5")
        self.assertEqual(self.note()["energy"], 5)
        self.assertIsNone(self.note()["energy_source"])
        self.assertIn("Năng lượng tự chấm: 5/5", "\n".join(self.say("/today")))

    def test_today_marks_auto(self):
        self.bot.send_daily_summary(self.day)
        self.assertIn("Năng lượng bot tự tính", "\n".join(self.say("/today")))

    def test_review_question_mentions_auto_value(self):
        save_note(self.bot.db, self.day, {"energy": 2, "energy_source": "auto"})
        text = self.bot.ask_text(("energy", "Năng lượng hôm nay từ 1 đến 5?"))
        self.assertIn("Bot đã tự tính năng lượng hôm nay: 2/5", text)
        self.assertIn("bỏ qua", text)

    def test_catch_up_day_label(self):
        day = (dt.date.fromisoformat(self.day) - dt.timedelta(days=1)).isoformat()
        insert_run(self.bot.db, day, "09:00", 60)
        self.api.clear()
        self.bot.send_daily_summary(day)
        self.assertIn(f"🔋 Ngày {dt.date.fromisoformat(day):%d/%m} bạn chưa chấm", self.api.sent()[0])

    def test_report_and_ai_facts_mark_auto(self):
        self.bot.send_daily_summary(self.day)
        path, _ = write_report(self.bot.db, self.cfg, self.day)
        with open(path, encoding="utf-8") as f:
            self.assertIn("(bot tự tính)", f.read())
        self.assertEqual(day_facts(self.bot.db, self.cfg, self.day).get("energy_source"), "app_uoc_tinh")
        save_note(self.bot.db, self.day, {"energy": 3})
        self.assertNotIn("energy_source", day_facts(self.bot.db, self.cfg, self.day))


class PromptTest(TempCase):
    def test_ai_told_energy_may_be_estimated(self):
        self.assertIn("app_uoc_tinh", motivation.DAILY_TASK)
        self.assertIn("app_uoc_tinh", motivation.WEEKLY_TASK)

    def test_summary_text_labels(self):
        t0 = dt.datetime(2026, 10, 15, 9).timestamp()
        a = {"has_data": True, "day": "2026-10-15", "first": t0, "last": t0 + 3600, "deep": 3600, "goal_h": 4,
             "vdi": 3600, "other": 0, "exits": 0, "minimized": 0, "idle": 0, "away": 0, "away_count": 0,
             "blocks": [], "active": 3600}
        self.assertIn("Năng lượng bot tự tính: 3/5", summary_text(a, {"energy": 3, "energy_source": "auto"}))
        self.assertIn("Năng lượng tự chấm: 3/5", summary_text(a, {"energy": 3}))
