"""Vòng lấy mẫu Tracker.run(): một ngày làm việc giả lập 07:00 → 18:00 với đồng hồ giả (không ngủ thật)."""
import bisect
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

try:                      # Windows không có module resource
    import resource
except ImportError:
    resource = None

from focus import holidays, logs, persona, tracker
from focus.analysis import analyze, daily_stats
from focus.storage import db_path, open_db, save_note
from focus.tracker import InstanceLock, Tracker
from tests.helpers import make_cfg, ts

FRIDAY = "2026-10-16"     # thứ Sáu, không phải ngày lễ: có cả báo cáo tuần
SATURDAY = "2026-10-17"

# Kịch bản một ngày. Mỗi đoạn kéo dài tới đầu đoạn sau. Loại:
#   vdi      VDI ở trước, toàn màn hình, đang gõ phím
#   vdi_win  VDI ở trước nhưng không toàn màn hình, đang gõ phím
#   idle_vdi VDI ở trước, ngồi yên (cầm điện thoại)
#   chrome   dùng Chrome, VDI nằm sau
#   min      VDI thu nhỏ (Windows vẫn báo cdviewer.exe là cửa sổ trước), vẫn bấm chuột
#   locked   khoá máy, không ai ở bàn
DAY_SCRIPT = [
    ("07:00:00", "locked"),
    ("07:30:00", "vdi"),       # vào sớm: chưa tới giờ làm, không cảnh báo
    ("09:05:00", "chrome"),    # 22 phút Chrome: nhắc lúc 09:15 và 09:25
    ("09:27:00", "vdi"),
    ("10:00:00", "min"),       # 11 phút VDI thu nhỏ: nhắc lúc 10:10
    ("10:11:00", "vdi"),
    ("10:30:00", "locked"),    # đi vệ sinh 20 phút: cảnh báo rời máy, rồi chào mừng quay lại
    ("10:50:00", "vdi"),
    ("11:15:00", "chrome"),    # nghỉ trưa lướt web: KHÔNG nhắc
    ("11:40:00", "locked"),
    ("12:25:00", "chrome"),
    ("12:30:00", "vdi_win"),   # 20 phút VDI không toàn màn hình: gợi ý phóng to lúc 12:45
    ("12:50:00", "vdi"),
    ("13:40:00", "chrome"),    # 5 phút ngoài VDI: không nhắc, nhưng ngắt khối tập trung
    ("13:45:00", "vdi"),
    ("14:40:00", "idle_vdi"),  # 3 lần ngồi yên 90 giây trước VDI: dấu hiệu điện thoại
    ("14:41:30", "vdi"),
    ("14:50:00", "idle_vdi"),
    ("14:51:30", "vdi"),
    ("15:00:00", "idle_vdi"),
    ("15:01:30", "vdi"),
    ("15:30:00", "chrome"),
    ("15:36:00", "vdi"),
    ("16:50:00", "chrome"),    # quá 17:00 vẫn ở Chrome: hết giờ làm, không nhắc
    ("17:30:00", "locked"),
]

# (giờ, nhãn việc gửi đi) đúng như mong đợi cho DAY_SCRIPT, với mức nhắc "nghiem" chu kỳ 10 phút (FullDayTest).
# pace_*: mốc kiểm tra tiến độ (luôn chạy; có gửi tin hay không tuỳ tiến độ, xem test_pace.py).
EXPECTED_DAY = [
    ("08:00:00", "morning"),
    ("08:00:00", "plan"),
    ("09:00:00", "break"),
    ("09:15:00", "out_of_vdi"),
    ("09:25:00", "out_of_vdi"),
    ("10:10:00", "out_of_vdi"),
    ("10:30:00", "pace_1030"),
    ("10:44:55", "away"),       # lần chạm phím cuối là 09:29:55 + 15 phút
    ("10:50:00", "back"),
    ("12:45:00", "not_fullscreen"),
    ("13:30:00", "break"),
    ("14:00:00", "pace_1400"),
    ("14:30:00", "boost"),
    ("14:45:00", "break"),
    ("15:01:35", "phone"),  # lần chạm đầu 15:01:30, mẫu sau có chạm tiếp mới tính là quay lại
    ("15:30:00", "pace_1530"),
    ("16:36:00", "break"),
    ("16:45:00", "review"),
    ("17:00:00", "summary"),
    ("17:05:00", "weekly"),  # sau tổng kết ngày: tuần có đủ số liệu và lời đánh giá thứ Sáu
]


def hms(day, s):
    h, m, sec = map(int, s.split(":"))
    return ts(day, f"{h:02d}:{m:02d}", sec)


class FakeClock:
    """Đồng hồ giả dùng chung cho clock / sleep / now. hook(t) chạy sau mỗi lần sleep."""

    def __init__(self, start):
        self.t = start
        self.slept = 0.0
        self.hook = None

    def clock(self):
        return self.t

    def sleep(self, d):
        self.slept += d
        self.t += d
        if self.hook:
            self.hook(self)

    def now(self):
        return dt.datetime.fromtimestamp(self.t)


class ScriptProbe:
    """Probe giả đọc kịch bản theo giờ của đồng hồ giả. idle = thời gian từ lần chạm phím cuối."""

    INPUT = {"vdi", "vdi_win", "chrome", "min"}

    def __init__(self, fc, day, script, fail_at=()):
        self.fc = fc
        self.starts = [hms(day, s) for s, _ in script]
        self.kinds = [k for _, k in script]
        self.last_input = None
        self.calls = []
        self.fail_at = fail_at   # hàm(t, số lần gọi) -> True thì raise

    def kind_at(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        return self.kinds[i] if i >= 0 else "locked"

    def sample(self):
        t = self.fc.t
        self.calls.append(t)
        if self.fail_at and self.fail_at(t, len(self.calls)):
            raise OSError("GetForegroundWindow lỗi giả")
        k = self.kind_at(t)
        if k in self.INPUT:
            self.last_input = t
        idle = 3600.0 if self.last_input is None else t - self.last_input
        if k in ("vdi", "vdi_win", "idle_vdi"):
            return {"idle": idle, "locked": False, "vdi_state": "foreground", "fg_proc": "cdviewer.exe",
                    "fg_title": "AZ-WIN11 - Desktop Viewer", "vdi_full": k != "vdi_win"}
        if k == "chrome":
            return {"idle": idle, "locked": False, "vdi_state": "background", "fg_proc": "chrome.exe",
                    "fg_title": "Báo Mới - Google Chrome", "vdi_full": None}
        if k == "min":
            return {"idle": idle, "locked": False, "vdi_state": "minimized", "fg_proc": "cdviewer.exe",
                    "fg_title": "AZ-WIN11 - Desktop Viewer", "vdi_full": None}
        return {"idle": idle, "locked": True, "vdi_state": "background", "fg_proc": "lockapp.exe",
                "fg_title": "", "vdi_full": None}


class FakeBot:
    """Bot Telegram giả: ghi lại mọi lời gọi tracker dùng."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._db = None
        self.sent = []      # (text, raw)
        self.calls = []     # (tên hàm, tham số)
        self.state = None
        self.stopped = 0

    @property
    def db(self):
        if self._db is None:
            self._db = open_db(db_path(self.cfg))
        return self._db

    def send(self, text, raw=False):
        self.sent.append((text, raw))

    def send_morning(self, day):
        self.calls.append(("morning", day))

    def start_convo(self, kind):
        self.calls.append(("start_convo", kind))

    def send_daily_summary(self, day):
        self.calls.append(("summary", day))

    def send_weekly(self, day):
        self.calls.append(("weekly", day))

    def send_boost(self, day):
        self.calls.append(("boost", day))

    def stop(self):
        self.stopped += 1
        if self._db is not None:
            self._db.close()


class SyncNotifier:
    """Hàng đợi giả: chạy ngay (đồng bộ) và ghi (nhãn, giờ). Không chạy dọn dẹp thật."""

    def __init__(self, fc):
        self.fc = fc
        self.jobs = []
        self.drained = 0
        self.errors = []

    def submit(self, label, fn, *args):
        self.jobs.append((label, self.fc.t))
        if label != "housekeeping":
            try:
                fn(*args)
            except Exception as e:  # giống Notifier thật: lỗi việc nền không lan ra vòng lấy mẫu
                self.errors.append((label, e))

    def drain(self, timeout=30):
        self.drained += 1
        return True


def make_tracker(cfg, day, start, script, bot=True, **kw):
    fc = FakeClock(hms(day, start))
    probe = ScriptProbe(fc, day, script, kw.pop("fail_at", ()))
    b = FakeBot(cfg) if bot else None
    notifier = SyncNotifier(fc)
    tr = Tracker(cfg, probe, b, fc.clock, fc.sleep, fc.now, notifier=notifier,
                 run_housekeeping=kw.pop("run_housekeeping", False), manual=kw.pop("manual", False))
    return tr, fc, probe, b, notifier


def labels(notifier, day, kinds=None):
    out = []
    for label, t in notifier.jobs:
        if kinds is None or label in kinds:
            out.append((dt.datetime.fromtimestamp(t).strftime("%H:%M:%S"), label))
    return out


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="focus-tracker-")
        self.cfg = make_cfg(self.tmp, ai_provider="off", auto_stop_at="18:00")
        logs.reset()
        logs.setup(self.cfg["data_dir"], console=False)
        holidays.clear_memo()
        p = mock.patch.object(holidays, "next_year_missing", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        logs.reset()
        holidays.clear_memo()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def audit_text(self):
        path = os.path.join(self.cfg["data_dir"], "audit.log")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def samples(self, day=FRIDAY):
        db = open_db(db_path(self.cfg))
        try:
            return db.execute("SELECT ts,dur,vdi_state FROM samples ORDER BY ts").fetchall()
        finally:
            db.close()


class FullDayTest(_Base):
    """Cả ngày thứ Sáu theo DAY_SCRIPT, chạy một lần rồi kiểm tra nhiều mặt."""

    def setUp(self):
        super().setUp()
        # nhắc uống nước tắt ở đây (kiểm tra riêng trong tests/test_health.py) để giữ nguyên EXPECTED_DAY
        self.cfg.update(nudge_level="nghiem", nudge_strict_minutes=10, water_reminder_minutes=0,
                        phone_pattern_count=3)  # kịch bản ngày viết với 3 lần (mặc định 5)
        self.tr, self.fc, self.probe, self.bot, self.nt = make_tracker(self.cfg, FRIDAY, "07:00:00", DAY_SCRIPT)
        self.result = self.tr.run()

    def test_returns_window_end_at_auto_stop(self):
        self.assertEqual(self.result, "window_end")
        self.assertEqual(self.fc.now().strftime("%H:%M:%S"), "18:00:00")
        self.assertIn("AUTO_STOP", self.audit_text())

    def test_exact_alerts_and_jobs_of_the_day(self):
        """Đúng loại, đúng giờ, không thừa không thiếu: nghỉ trưa và sau 17:00 không có cảnh báo."""
        self.assertEqual(labels(self.nt, FRIDAY), EXPECTED_DAY)

    def test_no_alert_outside_work_hours_or_lunch(self):
        alert_kinds = {"out_of_vdi", "away", "back", "break", "phone", "not_fullscreen"}
        for hhmmss, label in labels(self.nt, FRIDAY, alert_kinds):
            self.assertTrue("08:00:00" <= hhmmss < "17:00:00", (hhmmss, label))
            self.assertFalse("11:15:00" <= hhmmss < "12:30:00", (hhmmss, label))

    def test_each_job_fires_once(self):
        jobs = [lb for _, lb in labels(self.nt, FRIDAY, {"plan", "review", "summary", "weekly", "boost"})]
        self.assertEqual(sorted(jobs), sorted(["plan", "review", "summary", "weekly", "boost"]))
        self.assertEqual(self.nt.errors, [])
        self.assertEqual(self.bot.calls, [("morning", FRIDAY), ("start_convo", "plan"), ("boost", FRIDAY), ("start_convo", "review"),
                                          ("summary", FRIDAY), ("weekly", FRIDAY)])
        for job in ("PLAN", "REVIEW", "SUMMARY", "WEEKLY", "BOOST"):
            self.assertEqual(self.audit_text().count("JOB_" + job), 1, job)

    def test_messages_sent(self):
        texts = [t for t, _ in self.bot.sent]
        outs = [t for t in texts if "phút làm việc ngoài VDI" in t]
        self.assertEqual(len(outs), 3)
        self.assertIn("10 phút", outs[0])
        self.assertIn("20 phút", outs[1])
        self.assertIn("VDI đang thu nhỏ", outs[2], "VDI thu nhỏ phải bị coi là ngoài VDI")
        # lần nhắc thứ 2 kèm một câu khích lệ (gửi raw)
        self.assertEqual(sum(1 for _, raw in self.bot.sent if raw), 1)
        away = [t for t in texts if "rời máy 15 phút" in t]
        self.assertEqual(len(away), 1)
        self.assertIn("Máy đang khoá.", away[0])
        self.assertIn("từ 10:29", away[0])
        backs = [x.format(u="bạn", U="Bạn", me="mình", Me="Mình", boss="", m=20)
                 for t in persona.LEADS["back"].values() for x in t]
        self.assertTrue(any(t in backs for t in texts))           # tin quay lại (câu theo giọng, có 20 phút)
        self.assertEqual(sum("tập trung liên tục" in t for t in texts), 4)
        self.assertEqual(sum("📱" in t for t in texts), 1)
        self.assertEqual(sum("🖥️" in t for t in texts), 1)

    def test_minimized_alert_reports_minimized_state(self):
        line = [ln for ln in self.audit_text().splitlines() if "ALERT_OUT_OF_VDI" in ln]
        self.assertEqual(len(line), 3)
        self.assertIn("minimized", line[2])

    def test_samples_flushed_including_last_partial_batch(self):
        rows = self.samples()
        # 07:00:05 … 17:59:55; mẫu lúc 18:00:00 không ghi vì đã hết khung chạy
        self.assertEqual(len(rows), 11 * 720 - 1)
        self.assertEqual(len(rows) % 12, 11, "lô cuối chưa đủ 12 mẫu phải được ghi ở finally")
        self.assertTrue(all(abs(r[1] - 5) < 1e-6 for r in rows))
        self.assertEqual(self.nt.drained, 1)
        self.assertEqual(self.bot.stopped, 1)
        self.assertIs(self.bot.state, self.tr.state)

    def test_analysis_minimized_counts_as_not_focused(self):
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        a = analyze(db, self.cfg, FRIDAY)
        self.assertAlmostEqual(a["minimized"], 11 * 60, delta=1)
        # Chỉ đo sao nhãng trong giờ làm (08:00–11:15, 12:30–17:00): Chrome 22+5+6 phút + 16:50–17:00 10 phút
        # + 11 phút thu nhỏ; Chrome lúc trưa và sau 17:00 không tính. (±10 giây: mẫu 5 giây nằm vắt qua mốc giờ)
        self.assertAlmostEqual(a["other"], (22 + 5 + 6 + 10 + 11) * 60, delta=12)
        self.assertAlmostEqual(a["background"], (22 + 5 + 6 + 10) * 60, delta=12)
        # VDI ở trước trong giờ làm: 65 (08:00–09:05)+33+19+25+70+105+74 phút, trừ 3 lần ngồi yên 90 giây
        self.assertAlmostEqual(a["vdi"], (65 + 33 + 19 + 25 + 70 + 105 + 74) * 60 - 3 * 90, delta=12)
        # Làm trong VDI trước 08:00 (07:30) là làm ngoài giờ: chỉ cộng giờ làm, vẫn nằm trong khối tập trung
        self.assertAlmostEqual(a["ot"], 30 * 60, delta=12)
        self.assertAlmostEqual(a["deep_ot"], 30 * 60, delta=12)
        # Rời máy 20 phút lúc 10:30; khoá máy lúc trưa / sau 17:30 không tính
        self.assertAlmostEqual(a["away"], 20 * 60, delta=1)
        self.assertEqual(a["short_idle_count"], 3)
        self.assertEqual(a["minimize_count"], 1)
        self.assertEqual(a["inactive_10m_count"], 1)
        # Giờ 10: thu nhỏ 11 phút + rời máy 20 phút không tính vào VDI
        self.assertAlmostEqual(a["hourly"][10]["vdi"], (19 + 10) * 60, delta=6)
        self.assertAlmostEqual(a["hourly"][10]["other"], 11 * 60, delta=6)
        stored = json.loads(db.execute("SELECT data FROM daily_stats WHERE day=?", (FRIDAY,)).fetchone()[0])
        self.assertAlmostEqual(stored["minimized"], 660, delta=1)


class RunResultTest(_Base):
    def test_outside_window(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "06:30:00", DAY_SCRIPT)
        self.assertEqual(tr.run(), "outside_window")
        self.assertEqual(probe.calls, [])
        self.assertFalse(os.path.exists(db_path(self.cfg)), "chưa tới giờ thì không mở DB")
        bot.stop()

    def test_off_day_weekend(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, SATURDAY, "08:00:00", DAY_SCRIPT)
        self.assertEqual(tr.run(), "off_day")
        self.assertEqual(probe.calls, [])
        self.assertEqual(nt.jobs, [])
        bot.stop()

    def test_off_day_by_note(self):
        db = open_db(db_path(self.cfg))
        save_note(db, FRIDAY, {"day_off": "nghỉ phép"})
        db.close()
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "08:00:00", DAY_SCRIPT)
        self.assertEqual(tr.run(), "off_day")
        bot.stop()

    def test_off_day_still_runs_when_configured(self):
        self.cfg["run_on_off_days"] = True
        self.cfg["auto_stop_at"] = "08:10"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, SATURDAY, "08:00:00", [("08:00:00", "chrome")])
        self.assertEqual(tr.run(), "window_end")
        self.assertEqual(len(probe.calls), 119)  # 08:00:05 … 08:09:55
        self.assertEqual(nt.jobs, [], "ngày nghỉ: ghi số liệu nhưng không cảnh báo, không hỏi gì")

    def test_day_change_stops_at_window_end(self):
        self.cfg["auto_start_at"] = "00:00"
        self.cfg["auto_stop_at"] = "23:59"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, "2026-10-15", "23:58:00", [("00:00:00", "locked")])
        self.assertEqual(tr.run(), "window_end")
        self.assertLess(fc.t, hms("2026-10-16", "00:00:05"))

    def test_midnight_inside_window_continues_with_new_day(self):
        """Khung chạy qua nửa đêm: chốt ngày cũ, theo dõi tiếp ngày mới trong cùng tiến trình."""
        self.cfg["auto_start_at"] = "00:00"
        self.cfg["auto_stop_at"] = "23:59"
        thu, fri = "2026-10-15", FRIDAY
        tr, fc, probe, bot, nt = make_tracker(self.cfg, thu, "23:57:00", [("00:00:00", "vdi")])
        # Khung chạy giả 23:57 -> 00:05 hôm sau (qua nửa đêm).
        with mock.patch.object(tracker, "in_run_window", lambda cfg, hhmm: hhmm >= "23:57" or hhmm < "00:05"):
            self.assertEqual(tr.run(), "window_end")
        self.assertEqual(tr.day, fri)
        self.assertEqual(fc.now().strftime("%Y-%m-%d %H:%M"), f"{fri} 00:05")
        self.assertIn("NEW_DAY", self.audit_text())
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        for day in (thu, fri):
            self.assertIsNotNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (day,)).fetchone(), day)
        rows = self.samples()
        self.assertTrue(any(r[0] > hms(fri, "00:04:00") for r in rows))
        self.assertTrue(all(abs(r[1] - 5) < 1e-6 for r in rows))

    def test_overnight_sleep_wake_next_morning(self):
        """Máy ngủ từ 17:00 thứ Năm tới 08:00 thứ Sáu, vẫn trong khung giờ: không thoát, làm tiếp ngày thứ Sáu."""
        thu = "2026-10-15"
        script = [("07:00:00", "vdi")]
        tr, fc, probe, bot, nt = make_tracker(self.cfg, thu, "16:58:00", script)
        probe.starts = [hms(thu, "07:00:00")]
        sleep_at, wake_at = hms(thu, "17:00:00"), hms(FRIDAY, "08:00:00")
        st = {"slept": False}

        def hook(c):
            if not st["slept"] and c.t >= sleep_at:
                st["slept"] = True
                c.t = wake_at
            if c.t >= hms(FRIDAY, "08:20:00"):
                self.cfg["auto_stop_at"] = "08:20"
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end")
        self.assertEqual(tr.day, FRIDAY)
        self.assertEqual(tr.week_id, "2026-W42")
        text = self.audit_text()
        self.assertIn("WAKE", text)
        self.assertIn("NEW_DAY", text)
        self.assertIn(("morning", FRIDAY), bot.calls)
        self.assertIn(("start_convo", "plan"), bot.calls)
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertIsNotNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (thu,)).fetchone())
        fri_rows = [r for r in self.samples() if r[0] >= hms(FRIDAY, "00:00:00")]
        self.assertTrue(fri_rows)
        self.assertLessEqual(max(r[1] for r in fri_rows), 5, "quãng ngủ qua đêm không bị tính vào ngày mới")

    def test_midnight_into_off_day_stops(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "16:58:00", [("07:00:00", "chrome")])
        probe.starts = [hms(FRIDAY, "07:00:00")]
        st = {"slept": False}

        def hook(c):
            if not st["slept"] and c.t >= hms(FRIDAY, "17:00:00"):
                st["slept"] = True
                c.t = hms(SATURDAY, "09:00:00")
        fc.hook = hook
        self.assertEqual(tr.run(), "off_day")
        self.assertEqual(tr.day, FRIDAY)
        self.assertFalse([r for r in self.samples() if r[0] >= hms(SATURDAY, "00:00:00")])
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertIsNotNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (FRIDAY,)).fetchone())
        self.assertIsNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (SATURDAY,)).fetchone())

    def test_without_bot(self):
        self.cfg["auto_stop_at"] = "09:20"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "chrome")], bot=False)
        self.assertEqual(tr.run(), "window_end")
        self.assertEqual(nt.jobs, [])
        self.assertIn("ALERT_OUT_OF_VDI", self.audit_text())


class PauseWakeTest(_Base):
    def test_pause_stops_sampling_and_alerts(self):
        """/pause 09:02–09:20: không đọc máy, không nhắc; tiếp tục thì đồng hồ ngoài VDI tính lại từ đầu."""
        self.cfg["auto_stop_at"] = "09:40"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "08:55:00", [("08:55:00", "vdi"),
                                                                          ("09:00:00", "chrome")],
                                              run_housekeeping=True)
        p0, p1 = hms(FRIDAY, "09:02:00"), hms(FRIDAY, "09:20:00")

        def hook(c):
            if p0 <= c.t < p1:
                tr.state["paused"].set()
            else:
                tr.state["paused"].clear()
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end")
        self.assertEqual(nt.jobs[0][0], "housekeeping")
        self.assertFalse([t for t in probe.calls if p0 <= t < p1], "tạm dừng thì không đọc trạng thái máy")
        self.assertEqual(labels(nt, FRIDAY, {"out_of_vdi"}), [("09:35:00", "out_of_vdi")])  # mức vừa: 15 phút
        rows = self.samples()
        self.assertFalse([r for r in rows if p0 <= r[0] < p1])
        after = [r for r in rows if r[0] >= p1][0]
        self.assertEqual(after[1], 5, "quãng tạm dừng không bị gộp vào mẫu đầu tiên sau đó")

    def test_wake_from_sleep_resets_alerts(self):
        """Máy ngủ 30 phút giữa lúc đang ở Chrome: không nhắc ngay khi thức dậy, tính lại 15 phút (mức vừa)."""
        self.cfg["auto_stop_at"] = "09:55"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "chrome")])
        jump_at = hms(FRIDAY, "09:05:00")
        state = {"done": False}

        def hook(c):
            if not state["done"] and c.t >= jump_at:
                state["done"] = True
                c.t += 30 * 60
        fc.hook = hook
        self.assertEqual(tr.run(), "window_end")
        outs = [t for lb, t in nt.jobs if lb == "out_of_vdi"]
        self.assertEqual(len(outs), 1)
        self.assertAlmostEqual(outs[0], hms(FRIDAY, "09:50:00"), delta=5)
        self.assertIn("WAKE", self.audit_text())
        self.assertTrue(any(r[1] > 1800 for r in self.samples()), "quãng ngủ ghi thành một mẫu dài (rời máy)")


class MonotonicTest(_Base):
    def test_wall_clock_jump_back_does_not_stall_or_wake(self):
        """Giờ hệ thống bị chỉnh lùi 1 giờ (đồng bộ giờ): nhịp lấy mẫu theo đồng hồ đơn điệu vẫn đều."""
        self.cfg["auto_stop_at"] = "09:30"
        fc = FakeClock(hms(FRIDAY, "09:00:00"))
        mono = {"t": 5000.0}

        def sleep(d):
            fc.t += d
            mono["t"] += d
            if not st["jumped"] and fc.t >= hms(FRIDAY, "09:10:00"):
                st["jumped"] = True
                fc.t -= 600   # chỉnh giờ lùi 10 phút
        st = {"jumped": False}
        probe = ScriptProbe(fc, FRIDAY, [("08:00:00", "vdi")])
        tr = Tracker(self.cfg, probe, None, fc.clock, sleep, fc.now, notifier=SyncNotifier(fc),
                     run_housekeeping=False, mono=lambda: mono["t"])
        self.assertEqual(tr.run(), "window_end")
        self.assertNotIn("WAKE", self.audit_text())
        self.assertEqual(len(probe.calls), 30 * 12 + 120 - 1)
        self.assertTrue(all(abs(r[1] - 5) < 1e-6 for r in self.samples()))

    def test_mac_sleep_detected_by_wall_clock(self):
        """macOS: đồng hồ đơn điệu đứng yên khi máy ngủ; giờ thật nhảy 30 phút vẫn phải nhận ra là vừa ngủ dậy."""
        self.cfg["auto_stop_at"] = "09:50"
        fc = FakeClock(hms(FRIDAY, "09:00:00"))
        mono = {"t": 5000.0}
        st = {"done": False}

        def sleep(d):
            fc.t += d
            mono["t"] += d
            if not st["done"] and fc.t >= hms(FRIDAY, "09:05:00"):
                st["done"] = True
                fc.t += 30 * 60
        probe = ScriptProbe(fc, FRIDAY, [("09:00:00", "chrome")])
        tr = Tracker(self.cfg, probe, None, fc.clock, sleep, fc.now, notifier=SyncNotifier(fc),
                     run_housekeeping=False, mono=lambda: mono["t"])
        self.assertEqual(tr.run(), "window_end")
        self.assertIn("WAKE", self.audit_text())
        self.assertTrue(any(r[1] > 1800 for r in self.samples()))


class StateAndBotTest(_Base):
    def test_probe_platform_and_warnings_in_state(self):
        self.cfg["auto_stop_at"] = "09:01"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "vdi")])
        probe.platform_name = "macOS"
        probe.method = "CoreGraphics"
        probe.warnings = ["cần quyền Screen Recording"]
        tr.run()
        self.assertEqual(tr.state["platform"], "macOS: CoreGraphics")
        self.assertIs(tr.state["probe_warnings"], probe.warnings)
        self.assertIs(bot.state, tr.state)

    def test_state_keys_exist_without_metadata(self):
        tr, *_ = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "vdi")])
        self.assertEqual(tr.state["platform"], "")
        self.assertEqual(tr.state["probe_warnings"], [])

    def test_catch_up_called_once_at_start(self):
        self.cfg["auto_stop_at"] = "09:02"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "vdi")])
        bot.catch_up = lambda day: bot.calls.append(("catch_up", day))
        tr.run()
        self.assertEqual([c for c in bot.calls if c[0] == "catch_up"], [("catch_up", FRIDAY)])
        self.assertEqual([lb for lb, _ in nt.jobs].count("catchup"), 1)

    def test_persona_read_live(self):
        tr, *_ = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "vdi")])
        new = dict(self.cfg["persona"], name="Sếp mới")
        self.cfg["persona"] = new
        self.assertIs(tr.persona, new)


class ErrorTest(_Base):
    def test_db_write_errors_do_not_stop_sampling(self):
        """DB bị khoá / ổ đầy một lúc: vẫn lấy mẫu, giữ mẫu trong RAM, ghi bù khi DB dùng lại được."""
        import sqlite3
        from focus.storage import SampleWriter
        self.cfg["auto_stop_at"] = "09:30"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "vdi")])
        real_flush = SampleWriter.flush
        bad = (hms(FRIDAY, "09:05:00"), hms(FRIDAY, "09:20:00"))

        def flush(w):
            if bad[0] <= fc.t < bad[1]:
                raise sqlite3.OperationalError("database is locked")
            return real_flush(w)
        with mock.patch.object(SampleWriter, "flush", flush), mock.patch.object(tracker, "MAX_PENDING_ROWS", 100):
            self.assertEqual(tr.run(), "window_end")
        self.assertEqual(len(probe.calls), 30 * 12 - 1)
        rows = self.samples()
        # 15 phút lỗi = 180 mẫu (+ tối đa 11 mẫu chờ từ trước), chỉ giữ 100 mẫu mới nhất
        lost = len(probe.calls) - len(rows)
        self.assertTrue(80 <= lost <= 91, lost)
        self.assertEqual(sum(1 for r in rows if bad[1] - 100 * 5 <= r[0] < bad[1]), 100)
        self.assertTrue(any(r[0] > hms(FRIDAY, "09:29:00") for r in rows))


    def test_probe_errors_tolerated(self):
        self.cfg["auto_stop_at"] = "09:10"
        fail = lambda t, n: 3 <= n <= 5
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "09:00:00", [("09:00:00", "vdi")], fail_at=fail)
        self.assertEqual(tr.run(), "window_end")
        rows = self.samples()
        self.assertEqual(len(rows), len(probe.calls) - 3)
        self.assertTrue(all(abs(r[1] - 5) < 1e-6 for r in rows))

    def test_gives_up_after_max_errors_and_flushes(self):
        """Đọc lỗi liên tục MAX_CONSECUTIVE_ERRORS lần thì raise; mẫu còn trong RAM vẫn được ghi, hàng đợi được xả."""
        fail = lambda t, n: n > 7
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "08:00:00", [("08:00:00", "vdi")], fail_at=fail)
        with self.assertRaises(OSError):
            tr.run()
        self.assertEqual(len(probe.calls), 7 + tracker.MAX_CONSECUTIVE_ERRORS)
        self.assertEqual(len(self.samples()), 7)
        self.assertEqual(nt.drained, 1)
        self.assertEqual(bot.stopped, 1)
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertIsNotNone(db.execute("SELECT 1 FROM daily_stats WHERE day=?", (FRIDAY,)).fetchone())


class PerformanceTest(_Base):
    def test_loop_cost_over_simulated_day(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "07:00:00", DAY_SCRIPT)
        cpu0, wall0 = time.process_time(), time.perf_counter()
        self.assertEqual(tr.run(), "window_end")
        wall = time.perf_counter() - wall0
        cpu = time.process_time() - cpu0
        ticks = len(probe.calls)
        ms = wall / ticks * 1000
        cpu_pct = (cpu / ticks) / self.cfg["sample_seconds"] * 100   # % của 1 nhân khi chạy thật mỗi 5 giây
        if resource is not None:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_mb = rss / 1e6 if sys.platform == "darwin" else rss / 1024
        else:
            rss_mb = 0.0
        print(f"\n[perf] {ticks} vòng: {ms:.3f} ms/vòng, CPU tương đương {cpu_pct:.4f}% (1 nhân), "
              f"RSS đỉnh {rss_mb:.1f} MB", file=sys.stderr)
        self.assertLess(ms, 2.0)


class InstanceLockTest(unittest.TestCase):
    def setUp(self):
        import socket
        with socket.socket() as so:
            so.bind(("127.0.0.1", 0))
            self.port = so.getsockname()[1]

    @unittest.skipIf(sys.platform == "win32", "Windows dùng mutex")
    def test_second_instance_waits_then_gives_up(self):
        a = InstanceLock(port=self.port)
        self.assertTrue(a.acquire(wait=0))
        self.addCleanup(a.release)
        t = {"now": 0.0}
        sleeps = []

        def sleep(d):
            sleeps.append(d)
            t["now"] += d
        b = InstanceLock(port=self.port)
        self.assertFalse(b.acquire(wait=120, sleep=sleep, clock=lambda: t["now"]))
        self.assertAlmostEqual(sum(sleeps), 120)

    @unittest.skipIf(sys.platform == "win32", "Windows dùng mutex")
    def test_second_instance_gets_lock_when_first_exits(self):
        a = InstanceLock(port=self.port)
        self.assertTrue(a.acquire(wait=0))
        t = {"now": 0.0}

        def sleep(d):
            t["now"] += d
            if t["now"] >= 10:
                a.release()   # bản cũ thoát sau 10 giây
        b = InstanceLock(port=self.port)
        self.assertTrue(b.acquire(wait=120, sleep=sleep, clock=lambda: t["now"]))
        self.addCleanup(b.release)
        self.assertLess(t["now"], 15)


if __name__ == "__main__":
    unittest.main()


class ManualOffDayOvertimeTest(_Base):
    """Yêu cầu 16/10: làm bù thứ 7 / CN (tự bật bot): chỉ ghi giờ làm trong VDI có gõ phím / chuột, không ghi sao nhãng,
    ngồi yên, thu nhỏ; không nhắc gì. Lịch tự bật (không --manual) thì ngày nghỉ vẫn không chạy."""

    SCRIPT = [("08:00:00", "locked"), ("09:00:00", "vdi"), ("09:40:00", "chrome"), ("09:50:00", "min"),
              ("10:00:00", "idle_vdi"), ("10:03:00", "vdi"), ("10:30:00", "locked")]

    def test_saturday_manual_records_only_vdi_work(self):
        self.cfg["auto_stop_at"] = "11:00"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, SATURDAY, "08:00:00", self.SCRIPT, manual=True)
        self.assertEqual(tr.run(), "window_end")
        self.assertGreater(len(probe.calls), 0)
        self.assertEqual(nt.jobs, [], "ngày nghỉ: không nhắc, không hỏi gì")
        texts = [t for t, _ in bot.sent]
        self.assertEqual(sum("làm bù" in t for t in texts), 1, texts)
        db = open_db(db_path(self.cfg))
        a = analyze(db, self.cfg, SATURDAY)
        self.assertEqual(a["off"], "cuối tuần")
        self.assertAlmostEqual(a["ot"], 67 * 60, delta=30)  # 09:00–09:40 + 10:03–10:30
        for k in ("vdi", "other", "idle", "away", "minimized"):
            self.assertEqual(a[k], 0, k)
        for k in ("exits", "short_idle_count", "minimize_count", "away_count", "inactive_10m_count"):
            self.assertEqual(a[k], 0, k)
        self.assertAlmostEqual(a["deep"], 67 * 60, delta=30)
        rec = daily_stats(db, self.cfg, SATURDAY)
        self.assertEqual(rec["off"], "cuối tuần")
        self.assertNotIn("total", rec, "ngày nghỉ không chấm điểm")
        db.close()

    def test_saturday_scheduled_start_still_off(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, SATURDAY, "08:00:00", self.SCRIPT)
        self.assertEqual(tr.run(), "off_day")
        self.assertEqual(probe.calls, [])

    def test_manual_early_start_runs_before_auto_start(self):
        self.cfg["auto_stop_at"] = "07:00"
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "06:30:00", [("06:30:00", "vdi")], manual=True)
        self.assertEqual(tr.run(), "window_end")
        self.assertGreater(len(probe.calls), 300)
        db = open_db(db_path(self.cfg))
        a = analyze(db, self.cfg, FRIDAY)
        self.assertAlmostEqual(a["ot"], 30 * 60, delta=30)
        self.assertEqual(a["vdi"], 0, "trước giờ làm là làm bù")
        db.close()
