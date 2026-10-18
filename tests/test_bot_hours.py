"""Giờ bot tự bật / tự tắt (/giobot, /hours): lệnh, nhắn tự nhiên, kiểm tra hợp lệ, lưu prefs, ghi settings.json,
sửa lịch tự bật của máy (luôn bằng đồ giả: test KHÔNG BAO GIỜ chạy schtasks / powershell / launchctl thật),
tracker đổi giờ giữa chừng, tracker bật sớm / cuối tuần thoát im lặng."""
import base64
import datetime as dt
import json
import os
import plistlib
import sys
import threading
import unittest
from unittest import mock

from focus import actions, autostart, intent, prefs
from focus.actions import BY_NAME, parse_bot_hours, parse_command_args, validate
from focus.config import ConfigError, DEFAULTS, run_window_conflict, validate as validate_cfg
from focus.storage import db_path, get_pref, open_db
from focus.telegram_bot import TelegramBot
from focus.tracker import Tracker
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, make_cfg, msg, ts

THURSDAY = "2026-10-15"
SATURDAY = "2026-10-17"


class _BotCase(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "recheck": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.addCleanup(lambda: self.bot.db.close())
        # Giờ "bây giờ" của /giobot cố định cho câu trả lời ổn định.
        p = mock.patch.object(actions, "_now_hhmm", return_value="10:00")
        self.now = p.start()
        self.addCleanup(p.stop)
        # Chốt an toàn: lỡ test nào gọi tới hệ điều hành thì hỏng ngay, không chạy lệnh thật.
        p = mock.patch.object(autostart, "_run", side_effect=AssertionError("không được gọi lệnh hệ thống thật"))
        p.start()
        self.addCleanup(p.stop)

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def ok(self):
        pid = list(self.bot.pending)[0]
        self.api.clear()
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        return self.api.sent()

    def hours(self):
        return self.cfg["auto_start_at"], self.cfg["auto_stop_at"]


class CommandTest(_BotCase):
    def test_view_explains_and_writes_nothing(self):
        out = self.say("/giobot")[0]
        self.assertIn("bật 07:00 – tắt 23:59, thứ 2 – thứ 6 (theo settings.json)", out)
        self.assertIn("chờ tới 07:00", out)
        self.assertIn("Giờ tắt phải sau 17:05 (gửi tổng kết tuần)", out)
        for k in ("/giobot 08:30 18:00", "/giobot bat 08:30", "/giobot tat 19:00", "/giobot mac_dinh"):
            self.assertIn(k, out)
        self.assertFalse(self.bot.pending)
        self.assertIsNone(get_pref(self.bot.db, "auto_start_at"))
        self.assertEqual(self.say("/hours")[0], out, "/hours là tên khác của /giobot")

    def test_set_both(self):
        out = self.say("/giobot 08:30 18:00")[0]
        self.assertEqual(self.hours(), ("08:30", "18:00"))
        self.assertIn("✅ Giờ bot mới: bật 08:30 – tắt 18:00 (thứ 2 – thứ 6).", out)
        self.assertIn("muộn hơn giờ bắt đầu làm (08:00)", out, "giờ bật sau work_start: cảnh báo nhưng vẫn đổi")
        self.assertIn("Hôm nay bot tắt lúc 18:00.", out)
        self.assertEqual(get_pref(self.bot.db, "auto_start_at"), "08:30")
        self.assertEqual(get_pref(self.bot.db, "auto_stop_at"), "18:00")
        self.assertTrue(any("BOT_HOURS" in l and "08:30-18:00" in l for l in self.audit_lines()))

    def test_set_one_side(self):
        out = self.say("/giobot bat 7:30")[0]
        self.assertEqual(self.hours(), ("07:30", "23:59"))
        self.assertNotIn("⚠️", out, "bật trước giờ làm: không cảnh báo")
        out = self.say("/hours tat 19h")[0]
        self.assertEqual(self.hours(), ("07:30", "19:00"))
        self.assertIn("Giờ bật không đổi (07:30)", out)

    def test_validation_refuses_with_reason(self):
        cases = {"/giobot tat 16:30": "phải sau giờ gửi tổng kết ngày (17:00)",
                 "/giobot tat 16:55": "tổng kết ngày (17:00)",
                 "/giobot 18:00 08:00": "phải trước giờ tắt",
                 "/giobot bat 23:59": "Giờ bật (23:59) phải trước giờ tắt (23:59)",
                 "/giobot 25:00 18:00": "không đúng dạng HH:MM",
                 "/giobot 8:30": "08:30 là giờ BẬT hay giờ TẮT bot?"}
        for text, reason in cases.items():
            with self.subTest(text=text):
                out = self.say(text)[0]
                self.assertIn(reason, out)
                self.assertEqual(self.hours(), ("07:00", "23:59"))
                self.assertIsNone(get_pref(self.bot.db, "auto_stop_at"))
        self.cfg["weekly_report_at"] = "17:30"
        self.assertIn("tổng kết tuần (17:30)", self.say("/giobot tat 17:15")[0])

    def test_stop_already_passed_finishes_today(self):
        self.now.return_value = "18:30"
        out = self.say("/giobot tat 18:00")[0]
        self.assertIn("Đã quá 18:00: bot chốt số liệu hôm nay rồi tắt ngay (không gửi gì thêm)", out)
        self.assertEqual(self.cfg["auto_stop_at"], "18:00")

    def test_later_start_keeps_running_today(self):
        self.now.return_value = "08:10"
        out = self.say("/giobot bat 08:30")[0]
        self.assertIn("Hôm nay bot đang chạy nên chạy tiếp tới 23:59", out)

    def test_cfg_updated_after_reply(self):
        """Tracker đọc cfg mỗi vòng: câu trả lời phải gửi xong trước khi cfg đổi (giờ tắt đã qua -> tracker thoát)."""
        seen = []
        real = self.bot.send
        self.bot.send = lambda text, *a, **k: (seen.append(self.hours()), real(text, *a, **k))[1]
        self.say("/giobot 08:30 18:00")
        self.assertEqual(seen, [("07:00", "23:59")])
        self.assertEqual(self.hours(), ("08:30", "18:00"))

    def test_persist_and_apply_at_start(self):
        self.say("/giobot 08:30 18:00")
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.state, api=self.api)
        self.assertEqual((cfg2["auto_start_at"], cfg2["auto_stop_at"]), ("08:30", "18:00"))
        self.assertEqual((cfg2["_file_auto_start_at"], cfg2["_file_auto_stop_at"]), ("07:00", "23:59"))
        # settings.json sau đó dời giờ tổng kết ra sau giờ tắt đã lưu: bỏ giờ đã lưu, dùng settings.json.
        cfg3 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", daily_summary_at="18:30")
        TelegramBot(cfg3, self.state, api=self.api)
        self.assertEqual((cfg3["auto_start_at"], cfg3["auto_stop_at"]), ("07:00", "23:59"))

    def test_reset_to_settings(self):
        self.say("/giobot 08:30 18:00")
        out = self.say("/giobot mac_dinh")[0]
        self.assertIn("↩️ Về giờ trong settings.json: bật 07:00 – tắt 23:59", out)
        self.assertEqual(self.hours(), ("07:00", "23:59"))
        for key in ("auto_start_at", "auto_stop_at", "hours_orig"):
            self.assertIsNone(get_pref(self.bot.db, key))
        self.assertIn("(theo settings.json)", self.say("/giobot")[0])

    def test_status_and_help(self):
        self.say("/giobot 08:30 18:00")
        status = self.say("/status")[0]
        self.assertIn("Bot bật 08:30 – tắt 18:00 (thứ 2 – thứ 6) · /giobot", status)
        help_text = "\n".join(self.say("/help"))
        for word in ("/giobot /hours", "/giobot 08:30 18:00", "/giobot bat 08:30", "/giobot tat 19:00",
                     "«bật bot lúc 8 rưỡi»", "«cho bot chạy từ 8h đến 18h»", "tự bật lúc 08:30, tự tắt lúc 18:00"):
            self.assertIn(word, help_text)


class NaturalLanguageTest(_BotCase):
    def test_confirm_then_apply(self):
        cases = {"bật bot lúc 8 rưỡi": ("08:30", "23:59"),
                 "tắt bot lúc 6 giờ chiều": ("07:00", "18:00"),
                 "cho bot chạy từ 8h đến 18h": ("08:00", "18:00"),
                 "đổi giờ bot: bật 7h15 tắt 20h": ("07:15", "20:00")}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.cfg.update(auto_start_at="07:00", auto_stop_at="23:59")
                self.bot.pending.clear()
                out = self.say(text)
                self.assertTrue(self.bot.pending, out)
                self.assertIn("Mình hiểu bạn muốn: Đổi giờ bot:", out[0])
                self.assertEqual(self.hours(), ("07:00", "23:59"), "chưa bấm OK thì chưa đổi")
                self.ok()
                self.assertEqual(self.hours(), want)

    def test_question_is_view(self):
        out = self.say("bot tắt lúc mấy giờ?")
        self.assertFalse(self.bot.pending)
        self.assertIn("gio_bot", out[0], "nhắn tự nhiên: báo bot hiểu thành action nào")
        self.assertIn("⏰ Giờ bot: bật 07:00 – tắt 23:59", out[1])

    def test_refused_before_ok(self):
        out = self.say("tắt bot lúc 4 giờ chiều")
        self.assertFalse(self.bot.pending, "giờ tắt trước tổng kết: báo ngay, không hỏi OK")
        self.assertIn("tổng kết ngày (17:00)", out[0])

    def test_rules(self):
        self.assertEqual(parse_bot_hours("bật bot lúc 8 rưỡi"), {"start": "08:30"})
        self.assertEqual(parse_bot_hours("tắt bot lúc 6 giờ chiều"), {"stop": "18:00"})
        self.assertEqual(parse_bot_hours("cho bot chạy từ 8h đến 18h"), {"start": "08:00", "stop": "18:00"})
        self.assertEqual(parse_bot_hours("bật lúc 1 giờ trưa"), {"start": "13:00"})
        self.assertEqual(parse_bot_hours("08:30 18:00"), {"start": "08:30", "stop": "18:00"})
        self.assertEqual(parse_bot_hours("bat 08:30"), {"start": "08:30"})
        self.assertEqual(parse_bot_hours("tat 19:00"), {"stop": "19:00"})
        self.assertEqual(parse_bot_hours("mac_dinh"), {"reset": True})
        self.assertEqual(parse_bot_hours("8:30"), {"time": "08:30"})
        self.assertEqual(parse_bot_hours("bot chạy từ thứ 2 đến thứ 6 lúc 8h"), {"time": "08:00"},
                         "\"thứ 2\" không phải giờ; \"đến\" thuộc về thứ, không phải giờ")
        self.assertEqual(intent.by_rules("tắt bớt nhắc nhở")[0].name, "doi_muc_nhac", "\"bớt\" không phải \"bot\"")
        self.assertEqual(intent.by_rules("cho bot chạy từ 8h đến 18h")[0].name, "gio_bot")
        a = BY_NAME["gio_bot"]
        self.assertEqual(validate(a, {"start": "8h30", "stop": "18:00"}), ({"start": "08:30", "stop": "18:00"}, None))
        self.assertEqual(validate(a, {"reset": True})[0], {"reset": True})
        self.assertEqual(validate(a, parse_command_args(a, "bat 8")), ({"start": "08:00"}, None))


class SettingsFileTest(_BotCase):
    ORIGINAL = {"_ghi_chu": "giữ nguyên tiếng Việt", "work_start": "08:00", "auto_start_at": "07:00",
                "pace_checkpoints": ["10:30", "14:00"], "auto_stop_at": "23:59", "nudge_level": "vua"}

    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "settings.json")
        text = json.dumps(self.ORIGINAL, ensure_ascii=False, indent=2).replace("\n", "\r\n") + "\r\n"
        with open(self.path, "wb") as f:
            f.write(b"\xef\xbb\xbf" + text.encode("utf-8"))
        self.cfg["_settings_path"] = self.path

    def read(self):
        with open(self.path, "rb") as f:
            raw = f.read()
        return raw, json.loads(raw.decode("utf-8-sig"))

    def test_rewrite_keeps_other_keys_order_bom_crlf_and_backup(self):
        with open(self.path, "rb") as f:
            before = f.read()
        out = self.say("/giobot 08:30 18:00")[0]
        self.assertIn("Đã lưu vào config/settings.json (bản cũ: settings.json.bak).", out)
        raw, data = self.read()
        self.assertEqual(list(data), list(self.ORIGINAL), "giữ thứ tự khoá")
        self.assertEqual({k: v for k, v in data.items() if k not in prefs.HOURS},
                         {k: v for k, v in self.ORIGINAL.items() if k not in prefs.HOURS})
        self.assertEqual((data["auto_start_at"], data["auto_stop_at"]), ("08:30", "18:00"))
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "giữ BOM")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "giữ CRLF")
        with open(self.path + ".bak", "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual([n for n in os.listdir(self.tmp) if n.endswith(".tmp")], [], "không để file tạm")
        self.assertTrue(any("SETTINGS_WRITE" in l for l in self.audit_lines()))

    def test_reset_restores_original_file_values(self):
        self.say("/giobot 08:30 18:00")
        self.cfg.update(auto_start_at="08:30", auto_stop_at="18:00")
        self.say("/giobot bat 09:00")  # lần đổi thứ 2: giờ gốc vẫn là của settings.json ban đầu
        self.say("/giobot mac_dinh")
        _, data = self.read()
        self.assertEqual(data, self.ORIGINAL)
        self.assertEqual(self.hours(), ("07:00", "23:59"))

    def test_reset_removes_keys_that_were_absent(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"work_start": "08:00"}, f)
        self.say("/giobot 08:30 18:00")
        self.say("/giobot mac_dinh")
        _, data = self.read()
        self.assertEqual(data, {"work_start": "08:00"})
        self.assertEqual(self.hours(), (DEFAULTS["auto_start_at"], DEFAULTS["auto_stop_at"]))

    def test_reset_after_hand_edit_uses_file_and_does_not_overwrite(self):
        self.say("/giobot 08:30 18:00")
        raw, data = self.read()
        data["auto_start_at"] = "09:15"
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.say("/giobot mac_dinh")
        self.assertEqual(self.hours(), ("09:15", "18:00"))
        self.assertEqual(self.read()[1]["auto_start_at"], "09:15")

    def test_broken_file_not_overwritten_pref_still_applies(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ hỏng")
        out = self.say("/giobot 08:30 18:00")[0]
        self.assertIn("Không ghi được config/settings.json", out)
        self.assertIn("sai cú pháp JSON", out)
        self.assertEqual(self.hours(), ("08:30", "18:00"))
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{ hỏng")

    def test_write_settings_plain_lf_indent4_and_new_file(self):
        p = os.path.join(self.tmp, "lf.json")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write('{\n    "a": 1,\n    "auto_stop_at": "23:59"\n}\n')
        self.assertEqual(autostart.write_settings(p, {"auto_stop_at": "18:00", "auto_start_at": "08:00"}), (True, ""))
        with open(p, "rb") as f:
            raw = f.read()
        self.assertEqual(raw, b'{\n    "a": 1,\n    "auto_stop_at": "18:00",\n    "auto_start_at": "08:00"\n}\n')
        new = os.path.join(self.tmp, "sub", "new.json")
        self.assertTrue(autostart.write_settings(new, {"auto_start_at": "08:00"})[0])
        self.assertFalse(os.path.exists(new + ".bak"))
        self.assertEqual(autostart.read_settings(new), {"auto_start_at": "08:00"})
        with open(p, "w", encoding="utf-8") as f:
            f.write("[1, 2]")
        self.assertFalse(autostart.write_settings(p, {"auto_start_at": "08:00"})[0])


class AutostartTest(_BotCase):
    def setUp(self):
        super().setUp()
        self.cfg["_autostart_sync"] = True
        self.calls = []
        self.replies = []
        autostart._run.side_effect = self.fake_run
        p = mock.patch.object(autostart, "os_kind", return_value="windows")
        self.kind = p.start()
        self.addCleanup(p.stop)

    def fake_run(self, cmd, timeout=autostart.RUN_TIMEOUT):
        self.calls.append(cmd)
        self.assertLessEqual(timeout, 15)
        return self.replies.pop(0) if self.replies else (0, "")

    def script(self, cmd):
        return base64.b64decode(cmd[cmd.index("-EncodedCommand") + 1]).decode("utf-16-le")

    def test_windows_updates_calendar_trigger_only(self):
        self.replies = [(0, "OK 1")]
        out = self.say("/giobot 08:30 18:00")[0]
        self.assertEqual(len(self.calls), 1)
        cmd = self.calls[0]
        self.assertEqual(cmd[0], "powershell.exe")
        self.assertIn("-NonInteractive", cmd)
        s = self.script(cmd)
        self.assertIn("GetTask('FocusTracker')", s)
        self.assertIn("'T08:30:00'", s)
        self.assertIn("$tr.Type -eq 3", s, "chỉ trigger theo lịch tuần (giữ trigger đăng nhập / thức dậy)")
        self.assertIn("Task Scheduler: đã đổi giờ tự bật sang 08:30 (thứ 2 – thứ 6).", out)
        self.assertTrue(any("AUTOSTART_UPDATE" in l and "windows 08:30 ok" in l for l in self.audit_lines()))

    def test_windows_missing_task_tells_to_rerun_installer(self):
        self.replies = [(2, "NOTASK")]
        out = self.say("/giobot bat 08:30")[0]
        self.assertEqual(len(self.calls), 1, "chưa có task: không thử schtasks")
        self.assertIn("Chưa thấy task FocusTracker", out)
        self.assertIn("cai_tu_khoi_dong.bat", out)
        self.assertEqual(self.hours(), ("08:30", "23:59"), "giờ mới vẫn có hiệu lực")

    def test_windows_falls_back_to_schtasks(self):
        self.replies = [(3, "ERR COM bị chặn"), (0, "SUCCESS")]
        out = self.say("/giobot bat 08:30")[0]
        self.assertEqual(self.calls[1], ["schtasks", "/Change", "/TN", "FocusTracker", "/ST", "08:30"])
        self.assertIn("đã đổi giờ tự bật sang 08:30", out)

    def test_windows_all_fail(self):
        self.replies = [(None, "không có lệnh powershell.exe"), (1, "ERROR: Access is denied.")]
        out = self.say("/giobot bat 08:30")[0]
        self.assertIn("Chưa đổi được giờ tự bật trong Task Scheduler (ERROR: Access is denied.)", out)
        self.assertIn("cai_tu_khoi_dong.bat", out)

    def test_stop_only_does_not_touch_scheduler(self):
        out = self.say("/giobot tat 19:00")[0]
        self.assertEqual(self.calls, [])
        self.assertIn("không cần sửa lịch tự bật", out)

    def test_reset_resyncs_scheduler(self):
        self.replies = [(0, "OK 1"), (0, "OK 1")]
        self.say("/giobot bat 08:30")
        self.say("/giobot mac_dinh")
        self.assertIn("'T07:00:00'", self.script(self.calls[1]))

    def test_never_runs_without_flag(self):
        self.cfg.pop("_autostart_sync")
        out = self.say("/giobot bat 08:30")[0]
        self.assertEqual(self.calls, [])
        self.assertIn("chế độ thử", out)

    def test_exception_never_breaks_command(self):
        autostart._run.side_effect = RuntimeError("bùm")
        out = self.say("/giobot bat 08:30")[0]
        self.assertIn("Chưa đổi được giờ tự bật", out)
        self.assertEqual(self.hours(), ("08:30", "23:59"))

    def test_mac_rewrites_plist_without_launchctl(self):
        self.kind.return_value = "mac"
        folder = os.path.join(self.tmp, "LaunchAgents")
        os.makedirs(folder)
        self.cfg["_launch_agents_dir"] = folder
        path = os.path.join(folder, "com.focustracker.agent.plist")
        orig = {"Label": "com.focustracker.agent", "RunAtLoad": True, "ProgramArguments": ["/py", "x.py", "run"],
                "StartCalendarInterval": [{"Weekday": d, "Hour": 7, "Minute": 0} for d in range(1, 6)]}
        with open(path, "wb") as f:
            plistlib.dump(orig, f)
        out = self.say("/giobot bat 08:30")[0]
        self.assertEqual(self.calls, [], "không gọi launchctl (bootout sẽ giết chính tracker đang chạy)")
        with open(path, "rb") as f:
            data = plistlib.load(f)
        self.assertEqual(data["StartCalendarInterval"],
                         [{"Weekday": d, "Hour": 8, "Minute": 30} for d in range(1, 6)])
        self.assertEqual({k: v for k, v in data.items() if k != "StartCalendarInterval"},
                         {k: v for k, v in orig.items() if k != "StartCalendarInterval"})
        self.assertIn("launchd: đã ghi giờ tự bật 08:30", out)
        self.assertIn("đăng nhập lại / khởi động lại máy", out)

    def test_mac_missing_plist(self):
        self.kind.return_value = "mac"
        self.cfg["_launch_agents_dir"] = os.path.join(self.tmp, "none")
        out = self.say("/giobot bat 08:30")[0]
        self.assertIn("cai_tu_khoi_dong.command", out)

    def test_mac_label_from_installer(self):
        self.assertEqual(autostart.mac_label(), "com.focustracker.agent")
        self.assertEqual(autostart.mac_label(self.tmp), autostart.DEFAULT_LABEL)


class RunHelperTest(unittest.TestCase):
    """_run thật, chỉ với lệnh vô hại (python in một dòng)."""

    def test_run_harmless_and_missing(self):
        self.assertEqual(autostart._run([sys.executable, "-c", "print('xin chào')"]), (0, "xin chào"))
        code, why = autostart._run(["lenh-khong-ton-tai-focus"])
        self.assertIsNone(code)
        self.assertIn("không có lệnh", why)

    def test_os_kind(self):
        self.assertEqual(autostart.os_kind({"platform": "mac"}), "mac")
        self.assertEqual(autostart.os_kind({"platform": "windows"}), "windows")


class ConfigRuleTest(unittest.TestCase):
    def test_shared_rule(self):
        cfg = dict(DEFAULTS)
        self.assertIsNone(run_window_conflict(cfg, "08:00", "18:00"))
        self.assertEqual(run_window_conflict(cfg, "18:00", "18:00"), "auto_start_at")
        self.assertEqual(run_window_conflict(cfg, "08:00", "16:59"), "daily_summary_at")
        with self.assertRaises(ConfigError):
            validate_cfg(dict(DEFAULTS, auto_stop_at="16:00"))


# ------------------------------------------------------------ tracker

class FakeClock:
    def __init__(self, start):
        self.t, self.hook = start, None

    def clock(self):
        return self.t

    def sleep(self, d):
        self.t += d
        if self.hook:
            self.hook(self)

    def now(self):
        return dt.datetime.fromtimestamp(self.t)


class VdiProbe:
    def __init__(self, fc):
        self.fc, self.calls = fc, []

    def sample(self):
        self.calls.append(self.fc.t)
        return {"idle": 1.0, "locked": False, "vdi_state": "foreground", "fg_proc": "cdviewer.exe", "fg_title": "",
                "vdi_full": True}


class TrackerTest(TempCase):
    def make(self, day, hhmm, cfg=None):
        fc = FakeClock(ts(day, hhmm))
        probe = VdiProbe(fc)
        self.started = []
        tr = Tracker(cfg or self.cfg, probe, None, fc.clock, fc.sleep, fc.now, run_housekeeping=False,
                     on_start=lambda: self.started.append(fc.t))
        return tr, fc, probe

    def test_stop_moved_earlier_mid_run_finishes_day(self):
        tr, fc, probe = self.make(THURSDAY, "08:00")

        def hook(c):
            if c.t >= ts(THURSDAY, "09:00"):
                self.cfg.update({"auto_stop_at": "08:30"})  # như /giobot tat 08:30 lúc 09:00
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end")
        self.assertLess(fc.t, ts(THURSDAY, "09:00", 10), "thoát ngay vòng kế tiếp")
        self.assertEqual(len(self.started), 1)
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertIsNotNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (THURSDAY,)).fetchone(),
                             "chốt số liệu ngày trước khi thoát")
        self.assertGreater(db.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 700)
        self.assertTrue(any("AUTO_STOP" in l and "stop=08:30" in l for l in self.audit_lines()))

    def test_start_moved_later_mid_run_keeps_running(self):
        tr, fc, probe = self.make(THURSDAY, "08:00")

        def hook(c):
            if c.t >= ts(THURSDAY, "09:00"):
                self.cfg.update({"auto_start_at": "10:00"})
            if c.t >= ts(THURSDAY, "09:30"):
                self.cfg.update({"auto_stop_at": "09:30"})
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end")
        self.assertTrue(any(t >= ts(THURSDAY, "09:29") for t in probe.calls), "09:00–09:30 vẫn theo dõi")

    def test_before_start_exits_quietly_without_bot(self):
        tr, fc, probe = self.make(THURSDAY, "07:30", make_cfg(self.tmp, auto_start_at="08:00"))
        self.assertEqual(tr.run(), "outside_window")
        self.assertEqual(self.started, [], "không mở bot Telegram")
        self.assertEqual(probe.calls, [])
        self.assertTrue(any("OUTSIDE_WINDOW" in l and "07:30 08:00-23:59" in l for l in self.audit_lines()))

    def test_weekend_exits_quietly(self):
        tr, fc, probe = self.make(SATURDAY, "08:00")
        self.assertEqual(tr.run(), "off_day")
        self.assertEqual(self.started, [])
        self.assertEqual(probe.calls, [])

    def test_prefs_hours_used_for_start_decision(self):
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        db = open_db(db_path(cfg))
        prefs.set_bot_hours(cfg, db, "09:00", "20:00")
        db.close()
        bot = TelegramBot(cfg, None, api=FakeTelegramAPI())  # như cmd_run: tạo bot (prefs.apply) trước tracker.run
        self.addCleanup(lambda: bot.db.close())
        tr, fc, probe = self.make(THURSDAY, "08:30", cfg)
        self.assertEqual(tr.run(), "outside_window")


if __name__ == "__main__":
    unittest.main()
