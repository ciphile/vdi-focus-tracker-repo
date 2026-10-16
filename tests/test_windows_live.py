"""Thử thật trên Windows 10: cửa sổ tkinter đóng vai Citrix Desktop Viewer, đọc bằng Win32 thật.

Chỉ chạy khi sys.platform == "win32" (và có tkinter + màn hình). Nơi khác tự bỏ qua.
Cửa sổ giả có tiêu đề chứa từ khoá riêng của lần chạy này, nên cửa sổ Citrix thật đang mở (nếu có)
không ảnh hưởng kết quả. Tiêu đề chỉ được dùng khi không đọc được tên process (Citrix chạy quyền Admin), nên
test giả lập điều đó cho riêng tiến trình python của test.
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

from tests.helpers import make_cfg

WIN = sys.platform == "win32"


@unittest.skipUnless(WIN, "chỉ chạy trên Windows")
class WindowsLiveProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter
            cls.tk = tkinter
            root = tkinter.Tk()
        except Exception as e:  # không có tkinter / không có màn hình (chạy dịch vụ)
            raise unittest.SkipTest(f"không tạo được cửa sổ tkinter: {e}")
        root.destroy()
        import ctypes
        from ctypes import wintypes as wt
        cls.ct = ctypes
        u = cls.user32 = ctypes.WinDLL("user32", use_last_error=True)
        u.GetForegroundWindow.restype = wt.HWND
        u.SetForegroundWindow.argtypes = [wt.HWND]
        u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        u.IsIconic.argtypes = [wt.HWND]
        u.BringWindowToTop.argtypes = [wt.HWND]
        u.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_size_t]

    def setUp(self):
        from focus.probe import Win32, WindowsProbe
        self.keyword = f"focustest-{os.getpid()}-{time.monotonic_ns()}"
        tmp = tempfile.mkdtemp(prefix="focus-win-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.cfg = make_cfg(tmp, vdi_processes=[], vdi_title_keywords=[self.keyword])
        self.api = Win32()
        if self.api.is_locked():
            self.skipTest("máy đang khoá")
        self.probe = WindowsProbe(self.cfg, api=self.api)
        real_proc_name, me = self.probe.proc_name, os.getpid()
        # python.exe đọc được tên process -> tiêu đề bị bỏ qua; giả như không đọc được để test qua từ khoá tiêu đề
        self.probe.proc_name = lambda h: "" if self.api.pid(h) == me else real_proc_name(h)
        self.root = self.tk.Tk()
        self.root.title("FocusTest Other Window")   # cửa sổ "không phải VDI"
        self.root.geometry("300x200+50+50")
        self.addCleanup(self._destroy, self.root)
        self.vdi = self.tk.Toplevel(self.root)
        self.vdi.title(f"FocusTest Desktop Viewer {self.keyword}")
        self.vdi.geometry("400x300+200+200")
        self.addCleanup(self._destroy, self.vdi)
        self.pump()
        self.vdi_hwnd = self.hwnd(self.vdi)
        self.other_hwnd = self.hwnd(self.root)

    # ------------------------------------------------------------ tiện ích

    @staticmethod
    def _destroy(w):
        try:
            w.destroy()
        except Exception:
            pass

    def pump(self, seconds=0.05):
        end = time.perf_counter() + seconds
        while True:
            self.root.update()
            if time.perf_counter() >= end:
                return
            time.sleep(0.01)

    def hwnd(self, w):
        w.update_idletasks()
        return int(w.wm_frame(), 16)  # HWND của khung ngoài (cửa sổ cấp cao nhất)

    def bring_to_front(self, hwnd):
        """SetForegroundWindow bị Windows chặn nếu tiến trình không ở trước: nhấn-nhả Alt để được phép."""
        u = self.user32
        for _ in range(20):
            if u.IsIconic(hwnd):
                u.ShowWindow(hwnd, 9)  # SW_RESTORE
            u.keybd_event(0x12, 0, 0, 0)
            u.keybd_event(0x12, 0, 2, 0)
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
            self.pump()
            if u.GetForegroundWindow() == hwnd:
                return
        self.skipTest("Windows không cho đưa cửa sổ thử lên trước (foreground lock)")

    def wait_state(self, expected, timeout=3.0):
        end = time.perf_counter() + timeout
        s = None
        while time.perf_counter() < end:
            self.pump(0.02)
            s = self.probe.sample()
            if s["vdi_state"] == expected:
                return s
        self.fail(f"mong {expected}, đọc được {s and s['vdi_state']} (fg={s and s['fg_title']!r})")

    # ------------------------------------------------------------ các tình huống

    def test_foreground(self):
        self.bring_to_front(self.vdi_hwnd)
        s = self.wait_state("foreground")
        self.assertIn(self.keyword, s["fg_title"].lower())
        self.assertFalse(s["locked"])

    def test_iconify_is_minimized(self):
        self.bring_to_front(self.vdi_hwnd)
        self.wait_state("foreground")
        self.vdi.iconify()
        self.wait_state("minimized")

    def test_minimized_but_still_reported_as_foreground(self):
        """SW_SHOWMINIMIZED: thu nhỏ mà vẫn là cửa sổ active. GetForegroundWindow trả VDI, phải ra minimized."""
        self.bring_to_front(self.vdi_hwnd)
        self.wait_state("foreground")
        self.user32.ShowWindow(self.vdi_hwnd, 2)  # SW_SHOWMINIMIZED
        self.pump(0.2)
        self.assertTrue(self.user32.IsIconic(self.vdi_hwnd))
        if self.user32.GetForegroundWindow() != self.vdi_hwnd:
            self.user32.SetForegroundWindow(self.vdi_hwnd)
            self.pump(0.2)
        s = self.wait_state("minimized")
        self.assertIsNone(s["vdi_full"])
        # Dù GetForegroundWindow có trả VDI hay không, đọc nhiều lần vẫn luôn là minimized.
        for _ in range(20):
            self.assertEqual(self.probe.sample()["vdi_state"], "minimized")

    def test_other_window_on_top_is_background(self):
        self.bring_to_front(self.vdi_hwnd)
        self.wait_state("foreground")
        self.bring_to_front(self.other_hwnd)
        s = self.wait_state("background")
        self.assertNotIn(self.keyword, s["fg_title"].lower())

    def test_destroyed_is_absent(self):
        self.bring_to_front(self.other_hwnd)
        self.wait_state("background")
        self.vdi.destroy()
        self.pump(0.2)
        self.wait_state("absent")

    def test_minimize_restore_20_cycles(self):
        for i in range(20):
            with self.subTest(cycle=i):
                self.bring_to_front(self.vdi_hwnd)
                self.wait_state("foreground")
                self.vdi.iconify()
                self.wait_state("minimized")
                self.vdi.deiconify()
                self.pump()

    def test_tiny_window_with_keyword_is_not_foreground(self):
        """Cửa sổ phụ tí hon (kiểu thanh công cụ Citrix) không bao giờ là VDI ở trước."""
        bar = self.tk.Toplevel(self.root)
        bar.title(f"FocusTest toolbar {self.keyword}")
        bar.geometry("150x60+600+50")
        self.addCleanup(self._destroy, bar)
        self.vdi.iconify()
        self.pump(0.2)
        self.bring_to_front(self.hwnd(bar))
        s = self.wait_state("minimized")
        self.assertIsNone(s["vdi_full"])

    def test_tool_window_with_keyword_is_not_foreground(self):
        bar = self.tk.Toplevel(self.root)
        bar.title(f"FocusTest toolwindow {self.keyword}")
        bar.geometry("400x300+600+50")
        bar.attributes("-toolwindow", True)
        self.addCleanup(self._destroy, bar)
        self.vdi.iconify()
        self.pump(0.2)
        self.bring_to_front(self.hwnd(bar))
        self.wait_state("minimized")

    def test_sample_is_fast(self):
        self.bring_to_front(self.other_hwnd)   # trường hợp nặng nhất: VDI không ở trước, phải tìm cửa sổ VDI
        self.wait_state("background")
        n = 200
        t = time.perf_counter()
        for _ in range(n):
            self.probe.sample()
        per = (time.perf_counter() - t) / n * 1000
        self.probe._next_scan = 0   # thêm một lần quét toàn bộ cửa sổ
        t = time.perf_counter()
        self.probe.sample()
        scan = (time.perf_counter() - t) * 1000
        print(f"\n[win] mỗi lần đọc {per:.3f} ms, quét toàn bộ cửa sổ {scan:.1f} ms", file=sys.stderr)
        self.assertLess(per, 5.0)


if __name__ == "__main__":
    unittest.main()
