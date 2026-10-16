"""Nhận diện trạng thái cửa sổ Citrix Desktop Viewer trên Windows (Win32 giả lập)."""
import time
import unittest

from focus.probe import WindowsProbe
from tests.helpers import FakeWin32, make_cfg
import tempfile


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())
        self.w = FakeWin32()
        self.clock = Clock()
        self.vdi = self.w.add(1, "cdviewer.exe", "AZ-WIN11 - Desktop Viewer")
        self.chrome = self.w.add(2, "chrome.exe", "Báo Mới - Google Chrome")
        self.tray = self.w.add(3, "explorer.exe", "")  # thanh taskbar không có tiêu đề
        self.w.add(4, "wfica32.exe", "", visible=False)  # cửa sổ ẩn của Citrix
        self.w.fg = self.vdi
        self.p = WindowsProbe(self.cfg, api=self.w, clock=self.clock)

    def state(self):
        self.clock.t += 5
        return self.p.sample()

    def test_vdi_in_front_fullscreen(self):
        s = self.state()
        self.assertEqual(s["vdi_state"], "foreground")
        self.assertTrue(s["vdi_full"])
        self.assertEqual(s["fg_proc"], "cdviewer.exe")

    def test_vdi_in_front_windowed(self):
        self.w.windows[self.vdi]["full"] = False
        s = self.state()
        self.assertEqual(s["vdi_state"], "foreground")
        self.assertFalse(s["vdi_full"])

    def test_minimized_with_other_app_in_front(self):
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_minimized_but_windows_still_reports_it_as_foreground(self):
        """Thu nhỏ cửa sổ cuối cùng: GetForegroundWindow vẫn trả cửa sổ VDI. Phải là minimized."""
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = self.vdi
        s = self.state()
        self.assertEqual(s["vdi_state"], "minimized")
        self.assertIsNone(s["vdi_full"])

    def test_minimized_taskbar_in_front_or_nothing_in_front(self):
        self.w.windows[self.vdi]["iconic"] = True
        for fg in (self.tray, None, 0):
            with self.subTest(fg=fg):
                self.w.fg = fg
                self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_minimize_restore_cycle_many_times(self):
        for i in range(50):
            self.w.windows[self.vdi]["iconic"] = True
            self.w.fg = self.vdi if i % 2 else self.chrome
            self.assertEqual(self.state()["vdi_state"], "minimized", i)
            self.w.windows[self.vdi]["iconic"] = False
            self.w.fg = self.vdi
            self.assertEqual(self.state()["vdi_state"], "foreground", i)

    def test_background_side_by_side(self):
        self.w.windows[self.vdi]["full"] = False
        self.w.fg = self.chrome
        s = self.state()
        self.assertEqual(s["vdi_state"], "background")
        self.assertEqual(s["fg_proc"], "chrome.exe")

    def test_absent(self):
        del self.w.windows[self.vdi]
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "absent")

    def test_vdi_closed_then_reopened(self):
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "background")
        del self.w.windows[self.vdi]
        self.assertEqual(self.state()["vdi_state"], "absent")
        self.w.add(9, "cdviewer.exe", "AZ-WIN11 - Desktop Viewer")
        self.clock.t += 31  # quét lại sau tối đa 30 giây
        self.assertEqual(self.state()["vdi_state"], "background")

    def test_two_vdi_windows_one_minimized(self):
        v2 = self.w.add(5, "cdviewer.exe", "Monitor 2 - Desktop Viewer")
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "background")
        self.w.windows[v2]["iconic"] = True
        self.clock.t += 31
        self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_locked(self):
        self.w.locked = True
        s = self.state()
        self.assertTrue(s["locked"])
        self.assertNotEqual(s["vdi_state"], "foreground")
        self.w.locked = False
        self.w.fg = self.w.add(6, "lockapp.exe", "Windows Default Lock Screen")
        self.assertTrue(self.state()["locked"])

    def test_title_keyword_when_process_unknown(self):
        self.w.procs[self.w.windows[self.vdi]["pid"]] = ""  # chạy quyền Admin: không đọc được tên exe
        self.assertEqual(self.state()["vdi_state"], "foreground")

    def test_chrome_tab_with_citrix_word_is_not_vdi_by_process(self):
        self.cfg["vdi_title_keywords"] = ["desktop viewer"]
        self.w.fg = self.w.add(7, "chrome.exe", "Citrix Workspace - Google Chrome")
        self.assertEqual(self.state()["fg_proc"], "chrome.exe")
        self.assertEqual(self.state()["vdi_state"], "background")

    def test_other_vdi_clients(self):
        for exe in ("wfica32.exe", "msrdc.exe", "mstsc.exe"):
            with self.subTest(exe=exe):
                w = FakeWin32()
                w.fg = w.add(1, exe, "Some session")
                p = WindowsProbe(self.cfg, api=w, clock=self.clock)
                self.assertEqual(p.sample()["vdi_state"], "foreground")

    def test_enumeration_is_cached(self):
        self.w.fg = self.chrome
        for _ in range(5):
            self.state()  # 25 giây
        self.assertEqual(self.w.enum_calls, 1)
        self.clock.t += 30
        self.state()
        self.assertEqual(self.w.enum_calls, 2)
        self.w.fg = self.vdi
        for _ in range(100):
            self.state()
        self.assertEqual(self.w.enum_calls, 2, "VDI ở trước thì không cần quét cửa sổ")

    def test_process_name_cache_expires(self):
        self.state()
        n = self.w.proc_calls
        for _ in range(20):
            self.state()
        self.assertEqual(self.w.proc_calls, n)
        self.clock.t += 601
        self.state()
        self.assertGreater(self.w.proc_calls, n)

    # ---------------------------------------------------------- tiêu đề chỉ dùng khi không đọc được tên process

    def test_title_keyword_ignored_when_process_known(self):
        """Outlook/Chrome/Notepad có chữ "Desktop Viewer" trong tiêu đề: không phải VDI."""
        for exe in ("outlook.exe", "chrome.exe", "notepad.exe"):
            with self.subTest(exe=exe):
                w = FakeWin32()
                w.fg = w.add(1, exe, "Hướng dẫn cài Citrix Desktop Viewer - " + exe)
                p = WindowsProbe(self.cfg, api=w, clock=self.clock)
                s = p.sample()
                self.assertEqual(s["vdi_state"], "absent")
                self.assertEqual(p.warnings, [])

    def test_title_keyword_unknown_process_warns(self):
        self.w.procs[self.w.windows[self.vdi]["pid"]] = ""
        self.assertEqual(self.state()["vdi_state"], "foreground")
        self.assertTrue(any("tiêu đề" in x for x in self.p.warnings))

    # ---------------------------------------------------------- chỉ cửa sổ VDI chính mới là foreground

    def test_owned_toolbar_foreground_while_main_iconic(self):
        """Thanh công cụ Citrix (cửa sổ con thuộc Desktop Viewer) ở trước khi VDI thu nhỏ: minimized."""
        bar = self.w.add(20, "cdviewer.exe", "Desktop Viewer toolbar", pid=self.w.windows[self.vdi]["pid"],
                         owner=self.vdi, rect=(800, 0, 1100, 40))
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = bar
        for _ in range(3):
            s = self.state()
            self.assertEqual(s["vdi_state"], "minimized")
            self.assertIsNone(s["vdi_full"])
        self.clock.t += 31  # quét lại toàn bộ: thanh công cụ không lọt vào danh sách cửa sổ VDI
        self.assertEqual(self.state()["vdi_state"], "minimized")
        self.assertNotIn(bar, self.p._vdi)

    def test_owned_toolbar_foreground_while_main_shown(self):
        bar = self.w.add(20, "cdviewer.exe", "Desktop Viewer toolbar", owner=self.vdi, tool=True,
                         rect=(800, 0, 1100, 40))
        self.w.fg = bar
        s = self.state()
        self.assertEqual(s["vdi_state"], "foreground")
        self.assertTrue(s["vdi_full"])

    def test_tool_window_never_counts(self):
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = self.w.add(21, "wfica32.exe", "Citrix HDX", tool=True, rect=(0, 0, 800, 600))
        self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_hidden_window_of_same_process_foreground(self):
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = self.w.add(22, "cdviewer.exe", "CDViewer hidden", pid=self.w.windows[self.vdi]["pid"],
                               visible=False)
        self.assertEqual(self.state()["vdi_state"], "minimized")
        self.w.fg = 4  # cửa sổ ẩn không tiêu đề của wfica32.exe
        self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_tiny_or_offscreen_vdi_window(self):
        self.w.windows[self.vdi]["rect"] = (0, 0, 150, 120)
        self.assertNotEqual(self.state()["vdi_state"], "foreground")
        self.w.windows[self.vdi]["rect"] = (-32000, -32000, -31840, -31972)  # thu nhỏ mà IsIconic chưa kịp đổi
        self.clock.t += 31
        self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_two_vdis_one_minimized_other_foreground(self):
        v2 = self.w.add(5, "cdviewer.exe", "AZ-WIN11-DEV - Desktop Viewer")
        self.w.windows[self.vdi]["iconic"] = True
        self.w.fg = v2
        self.assertEqual(self.state()["vdi_state"], "foreground")
        self.w.windows[v2]["iconic"] = True
        self.assertEqual(self.state()["vdi_state"], "minimized")
        self.w.windows[self.vdi]["iconic"] = False
        self.w.fg = self.vdi
        self.assertEqual(self.state()["vdi_state"], "foreground")

    # ---------------------------------------------------------- nhớ tên process

    def test_failed_process_lookup_retried_after_30s(self):
        pid = self.w.windows[self.vdi]["pid"]
        self.w.procs[pid] = ""
        self.state()
        self.w.procs[pid] = "cdviewer.exe"
        self.w.windows[self.vdi]["title"] = "AZ-WIN11"  # không còn từ khoá: chỉ nhận được qua tên process
        self.assertEqual(self.state()["fg_proc"], "")
        self.clock.t += 30
        s = self.state()
        self.assertEqual(s["fg_proc"], "cdviewer.exe")
        self.assertEqual(s["vdi_state"], "foreground")

    def test_hwnd_pid_change_invalidates_cache(self):
        self.w.fg = self.w.add(30, "old.exe", "Old app", pid=777)
        self.assertEqual(self.state()["fg_proc"], "old.exe")
        self.w.procs[777] = "cdviewer.exe"  # pid 777 bị tái sử dụng
        self.w.windows[self.chrome]["pid"] = 777  # hwnd cũ giờ thuộc pid 777
        self.w.fg = self.chrome
        self.assertEqual(self.state()["fg_proc"], "cdviewer.exe")

    # ---------------------------------------------------------- Citrix HTML5 trong trình duyệt

    def browser_setup(self, keywords=("az-win11",)):
        cfg = dict(self.cfg, vdi_browser_title_keywords=list(keywords))
        w = FakeWin32()
        p = WindowsProbe(cfg, api=w, clock=self.clock)
        return w, p

    def test_html5_tab_active_is_foreground(self):
        w, p = self.browser_setup()
        for exe in ("chrome.exe", "msedge.exe", "firefox.exe"):
            with self.subTest(exe=exe):
                w.fg = w.add(40, exe, "AZ-WIN11 - Citrix Workspace - Google Chrome", full=True)
                s = p.sample()
                self.assertEqual(s["vdi_state"], "foreground")
                self.assertTrue(s["vdi_full"])
        self.assertIn("trình duyệt", p.method)

    def test_html5_other_tab_active_is_outside(self):
        w, p = self.browser_setup()
        b = w.fg = w.add(40, "chrome.exe", "AZ-WIN11 - Citrix Workspace - Google Chrome")
        self.clock.t += 1
        self.assertEqual(p.sample()["vdi_state"], "foreground")
        w.windows[b]["title"] = "YouTube - Google Chrome"   # chuyển sang tab khác trong cùng cửa sổ
        self.assertNotEqual(p.sample()["vdi_state"], "foreground")
        self.assertEqual(p.sample()["vdi_state"], "absent")
        w.fg = w.add(41, "explorer.exe", "")
        self.assertEqual(p.sample()["vdi_state"], "absent")

    def test_storeweb_page_is_outside(self):
        w, p = self.browser_setup()
        for title in ("Citrix Workspace - Google Chrome", "AZ-WIN11 | StoreWeb - Microsoft Edge",
                      "acme.cloud.com/Citrix/StoreWeb/#/home - Google Chrome"):
            with self.subTest(title=title):
                w.fg = w.add(42, "chrome.exe", title)
                self.assertNotEqual(p.sample()["vdi_state"], "foreground")

    def test_html5_off_when_no_keywords(self):
        w, p = self.browser_setup(keywords=())
        w.fg = w.add(40, "chrome.exe", "AZ-WIN11 - Citrix Workspace - Google Chrome")
        self.assertEqual(p.sample()["vdi_state"], "absent")
        self.assertNotIn("trình duyệt", p.method)

    def test_html5_browser_minimized_or_behind(self):
        w, p = self.browser_setup()
        b = w.add(40, "chrome.exe", "AZ-WIN11 - Citrix Workspace - Google Chrome")
        other = w.add(43, "notepad.exe", "Ghi chú - Notepad")
        w.fg = b
        self.assertEqual(p.sample()["vdi_state"], "foreground")
        w.windows[b]["iconic"] = True
        w.fg = other
        self.assertEqual(p.sample()["vdi_state"], "minimized")
        w.windows[b]["iconic"] = False
        self.assertEqual(p.sample()["vdi_state"], "background")

    def test_speed_with_many_windows(self):
        for h in range(100, 400):
            self.w.add(h, "app.exe", f"Window {h}")
        self.w.fg = self.chrome
        t = time.perf_counter()
        for _ in range(1000):
            self.state()
        per = (time.perf_counter() - t) / 1000 * 1000
        self.assertLess(per, 1.0, f"{per:.3f} ms mỗi lần đọc")


class CitrixSessionSurfaceTest(unittest.TestCase):
    """Máy thật (15/10/2026): gõ trong VDI thì cửa sổ ở trước là Citrix.EngineUI.App.exe «MockWindow» (tool window,
    đúng bằng vùng làm việc của Desktop Viewer), không phải Desktop Viewer. Ở chế độ Full screen của Citrix thì
    cửa sổ Desktop Viewer chính biến mất, chỉ còn mặt phiên."""
    TITLE = "AZ-WIN11-CONGTY-REGULAR - Desktop Viewer"

    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())
        self.w = FakeWin32()
        self.clock = Clock()
        self.frame = self.w.add(1, "citrix.desktopviewer.app.exe", self.TITLE, full=False, rect=(100, 50, 1663, 984))
        self.surface = self.w.add(2, "citrix.engineui.app.exe", "MockWindow", tool=True, full=False,
                                  rect=(111, 100, 1652, 978))
        self.chrome = self.w.add(3, "chrome.exe", "Google Chrome")
        self.p = WindowsProbe(self.cfg, api=self.w, clock=self.clock)

    def state(self):
        self.clock.t += 5
        return self.p.sample()

    def test_typing_in_session_surface_is_foreground_and_windowed(self):
        self.w.fg = self.surface
        s = self.state()
        self.assertEqual((s["vdi_state"], s["vdi_full"]), ("foreground", False))
        self.assertEqual(s["fg_proc"], "citrix.engineui.app.exe")
        self.assertIn("tool=1", s["fg_info"])

    def test_surface_with_maximized_frame_reports_full(self):
        self.w.windows[self.frame]["full"] = True
        self.w.fg = self.surface
        self.assertTrue(self.state()["vdi_full"])

    def test_frame_in_front_still_foreground(self):
        self.w.fg = self.frame
        self.assertEqual(self.state()["vdi_state"], "foreground")

    def test_surface_while_frame_minimized_is_not_foreground(self):
        self.w.windows[self.frame].update(iconic=True, rect=(-32000, -32000, -31840, -31972))
        self.w.fg = self.surface
        self.assertEqual(self.state()["vdi_state"], "minimized")

    def test_surface_off_screen_is_not_foreground(self):
        self.w.windows[self.surface]["rect"] = (-32000, -32000, -31840, -31972)
        self.w.fg = self.surface
        self.assertNotEqual(self.state()["vdi_state"], "foreground")

    def test_other_app_in_front_is_background_even_with_surface_on_screen(self):
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "background")

    def test_citrix_full_screen_only_surface_and_small_toolbar(self):
        """Full screen của Citrix: khung chính ẩn, thanh công cụ bé cùng tiêu đề, mặt phiên phủ cả màn hình."""
        self.w.windows[self.frame]["visible"] = False
        toolbar = self.w.add(4, "citrix.desktopviewer.app.exe", self.TITLE, rect=(700, 0, 1220, 30))
        self.w.windows[self.surface].update(rect=(0, 0, 1920, 1080), full=True)
        for fg in (self.surface, toolbar):
            with self.subTest(fg=fg):
                self.w.fg = fg
                s = self.state()
                self.assertEqual((s["vdi_state"], s["vdi_full"]), ("foreground", True))
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "background", "không còn báo absent khi VDI ở Full screen")

    def test_full_screen_vdi_is_not_absent_when_session_surface_visible(self):
        self.w.windows[self.frame]["visible"] = False
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "background")
        self.w.windows[self.surface]["visible"] = False
        self.clock.t += 31
        self.assertEqual(self.state()["vdi_state"], "absent")

    def test_hidden_helper_windows_of_engine_never_count(self):
        self.w.windows[self.surface]["rect"] = (0, 0, 50, 50)  # cửa sổ tí hon
        self.w.windows[self.frame]["iconic"] = True
        self.w.fg = self.chrome
        self.assertEqual(self.state()["vdi_state"], "minimized")


class CitrixRenameTest(unittest.TestCase):
    """Citrix đổi tên app ở bản sau: bot vẫn nhận ra VDI nhờ thư mục cài Citrix, tiêu đề và vị trí mặt phiên."""
    TITLE = "AZ-WIN11-CONGTY-REGULAR - Desktop Viewer"
    CITRIX_DIR = r"C:\Program Files (x86)\Citrix\ICA Client"

    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())
        self.w = FakeWin32()
        self.clock = Clock()
        self.chrome = self.w.add(3, "chrome.exe", "Google Chrome")
        self.p = WindowsProbe(self.cfg, api=self.w, clock=self.clock)

    def state(self):
        self.clock.t += 5
        return self.p.sample()

    def test_renamed_frame_in_citrix_folder_found_by_title(self):
        frame = self.w.add(1, "ctxdesktop.exe", self.TITLE, full=False, image=self.CITRIX_DIR + r"\ctxdesktop.exe")
        self.w.fg = frame
        self.assertEqual(self.state()["vdi_state"], "foreground")
        self.w.fg = self.chrome
        self.clock.t += 31
        self.assertEqual(self.state()["vdi_state"], "background")

    def test_same_name_outside_citrix_folder_is_not_vdi(self):
        self.w.fg = self.w.add(1, "ctxdesktop.exe", self.TITLE, image=r"C:\Tools\ctxdesktop.exe")
        self.assertEqual(self.state()["vdi_state"], "absent")

    def test_renamed_session_surface_covering_frame_counts_and_warns(self):
        self.w.add(1, "citrix.desktopviewer.app.exe", self.TITLE, full=False, rect=(100, 50, 1663, 984))
        surf = self.w.add(2, "citrix.newengine.exe", "MockWindow", tool=True, rect=(111, 100, 1652, 978))
        self.w.fg = self.chrome
        self.state()  # lần quét đầu: biết toạ độ khung
        self.w.fg = surf
        s = self.state()
        self.assertEqual((s["vdi_state"], s["vdi_full"]), ("foreground", False))
        self.assertTrue(any("citrix.newengine.exe" in w and "vdi_session_processes" in w for w in self.p.warnings))
        self.assertIn("tool=1", s["fg_info"])

    def test_renamed_surface_in_citrix_folder_without_citrix_name(self):
        self.w.add(1, "citrix.desktopviewer.app.exe", self.TITLE, full=True)
        surf = self.w.add(2, "hdxsurface.exe", "MockWindow", tool=True, image=self.CITRIX_DIR + r"\hdxsurface.exe")
        self.w.fg = surf
        self.assertEqual(self.state()["vdi_state"], "foreground")

    def test_citrix_tool_window_not_covering_vdi_is_not_vdi(self):
        self.w.add(1, "citrix.desktopviewer.app.exe", self.TITLE, full=False, rect=(0, 0, 900, 700))
        popup = self.w.add(2, "citrix.newengine.exe", "Thông báo", tool=True, rect=(1000, 100, 1900, 700))
        self.w.fg = popup
        self.assertEqual(self.state()["vdi_state"], "background")
        self.assertTrue(any("Citrix lạ" in w for w in self.p.warnings), "báo để người dùng biết tên mới")

    def test_non_citrix_tool_window_over_vdi_never_counts(self):
        self.w.add(1, "citrix.desktopviewer.app.exe", self.TITLE, full=True)
        overlay = self.w.add(2, "zoom.exe", "Zoom overlay", tool=True)
        self.w.fg = overlay
        self.assertEqual(self.state()["vdi_state"], "background")
        self.assertEqual(self.p.warnings, [])

    def test_known_toolbar_of_desktop_viewer_is_not_a_surface(self):
        frame = self.w.add(1, "citrix.desktopviewer.app.exe", self.TITLE, iconic=True)
        bar = self.w.add(2, "citrix.desktopviewer.app.exe", "Toolbar", tool=True, rect=(0, 0, 1920, 1080))
        self.w.fg = bar
        self.assertEqual(self.state()["vdi_state"], "minimized")
        self.assertTrue(frame)
