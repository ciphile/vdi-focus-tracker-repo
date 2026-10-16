"""Giờ tự bật của máy (Task Scheduler / launchd) và ghi giờ bật/tắt vào config/settings.json, cho /giobot.

Mọi lời gọi hệ điều hành nằm ở đây (dễ thay bằng đồ giả khi test; test KHÔNG BAO GIỜ gọi schtasks/launchctl thật):
- _run(cmd, timeout): chạy lệnh ẩn (Windows: CREATE_NO_WINDOW), trả (mã thoát, chữ in ra).
- os_kind(cfg): "windows" | "mac" | "other".

Windows (không cần quyền admin): sửa đúng trigger theo lịch (CalendarTrigger thứ 2 – thứ 6) của task "FocusTracker"
qua COM Schedule.Service (PowerShell), giữ nguyên trigger đăng nhập / thức dậy. Không được thì thử
`schtasks /Change /TN FocusTracker /ST HH:MM`. Vẫn lỗi: báo nhấp đúp lại cai_tu_khoi_dong.bat (script đọc giờ trong
settings.json, nên ghi settings.json là bước quan trọng).

Mac: chỉ ghi lại StartCalendarInterval trong ~/Library/LaunchAgents/<label>.plist. KHÔNG gọi launchctl
bootout/bootstrap: job đó chính là tracker đang chạy, bootout sẽ giết luôn nó (mất mẫu chưa ghi, không chốt ngày).
launchd đọc lại file khi đăng nhập lại / khởi động lại máy, hoặc khi chạy lại cai_tu_khoi_dong_mac.sh.

Không hàm nào raise: lỗi -> (False, câu tiếng Việt) + log + audit.
"""
import base64
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

from .config import ROOT
from .logs import audit, get_logger

log = get_logger()

TASK_NAME = "FocusTracker"
DEFAULT_LABEL = "com.focustracker.agent"
MAC_INSTALLER = "cai_tu_khoi_dong_mac.sh"
RUN_TIMEOUT = 15
CREATE_NO_WINDOW = 0x08000000
WIN_FIX = "Nhấp đúp lại cai_tu_khoi_dong.bat trên máy: file này đọc giờ bật mới trong config/settings.json."
MAC_FIX = "Nhấp đúp lại cai_tu_khoi_dong.command trên máy (file này đọc giờ bật mới trong config/settings.json)."


# ------------------------------------------------------------ chỗ chạm hệ điều hành (test thay thế)

def os_kind(cfg):
    p = (cfg or {}).get("platform") or "auto"
    if p in ("windows", "mac"):
        return p
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "other"


def _run(cmd, timeout=RUN_TIMEOUT):
    """Chạy lệnh, không hiện cửa sổ. Trả (mã thoát, stdout+stderr). Không tìm thấy / quá giờ: (None, lý do)."""
    kw = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, **kw)
    except FileNotFoundError:
        return None, f"không có lệnh {cmd[0]}"
    except subprocess.TimeoutExpired:
        return None, f"{cmd[0]} quá {timeout} giây không trả lời"
    except OSError as e:
        return None, f"{type(e).__name__}: {e}"
    return r.returncode, (r.stdout or b"").decode("utf-8", "replace").strip()


# ------------------------------------------------------------ settings.json

def read_settings(path):
    """Đọc settings.json. Trả dict ({} nếu chưa có file), hoặc None nếu không đọc được / sai JSON."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("Không đọc được %s: %s", path, e)
        return None
    return data if isinstance(data, dict) else None


def write_settings(path, updates):
    """Ghi các khoá trong updates vào settings.json (giá trị None = xoá khoá), giữ nguyên mọi khoá khác và thứ tự,
    giữ BOM / CRLF / độ thụt dòng của file cũ. Ghi ra file tạm rồi os.replace (không bao giờ để file ghi dở),
    bản cũ lưu ở settings.json.bak. Trả (True, "") hoặc (False, lý do tiếng Việt)."""
    if not path:
        return False, "không biết file settings.json ở đâu"
    raw = b""
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            return False, f"không đọc được file ({type(e).__name__}: {e})"
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("utf-8", "replace") if bom else raw.decode("utf-8", "replace")
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError as e:
        return False, f"file đang sai cú pháp JSON ({e}), mình không ghi đè"
    if not isinstance(data, dict):
        return False, "file không phải một object JSON {...}"
    for k, v in updates.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    m = re.search(r"\n([ \t]+)\S", text)
    indent = m.group(1) if m and "\t" in m.group(1) else (len(m.group(1)) if m else 2)
    out = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
    if "\r\n" in text:
        out = out.replace("\n", "\r\n")
    folder = os.path.dirname(os.path.abspath(path))
    tmp = None
    try:
        os.makedirs(folder, exist_ok=True)
        if raw:
            shutil.copyfile(path, path + ".bak")
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "wb") as f:
            f.write((b"\xef\xbb\xbf" if bom else b"") + out.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
    except OSError as e:
        log.warning("Không ghi được %s: %s", path, e, exc_info=True)
        return False, f"{type(e).__name__}: {e}"
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    log.info("Đã ghi %s vào %s (bản cũ: %s)", updates, path, ".bak" if raw else "chưa có")
    audit("SETTINGS_WRITE", json.dumps(updates, ensure_ascii=False))
    return True, ""


# ------------------------------------------------------------ Windows: Task Scheduler

PS_SCRIPT = r"""$ErrorActionPreference = 'Stop'
try { $s = New-Object -ComObject Schedule.Service; $s.Connect() } catch { Write-Output ('ERR ' + $_.Exception.Message); exit 3 }
$f = $s.GetFolder('\')
try { $t = $f.GetTask('{task}') } catch { Write-Output 'NOTASK'; exit 2 }
$d = $t.Definition
$n = 0
foreach ($tr in $d.Triggers) {
  if ($tr.Type -eq 2 -or $tr.Type -eq 3) {
    $tr.StartBoundary = ($tr.StartBoundary -replace 'T\d{1,2}:\d{2}(:\d{2})?', 'T{hhmm}:00')
    $n++
  }
}
if ($n -eq 0) { Write-Output 'NOTRIGGER'; exit 4 }
try { $null = $f.RegisterTaskDefinition('{task}', $d, 4, $null, $null, 3) } catch { Write-Output ('ERR ' + $_.Exception.Message); exit 5 }
Write-Output ('OK ' + $n)
"""


def _windows(hhmm):
    """Đổi giờ trigger theo lịch của task FocusTracker. Trả (ok, mã trạng thái, chi tiết)."""
    script = PS_SCRIPT.replace("{task}", TASK_NAME).replace("{hhmm}", hhmm)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    code, out = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-EncodedCommand", encoded])
    log.info("PowerShell đổi giờ task %s -> %s: mã %s, %s", TASK_NAME, hhmm, code, (out or "")[:300])
    if code == 0 and "OK" in (out or ""):
        return True, "ok", "PowerShell"
    if code == 2 or "NOTASK" in (out or ""):
        return False, "missing", f"chưa có task {TASK_NAME} trong Task Scheduler (chưa cài tự khởi động?)"
    # COM bị chặn / không có PowerShell / task không có trigger theo lịch: thử schtasks.
    code2, out2 = _run(["schtasks", "/Change", "/TN", TASK_NAME, "/ST", hhmm])
    log.info("schtasks /Change /ST %s: mã %s, %s", hhmm, code2, (out2 or "")[:300])
    if code2 == 0:
        return True, "ok", "schtasks"
    detail = ((out2 or out or "").splitlines() or ["lỗi không rõ"])[0][:200]
    return False, "error", detail


# ------------------------------------------------------------ Mac: launchd

def mac_label(root=ROOT):
    """Label của launchd job, đọc từ cai_tu_khoi_dong_mac.sh (LABEL="...")."""
    try:
        with open(os.path.join(root, MAC_INSTALLER), encoding="utf-8") as f:
            m = re.search(r'^LABEL="([^"]+)"', f.read(), re.M)
        if m:
            return m.group(1)
    except OSError as e:
        log.debug("Không đọc được %s: %s", MAC_INSTALLER, e)
    return DEFAULT_LABEL


MAC_PROTECTED = ("Documents", "Desktop", "Downloads", "Library/Mobile Documents", "Library/CloudStorage")


def mac_protected_folder(path, home=None):
    """Tên thư mục macOS chặn chương trình chạy nền (launchd) đọc khi chưa cấp quyền, nếu path nằm trong đó; không thì
    None. Cùng danh sách với cai_tu_khoi_dong_mac.sh."""
    home = (home or os.path.expanduser("~")).rstrip("/")
    full = os.path.abspath(path).rstrip("/") + "/"
    for name in MAC_PROTECTED:
        if full.startswith(f"{home}/{name}/"):
            return name
    return None


def mac_last_exit(text):
    """Đọc output `launchctl print`: (đang chạy?, mã thoát lần gần nhất hoặc None, mô tả)."""
    running = re.search(r"^\s*state = running\s*$", text, re.M) is not None
    m = re.search(r"^\s*last exit code = (-?\d+)(?::\s*(.*))?$", text, re.M)
    if not m:
        return running, None, ""
    return running, int(m.group(1)), (m.group(2) or "").strip()


def mac_plist_path(cfg):
    folder = (cfg or {}).get("_launch_agents_dir") or os.path.expanduser("~/Library/LaunchAgents")
    return os.path.join(folder, mac_label() + ".plist")


def _mac(cfg, hhmm):
    path = mac_plist_path(cfg)
    if not os.path.exists(path):
        return False, "missing", f"chưa có {path} (chưa cài tự khởi động?)"
    h, m = (int(x) for x in hhmm.split(":"))
    tmp = None
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
        data["StartCalendarInterval"] = [{"Weekday": d, "Hour": h, "Minute": m} for d in range(1, 6)]
        fd, tmp = tempfile.mkstemp(prefix=".focus-", suffix=".plist", dir=os.path.dirname(path))
        with os.fdopen(fd, "wb") as f:
            plistlib.dump(data, f)
        os.replace(tmp, path)
        tmp = None
    except Exception as e:  # plist hỏng, không có quyền ghi...
        log.warning("Không sửa được %s: %s", path, e, exc_info=True)
        return False, "error", f"{type(e).__name__}: {e}"
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    log.info("Đã ghi giờ bật %s vào %s (launchd đọc lại khi đăng nhập lại / khởi động lại máy).", hhmm, path)
    return True, "ok", path


# ------------------------------------------------------------ dùng từ /giobot

def update_start_time(cfg, hhmm):
    """Đặt giờ tự bật (thứ 2 – thứ 6) của máy = hhmm. Trả (ok, câu báo tiếng Việt). Không bao giờ raise."""
    if not (cfg or {}).get("_autostart_sync"):
        log.info("Bỏ qua sửa lịch tự khởi động của máy (cấu hình không nạp từ settings.json).")
        return False, "Chưa sửa lịch tự bật của máy (chế độ thử)."
    kind = os_kind(cfg)
    try:
        if kind == "windows":
            ok, status, detail = _windows(hhmm)
        elif kind == "mac":
            ok, status, detail = _mac(cfg, hhmm)
        else:
            return False, "Máy này không phải Windows / Mac: không có lịch tự bật để sửa."
    except Exception as e:  # không được làm hỏng /giobot
        log.error("Lỗi khi sửa lịch tự khởi động: %s", e, exc_info=True)
        ok, status, detail = False, "error", f"{type(e).__name__}: {e}"
    audit("AUTOSTART_UPDATE", f"{kind} {hhmm} {status} {detail}"[:300])
    if kind == "windows":
        if ok:
            return True, f"Task Scheduler: đã đổi giờ tự bật sang {hhmm} (thứ 2 – thứ 6)."
        if status == "missing":
            return False, (f"⚠️ Chưa thấy task {TASK_NAME} trong Task Scheduler nên máy chưa tự bật bot lúc {hhmm}. "
                           + WIN_FIX)
        return False, f"⚠️ Chưa đổi được giờ tự bật trong Task Scheduler ({detail}). " + WIN_FIX
    if ok:
        return True, (f"launchd: đã ghi giờ tự bật {hhmm} (thứ 2 – thứ 6). macOS áp dụng từ lần đăng nhập lại / "
                      f"khởi động lại máy tới. Muốn áp dụng ngay: nhấp đúp cai_tu_khoi_dong.command (bot khởi động lại).")
    if status == "missing":
        return False, f"⚠️ Chưa cài tự khởi động trên Mac nên máy chưa tự bật bot lúc {hhmm}. " + MAC_FIX
    return False, f"⚠️ Chưa sửa được lịch tự bật của launchd ({detail}). " + MAC_FIX
