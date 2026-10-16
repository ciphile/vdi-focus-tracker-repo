"""Nhận diện trạng thái cửa sổ Citrix Viewer trên macOS (danh sách cửa sổ CoreGraphics giả, không cần máy Mac)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from focus.probe import MacProbe, MacScriptWindows, mac_python_program, make_probe, ProbeError
from focus import probe as probe_mod
from tests.helpers import make_cfg

SCREEN = (0.0, 0.0, 1512.0, 982.0)       # MacBook Pro 14" (điểm)
FULL = SCREEN
HALF = (100.0, 100.0, 700.0, 500.0)


def win(owner, bounds=HALF, title=None, layer=0, alpha=1.0):
    return {"owner": owner, "layer": layer, "alpha": alpha, "bounds": bounds, "title": title}


class FakeMacAPI:
    """on: cửa sổ đang hiện ở Space hiện tại, từ trước ra sau. hidden: cửa sổ chỉ có trong danh sách đầy đủ
    (thu nhỏ xuống Dock, app bị ẩn bằng Cmd+H, nằm ở Space khác). titles=False: không có quyền Screen Recording."""

    method = "CoreGraphics (giả)"

    def __init__(self, on=(), hidden=(), locked=False, idle=1.0, titles=True):
        self.on, self.hidden = list(on), list(hidden)
        self.locked, self.idle, self.titles = locked, idle, titles
        self.calls = []
        self.warnings = []

    def _strip(self, ws, titles_for):
        out = []
        for w in ws:
            w = dict(w)
            if not titles_for or not titles_for(w["owner"].lower()):
                w["title"] = None
            elif not self.titles:
                w["title"] = ""
            out.append(w)
        return out

    def windows(self, onscreen, titles_for=None):
        self.calls.append(onscreen)
        return self._strip(self.on if onscreen else self.on + self.hidden, titles_for)

    def displays(self):
        return [SCREEN, (1512.0, 0.0, 1920.0, 1080.0)]

    def is_locked(self):
        return self.locked

    def idle_seconds(self):
        return self.idle


def temp_cfg(case, **over):
    tmp = tempfile.mkdtemp(prefix="focus-mac-")
    case.addCleanup(shutil.rmtree, tmp, True)
    # Mặc định app có sẵn từ khoá tab VDI công ty; test ở đây xét chế độ chỉ app Citrix trừ khi truyền từ khoá riêng.
    over.setdefault("vdi_browser_title_keywords", [])
    return make_cfg(tmp, **over)


class MacProbeTest(unittest.TestCase):
    def setUp(self):
        self.cfg = temp_cfg(self)
        self.api = FakeMacAPI()
        self.p = MacProbe(self.cfg, api=self.api)

    def state(self, **kw):
        for k, v in kw.items():
            setattr(self.api, k, list(v) if k in ("on", "hidden") else v)
        return self.p.sample()

    def test_foreground_fullscreen(self):
        s = self.state(on=[win("Citrix Viewer", FULL), win("Finder", HALF)])
        self.assertEqual(s["vdi_state"], "foreground")
        self.assertEqual(s["fg_proc"], "citrix viewer")
        self.assertTrue(s["vdi_full"])
        self.assertFalse(s["locked"])

    def test_foreground_windowed_and_zoomed(self):
        self.assertFalse(self.state(on=[win("Citrix Viewer", HALF)])["vdi_full"])
        zoomed = (0.0, 37.0, 1512.0, 870.0)  # phóng to: chừa thanh menu + Dock
        self.assertTrue(self.state(on=[win("Citrix Viewer", zoomed)])["vdi_full"])
        second = (1512.0, 0.0, 1920.0, 1080.0)  # toàn màn hình ở màn hình ngoài
        self.assertTrue(self.state(on=[win("Citrix Viewer", second)])["vdi_full"])

    def test_minimized_to_dock(self):
        s = self.state(on=[win("Google Chrome")], hidden=[win("Citrix Viewer", (0, 0, 1512, 982))])
        self.assertEqual(s["vdi_state"], "minimized")
        self.assertEqual(s["fg_proc"], "google chrome")
        self.assertIsNone(s["vdi_full"])

    def test_closed_session_leftover_invisible_helper_window_is_absent(self):
        """Phiên đã đóng nhưng Citrix Viewer còn cửa sổ phụ vô hình / tí hon: VDI không còn (absent), không phải thu nhỏ,
        để cảnh báo VDI bị ngắt vẫn chạy."""
        helpers = [win("Citrix Viewer", (0, 0, 1, 1), alpha=0.0), win("Citrix Viewer", (0, 0, 20, 20))]
        self.assertEqual(self.state(on=[win("Google Chrome")], hidden=helpers)["vdi_state"], "absent")

    def test_citrix_toolbar_on_top_of_fullscreen_session(self):
        toolbar = win("Citrix Viewer", (500.0, 0.0, 400.0, 60.0))
        s = self.state(on=[toolbar, win("Citrix Viewer", FULL)])
        self.assertEqual((s["vdi_state"], s["vdi_full"]), ("foreground", True))

    def test_hidden_with_cmd_h(self):
        self.assertEqual(self.state(on=[win("Finder")], hidden=[win("Citrix Viewer")])["vdi_state"], "minimized")

    def test_other_space_while_vdi_fullscreen(self):
        """VDI toàn màn hình ở Space riêng, người dùng vuốt sang Space khác: không còn trên màn hình -> minimized."""
        self.assertEqual(self.state(on=[win("Safari", FULL)], hidden=[win("Citrix Viewer", FULL)])["vdi_state"],
                         "minimized")

    def test_citrix_frontmost_but_only_window_minimized(self):
        """App Citrix Viewer vẫn là app phía trước nhưng cửa sổ duy nhất đã thu nhỏ: minimized, không phải foreground."""
        s = self.state(on=[win("Finder", (0, 0, 800, 600))], hidden=[win("Citrix Viewer")])
        self.assertEqual(s["vdi_state"], "minimized")
        self.assertEqual(self.state(on=[], hidden=[win("Citrix Viewer")])["vdi_state"], "minimized")

    def test_background(self):
        self.assertEqual(self.state(on=[win("Google Chrome"), win("Citrix Viewer", FULL)])["vdi_state"], "background")

    def test_two_vdi_windows(self):
        self.assertEqual(self.state(on=[win("Citrix Viewer"), win("Zalo")], hidden=[win("Citrix Viewer")])["vdi_state"],
                         "foreground")
        self.assertEqual(self.state(on=[win("Zalo"), win("Citrix Viewer")], hidden=[win("Citrix Viewer")])["vdi_state"],
                         "background")
        self.assertEqual(self.state(on=[win("Zalo")], hidden=[win("Citrix Viewer")] * 2)["vdi_state"], "minimized")

    def test_absent(self):
        self.assertEqual(self.state(on=[win("Google Chrome")], hidden=[])["vdi_state"], "absent")
        self.assertEqual(self.p.warnings, [])

    def test_unknown_citrix_app_hint(self):
        self.state(on=[win("Google Chrome")], hidden=[win("Citrix Viewer Beta 2")])  # có "citrix viewer": vẫn nhận
        self.assertEqual(self.p.warnings, [])
        s = self.state(on=[win("Google Chrome")], hidden=[win("Citrix HDX Viewer")])
        self.assertEqual(s["vdi_state"], "absent")
        self.assertTrue(any("Citrix HDX Viewer" in w for w in self.p.warnings))

    def test_ignores_menubar_overlays_and_invisible_windows(self):
        on = [win("Control Center", (0, 0, 300, 25), layer=25), win("Grammarly", HALF, alpha=0.0),
              win("Bartender", (0, 0, 20, 20)), win("Citrix Viewer", FULL)]
        self.assertEqual(self.state(on=on)["vdi_state"], "foreground")

    def test_minimize_restore_cycles(self):
        for i in range(30):
            self.assertEqual(self.state(on=[win("Finder")], hidden=[win("Citrix Viewer")])["vdi_state"], "minimized", i)
            self.assertEqual(self.state(on=[win("Citrix Viewer")], hidden=[])["vdi_state"], "foreground", i)

    def test_full_list_only_when_needed(self):
        self.state(on=[win("Citrix Viewer")])
        self.assertEqual(self.api.calls, [True])

    def test_locked_is_never_foreground(self):
        s = self.state(on=[win("Citrix Viewer", FULL)], locked=True)
        self.assertTrue(s["locked"])
        self.assertNotEqual(s["vdi_state"], "foreground")

    def test_idle_passthrough(self):
        s = self.state(on=[win("Citrix Viewer")], idle=123.5)
        self.assertEqual(s["idle"], 123.5)
        self.assertEqual(s["vdi_state"], "foreground")  # idle chỉ đọc ra, tracker mới quyết định rời máy

    def test_other_mac_vdi_clients(self):
        for app in ("Windows App", "Microsoft Remote Desktop"):
            with self.subTest(app=app):
                self.assertEqual(self.state(on=[win(app)])["vdi_state"], "foreground")

    def test_empty_window_list(self):
        s = self.state(on=[], hidden=[])
        self.assertEqual(s["vdi_state"], "absent")
        self.assertEqual(s["fg_proc"], "")

    def test_metadata(self):
        self.assertEqual(self.p.platform_name, "macOS")
        self.assertIn("app Citrix", self.p.method)
        self.assertNotIn("trình duyệt", self.p.method)


class MacBrowserTest(unittest.TestCase):
    """Citrix Workspace bản HTML5: VDI chạy trong tab trình duyệt, chỉ nhận ra qua tiêu đề (cần Screen Recording)."""

    def setUp(self):
        self.cfg = temp_cfg(self, vdi_browser_title_keywords=["AZ-WIN11"])
        self.api = FakeMacAPI()
        self.p = MacProbe(self.cfg, api=self.api)

    def test_vdi_tab_foreground(self):
        self.api.on = [win("Google Chrome", FULL, title="AZ-WIN11 - Citrix Workspace")]
        s = self.p.sample()
        self.assertEqual(s["vdi_state"], "foreground")
        self.assertTrue(s["vdi_full"])
        self.assertIn("trình duyệt", self.p.method)
        self.assertEqual(self.p.warnings, [])

    def test_other_tab_or_storeweb_is_outside(self):
        for title in ("YouTube", "Citrix Workspace", "acme.cloud.com/Citrix/StoreWeb/#/home"):
            with self.subTest(title=title):
                self.api.on = [win("Safari", FULL, title=title)]
                self.assertEqual(self.p.sample()["vdi_state"], "absent")

    def test_browser_minimized_on_vdi_tab(self):
        self.api.on = [win("Finder")]
        self.api.hidden = [win("Microsoft Edge", FULL, title="AZ-WIN11")]
        self.assertEqual(self.p.sample()["vdi_state"], "minimized")

    def test_no_screen_recording_permission_warns(self):
        self.api.titles = False
        self.api.on = [win("Google Chrome", FULL, title="AZ-WIN11 - Citrix Workspace")]
        s = self.p.sample()
        self.assertEqual(s["vdi_state"], "absent", "không có tiêu đề thì không bao giờ tính tab là VDI")
        warning = self.p.no_title_warning()
        self.assertIn(warning, self.p.warnings)
        self.p.sample()
        self.assertEqual(self.p.warnings.count(warning), 1)
        self.assertIn("Screen Recording", warning)
        self.assertIn(mac_python_program()[1], warning, "ghi rõ chương trình cần cấp quyền")

    def test_asks_screen_recording_permission_once_at_start(self):
        api = FakeMacAPI()
        api.can_read_titles = lambda: False
        api.asked = 0

        def ask():
            api.asked += 1
        api.ask_title_permission = ask
        p = MacProbe(self.cfg, api=api)
        self.assertEqual(api.asked, 1, "chưa có quyền: hiện hộp thoại macOS xin quyền cho chính chương trình này")
        self.assertIn(p.no_title_warning(), p.warnings)
        p.sample()
        self.assertEqual(api.asked, 1)
        api.can_read_titles = lambda: True
        api.asked = 0
        MacProbe(self.cfg, api=api)
        self.assertEqual(api.asked, 0, "đã có quyền thì không hỏi")
        MacProbe(temp_cfg(self), api=api)
        api.can_read_titles = lambda: False
        MacProbe(temp_cfg(self), api=api)
        self.assertEqual(api.asked, 0, "không dùng VDI qua trình duyệt thì không bao giờ xin quyền ghi màn hình")

    def test_permission_check_error_is_ignored(self):
        api = FakeMacAPI()
        api.can_read_titles = mock.Mock(side_effect=OSError("boom"))
        p = MacProbe(self.cfg, api=api)
        self.assertEqual(p.warnings, [])

    def test_no_titles_requested_when_browser_mode_off(self):
        p = MacProbe(temp_cfg(self), api=self.api)
        self.api.titles = False
        self.api.on = [win("Google Chrome", FULL, title="AZ-WIN11")]
        self.assertEqual(p.sample()["vdi_state"], "absent")
        self.assertEqual(p.warnings, [])


class MacScriptFallbackTest(unittest.TestCase):
    """Dự phòng AppleScript (khi không có CoreGraphics): giả subprocess.run."""

    def setUp(self):
        self.t = [0.0]
        self.sw = MacScriptWindows(["Citrix Viewer"], clock=lambda: self.t[0])

    def run_with(self, front, wins):
        out = json.dumps({"front": front, "wins": [{"o": o, "m": m} for o, m in wins]})
        self.t[0] += 10
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout=out)) as run:
            on = [w["owner"] for w in self.sw.windows(True)]
            allw = [w["owner"] for w in self.sw.windows(False)]
        self.assertEqual(run.call_count, 1, "một mẫu chỉ gọi osascript một lần")
        args, kw = run.call_args
        self.assertEqual(args[0][:3], ["osascript", "-l", "JavaScript"])
        self.assertLessEqual(kw["timeout"], 2)
        return on, allw

    def test_shapes(self):
        self.assertEqual(self.run_with("Citrix Viewer", [("Citrix Viewer", False)]),
                         (["Citrix Viewer"], ["Citrix Viewer"]))
        self.assertEqual(self.run_with("Citrix Viewer", [("Citrix Viewer", True)]), ([], ["Citrix Viewer"]))
        self.assertEqual(self.run_with("Google Chrome", [("Citrix Viewer", False)]),
                         (["Google Chrome", "Citrix Viewer"], ["Citrix Viewer"]))

    def test_probe_on_fallback(self):
        cfg = temp_cfg(self)
        api = FakeMacAPI()
        api.windows = self.sw.windows
        p = MacProbe(cfg, api=api)
        for front, wins, want in (("Citrix Viewer", [("Citrix Viewer", True)], "minimized"),
                                  ("Citrix Viewer", [("Citrix Viewer", False)], "foreground"),
                                  ("Zalo", [("Citrix Viewer", False)], "background"),
                                  ("Zalo", [], "absent")):
            out = json.dumps({"front": front, "wins": [{"o": o, "m": m} for o, m in wins]})
            self.t[0] += 10
            with mock.patch("subprocess.run", return_value=mock.Mock(stdout=out)):
                self.assertEqual(p.sample()["vdi_state"], want, (front, wins))

    def test_failures_tolerated(self):
        cases = [FileNotFoundError("osascript"), subprocess.TimeoutExpired("osascript", 2), OSError("denied")]
        for err in cases:
            with self.subTest(err=type(err).__name__), mock.patch("subprocess.run", side_effect=err):
                self.t[0] += 10
                self.assertEqual(self.sw.windows(True), [])
        for out in ("", "not json", "execution error: Not authorized (-1743)", "{}", "null", '{"wins": 5}'):
            with self.subTest(out=out), mock.patch("subprocess.run", return_value=mock.Mock(stdout=out)):
                self.t[0] += 10
                self.assertEqual(self.sw.windows(False), [])


class MakeProbeTest(unittest.TestCase):
    def setUp(self):
        self.cfg = temp_cfg(self)

    def test_auto_picks_by_os(self):
        with mock.patch.object(probe_mod, "WindowsProbe", return_value="win"), \
                mock.patch.object(probe_mod, "MacProbe", return_value="mac"):
            self.assertEqual(make_probe(self.cfg, os_name="win32"), "win")
            self.assertEqual(make_probe(self.cfg, os_name="darwin"), "mac")
            self.cfg["platform"] = "mac"
            self.assertEqual(make_probe(self.cfg, os_name="darwin"), "mac")
            self.cfg["platform"] = "windows"
            self.assertEqual(make_probe(self.cfg, os_name="win32"), "win")

    def test_mismatch_and_unsupported(self):
        self.cfg["platform"] = "mac"
        with self.assertRaises(ProbeError) as e:
            make_probe(self.cfg, os_name="win32")
        self.assertIn('"platform"', str(e.exception))
        self.assertIn("Windows", str(e.exception))
        self.cfg["platform"] = "windows"
        with self.assertRaises(ProbeError):
            make_probe(self.cfg, os_name="darwin")
        self.cfg["platform"] = "auto"
        with self.assertRaises(ProbeError) as e:
            make_probe(self.cfg, os_name="linux")
        self.assertIn("chưa được hỗ trợ", str(e.exception))


if __name__ == "__main__":
    unittest.main()


class MacPythonProgramTest(unittest.TestCase):
    def test_python_org_framework_maps_to_python_app(self):
        exe = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
        with mock.patch("os.path.realpath", side_effect=lambda p: p):
            self.assertEqual(mac_python_program(exe),
                             ("Python", "/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app"))

    def test_other_python_keeps_real_path(self):
        with mock.patch("os.path.realpath", side_effect=lambda p: p):
            self.assertEqual(mac_python_program("/opt/homebrew/Cellar/python@3.12/3.12.4/bin/python3.12"),
                             ("python3.12", "/opt/homebrew/Cellar/python@3.12/3.12.4/bin/python3.12"))
