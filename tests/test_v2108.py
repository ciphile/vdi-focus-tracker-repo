"""v2.10.8: khoi_dong_lai.bat / .command khởi động lại tracker mà không mất số liệu trong ngày."""
import os
import unittest

from focus.storage import db_path, open_db
from focus.tracker import RESTART_FLAG, Tracker
from tests.helpers import TempCase, ts
from tests.test_bot_hours import THURSDAY, FakeClock, VdiProbe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RestartFlagTest(TempCase):
    def make(self, hhmm, cfg=None):
        fc = FakeClock(ts(THURSDAY, hhmm))
        tr = Tracker(cfg or self.cfg, VdiProbe(fc), None, fc.clock, fc.sleep, fc.now, run_housekeeping=False)
        return tr, fc

    def flag(self):
        return os.path.join(self.cfg["data_dir"], RESTART_FLAG)

    def test_flag_makes_tracker_save_and_exit_within_a_minute(self):
        tr, fc = self.make("08:00")

        def hook(c):
            if c.t >= ts(THURSDAY, "09:00") and not getattr(self, "made", False):
                self.made = True
                with open(self.flag(), "w") as f:
                    f.write("restart")
        fc.hook = hook
        self.assertEqual(tr.run(), "restart")
        self.assertLess(fc.t, ts(THURSDAY, "09:01", 10), "thoát trong vòng 1 phút")
        self.assertFalse(os.path.exists(self.flag()), "xoá file yêu cầu để bản mới không thoát theo")
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertIsNotNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (THURSDAY,)).fetchone(),
                             "chốt số liệu ngày trước khi thoát")
        self.assertTrue(any("RESTART_REQUEST" in l for l in self.audit_lines()))

    def test_stale_flag_at_start_is_ignored(self):
        os.makedirs(self.cfg["data_dir"], exist_ok=True)
        flag = self.flag()
        with open(flag, "w") as f:
            f.write("restart")
        tr, fc = self.make("08:00")

        def hook(c):
            if c.t >= ts(THURSDAY, "08:30"):
                self.cfg.update({"auto_stop_at": "08:20"})  # như /giobot: tự tắt để kết thúc test
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end", "file sót lại không làm bản mới thoát")
        self.assertFalse(os.path.exists(flag))


class RestartScriptTest(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, name), "rb") as f:
            return f.read()

    def test_windows_script_asks_politely_then_restarts_hidden(self):
        bat, ps = self.read("khoi_dong_lai.bat"), self.read("khoi_dong_lai.ps1")
        self.assertIn(b"khoi_dong_lai.ps1", bat)
        self.assertIn(b"\r\n", ps)
        self.assertIn(RESTART_FLAG.encode(), ps)
        self.assertIn(b"start_tracker.vbs", ps)
        self.assertIn(b"--manual", ps, "đang làm bù thì bật lại vẫn giữ --manual")
        self.assertLess(ps.index(RESTART_FLAG.encode()), ps.index(b"Stop-Process"), "xin tự tắt trước, tắt hẳn sau")
        ps.decode("ascii")  # PowerShell 5.1 đọc file không BOM theo ANSI: giữ ASCII

    def test_mac_script_uses_sigterm_first(self):
        mac = self.read("khoi_dong_lai.command").decode("utf-8")
        self.assertLess(mac.index("pkill -f 'focus_tracker.py run'"), mac.index("pkill -9"))
        self.assertIn("$MANUAL", mac)
        self.assertTrue(os.access(os.path.join(ROOT, "khoi_dong_lai.command"), os.X_OK))


if __name__ == "__main__":
    unittest.main()
