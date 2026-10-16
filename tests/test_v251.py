"""2.5.1: tab VDI trong trình duyệt nhận sẵn theo tên máy ảo công ty; robot quà tặng kiểu đồ chơi nhựa 3D."""
import json
import os
import re
import tempfile
import unittest

from focus import robots
from focus.config import DEFAULTS
from focus.probe import WindowsProbe
from tests.helpers import FakeWin32, make_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class DefaultVdiDetectionTest(unittest.TestCase):
    """Cài mới, không sửa settings.json: cả app Citrix lẫn tab trình duyệt đều phải nhận đúng là VDI."""

    def setUp(self):
        self.clock = Clock()
        self.w = FakeWin32()
        self.p = WindowsProbe(make_cfg(tempfile.mkdtemp()), api=self.w, clock=self.clock)

    def state(self):
        self.clock.t += 5
        return self.p.sample()["vdi_state"]

    def test_default_keyword_in_code_and_example_settings(self):
        self.assertEqual(DEFAULTS["vdi_browser_title_keywords"], ["AZ-WIN11-SGLIFE"])
        with open(os.path.join(ROOT, "config", "settings.example.json"), encoding="utf-8") as f:
            example = json.load(f)
        self.assertEqual(example["vdi_browser_title_keywords"], ["AZ-WIN11-SGLIFE"])
        self.assertEqual(example["vdi_title_keywords"], ["Desktop Viewer"])

    def test_citrix_app_desktop_viewer(self):
        self.w.fg = self.w.add(1, "citrix.desktopviewer.app.exe", "AZ-WIN11-SGLIFE-REGULAR - Desktop Viewer")
        self.assertEqual(self.state(), "foreground")

    def test_citrix_app_with_other_vm_name(self):
        """Đồng nghiệp có máy ảo tên khác: app Citrix vẫn nhận qua tên process, không cần sửa gì."""
        self.w.fg = self.w.add(1, "citrix.desktopviewer.app.exe", "AZ-WIN10-KHAC-POWER - Desktop Viewer")
        self.assertEqual(self.state(), "foreground")

    def test_citrix_mock_window_while_typing(self):
        frame = self.w.add(1, "citrix.desktopviewer.app.exe", "AZ-WIN11-SGLIFE-REGULAR - Desktop Viewer")
        self.w.fg = self.w.add(2, "citrix.engineui.app.exe", "MockWindow", tool=True)
        self.assertEqual(self.state(), "foreground")
        self.assertTrue(frame)

    def test_browser_tab_with_company_vm_name(self):
        for exe, title in (("chrome.exe", "AZ-WIN11-SGLIFE-REGULAR - Google Chrome"),
                           ("msedge.exe", "AZ-WIN11-SGLIFE-REGULAR - Citrix Workspace - Microsoft Edge"),
                           ("firefox.exe", "az-win11-sglife-dev - Mozilla Firefox")):
            with self.subTest(exe=exe):
                self.w.fg = self.w.add(40, exe, title)
                self.assertEqual(self.state(), "foreground")

    def test_other_browser_tabs_are_outside(self):
        for title in ("YouTube - Google Chrome", "Citrix Workspace - Google Chrome",
                      "AZ-WIN11-SGLIFE-REGULAR | StoreWeb - Google Chrome"):
            with self.subTest(title=title):
                self.w.fg = self.w.add(41, "chrome.exe", title)
                self.assertNotEqual(self.state(), "foreground")

    def test_company_name_in_other_app_is_not_vdi(self):
        self.w.fg = self.w.add(42, "outlook.exe", "AZ-WIN11-SGLIFE-REGULAR chậm - Outlook")
        self.assertEqual(self.state(), "absent")

    def test_user_can_turn_browser_mode_off(self):
        p = WindowsProbe(make_cfg(tempfile.mkdtemp(), vdi_browser_title_keywords=[]), api=self.w, clock=self.clock)
        self.w.fg = self.w.add(40, "chrome.exe", "AZ-WIN11-SGLIFE-REGULAR - Google Chrome")
        self.assertEqual(p.sample()["vdi_state"], "absent")

    def test_laptop_settings_override_still_works(self):
        """settings.json kiểu máy Khang (vdi_title_keywords có thêm "AZ-WIN11") vẫn nhận cả app lẫn tab."""
        cfg = make_cfg(tempfile.mkdtemp(), vdi_title_keywords=["Desktop Viewer", "AZ-WIN11"])
        p = WindowsProbe(cfg, api=self.w, clock=self.clock)
        self.w.fg = self.w.add(1, "citrix.desktopviewer.app.exe", "AZ-WIN11-SGLIFE-REGULAR - Desktop Viewer")
        self.assertEqual(p.sample()["vdi_state"], "foreground")
        self.w.fg = self.w.add(40, "chrome.exe", "AZ-WIN11-SGLIFE-REGULAR - Google Chrome")
        self.assertEqual(p.sample()["vdi_state"], "foreground")


class Robot3DTest(unittest.TestCase):
    def test_gradient_shading_and_unique_ids(self):
        svgs = [robots.robot_svg(i, 170) for i in range(5)] + [robots.robot_svg(i, 58) for i in range(5)]
        ids = []
        for s in svgs:
            self.assertIn("<linearGradient", s, "đổ bóng 3D bằng gradient")
            own = re.findall(r"id='([^']+)'", s)
            for ref in re.findall(r"url\(#([^)]+)\)", s):
                self.assertIn(ref, own, "gradient được dùng phải nằm trong chính hình đó")
            ids += own
        self.assertEqual(len(ids), len(set(ids)), "hạng / cỡ khác nhau không trùng id gradient")

    def test_levels_clamped_and_frame_unchanged(self):
        self.assertIn("robot hạng 0", robots.robot_svg(-3))
        self.assertIn("robot hạng 4", robots.robot_svg(9))
        self.assertIn("viewBox='0 0 200 230'", robots.robot_svg(2, 100))
        self.assertIn("height='115'", robots.robot_svg(2, 100))


if __name__ == "__main__":
    unittest.main()
