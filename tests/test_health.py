"""Nhắc sức khoẻ: nghỉ khi ngồi lâu (/break) và uống nước (/water). Không phụ thuộc mức nhắc sao nhãng."""
import tempfile
import threading
import unittest
from unittest import mock

from focus import intent, messages, motivation, persona
from focus.alerts import RealtimeAlerts
from focus.config import ConfigError, DEFAULTS, validate
from focus.storage import db_path, get_pref, open_db
from focus.telegram_bot import TelegramBot
from focus.tracker import Tracker
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, make_cfg, msg, sample, ts

DAY = "2026-10-14"


class Sim:
    def __init__(self, cfg, start="08:00"):
        self.al = RealtimeAlerts(cfg)
        self.t = ts(DAY, start)
        self.events = []

    def run(self, minutes, work=True, **kw):
        idle_grow = kw.pop("idle_grow", False)
        for i in range(int(minutes * 12)):
            self.t += 5
            s = sample(**kw)
            if idle_grow or s["locked"]:
                s["idle"] = (i + 1) * 5
            for k, d in self.al.update(s, self.t, work):
                self.events.append((self.t, k, d))
        return self

    def at(self, kind):
        import datetime as dt
        return [dt.datetime.fromtimestamp(t).strftime("%H:%M") for t, k, _ in self.events if k == kind]


class AlertsTest(unittest.TestCase):
    def cfg(self, **kw):
        kw.setdefault("water_reminder_minutes", 0)
        kw.setdefault("water_reminder_enabled", True)  # mặc định tắt khi cài lần đầu; các test này bật để kiểm
        kw.setdefault("break_reminder_minutes", 0)
        return make_cfg(tempfile.mkdtemp(), **kw)

    def test_break_toggle_and_minutes(self):
        self.assertEqual(Sim(self.cfg(break_reminder_minutes=45)).run(100).at("break"), ["08:45", "09:30"])
        off = self.cfg(break_reminder_minutes=45, break_reminder_enabled=False)
        self.assertEqual(Sim(off).run(100).at("break"), [])

    def test_water_every_hour_in_work_time_only(self):
        sim = Sim(self.cfg(water_reminder_minutes=60))
        sim.run(130, vdi="background")          # 08:00–10:10 (cả lúc ngoài VDI vẫn nhắc)
        sim.run(60, work=False)                 # 10:10–11:10 coi như nghỉ trưa: không nhắc, đồng hồ tính lại
        sim.run(65)                             # 11:10–12:15
        self.assertEqual(sim.at("water"), ["09:00", "10:00", "12:10"])

    def test_water_waits_while_locked_then_sends_once(self):
        sim = Sim(self.cfg(water_reminder_minutes=60))
        sim.run(50).run(40, locked=True).run(5)
        self.assertEqual(sim.at("water"), ["09:30"], "khoá máy lúc tới hạn: gửi ngay khi quay lại, 1 lần")

    def test_merge_with_break_same_minute(self):
        sim = Sim(self.cfg(water_reminder_minutes=60, break_reminder_minutes=60))
        sim.run(125)
        self.assertEqual(sim.at("water"), [], "trùng giờ nhắc nghỉ: gộp, không gửi riêng")
        breaks = [d for _, k, d in sim.events if k == "break"]
        self.assertEqual([d["water"] for d in breaks], [True, True])

    def test_water_slightly_before_break_waits_to_merge(self):
        sim = Sim(self.cfg(water_reminder_minutes=60, break_reminder_minutes=60), start="08:00")
        sim.run(1, vdi="background")  # nước tính từ 08:00, khối tập trung từ 08:01
        sim.run(65)
        self.assertEqual(sim.at("water"), [])
        self.assertEqual([d["water"] for _, k, d in sim.events if k == "break"], [True])

    def test_not_affected_by_nudge_off(self):
        sim = Sim(self.cfg(nudge_level="off", water_reminder_minutes=30, break_reminder_minutes=40)).run(61)
        self.assertEqual(sim.at("water"), ["08:30", "09:00"])
        self.assertEqual(sim.at("break"), ["08:40"])

    def test_water_off(self):
        self.assertEqual(Sim(self.cfg(water_reminder_minutes=60, water_reminder_enabled=False)).run(130).at("water"), [])


class WordingTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)

    def test_break_message_covers_moving_and_eyes_per_tone(self):
        leads = set()
        with mock.patch.object(persona.random, "choice", lambda xs: xs[0]):
            for tone in persona.TONES:
                t = motivation.break_message(self.db, 60, dict(persona.DEFAULT, giong=tone))
                for word in ("đi lại", "vươn vai", "20-20-20", "60 phút"):
                    self.assertIn(word, t)
                leads.add(t.splitlines()[0])
        self.assertEqual(len(leads), 4)
        self.assertIn("💧", motivation.break_message(self.db, 60, persona.DEFAULT, water=True))
        self.assertNotIn("💧", motivation.break_message(self.db, 60).split("\n\n")[0])

    def test_water_varied_per_tone(self):
        for tone in persona.TONES:
            p = dict(persona.DEFAULT, giong=tone)
            texts = {messages.water({}, p).splitlines()[0] for _ in range(60)}
            self.assertGreaterEqual(len(texts), 2, tone)
        boss = messages.water({}, dict(persona.DEFAULT, giong="sep_kho_tinh"))
        self.assertNotRegex(boss.splitlines()[0], "[😄🥤💦🌵]")


class FakeBot:
    def __init__(self, cfg):
        self.cfg, self.sent, self._db = cfg, [], None

    @property
    def db(self):
        if self._db is None:
            self._db = open_db(db_path(self.cfg))
        return self._db

    def send(self, text, raw=False):
        self.sent.append(text)


class TrackerSendTest(TempCase):
    def test_dispatch_water_and_merged_break(self):
        bot = FakeBot(self.cfg)
        self.addCleanup(lambda: bot._db and bot._db.close())
        tr = Tracker(self.cfg, None, bot, notifier=None, run_housekeeping=False)
        tr.db, tr.day = bot.db, DAY
        with mock.patch("focus.messages.random.choice", lambda seq: seq[0]):  # mẹo "" (không kèm 💧) là ngẫu nhiên
            tr.dispatch("water", {"minutes": 60}, {})
        tr.dispatch("break", {"minutes": 60, "nth": 1, "water": True}, {})
        self.assertEqual(len(bot.sent), 2)
        self.assertIn("💧", bot.sent[0])
        self.assertIn("20-20-20", bot.sent[1])
        self.assertIn("ly nước", bot.sent[1])
        self.assertTrue(any("ALERT_WATER" in l for l in self.audit_lines()))


class CommandTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def ok(self):
        pid = list(self.bot.pending)[0]
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})

    def test_break_command_persist(self):
        self.assertIn("ĐANG BẬT, mỗi 60 phút", self.say("/break")[0])
        self.assertIn("ĐANG TẮT", self.say("/break off")[0])
        self.assertFalse(self.cfg["break_reminder_enabled"])
        self.assertEqual(get_pref(self.bot.db, "break_enabled"), "0")
        self.assertIn("mỗi 45 phút", self.say("/nghingoi 45")[0])
        self.assertTrue(self.cfg["break_reminder_enabled"])
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.state, api=self.api)
        self.assertEqual((cfg2["break_reminder_enabled"], cfg2["break_reminder_minutes"]), (True, 45))
        self.say("/break mac_dinh")
        self.assertEqual(self.cfg["break_reminder_minutes"], 60)
        self.assertIsNone(get_pref(self.bot.db, "break_minutes"))
        self.assertIn("5 đến 240", self.say("/break 1000")[0])
        self.assertIn("Chọn on", self.say("/break abc")[0])

    def test_water_command_persist(self):
        self.say("/water off")
        self.assertFalse(self.cfg["water_reminder_enabled"])
        self.say("/uongnuoc 30")
        self.assertEqual((self.cfg["water_reminder_enabled"], self.cfg["water_reminder_minutes"]), (True, 30))
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.state, api=self.api)
        self.assertEqual(cfg2["water_reminder_minutes"], 30)
        self.assertTrue(any("WATER_REMINDER" in l for l in self.audit_lines()))

    def test_water_on_when_file_has_zero(self):
        self.cfg["water_reminder_minutes"] = 0
        self.say("/water on")
        self.assertEqual(self.cfg["water_reminder_minutes"], 60)

    def test_natural_language(self):
        cases = [("tắt nhắc đứng dậy", "break_reminder_enabled", False),
                 ("nhắc nghỉ mỗi 45 phút", "break_reminder_minutes", 45),
                 ("tắt nhắc uống nước", "water_reminder_enabled", False),
                 ("nhắc uống nước", "water_reminder_enabled", True)]
        for text, key, want in cases:
            with self.subTest(text=text):
                self.bot.pending.clear()
                self.say(text)
                self.assertTrue(self.bot.pending, text)
                self.ok()
                self.assertEqual(self.cfg[key], want)
        self.assertEqual(intent.by_rules("nhắc nghỉ ngơi cài thế nào?")[0].name, "nhac_nghi_ngoi")

    def test_status_and_help(self):
        self.say("/water off")
        status = self.say("/status")[0]
        self.assertIn("nhắc nghỉ (/break): 60'", status)
        self.assertIn("uống nước (/water): tắt", status)
        text = "\n".join(self.say("/help"))
        for word in ("/break /nghingoi", "/water /uongnuoc", "20-20-20", "Uống nước: (đã tắt)"):
            self.assertIn(word, text)


class ConfigTest(unittest.TestCase):
    def test_validation(self):
        c = dict(DEFAULTS)
        validate(c)
        self.assertEqual((c["water_reminder_minutes"], c["break_reminder_enabled"]), (60, True))
        for bad in ({"water_reminder_minutes": -5}, {"water_reminder_enabled": "yes"},
                    {"break_reminder_enabled": 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    validate(dict(DEFAULTS, **bad))


if __name__ == "__main__":
    unittest.main()
