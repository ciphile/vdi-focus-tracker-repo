"""2.6.1: tắt tracker giữa ngày (End task python) rồi bật lại thì bộ đếm sao nhãng hôm nay đếm tiếp, không về 1."""
import datetime as dt
import json
import tempfile
import unittest

from focus.alerts import RealtimeAlerts
from focus.storage import db_path, get_pref, open_db
from focus.tracker import ALERT_COUNTERS_KEY
from tests.helpers import make_cfg, sample
from tests.test_tracker import FRIDAY, _Base, hms, make_tracker


class AlertCountersTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp(), nudge_level="nghiem", nudge_strict_minutes=5)
        self.t = dt.datetime(2026, 10, 19, 9, 0).timestamp()

    def run_for(self, al, minutes, **kw):
        out = []
        for _ in range(int(minutes * 12)):
            self.t += 5
            out += al.update(sample(**kw), self.t, True)
        return out

    def test_round_trip_same_day(self):
        al = RealtimeAlerts(self.cfg)
        self.run_for(al, 1)
        self.run_for(al, 6, vdi="minimized", proc="notepad.exe")   # lần 1: 6 phút, nhắc 1 lần
        self.run_for(al, 1)
        self.run_for(al, 3, vdi="minimized", proc="notepad.exe")   # lần 2 đang dở lúc "tắt"
        saved = json.loads(json.dumps(al.day_counters()))
        self.assertEqual(saved["episodes"], 2)
        self.assertEqual(saved["nudges"], 1)
        self.assertGreaterEqual(saved["lost"], 8 * 60)

        al2 = RealtimeAlerts(self.cfg)
        self.assertTrue(al2.restore_day(saved, dt.date(2026, 10, 19)))
        self.run_for(al2, 1)
        ev = self.run_for(al2, 6, vdi="minimized", proc="taskmgr.exe")
        data = [d for k, d in ev if k == "out_of_vdi"][0]
        self.assertEqual(data["today_count"], 3)           # không về 1
        self.assertEqual(data["day_nudges"], 2)
        self.assertGreaterEqual(data["today_minutes"], 13)

    def test_other_day_or_bad_data_ignored(self):
        al = RealtimeAlerts(self.cfg)
        old = {"date": "2026-10-16", "episodes": 9, "lost": 600, "nudges": 4, "light_done": True}
        self.assertFalse(al.restore_day(old, dt.date(2026, 10, 19)))
        self.assertEqual(al.today()["count"], 0)
        self.assertFalse(al.restore_day({"date": "2026-10-19", "episodes": "x"}, dt.date(2026, 10, 19)))
        self.assertFalse(al.restore_day(None, dt.date(2026, 10, 19)))
        self.assertEqual(al.today(), {"count": 0, "minutes": 0, "nudges": 0, "light_done": False})

    def test_light_level_stays_done_after_restart(self):
        al = RealtimeAlerts(self.cfg)
        saved = {"date": "2026-10-19", "episodes": 1, "lost": 900, "nudges": 1, "light_done": True}
        al.restore_day(saved, dt.date(2026, 10, 19))
        self.cfg["nudge_level"] = "nhe"
        self.run_for(al, 1)
        ev = self.run_for(al, 30, vdi="minimized", proc="chrome.exe")
        self.assertNotIn("out_of_vdi", [k for k, _ in ev])   # mức nhẹ đã nhắc hôm nay: bật lại vẫn im

    def test_no_day_yet(self):
        self.assertIsNone(RealtimeAlerts(self.cfg).day_counters())


SCRIPT = [
    ("08:30:00", "vdi"),
    ("09:05:00", "chrome"),   # 12 phút ngoài VDI: nhắc lúc 09:15 (mức nghiêm 10 phút)
    ("09:17:00", "vdi"),
    ("09:40:00", "min"),      # 12 phút VDI thu nhỏ: nhắc lúc 09:50
    ("09:52:00", "vdi"),
    ("10:05:00", "chrome"),   # sau khi bật lại: 12 phút ngoài VDI, nhắc lúc 10:15
    ("10:17:00", "vdi"),
]


class RestartTest(_Base):
    def test_counters_survive_restart(self):
        self.cfg.update(nudge_level="nghiem", nudge_strict_minutes=10, water_reminder_minutes=0,
                        break_reminder_minutes=0, auto_stop_at="10:00")
        tr, fc, *_ = make_tracker(self.cfg, FRIDAY, "08:30:00", SCRIPT)
        seen = {}

        def peek(f):  # đọc DB giữa chừng (trước khi tracker thoát): bộ đếm đã được lưu định kỳ (~25 phút/lần)
            if "mid" not in seen and f.t >= hms(FRIDAY, "09:56:00"):
                db = open_db(db_path(self.cfg))
                seen["mid"] = json.loads(get_pref(db, ALERT_COUNTERS_KEY) or "null")
                db.close()
        fc.hook = peek
        tr.run()
        self.assertEqual(seen["mid"]["episodes"], 2)   # lần lưu 09:45: lần 2 đã đủ 1 phút
        self.assertEqual(seen["mid"]["nudges"], 1)     # nhắc lần 2 lúc 09:50, sau lần lưu 09:45
        db = open_db(db_path(self.cfg))               # tracker thoát (auto_stop) thì lưu nốt
        self.assertEqual(json.loads(get_pref(db, ALERT_COUNTERS_KEY))["nudges"], 2)
        db.close()

        cfg2 = dict(self.cfg, auto_stop_at="10:30")
        tr2, *_ = make_tracker(cfg2, FRIDAY, "10:00:00", SCRIPT)
        self.assertEqual(tr2.alerts.today()["count"], 0)
        tr2.run()
        today = tr2.alerts.today()
        self.assertEqual(today["count"], 3)
        self.assertEqual(today["nudges"], 3)
        self.assertGreaterEqual(today["minutes"], 30)
        self.assertIn("Nạp lại bộ đếm sao nhãng hôm nay: 2 lần", self.log_text())

    def log_text(self):
        import glob
        import os
        out = ""
        for p in glob.glob(os.path.join(self.cfg["data_dir"], "logs", "*.log")):
            with open(p, encoding="utf-8") as f:
                out += f.read()
        return out


if __name__ == "__main__":
    unittest.main()
