"""Hai lớp log, cả hai là file theo NGÀY và tự xoá sau 30 ngày (focus.log: TimedRotatingFileHandler backupCount=30;
audit-YYYY-MM-DD.log: housekeeping.trim_text_logs xoá bản cũ hơn AUDIT_KEEP_DAYS):

- data/logs/focus.log   log KỸ THUẬT đầy đủ: mọi tin nhắn, lệnh, lần gọi AI, cảnh báo, việc chạy nền, mọi lỗi
                        (kể cả lỗi nhỏ đã tự xử lý) kèm traceback. Qua đêm đổi tên thành focus.log.YYYY-MM-DD.
- data/audit.log        nhật ký SỰ KIỆN của hôm nay cho người đọc: 1 sự kiện 1 dòng. Qua ngày chuyển thành
                        data/logs/audit-YYYY-MM-DD.log. Mỗi sự kiện cũng được chép vào focus.log.
- Lỗi không ai bắt (thread nào cũng vậy) cũng được ghi vào focus.log (setup() gắn excepthook).
"""
import datetime as dt
import logging
import logging.handlers
import os
import sys
import threading

_LOG = None
_AUDIT_PATH = None
_AUDIT_LOCK = threading.Lock()
_AUDIT_DAY = None


def setup(data_dir, keep_days=30, console=True):
    """Gọi một lần lúc khởi động. Gọi lại thì bỏ qua."""
    global _LOG, _AUDIT_PATH
    if _LOG:
        return _LOG
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    _AUDIT_PATH = os.path.join(data_dir, "audit.log")
    log = logging.getLogger("focus")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    fh = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "focus.log"), when="midnight", backupCount=keep_days, encoding="utf-8", delay=True)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s %(module)s: %(message)s"))
    log.addHandler(fh)
    if console and sys.stderr:  # chạy ẩn (pythonw) thì không có console
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        log.addHandler(ch)
    logging.captureWarnings(True)  # warnings của Python (DeprecationWarning...) cũng vào log
    logging.getLogger("py.warnings").addHandler(fh)
    _hook_uncaught(log)
    _LOG = log
    log.info("===== Bắt đầu ghi log (pid %s, Python %s, %s) =====", os.getpid(), sys.version.split()[0], sys.platform)
    return log


def _hook_uncaught(log):
    """Lỗi không được bắt ở bất kỳ thread nào: ghi traceback vào focus.log thay vì mất trên console ẩn."""
    if getattr(sys.excepthook, "_focus", False):
        return
    old_sys, old_thread = sys.excepthook, threading.excepthook

    def on_error(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            log.critical("Lỗi không được bắt: %s", exc, exc_info=(exc_type, exc, tb))
        old_sys(exc_type, exc, tb)

    def on_thread_error(args):
        if args.exc_type is not SystemExit:
            log.critical("Lỗi không được bắt trong thread %s: %s", getattr(args.thread, "name", "?"), args.exc_value,
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        old_thread(args)

    on_error._focus = True
    sys.excepthook, threading.excepthook = on_error, on_thread_error


def reset():
    """Chỉ dùng trong test."""
    global _LOG, _AUDIT_PATH, _AUDIT_DAY
    _AUDIT_DAY = None
    if _LOG:
        for lg in (_LOG, logging.getLogger("py.warnings")):
            for h in list(lg.handlers):
                h.close()
                lg.removeHandler(h)
    _LOG, _AUDIT_PATH = None, None


def get_logger():
    return _LOG or logging.getLogger("focus")


def _rotate_audit(today):
    """audit.log của ngày cũ -> data/logs/audit-<ngày>.log (gọi trong _AUDIT_LOCK)."""
    global _AUDIT_DAY
    _AUDIT_DAY = today
    try:
        old = dt.date.fromtimestamp(os.path.getmtime(_AUDIT_PATH)).isoformat()
    except OSError:
        return  # chưa có file
    if old == today:
        return
    target = os.path.join(os.path.dirname(_AUDIT_PATH), "logs", f"audit-{old}.log")
    try:
        if os.path.exists(target):  # hiếm: đã có file ngày đó -> nối thêm
            with open(_AUDIT_PATH, encoding="utf-8", errors="replace") as src, open(target, "a", encoding="utf-8") as dst:
                dst.write(src.read())
            os.remove(_AUDIT_PATH)
        else:
            os.replace(_AUDIT_PATH, target)
    except OSError as e:
        get_logger().warning("Không chuyển được audit.log sang file ngày %s: %s", old, e)


def audit(event, detail=""):
    """Ghi 1 dòng sự kiện (và chép vào focus.log). Xoá xuống dòng để 1 sự kiện luôn là 1 dòng."""
    detail = str(detail).replace("\r", " ").replace("\n", " ⏎ ")[:500]
    get_logger().info("[sự kiện] %s | %s", event, detail)
    if not _AUDIT_PATH:
        return
    now = dt.datetime.now()
    line = f"{now:%Y-%m-%dT%H:%M:%S} | {event} | {detail}\n"
    try:
        with _AUDIT_LOCK:
            today = now.date().isoformat()
            if _AUDIT_DAY != today:
                _rotate_audit(today)
            with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except OSError as e:
        get_logger().warning("Không ghi được audit.log: %s", e)
