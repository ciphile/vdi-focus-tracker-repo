"""Đồ giả dùng chung cho test: cấu hình tạm, Win32 giả, Telegram giả, đồng hồ giả."""
import datetime as dt
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from focus import holidays, logs
from focus import persona
from focus.config import DEFAULTS, validate


TOKEN = "123456:" + "A" * 30  # token giả đúng định dạng


def make_cfg(tmp, **over):
    cfg = dict(DEFAULTS)
    cfg.update({"data_dir": os.path.join(tmp, "data"), "report_dir": os.path.join(tmp, "reports"),
                "timesheet_data_dir": os.path.join(tmp, "timesheet")})
    cfg["auto_start_at"] = "07:00"  # test viết theo khung chạy từ 07:00, không phụ thuộc mặc định của app
    cfg.update(over)
    validate(cfg)
    cfg.setdefault("persona", dict(persona.DEFAULT))
    os.makedirs(cfg["data_dir"], exist_ok=True)
    os.makedirs(cfg["report_dir"], exist_ok=True)
    return cfg


class TempCase(unittest.TestCase):
    """Mỗi test có thư mục dữ liệu riêng, log riêng."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="focus-test-")
        self.cfg = make_cfg(self.tmp)
        logs.reset()
        logs.setup(self.cfg["data_dir"], console=False)
        holidays.clear_memo()
        persona._USED.clear()  # câu nhắc luân phiên: mỗi test bắt đầu vòng mới
        # Test không bao giờ gọi mạng thật (trang MOM): test nào cần tải thì tự mock _download / urlopen.
        guard = mock.patch.object(holidays, "_download", side_effect=OSError("test: không gọi mạng thật"))
        guard.start()
        self.addCleanup(guard.stop)

    def tearDown(self):
        logs.reset()
        holidays.clear_memo()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def audit_lines(self):
        path = os.path.join(self.cfg["data_dir"], "audit.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()


def ts(day, hhmm, sec=0):
    h, m = map(int, hhmm.split(":"))
    d = dt.date.fromisoformat(day) if isinstance(day, str) else day
    return dt.datetime.combine(d, dt.time(h, m, sec)).timestamp()


def sample(vdi="foreground", idle=1.0, locked=False, proc=None, full=True):
    proc = proc if proc is not None else ("cdviewer.exe" if vdi == "foreground" else "chrome.exe")
    return {"idle": idle, "locked": locked, "vdi_state": vdi, "fg_proc": proc, "fg_title": "",
            "vdi_full": full if vdi == "foreground" else None}


def insert_run(db, day, start, minutes, step=5, **kw):
    """Ghi một đoạn mẫu liên tục (giống tracker thật) vào DB. Trả ts của mẫu cuối."""
    t0 = ts(day, start)
    n = int(minutes * 60 / step)
    idle_mode = kw.pop("idle_grow", False)
    rows = []
    for i in range(1, n + 1):
        s = sample(**kw)
        if idle_mode:
            s["idle"] = i * step
        rows.append((t0 + i * step, step, s["idle"], int(s["locked"]), s["vdi_state"], s["fg_proc"], None,
                     None if s["vdi_full"] is None else int(s["vdi_full"])))
    with db:
        db.executemany("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?)", rows)
    return t0 + n * step


class FakeWin32:
    """Màn hình Windows giả: danh sách cửa sổ, cửa sổ đang ở trước, idle, khoá máy."""

    def __init__(self):
        self.windows = {}   # hwnd -> dict(pid, title, visible, iconic, full, owner, tool, rect)
        self.procs = {}     # pid -> tên exe
        self.images = {}    # pid -> đường dẫn đầy đủ của exe (tuỳ chọn; trống thì probe dùng proc_name)
        self.fg = None
        self.idle = 1.0
        self.locked = False
        self.enum_calls = 0
        self.proc_calls = 0

    def add(self, hwnd, exe, title, pid=None, visible=True, iconic=False, full=True, owner=None, tool=False,
            rect=None, image=None):
        """owner: hwnd cửa sổ sở hữu (thanh công cụ thuộc cửa sổ chính); tool: WS_EX_TOOLWINDOW;
        rect: (trái, trên, phải, dưới), mặc định 1920x1080 (thu nhỏ thì ở -32000)."""
        pid = pid or hwnd * 10
        self.procs[pid] = exe
        if image:
            self.images[pid] = image.lower()
        self.windows[hwnd] = {"pid": pid, "title": title, "visible": visible, "iconic": iconic, "full": full,
                              "owner": owner, "tool": tool, "rect": rect}
        return hwnd

    def foreground(self):
        return self.fg

    def idle_seconds(self):
        return self.idle

    def is_locked(self):
        return self.locked

    def title(self, h):
        return self.windows.get(h, {}).get("title", "")

    def pid(self, h):
        return self.windows.get(h, {}).get("pid", 0)

    def proc_name(self, pid):
        self.proc_calls += 1
        return self.procs.get(pid, "")

    def proc_image(self, pid):
        if pid not in self.images:
            return ""
        self.proc_calls += 1
        return self.images[pid]

    def top_windows(self):
        self.enum_calls += 1
        return list(self.windows)

    def is_visible(self, h):
        return self.windows.get(h, {}).get("visible", False)

    def is_iconic(self, h):
        return self.windows.get(h, {}).get("iconic", False)

    def is_window(self, h):
        return h in self.windows

    def root_owner(self, h):
        seen = set()
        while h in self.windows and self.windows[h].get("owner") and h not in seen:
            seen.add(h)
            h = self.windows[h]["owner"]
        return h

    def is_toolwindow(self, h):
        return self.windows.get(h, {}).get("tool", False)

    def rect(self, h):
        w = self.windows.get(h)
        if w is None:
            return None
        if w.get("rect"):
            return w["rect"]
        return (-32000, -32000, -31840, -31972) if w["iconic"] else (0, 0, 1920, 1080)

    def fills_screen(self, h):
        return self.windows.get(h, {}).get("full")


class FakeTelegramAPI:
    def __init__(self):
        self.calls = []
        self.updates = []
        self.fail = 0
        self.lock = threading.Lock()
        self.msg_id = 100

    def call(self, method, params=None, files=None, timeout=40):
        with self.lock:
            if self.fail:
                self.fail -= 1
                raise OSError("network down")
            self.calls.append((method, params or {}, files))
            if method == "getUpdates":
                ups, self.updates = self.updates, []
                return {"ok": True, "result": ups}
            if method == "getFile":
                return {"ok": True, "result": {"file_path": "photos/x.jpg"}}
            self.msg_id += 1
            return {"ok": True, "result": {"message_id": self.msg_id}}

    def download(self, file_path, limit=0):
        return b"\xff\xd8fakejpeg"

    def sent(self):
        return [p.get("text", "") for m, p, f in self.calls if m == "sendMessage"]

    def last(self):
        s = self.sent()
        return s[-1] if s else ""

    def clear(self):
        self.calls.clear()


def msg(text, chat=42, **kw):
    m = {"chat": {"id": chat}, "text": text, "message_id": 1}
    m.update(kw)
    return m
