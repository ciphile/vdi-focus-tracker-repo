"""v2.12.0: /tatapp (tắt hẳn app, luôn hỏi OK), /lambu on|off (chế độ làm bù / thường khi đang chạy),
/chay247 on|off (bot 00:00–24:00 + chạy cả ngày nghỉ). Test không bao giờ gọi Task Scheduler / launchctl thật."""
import json
import os
import threading
import time
from unittest import mock

from focus import actions, autostart, intent, prefs
from focus.actions import BY_NAME, bot_commands, full_help, hours_line, run247_on
from focus.storage import db_path, get_pref, open_db, save_note
from focus.telegram_bot import TelegramBot
from focus.tracker import Tracker
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, msg, ts
from tests.test_bot_hours import FakeClock, VdiProbe

THURSDAY = "2026-10-15"
FRIDAY = "2026-10-16"
SATURDAY = "2026-10-17"


class _Bot(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "recheck": threading.Event(), "quit": threading.Event(),
                      "last": None, "perf": "", "manual": False}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.addCleanup(lambda: self.bot.db.close())
        for target, kw in ((actions, {"_now_hhmm": "10:00"}), (actions, {"off_day": None})):
            name, value = next(iter(kw.items()))
            p = mock.patch.object(target, name, return_value=value)
            setattr(self, name.strip("_"), p.start())
            self.addCleanup(p.stop)
        p = mock.patch.object(autostart, "_run", side_effect=AssertionError("không được gọi lệnh hệ thống thật"))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(autostart, "update_start_time", return_value=(True, "Task Scheduler: đã đổi giờ."))
        self.upd = p.start()
        self.addCleanup(p.stop)

    def say(self, text, **kw):
        self.api.clear()
        self.bot.handle(msg(text, **kw))
        return self.api.sent()

    def press(self, verb="ok"):
        pid = list(self.bot.pending)[0]
        self.api.clear()
        self.bot.handle_callback({"id": "c", "data": f"{verb}:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        return self.api.sent()


class TatAppTest(_Bot):
    def test_command_always_asks_ok_first(self):
        out = self.say("/tatapp")
        self.assertFalse(self.state["quit"].is_set(), "gõ lệnh chưa được tắt ngay")
        self.assertEqual(len(self.bot.pending), 1)
        self.assertIn("Tắt hẳn app", out[-1])
        out = self.press("ok")
        self.assertTrue(self.state["quit"].is_set())
        self.assertIn("Đang tắt app", out[0])
        self.assertIn("start_tracker", out[0])
        self.assertIn("07:00", out[0], "giờ tự bật lại")
        self.assertTrue(any("QUIT" in l for l in self.audit_lines()))

    def test_cancel_keeps_running(self):
        self.say("/tatapp")
        self.press("no")
        self.assertFalse(self.state["quit"].is_set())

    def test_natural_language_asks_ok(self):
        self.say("tắt app đi")
        self.assertFalse(self.state["quit"].is_set())
        self.assertEqual(len(self.bot.pending), 1)
        self.press("ok")
        self.assertTrue(self.state["quit"].is_set())

    def test_old_message_from_before_start_is_skipped(self):
        for text in ("/tatapp", "tắt app đi"):
            out = self.say(text, date=int(time.time()) - 3 * 3600)
            self.assertFalse(self.bot.pending, text)
            self.assertFalse(self.state["quit"].is_set(), text)
            self.assertIn("Bỏ qua lệnh «Tắt hẳn app»", out[0])

    def test_lambu_before_state_ready(self):
        self.bot.state = None
        self.assertIn("Chưa đổi được", self.say("/lambu on")[0])

    def test_no_quit_event_yet(self):
        self.state.pop("quit")
        self.say("/tatapp")
        out = self.press("ok")
        self.assertIn("Chưa tắt được", out[0])

    def test_stop_acknowledges_last_update(self):
        self.bot.offset = 77
        self.api.clear()
        self.bot.stop()
        self.assertIn(("getUpdates", {"offset": 77, "timeout": 0, "limit": 1}, None), self.api.calls)
        self.bot.offset = 0
        self.api.clear()
        self.bot.stop()
        self.assertEqual(self.api.calls, [], "chưa nhận tin nào: không gọi Telegram")


class LamBuTest(_Bot):
    def test_view_on_off_workday(self):
        out = self.say("/lambu")[0]
        self.assertIn("Chế độ đang dùng: THƯỜNG", out)
        self.assertIn("/lambu on", out)
        self.assertFalse(self.bot.pending, "xem không cần OK")
        out = self.say("/lambu on")[0]
        self.assertTrue(self.state["manual"])
        self.assertIn("Đã bật chế độ làm bù (OT)", out)
        self.assertIn("Chế độ đang dùng: LÀM BÙ (OT)", self.say("/lambu")[0])
        out = self.say("/lambu off")[0]
        self.assertFalse(self.state["manual"])
        self.assertIn("Đã về chế độ thường", out)
        self.assertTrue(self.state["recheck"].is_set(), "tracker xét lại ngày nghỉ ngay")

    def test_off_on_off_day_says_app_stops(self):
        self.off_day.return_value = "Thứ Bảy"
        self.state["manual"] = True
        out = self.say("/lambu off")[0]
        self.assertIn("Hôm nay nghỉ (Thứ Bảy) nên mình chốt số liệu làm bù rồi tắt app ngay", out)
        self.cfg["run_on_off_days"] = True
        out = self.say("/lambu off")[0]
        self.assertIn("/chay247", out)
        self.assertNotIn("tắt app ngay", out)

    def test_natural_language_confirms(self):
        self.say("bật chế độ OT")
        self.assertFalse(self.state["manual"])
        self.press("ok")
        self.assertTrue(self.state["manual"])
        self.say("về chế độ thường")
        self.press("ok")
        self.assertFalse(self.state["manual"])

    def test_old_lambu_message_skipped(self):
        self.say("/lambu on", date=int(time.time()) - 3 * 3600)
        self.assertFalse(self.state["manual"])


class Chay247Test(_Bot):
    def setUp(self):
        super().setUp()
        self.cfg["_settings_path"] = self.path = os.path.join(self.tmp, "settings.json")
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"work_start": "08:00", "auto_start_at": "07:00"}, f)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_on_then_off_restores_everything(self):
        self.assertIn("KHÔNG chạy 24/24", self.say("/chay247")[0])
        out = self.say("/chay247 on")[0]
        self.assertIn("Đã bật chạy 24/24", out)
        self.assertIn("Sleep = Never", out)
        self.assertEqual((self.cfg["auto_start_at"], self.cfg["auto_stop_at"], self.cfg["run_on_off_days"]),
                         ("00:00", "24:00", True))
        self.assertTrue(run247_on(self.cfg))
        self.assertEqual(self.read(), {"work_start": "08:00", "auto_start_at": "00:00", "auto_stop_at": "24:00",
                                       "run_on_off_days": True})
        self.upd.assert_called_with(self.cfg, "00:00")
        self.assertEqual(get_pref(self.bot.db, "run_on_off_days"), "1")
        self.assertIn("đang chạy 24/24 rồi", self.say("/chay247 on")[0])
        self.assertEqual(hours_line(self.cfg), "Bot chạy 24/24 (00:00 – 24:00, cả ngày nghỉ) · /chay247")

        out = self.say("/chay247 off")[0]
        self.assertIn("Đã tắt chạy 24/24: bot bật 07:00 – tắt 23:59", out)
        self.assertIn("Hôm nay app tắt lúc 23:59.", out)
        self.assertEqual((self.cfg["auto_start_at"], self.cfg["auto_stop_at"], self.cfg["run_on_off_days"]),
                         ("07:00", "23:59", False))
        self.assertEqual(self.read(), {"work_start": "08:00", "auto_start_at": "07:00", "auto_stop_at": "23:59"})
        self.upd.assert_called_with(self.cfg, "07:00")
        self.assertIsNone(get_pref(self.bot.db, "run247_prev"))
        self.assertIsNone(get_pref(self.bot.db, "run_on_off_days"), "đã ghi lại file: sửa tay settings.json vẫn có tác dụng")
        self.assertIn("đang không chạy 24/24", self.say("/chay247 off")[0])
        self.assertTrue(any("RUN_247" in l for l in self.audit_lines()))

    def test_off_without_settings_file_keeps_pref(self):
        self.cfg.pop("_settings_path")
        self.say("/chay247 on")
        self.say("/chay247 off")
        self.assertEqual(get_pref(self.bot.db, "run_on_off_days"), "0", "không có file để ghi: giữ trong DB")

    def test_setting_survives_restart(self):
        self.say("/chay247 on")
        cfg2 = dict(self.cfg, run_on_off_days=False, auto_start_at="07:00", auto_stop_at="23:59")
        for k in [k for k in cfg2 if k.startswith("_file_")]:
            cfg2.pop(k)
        prefs.apply(cfg2, self.bot.db)
        self.assertTrue(run247_on(cfg2), "bật lại app: vẫn 24/24 dù settings.json bị sửa tay")

    def test_off_on_off_day_and_past_stop(self):
        self.say("/chay247 on")
        self.off_day.return_value = "Chủ Nhật"
        self.assertIn("Hôm nay nghỉ (Chủ Nhật): app chốt số liệu rồi tắt ngay", self.say("/chay247 off")[0])
        self.say("/chay247 on")
        self.off_day.return_value = None
        self.now_hhmm.return_value = "23:59"
        self.assertIn("Đã quá 23:59: app chốt số liệu hôm nay rồi tắt ngay", self.say("/chay247 off")[0])
        self.say("/chay247 on")
        self.now_hhmm.return_value = "03:00"
        self.assertIn("chạy tiếp tới 23:59", self.say("/chay247 off")[0])

    def test_keeps_original_when_turned_on_twice_after_giobot(self):
        self.say("/chay247 on")
        self.say("/giobot 01:00 24:00")
        self.assertFalse(run247_on(self.cfg))
        self.say("/chay247 on")
        self.say("/chay247 off")
        self.assertEqual((self.cfg["auto_start_at"], self.cfg["auto_stop_at"]), ("07:00", "23:59"))

    def test_natural_language(self):
        self.say("cho app chạy 24/24")
        self.assertFalse(self.cfg["run_on_off_days"], "chưa bấm OK")
        self.press("ok")
        self.assertTrue(run247_on(self.cfg))
        out = self.say("app có chạy 24/24 không?")
        self.assertFalse(self.bot.pending)
        self.assertIn("App đang chạy 24/24", out[-1])


class HelpTest(TempCase):
    def test_listed_in_menu_and_help(self):
        cmds = {c["command"] for c in bot_commands()}
        self.assertTrue({"tatapp", "lambu", "chay247"} <= cmds)
        text = full_help(self.cfg)
        for c in ("/tatapp", "/lambu", "/chay247"):
            self.assertIn(c, text)
        self.assertTrue(BY_NAME["tat_app"].confirm_command)

    def test_rules_do_not_steal_other_sentences(self):
        for text, name in (("cho bot chạy từ 8h đến 18h", "gio_bot"), ("tắt nhắc nhở", "doi_muc_nhac"),
                           ("tạm dừng theo dõi nhé", "tam_dung"), ("tắt chạy 24/24", "chay_24_24"),
                           ("tắt chế độ làm bù", "che_do_lam_bu")):
            self.assertEqual(intent.by_rules(text)[0].name, name, text)
        self.assertEqual(intent.by_rules("tắt chạy 24/24")[1], {"state": "off"})


class TrackerTest(TempCase):
    def make(self, day, hhmm, manual=False):
        fc = FakeClock(ts(day, hhmm))
        tr = Tracker(self.cfg, VdiProbe(fc), None, fc.clock, fc.sleep, fc.now, run_housekeeping=False,
                     manual=manual)
        return tr, fc

    def test_quit_event_finishes_day_and_exits(self):
        tr, fc = self.make(THURSDAY, "09:00")

        def hook(c):
            if c.t >= ts(THURSDAY, "09:30"):
                tr.state["quit"].set()
        fc.hook = hook
        self.assertEqual(tr.run(), "quit")
        self.assertLess(fc.t, ts(THURSDAY, "09:30", 11))
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertTrue(db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] > 300, "mẫu đã ghi xuống DB")
        self.assertTrue(any("QUIT_REQUEST" in l for l in self.audit_lines()))

    def test_manual_is_shared_with_bot_state(self):
        tr, _ = self.make(THURSDAY, "09:00", manual=True)
        self.assertTrue(tr.manual and tr.state["manual"])
        tr.state["manual"] = False
        self.assertFalse(tr.manual)

    def test_lambu_off_on_saturday_stops_tracker(self):
        tr, fc = self.make(SATURDAY, "10:00", manual=True)

        def hook(c):
            if c.t >= ts(SATURDAY, "11:00") and tr.state["manual"]:
                tr.state["manual"] = False  # như /lambu off
                tr.state["recheck"].set()
        fc.hook = hook
        self.assertEqual(tr.run(), "off_day")
        self.assertLess(fc.t, ts(SATURDAY, "11:00", 11))

    def test_lambu_on_keeps_running_into_saturday(self):
        self.cfg.update(auto_start_at="00:00", auto_stop_at="24:00")
        tr, fc = self.make(FRIDAY, "23:00")
        tr.state["manual"] = True  # như /lambu on tối thứ Sáu
        fc.hook = lambda c: tr.state["quit"].set() if c.t >= ts(SATURDAY, "01:00") else None
        self.assertEqual(tr.run(), "quit", "qua nửa đêm sang thứ Bảy vẫn chạy (làm bù)")

    def test_247_runs_on_weekend_without_manual(self):
        self.cfg.update(auto_start_at="00:00", auto_stop_at="24:00", run_on_off_days=True)
        tr, fc = self.make(SATURDAY, "03:00")
        fc.hook = lambda c: tr.state["quit"].set() if c.t >= ts(SATURDAY, "04:00") else None
        self.assertEqual(tr.run(), "quit")

    def test_normal_mode_friday_night_stops_at_saturday(self):
        self.cfg.update(auto_start_at="00:00", auto_stop_at="24:00")
        tr, fc = self.make(FRIDAY, "23:00")
        self.assertEqual(tr.run(), "off_day")
        self.assertLess(fc.t, ts(SATURDAY, "00:01"))
