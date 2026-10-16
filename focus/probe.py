"""Đọc trạng thái máy mỗi lần lấy mẫu: Windows 10/11 (Win32 API qua ctypes) hoặc macOS (CoreGraphics qua ctypes).

Một mẫu = {"idle": giây không chạm phím/chuột, "locked": máy đang khoá,
           "vdi_state": foreground | background | minimized | absent,
           "fg_proc": process đang nhận phím/chuột, "fg_title": tiêu đề cửa sổ đó,
           "vdi_full": VDI đang phóng to / toàn màn hình (chỉ có khi VDI ở trước, còn lại None)}

- foreground: cửa sổ VDI chính (Citrix Desktop Viewer / Citrix Viewer, hoặc tab VDI HTML5 trong trình duyệt)
              đang hiện và đang nhận phím/chuột. Chỉ trạng thái này tính là làm việc.
- background: VDI vẫn mở nhưng app khác đang ở trước (kể cả khi kéo VDI nhỏ lại để làm song song).
- minimized:  mọi cửa sổ VDI đều đang thu nhỏ (taskbar / Dock), bị ẩn (Cmd+H) hoặc nằm ở Space khác.
- absent:     không thấy cửa sổ VDI nào.

Cho nhẹ: chỉ khi VDI không ở trước mới cần tìm cửa sổ VDI. Danh sách cửa sổ VDI được nhớ lại
và chỉ quét lại toàn bộ cửa sổ mỗi 30 giây (hoặc khi cửa sổ cũ đã đóng).

Mỗi probe có thêm: platform_name ("Windows" / "macOS"), method (cách đọc, tiếng Việt), warnings (list câu
cảnh báo tiếng Việt cho /status và lệnh check; list được cập nhật tại chỗ khi phát hiện điều bất thường).
"""
import logging
import ntpath
import os
import sys
import time

from .logs import get_logger

LOCK_SCREEN_PROCS = ("logonui.exe", "lockapp.exe")
RESCAN_SECONDS = 30
PROC_CACHE_SECONDS = 600
PROC_FAIL_CACHE_SECONDS = 30   # không đọc được tên process (quyền Admin, vừa thoát): thử lại sau 30 giây
SURFACE_COVER_SHARE = 0.8      # tool window Citrix lạ phủ >= 80% khung VDI đang hiện = mặt phiên (Citrix đổi tên app)
UNKNOWN_CITRIX_WARN_SIZE = (800, 500)  # cửa sổ Citrix lạ to cỡ này mà không tính là VDI thì ghi cảnh báo
MIN_MAIN_SIZE = 200            # cửa sổ nhỏ hơn 200 px (thanh công cụ Citrix...) không phải cửa sổ VDI chính
GA_ROOTOWNER = 3
WS_EX_TOOLWINDOW = 0x80
DEFAULT_BROWSERS = ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
                    "google chrome", "microsoft edge", "safari", "firefox", "arc", "brave browser")


_LIMITED = {}  # khoá -> lần ghi log gần nhất (time.monotonic)


def log_limited(key, msg, *args, level=logging.WARNING, every=600, exc_info=False, clock=time.monotonic):
    """Ghi log lần đầu, sau đó tối đa 1 lần / 10 phút cho mỗi khoá (lỗi lặp lại mỗi 5 giây không làm phình log).
    Trả True nếu dòng log được ghi."""
    now = clock()
    last = _LIMITED.get(key)
    if last is not None and now - last < every:
        return False
    _LIMITED[key] = now
    get_logger().log(level, msg, *args, exc_info=exc_info)
    return True


class ProbeError(RuntimeError):
    """Không đọc được trạng thái máy trên hệ điều hành này (câu báo lỗi tiếng Việt, đưa thẳng cho người dùng)."""


def browser_title_is_vdi(title, keywords):
    """Tab Citrix HTML5: tiêu đề có tên desktop người dùng khai báo. Trang StoreWeb (danh sách app) không tính."""
    t = (title or "").lower()
    if not t or not keywords or "storeweb" in t:
        return False
    return any(kw in t for kw in keywords)


def _modes(cfg):
    on = bool(cfg.get("vdi_browser_title_keywords"))
    return "app Citrix" + (" + tab trình duyệt (Citrix HTML5)" if on else "")


# ------------------------------------------------------------ Windows

class Win32:
    """Lớp mỏng bọc các hàm Win32 cần dùng. Test thay bằng bản giả có cùng tên hàm."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt
        self.ct, self.wt = ctypes, wt
        u = self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        k = self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._dpi_aware(u)
        u.GetForegroundWindow.restype = wt.HWND
        u.GetForegroundWindow.argtypes = []
        u.OpenInputDesktop.restype = wt.HANDLE
        u.OpenInputDesktop.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        u.SwitchDesktop.argtypes = [wt.HANDLE]
        u.SwitchDesktop.restype = wt.BOOL
        u.CloseDesktop.argtypes = [wt.HANDLE]
        u.CloseDesktop.restype = wt.BOOL
        for fn in ("IsIconic", "IsWindowVisible", "IsWindow"):
            getattr(u, fn).argtypes = [wt.HWND]
            getattr(u, fn).restype = wt.BOOL
        u.GetWindowTextLengthW.argtypes = [wt.HWND]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        u.GetWindowThreadProcessId.restype = wt.DWORD
        u.GetAncestor.argtypes = [wt.HWND, wt.UINT]
        u.GetAncestor.restype = wt.HWND
        # Python 32-bit: user32 không có GetWindowLongPtrW (chỉ là macro), dùng GetWindowLongW.
        self._getlong = getattr(u, "GetWindowLongPtrW", None) or u.GetWindowLongW
        self._getlong.argtypes = [wt.HWND, ctypes.c_int]
        self._getlong.restype = ctypes.c_ssize_t  # LONG_PTR

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]
        self._lii = LASTINPUTINFO()
        self._lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        u.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
        u.GetLastInputInfo.restype = wt.BOOL
        k.GetTickCount.restype = wt.DWORD
        k.GetTickCount.argtypes = []
        k.OpenProcess.restype = wt.HANDLE
        k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k.CloseHandle.argtypes = [wt.HANDLE]
        k.CloseHandle.restype = wt.BOOL
        k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        k.QueryFullProcessImageNameW.restype = wt.BOOL
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        u.EnumWindows.argtypes = [self.WNDENUMPROC, wt.LPARAM]
        u.EnumWindows.restype = wt.BOOL
        self._buf = ctypes.create_unicode_buffer(1024)

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]
        self._mi = MONITORINFO()
        self._mi.cbSize = ctypes.sizeof(MONITORINFO)
        self._rect = wt.RECT()
        u.IsZoomed.argtypes = [wt.HWND]
        u.IsZoomed.restype = wt.BOOL
        u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        u.GetWindowRect.restype = wt.BOOL
        u.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
        u.MonitorFromWindow.restype = wt.HANDLE
        u.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
        u.GetMonitorInfoW.restype = wt.BOOL

    def _dpi_aware(self, u):
        """Toạ độ cửa sổ và màn hình cùng tính bằng pixel thật (màn hình scale 125%/150%), để so 'toàn màn hình'
        cho đúng. Windows 10 1703+: per-monitor v2; Windows cũ hơn: SetProcessDPIAware. Lỗi thì bỏ qua."""
        try:
            fn = u.SetProcessDpiAwarenessContext
            fn.argtypes = [self.ct.c_ssize_t]
            fn.restype = self.wt.BOOL
            if fn(-4):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
                get_logger().debug("DPI: per-monitor v2")
                return
            get_logger().debug("DPI: SetProcessDpiAwarenessContext từ chối (lỗi %s), thử SetProcessDPIAware",
                               self.ct.get_last_error())
        except Exception as e:
            get_logger().debug("DPI: không có SetProcessDpiAwarenessContext (%s), thử SetProcessDPIAware", e)
        try:
            u.SetProcessDPIAware()
        except Exception as e:
            get_logger().warning("DPI: không đặt được chế độ DPI-aware (%s): so 'toàn màn hình' có thể lệch", e)

    def foreground(self):
        return self.user32.GetForegroundWindow()

    def idle_seconds(self):
        if not self.user32.GetLastInputInfo(self.ct.byref(self._lii)):
            return 0.0
        # GetTickCount quay vòng sau 49,7 ngày: phép & giữ hiệu số luôn đúng.
        return ((self.kernel32.GetTickCount() - self._lii.dwTime) & 0xFFFFFFFF) / 1000.0

    def is_locked(self):
        # Màn hình khoá (Win+L) hoặc màn hình UAC: không chuyển được sang input desktop.
        h = self.user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
        if not h:
            return True
        try:
            return not self.user32.SwitchDesktop(h)
        finally:
            self.user32.CloseDesktop(h)

    def title(self, hwnd):
        n = self.user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = self._buf if n < len(self._buf) else self.ct.create_unicode_buffer(n + 1)
        self.user32.GetWindowTextW(hwnd, buf, len(buf))
        return buf.value

    def pid(self, hwnd):
        pid = self.wt.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, self.ct.byref(pid))
        return pid.value

    def proc_image(self, pid):
        """Đường dẫn đầy đủ (chữ thường) của file .exe, "" nếu không đọc được."""
        h = self.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""  # process chạy quyền Admin hoặc đã thoát
        try:
            size = self.wt.DWORD(len(self._buf))
            if self.kernel32.QueryFullProcessImageNameW(h, 0, self._buf, self.ct.byref(size)):
                return self._buf.value.lower()
            return ""
        finally:
            self.kernel32.CloseHandle(h)

    def proc_name(self, pid):
        return ntpath.basename(self.proc_image(pid))

    def top_windows(self):
        found = []
        cb = self.WNDENUMPROC(lambda hwnd, _: found.append(hwnd) or True)
        self.user32.EnumWindows(cb, 0)
        return found

    def is_visible(self, hwnd):
        return bool(self.user32.IsWindowVisible(hwnd))

    def is_iconic(self, hwnd):
        return bool(self.user32.IsIconic(hwnd))

    def is_window(self, hwnd):
        return bool(self.user32.IsWindow(hwnd))

    def root_owner(self, hwnd):
        """Cửa sổ gốc sở hữu hwnd (thanh công cụ Citrix thuộc cửa sổ Desktop Viewer). Không có thì chính nó."""
        return self.user32.GetAncestor(hwnd, GA_ROOTOWNER) or hwnd

    def is_toolwindow(self, hwnd):
        return bool(self._getlong(hwnd, -20) & WS_EX_TOOLWINDOW)  # GWL_EXSTYLE

    def rect(self, hwnd):
        if not self.user32.GetWindowRect(hwnd, self.ct.byref(self._rect)):
            return None
        r = self._rect
        return r.left, r.top, r.right, r.bottom

    def fills_screen(self, hwnd):
        """True nếu cửa sổ đang phóng to (maximize) hoặc phủ kín màn hình (full screen)."""
        if self.user32.IsZoomed(hwnd):
            return True
        mon = self.user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not mon or not self.user32.GetMonitorInfoW(mon, self.ct.byref(self._mi)):
            return None
        if not self.user32.GetWindowRect(hwnd, self.ct.byref(self._rect)):
            return None
        r, m = self._rect, self._mi.rcMonitor
        return r.left <= m.left + 8 and r.top <= m.top + 8 and r.right >= m.right - 8 and r.bottom >= m.bottom - 8


class WindowsProbe:
    platform_name = "Windows"

    def __init__(self, cfg, api=None, clock=time.monotonic):
        self.cfg = cfg
        self.api = api or Win32()
        self.clock = clock
        self._vdi = []           # các cửa sổ VDI chính đã biết
        self._next_scan = 0.0
        # (hwnd, pid) -> (tên process, hết hạn lúc; 0 = tới lần quên chung). Nhớ theo CẶP cửa sổ + pid, không theo
        # pid: Windows tái sử dụng pid rất nhanh, cửa sổ MỚI của process khác mang pid cũ không được dùng tên cũ.
        self._procs = {}
        self._procs_reset = clock() + PROC_CACHE_SECONDS
        self.browser_kw = cfg.get("vdi_browser_title_keywords") or []
        self.browsers = set(cfg.get("browser_processes", DEFAULT_BROWSERS))
        self.session_procs = set(cfg.get("vdi_session_processes") or [])
        self._frame_rects = []   # toạ độ các khung VDI đang hiện (lần quét gần nhất), để nhận mặt phiên Citrix lạ
        self.method = f"Win32 API (cửa sổ + tên tiến trình), nhận VDI qua: {_modes(cfg)}"
        self.warnings = []

    def warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)
            get_logger().info("Probe cảnh báo: %s", text)

    def proc_name(self, hwnd):
        now = self.clock()
        if now >= self._procs_reset:  # cửa sổ đã đóng / handle tái sử dụng: thỉnh thoảng quên hết
            self._procs.clear()
            self._procs_reset = now + PROC_CACHE_SECONDS
        pid = self.api.pid(hwnd)
        key = (hwnd, pid)  # cửa sổ mới (hwnd mới) hoặc hwnd đổi pid: đọc lại tên (1 lần OpenProcess)
        hit = self._procs.get(key)
        if hit is None or (hit[1] and now >= hit[1]):
            image = self.api.proc_image(pid) if hasattr(self.api, "proc_image") else ""
            name = ntpath.basename(image) if image else self.api.proc_name(pid)
            hit = self._procs[key] = (name, 0 if name else now + PROC_FAIL_CACHE_SECONDS, "\\citrix\\" in image)
        return hit[0]

    def is_citrix(self, hwnd, proc=None):
        """Cửa sổ của app Citrix: tên process bắt đầu bằng "citrix", HOẶC file .exe nằm trong thư mục ...\\Citrix\\...
        Citrix từng đổi tên file (cdviewer.exe -> Citrix.DesktopViewer.App.exe) nhưng vẫn cài vào thư mục Citrix."""
        proc = self.proc_name(hwnd) if proc is None else proc
        if proc.startswith("citrix"):
            return True
        hit = self._procs.get((hwnd, self.api.pid(hwnd)))
        return bool(hit and len(hit) > 2 and hit[2])

    def is_vdi(self, proc, title, hwnd=None):
        if proc:  # biết tên process thì chỉ tin tên process (Outlook/Chrome có chữ "Desktop Viewer" không tính)
            if proc in self.cfg["vdi_processes"] or proc in self.session_procs:
                return True
            if proc in self.browsers:
                return browser_title_is_vdi(title, self.browser_kw)
            # Citrix đổi tên file giữa các bản (cdviewer.exe -> Citrix.DesktopViewer.App.exe...): app Citrix (tên bắt
            # đầu bằng "citrix" hoặc nằm trong thư mục Citrix) mà tiêu đề có từ khoá VDI thì vẫn là cửa sổ VDI.
            t = (title or "").lower()
            if not any(kw in t for kw in self.cfg["vdi_title_keywords"]):
                return False
            return proc.startswith("citrix") or (hwnd is not None and self.is_citrix(hwnd, proc))
        t = (title or "").lower()  # không đọc được tên process (Citrix chạy quyền Admin): dựa vào tiêu đề
        return bool(t) and any(kw in t for kw in self.cfg["vdi_title_keywords"])

    def window_kind(self, h):
        """'shown': cửa sổ chính đang hiện; 'min': cửa sổ chính đang thu nhỏ;
        None: cửa sổ phụ (ẩn, thanh công cụ, tool window, tí hon) - không bao giờ tính là VDI."""
        api = self.api
        if not api.is_visible(h):
            return None
        if api.is_toolwindow(h):
            return "shown" if self._is_surface(h) else None
        if api.is_iconic(h):
            return "min"
        root = api.root_owner(h)
        if root and root != h and api.is_iconic(root):
            return None  # cửa sổ phụ của một cửa sổ đang thu nhỏ: chỉ cửa sổ gốc mới quyết định
        r = api.rect(h)
        if r is None:
            return None
        left, top, right, bottom = r
        if left <= -30000 and top <= -30000:  # vị trí -32000 của cửa sổ thu nhỏ
            return "min"
        if right - left < MIN_MAIN_SIZE or bottom - top < MIN_MAIN_SIZE:
            return None
        return "shown"

    def _big_on_screen(self, h, min_w=MIN_MAIN_SIZE, min_h=MIN_MAIN_SIZE):
        if self.api.is_iconic(h):
            return None
        r = self.api.rect(h)
        if r is None or (r[0] <= -30000 and r[1] <= -30000):
            return None
        return r if r[2] - r[0] >= min_w and r[3] - r[1] >= min_h else None

    def _covers_frame(self, r):
        area = (r[2] - r[0]) * (r[3] - r[1])
        for f in self._frame_rects:
            ix = max(0, min(r[2], f[2]) - max(r[0], f[0]))
            iy = max(0, min(r[3], f[3]) - max(r[1], f[1]))
            if area and ix * iy >= SURFACE_COVER_SHARE * area:
                return True
        return False

    def _is_surface(self, h):
        """Cửa sổ 'mặt phiên' của Citrix: tool window đang hiện thật trên màn hình, đủ lớn, nhận phím khi gõ trong VDI
        (máy thật: Citrix.EngineUI.App.exe «MockWindow»). Là process trong vdi_session_processes, hoặc app Citrix tên
        lạ (Citrix đổi tên ở bản sau) mà phủ lên khung Desktop Viewer đang hiện."""
        r = self._big_on_screen(h)
        if r is None:
            return False
        proc = self.proc_name(h)
        if proc in self.session_procs:
            return True
        if not proc or proc in self.cfg["vdi_processes"] or not self.is_citrix(h, proc):
            return False  # thanh công cụ / hộp thoại của Desktop Viewer không phải mặt phiên
        if self._covers_frame(r):
            self.warn(f'Cửa sổ Citrix "{proc}" phủ lên VDI, đang tạm tính là VDI. Nên thêm "{proc}" vào '
                      f'"vdi_session_processes" trong config/settings.json (README mục 4.2).')
            return True
        return False

    def _frame_of(self, h):
        """Khung Desktop Viewer (cửa sổ thường, không phải tool window) đang hiện, hoặc None (VDI ở Full screen)."""
        for w, kind in self.vdi_windows():
            if kind == "shown" and not self.api.is_toolwindow(w):
                return w
        return None

    def front_main(self, fg):
        """Cửa sổ VDI chính đang ở trước, hoặc None. Hộp thoại/thanh công cụ của VDI ở trước thì dùng cửa sổ
        gốc sở hữu nó, nhưng chỉ khi cửa sổ gốc đang hiện thật (không thu nhỏ)."""
        kind = self.window_kind(fg)
        if kind == "shown":
            return fg
        if kind is None:
            root = self.api.root_owner(fg)
            if root and root != fg and self.window_kind(root) == "shown":
                return root
        return None

    def _still_vdi(self, h):
        if not self.api.is_window(h):
            return None
        kind = self.window_kind(h)
        if kind and self.browser_kw and self.proc_name(h) in self.browsers:
            # cửa sổ trình duyệt: tiêu đề đổi theo tab đang mở, tab khác = không còn là VDI
            if not browser_title_is_vdi(self.api.title(h), self.browser_kw):
                return None
        return kind

    def vdi_windows(self):
        """[(hwnd, 'shown' | 'min')] của các cửa sổ VDI chính. Khung Desktop Viewer đã thu nhỏ hết thì mặt phiên
        Citrix (nếu còn hiện) không tính: VDI đang thu nhỏ."""
        found = self._vdi_windows_raw()
        frames = [(h, k) for h, k in found if not self.api.is_toolwindow(h)]
        self._frame_rects = [r for h, k in frames if k == "shown" for r in (self.api.rect(h),) if r]
        return frames if frames and all(k == "min" for _, k in frames) else found

    def _vdi_windows_raw(self):
        now = self.clock()
        if self._vdi and now < self._next_scan:
            known = [(h, k) for h in self._vdi for k in (self._still_vdi(h),) if k]
            if known:
                self._vdi = [h for h, _ in known]
                return known
        found = []
        for h in self.api.top_windows():
            if not self.api.is_visible(h):
                continue
            title = self.api.title(h)
            if title and self.is_vdi(self.proc_name(h), title, h):
                kind = self.window_kind(h)
                if kind:
                    found.append((h, kind))
        self._vdi = [h for h, _ in found]
        self._next_scan = now + RESCAN_SECONDS
        return found

    def sample(self):
        api = self.api
        fg = api.foreground()
        fg_proc = self.proc_name(fg) if fg else ""
        fg_title = api.title(fg) if fg else ""
        locked = fg_proc in LOCK_SCREEN_PROCS or api.is_locked()
        vdi_full = None
        vdi_state = None
        # Thu nhỏ cửa sổ cuối cùng trên màn hình thì Windows có thể vẫn coi nó (hoặc thanh công cụ / cửa sổ ẩn
        # của Citrix) là "foreground": chỉ cửa sổ VDI chính đang hiện thật mới được tính là đang làm trong VDI.
        fg_vdi = bool(fg) and not locked and self.is_vdi(fg_proc, fg_title, fg)
        if fg and not locked and not fg_vdi and fg_proc and api.is_toolwindow(fg) and self.is_citrix(fg, fg_proc):
            self.vdi_windows()  # cập nhật toạ độ khung VDI rồi xét: tool window Citrix tên lạ có phải mặt phiên không
            fg_vdi = self._is_surface(fg)
        if fg_vdi:
            main = self.front_main(fg)
            if main is None and self.session_surface() and (fg_proc in self.session_procs
                                                             or fg_proc in self.cfg["vdi_processes"]
                                                             or self.is_citrix(fg, fg_proc)):
                main = self.session_surface()  # cửa sổ VDI ở trước nhưng bé/ẩn (thanh Full screen...): mặt phiên đang hiện
            if main and api.is_toolwindow(main):  # mặt phiên: phóng to hay không xét theo khung Desktop Viewer
                frame = self._frame_of(main)
                frames = [h for h, _ in self.vdi_windows() if not api.is_toolwindow(h)]
                if not frame and frames:
                    main = None  # còn khung Desktop Viewer nhưng đang thu nhỏ: không tính là đang làm trong VDI
                else:
                    vdi_full = api.fills_screen(frame or main)
            if main:
                vdi_state = "foreground"
                vdi_full = vdi_full if vdi_full is not None else api.fills_screen(main)
                if main not in self._vdi:
                    self._vdi.append(main)
                if not fg_proc:
                    self.warn("Không đọc được tên tiến trình của cửa sổ VDI (Citrix chạy quyền Admin?): "
                              "đang nhận VDI theo tiêu đề cửa sổ.")
        if vdi_state is None:
            wins = self.vdi_windows()
            if not wins:
                vdi_state = "absent"
            elif all(k == "min" for _, k in wins):
                vdi_state = "minimized"
            else:
                vdi_state = "background"
        citrix_fg = bool(fg) and bool(fg_proc) and self.is_citrix(fg, fg_proc)
        if citrix_fg and vdi_state != "foreground" and fg_proc not in self.cfg["vdi_processes"] \
                and fg_proc not in self.session_procs and api.is_toolwindow(fg) \
                and self._big_on_screen(fg, *UNKNOWN_CITRIX_WARN_SIZE):
            self.warn(f'Thấy cửa sổ Citrix lạ "{fg_proc}" ở trước nhưng chưa tính là VDI. Nếu lúc đó bạn đang gõ trong '
                      f'VDI: thêm "{fg_proc}" vào "vdi_session_processes" trong config/settings.json (README mục 4.2).')
        return {"idle": api.idle_seconds(), "locked": locked, "vdi_state": vdi_state,
                "fg_proc": fg_proc, "fg_title": fg_title, "vdi_full": vdi_full,
                "fg_info": self.describe(fg) if citrix_fg else ""}

    def session_surface(self):
        """Mặt phiên Citrix đang hiện trên màn hình (hwnd) hoặc None."""
        if not self.session_procs:
            return None
        for h in self.api.top_windows():
            if self.api.is_visible(h) and self.api.is_toolwindow(h) and self._is_surface(h):
                return h
        return None

    def describe(self, h):
        """Một dòng mô tả cửa sổ (để kiem_tra_may ghi lại khi gặp cửa sổ Citrix lạ): hiện/ẩn, tool, thu nhỏ, kích thước."""
        api = self.api
        r = api.rect(h) or (0, 0, 0, 0)
        return (f"vis={int(api.is_visible(h))} tool={int(api.is_toolwindow(h))} icon={int(api.is_iconic(h))} "
                f"{r[2] - r[0]}x{r[3] - r[1]}@{r[0]},{r[1]} kind={self.window_kind(h)}")


# ------------------------------------------------------------ macOS

RUNLOOP_MAX_EVENTS = 50   # số tin NSWorkspace tối đa xử lý mỗi lần đọc app ở trước
FULL_SCREEN_SHARE = 0.85   # cửa sổ phủ >= 85% một màn hình = toàn màn hình (trừ thanh menu + Dock khi phóng to)
DISPLAY_CACHE_SECONDS = 60
NO_TITLE_WARNING = ("Đang bật nhận VDI qua tab trình duyệt nhưng macOS không cho đọc tiêu đề cửa sổ: tab VDI sẽ KHÔNG "
                    "được tính. Mở System Settings > Privacy & Security > Screen Recording (Ghi màn hình), bật cho "
                    "{program} (tracker tự chạy nền) và Terminal (khi chạy start_tracker.command), rồi chạy lại "
                    "tracker. Không thấy tên trong danh sách thì bấm + và chọn {path}. Hoặc mở VDI bằng app Citrix "
                    "Workspace thay vì trình duyệt.")


def mac_python_program(exe=None):
    """(tên hiện trong System Settings, đường dẫn) của chương trình Python đang chạy, để xin quyền Screen Recording.
    Python cài từ python.org chạy thật bằng Python.app bên trong framework."""
    exe = os.path.realpath(exe or sys.executable or "python3")
    if "/Python.framework/Versions/" in exe and "/bin/" in exe:
        return "Python", exe.split("/bin/")[0] + "/Resources/Python.app"
    return os.path.basename(exe) or "python3", exe
SCRIPT_WARNING = ("Không dùng được CoreGraphics để đọc danh sách cửa sổ: đang dùng AppleScript (System Events), "
                  "cần cấp quyền Accessibility (Trợ năng) cho Terminal/Python trong System Settings > Privacy & "
                  "Security > Accessibility. Cách này chậm hơn và có thể không nhận ra Space khác.")

JXA = r"""
var se = Application("System Events");
var front = "";
try { front = se.processes.whose({frontmost: true})[0].name(); } catch (e) {}
var names = JSON.parse(%s);
var wins = [];
names.forEach(function (n) {
  try {
    var ps = se.processes.whose({name: {_contains: n}})();
    ps.forEach(function (p) {
      var pn = p.name();
      p.windows().forEach(function (w) {
        var m = false;
        try { m = w.attributes.byName("AXMinimized").value(); } catch (e) {}
        wins.push({o: pn, m: m});
      });
    });
  } catch (e) {}
});
JSON.stringify({front: front, wins: wins});
"""


def _win(owner, title=None, bounds=None):
    return {"owner": owner, "layer": 0, "alpha": 1.0, "bounds": bounds, "title": title}


class MacScriptWindows:
    """Dự phòng khi không có CoreGraphics: hỏi System Events bằng osascript (cần quyền Accessibility).
    Trả danh sách cửa sổ cùng dạng với MacAPI.windows (không có toạ độ, không có tiêu đề)."""

    TIMEOUT = 2.0

    def __init__(self, names, clock=time.monotonic):
        self.names, self.clock = list(names), clock
        self._cache, self._at = None, -1e9

    def query(self):
        import json
        import subprocess
        now = self.clock()
        if self._cache is not None and now - self._at < 1.0:  # 1 mẫu gọi 2 lần (trên màn hình / tất cả)
            return self._cache
        script = JXA % json.dumps(json.dumps(self.names))
        try:
            out = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True,
                                 text=True, timeout=self.TIMEOUT).stdout
            data = json.loads(out or "{}")
        except Exception as e:
            log_limited("mac-osascript-" + type(e).__name__, "osascript (System Events) lỗi: %s: %s",
                        type(e).__name__, e)
            data = {}
        if not isinstance(data, dict):  # osascript in ra JSON lạ (null, chuỗi...): coi như không đọc được
            data = {}
        wins = data.get("wins")
        wins = [w for w in wins if isinstance(w, dict)] if isinstance(wins, list) else []
        self._cache, self._at = (str(data.get("front") or ""), wins), now
        return self._cache

    def windows(self, onscreen, titles_for=None):
        front, wins = self.query()
        if not onscreen:
            return [_win(str(w.get("o") or "")) for w in wins]
        shown = [_win(str(w.get("o") or "")) for w in wins if not w.get("m")]
        mine = [w for w in shown if w["owner"] == front]
        others = [w for w in shown if w["owner"] != front]
        if mine:
            return mine + others
        known = {str(w.get("o") or "") for w in wins}
        if front and front not in known:  # app khác ở trước (không biết cửa sổ của nó, coi như có 1)
            return [_win(front)] + others
        return others  # app VDI ở trước nhưng mọi cửa sổ đã thu nhỏ: không có gì ở trước


class MacAPI:
    """Đọc trạng thái trên macOS bằng CoreGraphics qua ctypes, KHÔNG cần quyền Accessibility/Automation:
    - CGWindowListCopyWindowInfo: danh sách cửa sổ (trên màn hình: xếp từ trước ra sau) + tên app + toạ độ.
      Tiêu đề cửa sổ chỉ có khi được quyền Screen Recording, nên chỉ dùng cho tab trình duyệt.
    - CGEventSourceSecondsSinceLastEventType: idle. CGSessionCopyCurrentDictionary: khoá màn hình.
    Không có CoreGraphics window list thì dùng AppleScript (MacScriptWindows) làm dự phòng."""

    UTF8 = 0x08000100

    def __init__(self, names=("Citrix Viewer",)):
        import ctypes
        import ctypes.util
        self.ct = ctypes
        self.warnings = []
        try:
            cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics") or
                                         "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation") or
                                         "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        except OSError as e:
            raise ProbeError(f"Không nạp được CoreGraphics/CoreFoundation của macOS ({e}).") from e
        c_void_p, c_bool, c_long = ctypes.c_void_p, ctypes.c_bool, ctypes.c_long
        cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
        cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        cg.CGSessionCopyCurrentDictionary.restype = c_void_p
        cg.CGSessionCopyCurrentDictionary.argtypes = []
        cf.CFStringCreateWithCString.restype = c_void_p
        cf.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFDictionaryGetValue.restype = c_void_p
        cf.CFDictionaryGetValue.argtypes = [c_void_p, c_void_p]
        cf.CFBooleanGetValue.restype = c_bool
        cf.CFBooleanGetValue.argtypes = [c_void_p]
        cf.CFRelease.argtypes = [c_void_p]
        cf.CFRelease.restype = None
        cf.CFArrayGetCount.restype = c_long
        cf.CFArrayGetCount.argtypes = [c_void_p]
        cf.CFArrayGetValueAtIndex.restype = c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        cf.CFNumberGetValue.restype = c_bool
        cf.CFNumberGetValue.argtypes = [c_void_p, ctypes.c_int, c_void_p]
        cf.CFStringGetCStringPtr.restype = c_void_p
        cf.CFStringGetCStringPtr.argtypes = [c_void_p, ctypes.c_uint32]
        cf.CFStringGetCString.restype = c_bool
        cf.CFStringGetCString.argtypes = [c_void_p, ctypes.c_char_p, c_long, ctypes.c_uint32]
        self.cg, self.cf = cg, cf
        self._cfstr = lambda s: cf.CFStringCreateWithCString(None, s.encode(), self.UTF8)  # giữ suốt đời tiến trình
        self._lock_key = self._cfstr("CGSSessionScreenIsLocked")
        self._console_key = self._cfstr("kCGSSessionOnConsoleKey")
        self._sbuf = ctypes.create_string_buffer(1024)
        self._int, self._dbl = ctypes.c_int(), ctypes.c_double()

        class CGRect(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("w", ctypes.c_double), ("h", ctypes.c_double)]
        self.CGRect = CGRect
        self._rect = CGRect()
        self.script = None
        self._preflight = self._request = None
        try:
            cg.CGWindowListCopyWindowInfo.restype = c_void_p
            cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
            cg.CGRectMakeWithDictionaryRepresentation.restype = c_bool
            cg.CGRectMakeWithDictionaryRepresentation.argtypes = [c_void_p, ctypes.POINTER(CGRect)]
            cg.CGGetActiveDisplayList.restype = ctypes.c_int32
            cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                                  ctypes.POINTER(ctypes.c_uint32)]
            cg.CGDisplayBounds.restype = CGRect
            cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
            self._preflight = getattr(cg, "CGPreflightScreenCaptureAccess", None)
            self._request = getattr(cg, "CGRequestScreenCaptureAccess", None)
            for fn in (self._preflight, self._request):
                if fn is not None:
                    fn.restype, fn.argtypes = c_bool, []
        except AttributeError as e:
            get_logger().warning("CoreGraphics thiếu hàm đọc cửa sổ (%s): dùng AppleScript dự phòng", e)
            self.script = MacScriptWindows(names)
            self.warnings.append(SCRIPT_WARNING)
        self.method = ("AppleScript/System Events (dự phòng, cần quyền Accessibility)" if self.script else
                       "CoreGraphics (danh sách cửa sổ + tên app, không cần quyền Trợ năng)")
        self.K = {k: self._cfstr(v) for k, v in (
            ("layer", "kCGWindowLayer"), ("owner", "kCGWindowOwnerName"), ("bounds", "kCGWindowBounds"),
            ("alpha", "kCGWindowAlpha"), ("name", "kCGWindowName"), ("pid", "kCGWindowOwnerPID"))}
        self._objc = None
        self._init_front_app()

    def _init_front_app(self):
        """App đang nhận phím/chuột: NSWorkspace.frontmostApplication qua libobjc (KHÔNG cần quyền gì).
        Lỗi bất kỳ (không có AppKit...) thì bỏ, MacProbe dùng cách cũ (chủ cửa sổ trên cùng)."""
        ct = self.ct
        try:
            import ctypes.util
            objc = ct.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
            ct.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")  # NSWorkspace nằm ở AppKit
            objc.objc_getClass.restype = ct.c_void_p
            objc.objc_getClass.argtypes = [ct.c_char_p]
            objc.sel_registerName.restype = ct.c_void_p
            objc.sel_registerName.argtypes = [ct.c_char_p]
            objc.objc_autoreleasePoolPush.restype = ct.c_void_p
            objc.objc_autoreleasePoolPush.argtypes = []
            objc.objc_autoreleasePoolPop.restype = None
            objc.objc_autoreleasePoolPop.argtypes = [ct.c_void_p]
            addr = ct.cast(objc.objc_msgSend, ct.c_void_p).value
            # objc_msgSend phải gọi đúng kiểu trả về (arm64 không chấp nhận gọi kiểu variadic).
            self._msg_obj = ct.CFUNCTYPE(ct.c_void_p, ct.c_void_p, ct.c_void_p)(addr)
            self._msg_int = ct.CFUNCTYPE(ct.c_int32, ct.c_void_p, ct.c_void_p)(addr)
            sel = objc.sel_registerName
            cls = objc.objc_getClass(b"NSWorkspace")
            ws = self._msg_obj(cls, sel(b"sharedWorkspace")) if cls else None
            if not ws:
                raise OSError("không có NSWorkspace")
            self._ws, self._objc = ws, objc
            self._sel = {k: sel(k.encode()) for k in ("frontmostApplication", "processIdentifier",
                                                       "localizedName", "UTF8String")}
            # Không có run loop chạy thì NSWorkspace không nhận tin "app khác lên trước": chạy run loop 0 giây
            # mỗi lần hỏi để nó cập nhật (MacProbe vẫn chỉ tin kết quả sau khi thấy nó đổi ít nhất một lần).
            cf = self.cf
            cf.CFRunLoopRunInMode.restype = ct.c_int32
            cf.CFRunLoopRunInMode.argtypes = [ct.c_void_p, ct.c_double, ct.c_bool]
            self._rl_mode = ct.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode").value
        except Exception as e:
            self._objc = None
            get_logger().info("Không đọc được app đang ở trước qua NSWorkspace (%s): dùng cửa sổ trên cùng", e)

    def front_app(self):
        """(pid, tên) của app đang ở trước (nhận phím/chuột), hoặc None nếu không đọc được."""
        objc = self._objc
        if objc is None:
            return None
        pool = objc.objc_autoreleasePoolPush()
        try:
            if self._rl_mode:  # xử lý hết tin đang chờ (mỗi lần gọi chỉ xử lý 1 tin; 4 = vừa xử lý xong 1 tin)
                for _ in range(RUNLOOP_MAX_EVENTS):
                    if self.cf.CFRunLoopRunInMode(self._rl_mode, 0.0, True) != 4:
                        break
            app = self._msg_obj(self._ws, self._sel["frontmostApplication"])
            if not app:
                return None
            pid = self._msg_int(app, self._sel["processIdentifier"])
            name = ""
            ns = self._msg_obj(app, self._sel["localizedName"])
            if ns:
                p = self._msg_obj(ns, self._sel["UTF8String"])
                if p:
                    name = self.ct.string_at(p).decode("utf-8", "replace")
            return (pid, name) if pid > 0 else None
        finally:
            objc.objc_autoreleasePoolPop(pool)

    # ---------------------------------------------------------- đọc giá trị CoreFoundation (không cần release)

    def _str(self, d, key):
        v = self.cf.CFDictionaryGetValue(d, key)
        if not v:
            return ""
        p = self.cf.CFStringGetCStringPtr(v, self.UTF8)
        if p:
            return self.ct.string_at(p).decode("utf-8", "replace")
        if self.cf.CFStringGetCString(v, self._sbuf, len(self._sbuf), self.UTF8):
            return self._sbuf.value.decode("utf-8", "replace")
        return ""

    def _num(self, d, key, default, double=False):
        v = self.cf.CFDictionaryGetValue(d, key)
        out = self._dbl if double else self._int
        if not v or not self.cf.CFNumberGetValue(v, 13 if double else 9, self.ct.byref(out)):  # Double / Int
            return default
        return out.value

    def _bounds(self, d):
        v = self.cf.CFDictionaryGetValue(d, self.K["bounds"])
        if not v or not self.cg.CGRectMakeWithDictionaryRepresentation(v, self.ct.byref(self._rect)):
            return None
        r = self._rect
        return (r.x, r.y, r.w, r.h)

    # ---------------------------------------------------------- API cho MacProbe

    def windows(self, onscreen, titles_for=None):
        """Cửa sổ lớp 0 (cửa sổ app bình thường). onscreen=True: chỉ cửa sổ đang hiện ở Space hiện tại, xếp từ
        trước ra sau; False: mọi cửa sổ kể cả thu nhỏ xuống Dock, app bị ẩn (Cmd+H), Space khác.
        titles_for(owner_lower) -> True thì đọc thêm tiêu đề (cần quyền Screen Recording, không có thì "")."""
        if self.script:
            return self.script.windows(onscreen, titles_for)
        # kCGWindowListOptionOnScreenOnly (1) | ExcludeDesktopElements (16); All = 0
        arr = self.cg.CGWindowListCopyWindowInfo(17 if onscreen else 16, 0)
        if not arr:
            return []
        K, out = self.K, []
        try:
            for i in range(self.cf.CFArrayGetCount(arr)):
                d = self.cf.CFArrayGetValueAtIndex(arr, i)
                if not d or self._num(d, K["layer"], -1) != 0:
                    continue
                owner = self._str(d, K["owner"])
                title = self._str(d, K["name"]) if titles_for and titles_for(owner.lower()) else None
                out.append({"owner": owner, "layer": 0, "alpha": self._num(d, K["alpha"], 1.0, True),
                            "bounds": self._bounds(d), "title": title, "pid": self._num(d, K["pid"], None)})
        finally:
            self.cf.CFRelease(arr)
        return out

    def displays(self):
        """Toạ độ (x, y, rộng, cao) các màn hình đang bật, cùng hệ toạ độ với kCGWindowBounds."""
        if self.script:
            return []
        ids = (self.ct.c_uint32 * 16)()
        n = self.ct.c_uint32()
        if self.cg.CGGetActiveDisplayList(16, ids, self.ct.byref(n)) != 0:
            return []
        out = []
        for i in range(n.value):
            r = self.cg.CGDisplayBounds(ids[i])
            out.append((r.x, r.y, r.w, r.h))
        return out

    def can_read_titles(self):
        """True/False: tiến trình này có quyền Screen Recording (đọc tiêu đề cửa sổ app khác) không; None: không rõ."""
        return bool(self._preflight()) if self._preflight else None

    def ask_title_permission(self):
        """Hiện hộp thoại macOS xin quyền Screen Recording cho chính chương trình đang chạy (1 lần) và thêm nó vào
        danh sách trong System Settings. Quyền mới chỉ có tác dụng sau khi chạy lại tracker."""
        if self._request:
            self._request()

    def idle_seconds(self):
        return float(self.cg.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF))  # HID state, mọi loại input

    def is_locked(self):
        d = self.cg.CGSessionCopyCurrentDictionary()
        if not d:
            return True  # không có phiên đăng nhập màn hình (đang ở màn hình đăng nhập / chuyển user)
        try:
            v = self.cf.CFDictionaryGetValue(d, self._lock_key)
            if v and self.cf.CFBooleanGetValue(v):
                return True
            c = self.cf.CFDictionaryGetValue(d, self._console_key)
            return bool(c) and not self.cf.CFBooleanGetValue(c)  # user khác đang dùng màn hình (Fast User Switching)
        finally:
            self.cf.CFRelease(d)


def _covers_display(bounds, displays):
    if not bounds or not displays:
        return None
    x, y, w, h = bounds
    for dx, dy, dw, dh in displays:
        if dw <= 0 or dh <= 0:
            continue
        iw = min(x + w, dx + dw) - max(x, dx)
        ih = min(y + h, dy + dh) - max(y, dy)
        if iw > 0 and ih > 0 and iw * ih >= FULL_SCREEN_SHARE * dw * dh:
            return True
    return False


class MacProbe:
    """Trạng thái VDI trên MacBook (Citrix Workspace for Mac: app "Citrix Viewer"), chỉ từ danh sách cửa sổ:
    - app ở trước = chủ của cửa sổ lớp 0 đầu tiên trên màn hình. Là app VDI -> foreground.
    - còn cửa sổ VDI nào trên màn hình (sau app khác) -> background.
    - cửa sổ VDI chỉ còn trong danh sách đầy đủ (thu nhỏ xuống Dock, Cmd+H, ở Space toàn màn hình khác) -> minimized.
    App Citrix ở trước mà không còn cửa sổ nào hiện (vừa thu nhỏ cửa sổ cuối) thì cửa sổ đầu tiên là của app khác,
    nên tự nhiên ra minimized, không bao giờ là foreground."""

    platform_name = "macOS"

    def __init__(self, cfg, api=None, clock=time.monotonic):
        self.cfg = cfg
        self.apps = [p for p in cfg["vdi_processes"] if not p.endswith(".exe")] or ["citrix viewer"]
        self.browsers = {b for b in cfg.get("browser_processes", DEFAULT_BROWSERS) if not b.endswith(".exe")}
        self.browser_kw = cfg.get("vdi_browser_title_keywords") or []
        self.clock = clock
        names = [" ".join(w.capitalize() for w in n.split()) for n in self.apps]  # "Citrix Viewer"
        self.api = api or MacAPI(names)
        self.warnings = list(getattr(self.api, "warnings", []))
        self.method = f"{getattr(self.api, 'method', 'CoreGraphics')}, nhận VDI qua: {_modes(cfg)}"
        self._displays, self._displays_at = [], -1e9
        self._titles_for = (lambda owner: owner in self.browsers) if self.browser_kw else None
        self._check_title_permission()
        self._front_seen = set()  # các pid app-ở-trước đã thấy: chỉ tin NSWorkspace sau khi thấy nó đổi (>= 2 pid)
        self._front_trusted = False

    def warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)
            get_logger().info("Probe cảnh báo: %s", text)

    def _check_title_permission(self):
        """Nhận VDI qua tab trình duyệt cần đọc tiêu đề cửa sổ = quyền Screen Recording. Chưa có thì xin (macOS hiện
        hộp thoại 1 lần) và cảnh báo ghi rõ chương trình cần bật."""
        if not self.browser_kw or not hasattr(self.api, "can_read_titles"):
            return
        try:
            if self.api.can_read_titles() is False:
                self.warn(self.no_title_warning())
                self.api.ask_title_permission()
        except Exception as e:
            log_limited("mac-screen-perm-" + type(e).__name__, "Không kiểm tra được quyền Screen Recording: %s: %s",
                        type(e).__name__, e)

    @staticmethod
    def no_title_warning():
        program, path = mac_python_program()
        return NO_TITLE_WARNING.format(program=f"«{program}»", path=path)

    def is_vdi(self, w, seen):
        owner = (w.get("owner") or "").lower()
        if any(n in owner for n in self.apps):
            return True
        if self.browser_kw and owner in self.browsers:
            seen.append(w.get("title") or "")
            return browser_title_is_vdi(w.get("title"), self.browser_kw)
        return False

    @staticmethod
    def _real(w):
        """Cửa sổ app bình thường: lớp 0, không trong suốt, không tí hon (bỏ cửa sổ phụ vô hình)."""
        if w.get("layer", 0) != 0 or (w.get("alpha") is not None and w["alpha"] <= 0):
            return False
        b = w.get("bounds")
        return not b or (b[2] >= 50 and b[3] >= 50)

    def displays(self):
        now = self.clock()
        if now - self._displays_at >= DISPLAY_CACHE_SECONDS or not self._displays:
            try:
                self._displays = list(self.api.displays())
            except Exception as e:
                log_limited("mac-displays-" + type(e).__name__, "Không đọc được danh sách màn hình: %s: %s",
                            type(e).__name__, e)
                self._displays = []
            self._displays_at = now
        return self._displays

    def front_app(self):
        """(pid, tên) app đang nhận phím/chuột theo NSWorkspace, hoặc None (không có / lỗi / chưa chắc còn cập nhật).
        Chỉ tin sau khi đã thấy giá trị đổi ít nhất một lần: nếu NSWorkspace bị "đứng" (không nhận tin đổi app)
        thì không bao giờ được hạ VDI đang ở trước thành "background" vì một giá trị cũ."""
        fn = getattr(self.api, "front_app", None)
        if fn is None:
            return None
        try:
            app = fn()
        except Exception as e:
            log_limited("mac-front-" + type(e).__name__, "Không đọc được app đang ở trước: %s: %s",
                        type(e).__name__, e)
            return None
        if not app:
            return None
        if not self._front_trusted:
            self._front_seen.add(app[0])
            if len(self._front_seen) < 2:
                return None
            self._front_trusted = True
            self._front_seen.clear()
            get_logger().info("macOS: dùng app đang ở trước từ NSWorkspace (đã thấy đổi app).")
        return app

    def sample(self):
        api = self.api
        locked = api.is_locked()
        on = [w for w in api.windows(True, self._titles_for) if self._real(w)]
        front = on[0] if on else None
        fg_proc = (front.get("owner") or "").lower() if front else ""
        app = self.front_app() if front is not None and front.get("pid") is not None else None
        if app and front.get("pid") != app[0]:
            # App đang nhận phím/chuột không phải chủ cửa sổ trên cùng (bấm ra desktop Finder, Cmd+Tab sang app
            # không có cửa sổ phía trên): cửa sổ "ở trước" là cửa sổ trên cùng của chính app đó, nếu có.
            mine = [w for w in on if w.get("pid") == app[0]]
            front = mine[0] if mine else None
            fg_proc = (front.get("owner") or "").lower() if front else (app[1] or "").lower()
        fg_title = (front.get("title") or "") if front else ""
        seen = []
        vdi_on = [w for w in on if self.is_vdi(w, seen)]
        if self.browser_kw and seen and not any(seen):
            self.warn(self.no_title_warning())
        vdi_full = None
        if front is not None and vdi_on and vdi_on[0] is front and not locked:
            state = "foreground"
            disp = self.displays()
            covers = [_covers_display(w.get("bounds"), disp) for w in vdi_on if w.get("owner") == front.get("owner")]
            vdi_full = True if any(covers) else (None if all(c is None for c in covers) else False)
        elif vdi_on:
            state = "background"
        else:
            allw = [w for w in api.windows(False, self._titles_for) if self._real(w)]
            state = "minimized" if any(self.is_vdi(w, []) for w in allw) else "absent"
            if state == "absent":
                for w in allw:
                    owner = w.get("owner") or ""
                    if "citrix" in owner.lower() and "workspace" not in owner.lower():
                        self.warn(f'Thấy app "{owner}" nhưng không có trong "vdi_processes": nếu đây là cửa sổ VDI, '
                                  f'thêm "{owner.lower()}" vào vdi_processes trong config/settings.json.')
                        break
        return {"idle": api.idle_seconds(), "locked": locked, "vdi_state": state,
                "fg_proc": fg_proc, "fg_title": fg_title, "vdi_full": vdi_full}


# ------------------------------------------------------------ chọn theo hệ điều hành

OS_NAMES = {"windows": "Windows", "mac": "macOS"}


def make_probe(cfg, os_name=None):
    """Chọn probe theo cfg["platform"] ("auto" = theo máy đang chạy). Sai/không hỗ trợ -> ProbeError tiếng Việt."""
    real = os_name or sys.platform
    kind = "windows" if real == "win32" else "mac" if real == "darwin" else None
    want = cfg.get("platform") or "auto"
    if kind is None:
        raise ProbeError(f"Hệ điều hành này ({real}) chưa được hỗ trợ: Focus Tracker chỉ chạy trên Windows 10/11 "
                         "hoặc macOS (MacBook), nơi bạn mở cửa sổ Citrix VDI.")
    if want not in ("auto", kind):
        raise ProbeError(f'config/settings.json đặt "platform": "{want}" ({OS_NAMES.get(want, want)}) nhưng máy này '
                         f'là {OS_NAMES[kind]}. Sửa thành "platform": "auto" (tự nhận) hoặc "{kind}".')
    return WindowsProbe(cfg) if kind == "windows" else MacProbe(cfg)
