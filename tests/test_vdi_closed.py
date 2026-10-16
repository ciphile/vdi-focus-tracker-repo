"""Cửa sổ VDI biến mất trong giờ làm (Citrix tự ngắt sau 10–20 phút không dùng): báo ngay 1 lần, ghi vào số liệu ngày."""
import datetime as dt
import tempfile
import unittest

from focus import analysis, messages
from focus.alerts import VDI_CLOSED_GRACE, RealtimeAlerts
from focus.storage import db_path, open_db
from tests.helpers import TempCase, insert_run, make_cfg, sample, ts

DAY = "2026-10-13"


class VdiClosedAlertTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp(), nudge_level="off")
        self.al = RealtimeAlerts(self.cfg)
        self.t = ts(DAY, "09:00")
        self.events = []

    def run_for(self, minutes, work=True, idle_grow=False, **kw):
        out = []
        for i in range(int(minutes * 12)):
            self.t += 5
            s = sample(**kw)
            if idle_grow:
                s["idle"] = (i + 1) * 5 + kw.get("idle", 0)
            out += [(k, d) for k, d in self.al.update(s, self.t, work)]
        self.events += out
        return out

    def closed(self, evs=None):
        return [d for k, d in (self.events if evs is None else evs) if k == "vdi_closed"]

    def test_vdi_times_out_while_away(self):
        """Làm trong VDI, bỏ đi 20 phút (VDI ở trước, ngồi yên), Citrix tự ngắt: cửa sổ mất -> báo 1 lần."""
        self.run_for(10)
        last = self.t
        self.run_for(18, idle_grow=True)
        self.assertEqual(self.closed(), [], "cửa sổ còn: chưa báo VDI đóng")
        gone_at = self.t
        evs = self.run_for(VDI_CLOSED_GRACE / 60 + 0.2, vdi="absent", idle_grow=True, idle=18 * 60, proc="explorer.exe")
        c = self.closed(evs)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["since"], gone_at, "tính từ lần cuối còn thấy cửa sổ")
        self.assertAlmostEqual(c[0]["last_input"], last, delta=5)
        self.assertGreaterEqual(c[0]["minutes"], 19)
        self.assertEqual(self.closed(self.run_for(30, vdi="absent", proc="explorer.exe")), [], "không báo lặp")
        msg = messages.vdi_closed(c[0])
        self.assertIn("Cửa sổ VDI đã đóng từ", msg)
        self.assertIn("Lần cuối bạn làm trong VDI lúc", msg)

    def test_short_blink_ignored(self):
        """Cửa sổ mất vài giây (đang kết nối lại / đổi toàn màn hình) thì không báo."""
        self.run_for(5)
        self.run_for(0.5, vdi="absent", proc="explorer.exe")
        self.run_for(5)
        self.assertEqual(self.closed(), [])

    def test_morning_before_opening_vdi_is_not_closed(self):
        self.run_for(30, vdi="absent", proc="explorer.exe")
        self.assertEqual(self.closed(), [], "chưa mở VDI lần nào hôm nay")

    def test_vdi_opened_early_never_used_then_timeout_no_alert(self):
        """Log thật 16/10: mở VDI 07:45 chưa làm, tracker bật 08:00 thấy VDI ở trước nhưng ngồi yên, 08:02 Citrix tự
        ngắt (chrome ở trước), 08:06 mở lại. Chưa làm trong VDI lần nào hôm nay: không báo "VDI đã đóng"."""
        self.t = ts(DAY, "08:00")
        self.run_for(2, idle_grow=True, idle=15 * 60)
        self.run_for(4, vdi="absent", proc="chrome.exe")
        self.run_for(1, vdi="minimized", proc="telegram.exe")
        self.assertEqual(self.closed(), [])

    def test_alert_after_first_real_vdi_use(self):
        self.t = ts(DAY, "08:00")
        self.run_for(2, idle_grow=True, idle=15 * 60)
        self.run_for(10)  # bắt đầu làm trong VDI
        self.run_for(2, vdi="absent", proc="chrome.exe")
        self.assertEqual(len(self.closed()), 1)
        self.assertIsNotNone(self.closed()[0]["last_input"])

    def test_reopen_then_close_again_alerts_again(self):
        self.run_for(5)
        self.run_for(3, vdi="absent", proc="explorer.exe")
        self.run_for(5)
        self.run_for(3, vdi="absent", proc="explorer.exe")
        self.assertEqual(len(self.closed()), 2)

    def test_lunch_closure_reported_when_work_resumes(self):
        """Mất lúc nghỉ trưa: không báo trong giờ trưa, vào giờ làm lại mà VDI vẫn mất thì báo."""
        self.run_for(5)
        self.assertEqual(self.closed(self.run_for(40, work=False, vdi="absent", proc="explorer.exe")), [])
        self.assertEqual(len(self.closed(self.run_for(1, vdi="absent", proc="explorer.exe"))), 1)

    def test_after_hours_never_alerts(self):
        self.run_for(5)
        self.assertEqual(self.closed(self.run_for(60, work=False, vdi="absent", proc="explorer.exe")), [])

    def test_toggle_off(self):
        self.cfg["vdi_closed_alert"] = False
        self.run_for(5)
        self.run_for(5, vdi="absent", proc="explorer.exe")
        self.assertEqual(self.closed(), [])

    def test_new_day_starts_clean(self):
        self.run_for(5)
        self.t = ts("2026-10-14", "08:00")
        self.assertEqual(self.closed(self.run_for(20, vdi="absent", proc="explorer.exe")), [],
                         "VDI đóng từ hôm qua: sáng nay chưa mở thì không phải VDI đóng")


class VdiClosedAnalysisTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))

    def test_closed_window_in_day_facts_and_summary(self):
        insert_run(self.db, DAY, "09:00", 60)
        insert_run(self.db, DAY, "10:00", 30, vdi="absent", proc="explorer.exe", idle_grow=True)
        insert_run(self.db, DAY, "10:30", 30)
        insert_run(self.db, DAY, "11:30", 50, vdi="absent", proc="explorer.exe")  # trưa: không tính
        a = analysis.analyze(self.db, self.cfg, DAY)
        self.assertEqual([(analysis.fmt_t(x), analysis.fmt_t(y)) for x, y in a["vdi_closed"]], [("10:00", "10:30")])
        facts = analysis.day_facts(self.db, self.cfg, DAY)
        self.assertEqual(facts["vdi_closed"], ["10:00–10:30"])
        self.assertEqual(a["vdi"], 90 * 60, "lúc VDI đóng không tính giờ làm")

    def test_closure_before_first_vdi_use_not_counted(self):
        insert_run(self.db, DAY, "08:00", 2, idle=15 * 60)
        insert_run(self.db, DAY, "08:02", 4, vdi="absent", proc="chrome.exe")
        insert_run(self.db, DAY, "08:06", 60)
        insert_run(self.db, DAY, "09:06", 10, vdi="absent", proc="chrome.exe")
        insert_run(self.db, DAY, "09:16", 10)
        a = analysis.analyze(self.db, self.cfg, DAY)
        self.assertEqual([(analysis.fmt_t(x), analysis.fmt_t(y)) for x, y in a["vdi_closed"]], [("09:06", "09:16")])

    def test_no_closure(self):
        insert_run(self.db, DAY, "09:00", 60)
        self.assertEqual(analysis.analyze(self.db, self.cfg, DAY)["vdi_closed"], [])
        self.assertEqual(analysis.day_facts(self.db, self.cfg, DAY)["vdi_closed"], [])


class VdiClosedForgetTest(unittest.TestCase):
    def test_sleep_pause_leave_forget_window(self):
        cfg = make_cfg(tempfile.mkdtemp(), nudge_level="off")
        al = RealtimeAlerts(cfg)
        t = ts(DAY, "09:00")
        for _ in range(60):
            t += 5
            al.update(sample(), t, True)
        al.reset(forget_vdi=True)  # máy thức dậy sau khi gập: VDI mất là bình thường
        evs = []
        for _ in range(240):
            t += 5
            evs += al.update(sample("absent", proc="explorer.exe"), t, True)
        self.assertNotIn("vdi_closed", [k for k, _ in evs])


class VdiAppNotOutsideTest(TempCase):
    def test_minimized_viewer_in_front_not_listed_as_outside_app(self):
        """Báo cáo 15/10: «citrix.desktopviewer.app.exe 7m» nằm trong bảng app ngoài VDI. Bấm thu nhỏ VDI mà chưa bấm
        app khác thì Windows vẫn giữ cửa sổ VDI (đã thu nhỏ) là cửa sổ đang chọn: vẫn là VDI thu nhỏ (không tập
        trung) nhưng không phải app ngoài VDI."""
        db = open_db(db_path(self.cfg))
        insert_run(db, DAY, "09:00", 30)
        insert_run(db, DAY, "09:30", 7, vdi="minimized", proc="citrix.desktopviewer.app.exe")
        insert_run(db, DAY, "09:37", 3, vdi="minimized", proc="chrome.exe")
        insert_run(db, DAY, "09:40", 20)
        a = analysis.analyze(db, self.cfg, DAY)
        self.assertEqual([p for p, _ in a["apps"]], ["chrome.exe"])
        self.assertAlmostEqual(a["minimized"], 10 * 60, delta=1)
        self.assertAlmostEqual(a["other"], 10 * 60, delta=1)
