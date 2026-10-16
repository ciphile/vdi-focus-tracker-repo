"""Kiểm tra lần 2 (audit round 2): 7 lỗi đã sửa.

1. Windows tái sử dụng pid: cửa sổ MỚI mang pid cũ không được dùng tên process đã nhớ.
2. /pause không kéo sang ngày mới (máy ngủ qua đêm); đang tạm dừng vẫn gửi tổng kết / hỏi tổng kết / báo cáo tuần.
3. Lịch lễ từ file timesheet: chỉ đọc trường ngày thật; thứ Hai nghỉ bù đã liệt kê sẵn không bị dời sang thứ Ba.
4. cai_tu_khoi_dong.ps1: gọi Python với -X utf8 (đường dẫn có dấu), vẫn ASCII + CRLF.
5. Gợi ý toàn màn hình / chờ nhắc điện thoại tính lại mỗi ngày.
6. macOS: app đang ở trước (NSWorkspace) khác chủ cửa sổ Citrix trên cùng -> không phải foreground.
7. Sang ngày mới (máy ngủ qua đêm): chạy lại housekeeping + kiểm lịch lễ.
"""
import json
import os
import tempfile
import unittest

from focus import holidays
from focus.alerts import RealtimeAlerts
from focus.config import ROOT
from focus.probe import MacProbe, WindowsProbe
from tests.helpers import FakeWin32, TempCase, make_cfg, sample, ts
from tests.test_tracker import FRIDAY, _Base, hms, labels, make_tracker

THU = "2026-10-15"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ------------------------------------------------------------ 1. pid tái sử dụng

class PidReuseTest(unittest.TestCase):
    def setUp(self):
        self.w, self.c = FakeWin32(), Clock()
        self.p = WindowsProbe(make_cfg(tempfile.mkdtemp()), api=self.w, clock=self.c)

    def step(self, sec=5):
        self.c.t += sec
        return self.p.sample()

    def test_new_window_reusing_dead_vdi_pid_is_not_vdi(self):
        self.w.fg = self.w.add(1, "cdviewer.exe", "AZ - Desktop Viewer", pid=1234)
        self.assertEqual(self.step()["vdi_state"], "foreground")
        del self.w.windows[1]  # đóng VDI, pid 1234 được trả lại
        self.w.fg = self.w.add(7, "notepad.exe", "notes.txt - Notepad", pid=1234)
        s = self.step(60)
        self.assertEqual(s["fg_proc"], "notepad.exe")
        self.assertEqual(s["vdi_state"], "absent")

    def test_new_vdi_reusing_dead_chrome_pid_is_vdi(self):
        self.w.fg = self.w.add(2, "chrome.exe", "News - Google Chrome", pid=4321)
        self.step()
        del self.w.windows[2]
        self.w.fg = self.w.add(9, "cdviewer.exe", "AZ - Desktop Viewer", pid=4321)
        s = self.step(60)
        self.assertEqual(s["fg_proc"], "cdviewer.exe")
        self.assertEqual(s["vdi_state"], "foreground")

    def test_real_machine_citrix_desktop_viewer(self):
        """Máy thật (14/10/2026): process Citrix.DesktopViewer.App.exe, cửa sổ «AZ-WIN11-CONGTY-REGULAR - Desktop Viewer»."""
        title = "AZ-WIN11-CONGTY-REGULAR - Desktop Viewer"
        self.w.fg = self.w.add(1, "Citrix.DesktopViewer.App.exe".lower(), title, pid=21764)
        s = self.step()
        self.assertEqual((s["vdi_state"], s["vdi_full"]), ("foreground", True))
        self.w.windows[1]["iconic"] = True
        self.w.windows[1]["rect"] = (-32000, -32000, -31840, -31972)
        self.w.fg = self.w.add(2, "chrome.exe", "Google", pid=9)
        self.assertEqual(self.step(60)["vdi_state"], "minimized")
        del self.w.windows[1]
        self.assertEqual(self.step(60)["vdi_state"], "absent")

    def test_unknown_citrix_process_name_still_found_by_title(self):
        """Citrix đổi tên file ở bản sau: process bắt đầu bằng "citrix" + tiêu đề có «Desktop Viewer» vẫn là VDI."""
        self.w.fg = self.w.add(1, "citrix.newname.exe", "AZ-WIN11 - Desktop Viewer", pid=5)
        self.assertEqual(self.step()["vdi_state"], "foreground")
        self.w.fg = self.w.add(3, "citrix.updater.exe", "Citrix Updater", pid=6)
        self.assertEqual(self.step()["vdi_state"], "background", "process Citrix khác, tiêu đề không phải VDI")

    def test_other_apps_with_desktop_viewer_title_still_not_vdi(self):
        self.w.fg = self.w.add(4, "outlook.exe", "Re: Desktop Viewer lỗi - Outlook", pid=7)
        self.assertEqual(self.step()["vdi_state"], "absent")

    def test_same_window_still_cached(self):
        self.w.fg = self.w.add(1, "cdviewer.exe", "AZ - Desktop Viewer", pid=1234)
        self.step()
        n = self.w.proc_calls
        for _ in range(50):
            self.step()
        self.assertEqual(self.w.proc_calls, n, "mỗi vòng không gọi OpenProcess lại")


# ------------------------------------------------------------ 2. /pause

class PauseTest(_Base):
    def test_pause_does_not_carry_into_new_day(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, THU, "16:58:00", [("07:00:00", "vdi")])
        probe.starts = [hms(THU, "07:00:00")]
        tr.state["paused"].set()  # /pause tối thứ Năm rồi gập máy
        st = {"slept": False}

        def hook(c):
            if not st["slept"] and c.t >= hms(THU, "17:00:00"):
                st["slept"] = True
                c.t = hms(FRIDAY, "08:00:00")
            if c.t >= hms(FRIDAY, "09:00:00"):
                self.cfg["auto_stop_at"] = "09:00"
        fc.hook = hook
        tr.run()
        self.assertFalse(tr.state["paused"].is_set())
        fri = [r for r in self.samples() if r[0] >= hms(FRIDAY, "00:00:00")]
        self.assertGreater(len(fri), 600)
        self.assertIn(("morning", FRIDAY), bot.calls)
        self.assertIn("RESUME", self.audit_text())

    def test_jobs_still_sent_while_paused(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "16:00:00", [("07:00:00", "vdi")])

        def hook(c):
            if c.t >= hms(FRIDAY, "16:30:00"):
                tr.state["paused"].set()
        fc.hook = hook
        tr.run()
        self.assertIn(("start_convo", "review"), bot.calls)
        self.assertIn(("summary", FRIDAY), bot.calls)
        self.assertIn(("weekly", FRIDAY), bot.calls)
        self.assertFalse([l for l in labels(nt, FRIDAY) if l[1].startswith("pace_") and l[0] >= "16:30:00"])

    def test_pace_not_sent_while_paused(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, FRIDAY, "15:00:00", [("07:00:00", "vdi")])
        tr.state["paused"].set()

        def hook(c):
            if c.t >= hms(FRIDAY, "16:00:00"):
                self.cfg["auto_stop_at"] = "16:00"
        fc.hook = hook
        tr.run()
        self.assertFalse([l for l in labels(nt, FRIDAY) if l[1].startswith("pace_")])


# ------------------------------------------------------------ 3. lịch lễ timesheet

class TimesheetHolidayTest(TempCase):
    def write_timesheet(self, year, content):
        os.makedirs(self.cfg["timesheet_data_dir"], exist_ok=True)
        with open(os.path.join(self.cfg["timesheet_data_dir"], f"sg_holidays_{year}.json"), "w",
                  encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))

    def test_listed_observed_monday_not_shifted_to_tuesday(self):
        self.write_timesheet(2027, {"holidays": [{"date": d} for d in
                                                 ("2027-01-01", "2027-02-06", "2027-02-07", "2027-02-08")]})
        self.assertEqual(holidays.off_detail(self.cfg, "2027-02-08")[0], "holiday")
        self.assertIsNone(holidays.off_reason(self.cfg, "2027-02-09"), "thứ Ba là ngày làm việc")
        holidays.clear_memo()  # lần sau đọc từ cache riêng (nguồn timesheet): vẫn đúng
        self.assertIsNone(holidays.off_reason(self.cfg, "2027-02-09"))

    def test_sunday_without_listed_monday_still_gets_monday(self):
        self.write_timesheet(2026, ["2026-08-09"])
        self.assertEqual(holidays.off_detail(self.cfg, "2026-08-10")[0], "observed")

    def test_timestamps_and_metadata_dates_ignored(self):
        self.write_timesheet(2026, {"updated": "2026-03-02T09:00:00", "generated": "2026-03-03",
                                    "holidays": [{"date": "2026-08-09", "name": "National Day",
                                                  "fetched": "2026-03-04"}],
                                    "by_day": {"2026-12-25": "Christmas"}})
        h = holidays.holidays(self.cfg, 2026)
        self.assertEqual(sorted(h), ["2026-08-09", "2026-12-25"])
        self.assertIsNone(holidays.off_reason(self.cfg, "2026-03-02"))

    def test_observed_name_marker_any_source(self):
        hol = {"2028-01-02": "A", "2028-01-03": "A (observed)"}
        self.assertEqual(holidays.observed(hol), {})
        hol = {"2028-01-02": "A", "2028-01-03": "B"}  # MOM: thứ Hai là lễ khác -> nghỉ bù thứ Ba
        self.assertEqual(holidays.observed(hol), {"2028-01-04": "A"})


# ------------------------------------------------------------ 4. cai_tu_khoi_dong.ps1

class InstallerScriptTest(unittest.TestCase):
    def test_python_detection_uses_utf8_and_stays_ascii_crlf(self):
        with open(os.path.join(ROOT, "cai_tu_khoi_dong.ps1"), "rb") as f:
            raw = f.read()
        raw.decode("ascii")  # PowerShell 5.1 đọc file không BOM theo ANSI: phải là ASCII
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "phải là CRLF")
        text = raw.decode("ascii")
        self.assertIn('Invoke-PyUtf8 $exe @("-X", "utf8"', text)
        self.assertIn('Invoke-PyUtf8 "py.exe" @("-3", "-X", "utf8"', text)
        self.assertNotIn('& $exe -c "import sys', text)
        self.assertNotIn('& py.exe -3 -c', text)


# ------------------------------------------------------------ 5. cờ trong ngày của cảnh báo

class AlertDayFlagsTest(unittest.TestCase):
    def test_fullscreen_tip_again_next_day(self):
        a = RealtimeAlerts(make_cfg(tempfile.mkdtemp(), fullscreen_tip_minutes=15))
        for day in (THU, FRIDAY):
            t = ts(day, "09:00")
            ev = []
            for i in range(0, 20 * 60, 5):
                ev += a.update(sample(full=False), t + i, True)
            self.assertIn("not_fullscreen", [k for k, _ in ev], day)
            a.reset()  # tracker: sang ngày mới

    def test_phone_cooldown_reset_next_day(self):
        a = RealtimeAlerts(make_cfg(tempfile.mkdtemp()))
        a.phone_alert_at = ts(THU, "16:59")
        a.update(sample(), ts(FRIDAY, "08:00"), True)
        self.assertIsNone(a.phone_alert_at)


# ------------------------------------------------------------ 6. macOS: app đang ở trước

class PlainMacAPI:
    """Giống API cũ / AppleScript dự phòng: không có front_app."""
    method = "fake"

    def __init__(self):
        self.warnings = []
        self.front = None  # (pid, tên) hoặc None
        self.on = []
        self.calls = 0

    def windows(self, onscreen, titles_for=None):
        return list(self.on)

    def displays(self):
        return [(0, 0, 1440, 900)]

    def idle_seconds(self):
        return 1.0

    def is_locked(self):
        return False


class FakeMacAPI(PlainMacAPI):
    def front_app(self):
        self.calls += 1
        return self.front


def win(owner, pid, bounds=(0, 25, 1440, 875)):
    return {"owner": owner, "layer": 0, "alpha": 1.0, "bounds": bounds, "title": None, "pid": pid}


class MacFrontAppTest(TempCase):  # TempCase: log vào file tạm, không in ra màn hình test
    def setUp(self):
        super().setUp()
        self.api = FakeMacAPI()
        self.api.on = [win("Citrix Viewer", 500), win("Google Chrome", 600, (0, 25, 800, 600))]
        self.p = MacProbe(self.cfg, api=self.api)

    def warm_up(self):
        """NSWorkspace chỉ được tin sau khi đã thấy app ở trước đổi ít nhất một lần."""
        for pid in (600, 500):
            self.api.front = (pid, "x")
            self.p.sample()

    def test_finder_desktop_active_is_not_foreground(self):
        self.warm_up()
        self.api.front = (42, "Finder")  # bấm ra desktop: Finder ở trước, không có cửa sổ lớp 0
        s = self.p.sample()
        self.assertEqual(s["vdi_state"], "background")
        self.assertEqual(s["fg_proc"], "finder")
        self.assertIsNone(s["vdi_full"])

    def test_citrix_active_is_foreground(self):
        self.warm_up()
        self.api.front = (500, "Citrix Viewer")
        s = self.p.sample()
        self.assertEqual(s["vdi_state"], "foreground")
        self.assertTrue(s["vdi_full"])

    def test_active_app_window_below_top_window(self):
        self.warm_up()
        self.api.front = (600, "Google Chrome")  # Chrome đang nhận phím, cửa sổ của nó nằm dưới Citrix
        s = self.p.sample()
        self.assertEqual(s["vdi_state"], "background")
        self.assertEqual(s["fg_proc"], "google chrome")

    def test_not_trusted_until_value_changes(self):
        self.api.front = (42, "Finder")  # có thể là giá trị "đứng": chưa tin
        for _ in range(5):
            self.assertEqual(self.p.sample()["vdi_state"], "foreground")

    def test_fallback_when_unavailable_or_failing(self):
        self.api.front = None
        self.assertEqual(self.p.sample()["vdi_state"], "foreground")

        def boom():
            raise OSError("objc")
        self.api.front_app = boom
        self.assertEqual(self.p.sample()["vdi_state"], "foreground")

    def test_api_without_front_app_unchanged(self):
        api = PlainMacAPI()
        api.on = [win("Citrix Viewer", 500)]
        self.assertEqual(MacProbe(make_cfg(tempfile.mkdtemp()), api=api).sample()["vdi_state"], "foreground")


# ------------------------------------------------------------ 7. ngày mới: dọn dẹp + lịch lễ

class NewDayHousekeepingTest(_Base):
    def test_new_day_submits_housekeeping_and_holidays(self):
        tr, fc, probe, bot, nt = make_tracker(self.cfg, THU, "16:58:00", [("07:00:00", "vdi")], run_housekeeping=True)
        probe.starts = [hms(THU, "07:00:00")]
        nt.submit = (lambda orig: lambda label, fn, *a: orig(label, (lambda *x: None) if label in (
            "housekeeping", "holidays") else fn, *a))(nt.submit)  # không chạy thật (không gọi mạng)
        st = {"slept": False}

        def hook(c):
            if not st["slept"] and c.t >= hms(THU, "17:00:00"):
                st["slept"] = True
                c.t = hms(FRIDAY, "08:00:00")
            if c.t >= hms(FRIDAY, "08:10:00"):
                self.cfg["auto_stop_at"] = "08:10"
        fc.hook = hook
        tr.run()
        fri = [label for label, t in nt.jobs if t >= hms(FRIDAY, "00:00:00")]
        self.assertIn("housekeeping", fri)
        self.assertIn("holidays", fri)


if __name__ == "__main__":
    unittest.main()
