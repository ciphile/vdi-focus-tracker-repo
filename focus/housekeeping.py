"""Dọn dẹp mỗi ngày một lần (lúc tracker khởi động và lúc qua ngày mới), giữ app nhẹ.
Mỗi bước chạy riêng: một bước lỗi không chặn bước khác, không chặn tracker.

| Thứ                                   | Giữ                                                     |
|---------------------------------------|---------------------------------------------------------|
| samples (mẫu 5 giây)                  | keep_samples_days. Trước khi xoá, chốt số liệu ngày vào daily_stats |
| daily_stats, notes, prefs             | Giữ mãi (rất nhỏ)                                       |
| ai_cache (nhận xét AI)                | 60 ngày                                                 |
| quotes (câu đã gửi)                   | 90 ngày                                                 |
| sent_log (đã nhắc gì)                 | 30 ngày                                                 |
| focus.db-wal                          | checkpoint TRUNCATE mỗi ngày (về 0 byte)                |
| focus.db (chỗ trống)                  | VACUUM ngày 1 hằng tháng, hoặc khi trang trống > 25%    |
| data/backup/focus-YYYY-MM-DD.db.zip   | keep_db_backups bản gần nhất (tính chung bản .db cũ)    |
| reports/focus-*.html                  | keep_reports_days, tạo lại được                         |
| audit.log                             | cắt còn 5.000 dòng cuối khi quá 20.000                  |
| logs/focus.log.*                      | tự xoay mỗi đêm (log_setup)                             |
| logs/config-error.txt                 | xoá sau 30 ngày                                         |
| logs/ file khác (launcher-error.txt,  | > 1 MB thì cắt còn ~200 KB cuối (giữ nguyên mã hoá      |
|   launchd.err.log, launchd.out.log…)  | UTF-16/UTF-8); .txt/.log không ghi 60 ngày thì xoá      |
| holidays_<năm>.json                   | giữ 2 năm trước                                         |
| *.tmp (data, data/backup, data/logs,  | xoá khi cũ hơn 1 ngày (file ghi dở do tắt máy ngang)    |
|   reports/focus-*.tmp)                |                                                         |
| focus/__pycache__, tests/__pycache__  | xoá .pyc của module không còn file .py (sau khi cập nhật) |

Khôi phục DB từ bản sao lưu: tắt tracker, giải nén data/backup/focus-YYYY-MM-DD.db.zip (bên trong là
focus.db), chép đè lên data/focus.db, xoá data/focus.db-wal và data/focus.db-shm nếu có, rồi bật lại.

Chạy tay: python focus_tracker.py housekeeping
"""
import datetime as dt
import glob
import os
import re
import sqlite3
import sys
import time
import zipfile

from . import holidays, logs
from .analysis import daily_stats
from .logs import audit, get_logger
from .storage import db_path, open_db

log = get_logger()

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # thư mục chứa gói focus/
_BACKUP_RE = re.compile(r"^focus-(\d{4}-\d{2}-\d{2})\.db(\.zip)?$")
MB = 1024 * 1024


def _step(results, name, fn):
    try:
        results[name] = fn()
    except Exception as e:
        log.warning("Housekeeping %s lỗi: %s", name, e, exc_info=True)
        results[name] = f"lỗi: {e}"


def run(cfg, force=False):
    flag = os.path.join(cfg["data_dir"], "housekeeping_last_run.txt")
    today = dt.date.today().isoformat()
    try:
        with open(flag, encoding="utf-8") as f:
            if f.read().strip() == today and not force:
                return {"skipped": "đã dọn hôm nay"}
    except OSError:
        pass
    started = time.time()
    results = {}
    before = {}
    _step(results, "usage_before", lambda: before.update(data_usage(cfg)) or fmt_size(before["total_bytes"]))
    db = open_db(db_path(cfg))
    _step(results, "db_backup", lambda: backup_db(cfg, db))
    _step(results, "samples", lambda: prune_samples(cfg, db))
    _step(results, "tables", lambda: prune_tables(db))
    _step(results, "reports", lambda: prune_files(os.path.join(cfg["report_dir"], "focus-*.html"),
                                                   cfg["keep_reports_days"]))
    _step(results, "audit_log", lambda: trim_audit(cfg))
    _step(results, "text_logs", lambda: trim_text_logs(cfg))
    _step(results, "holiday_caches", lambda: holidays.prune(cfg))
    _step(results, "tmp_files", lambda: prune_tmp(cfg))
    _step(results, "bytecode", lambda: prune_bytecode())
    if dt.date.today().day == 1 or _free_ratio(db) > 0.25:
        _step(results, "vacuum", lambda: (db.execute("VACUUM"), "ok")[1])
    _step(results, "wal", lambda: checkpoint_wal(db))  # sau VACUUM: VACUUM ghi cả DB vào WAL
    holidays.clear_memo()  # đọc lại lịch lễ (có thể vừa có file lịch năm mới)
    db.close()
    try:
        with open(flag, "w", encoding="utf-8") as f:
            f.write(today)
    except OSError as e:
        log.warning("Không ghi được cờ housekeeping: %s", e)

    def freed():
        after = data_usage(cfg)
        results["usage_after"] = fmt_size(after["total_bytes"])
        return before["total_bytes"] - after["total_bytes"]  # âm nếu dữ liệu mới nhiều hơn phần đã dọn
    _step(results, "freed_bytes", freed)
    results["seconds"] = round(time.time() - started, 2)
    log.info("Housekeeping xong: %s", results)
    audit("HOUSEKEEPING", results)
    return results


# ------------------------------------------------------------ DB

def backup_db(cfg, db):
    """Sao lưu DB thành focus-YYYY-MM-DD.db.zip (nén ~3 lần). Giữ keep_db_backups bản mới nhất."""
    folder = os.path.join(cfg["data_dir"], "backup")
    os.makedirs(folder, exist_ok=True)
    day = dt.date.today().isoformat()
    target = os.path.join(folder, f"focus-{day}.db.zip")
    raw = os.path.join(folder, f"focus-{day}.db.raw.tmp")
    tmp = target + ".tmp"
    try:
        dest = sqlite3.connect(raw)
        try:
            db.backup(dest)  # an toàn kể cả khi DB đang được ghi
        finally:
            dest.close()
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(raw, "focus.db")
        os.replace(tmp, target)  # không bao giờ để lại file zip viết dở mang tên thật
    finally:
        for p in (raw, tmp):
            if os.path.exists(p):
                os.remove(p)
    # Xoay vòng, tính chung bản .db cũ (trước khi nén): mỗi ngày một bản (có .zip thì bỏ .db), giữ keep ngày mới nhất.
    by_day = {}
    for name in sorted(os.listdir(folder)):
        m = _BACKUP_RE.match(name)
        if m:
            by_day.setdefault(m.group(1), []).append(name)
    for day_, names in by_day.items():
        if len(names) > 1:  # focus-D.db và focus-D.db.zip: giữ .zip
            for name in names:
                if not name.endswith(".zip"):
                    os.remove(os.path.join(folder, name))
    days = sorted(by_day)
    keep = cfg["keep_db_backups"]
    for day_ in days[:-keep]:
        for name in by_day[day_]:
            if os.path.exists(os.path.join(folder, name)):
                os.remove(os.path.join(folder, name))
    n = min(len(days), keep)
    return f"{os.path.basename(target)} ({fmt_size(os.path.getsize(target))}), giữ {n} bản"


def prune_samples(cfg, db):
    cutoff_day = dt.date.today() - dt.timedelta(days=cfg["keep_samples_days"])
    cutoff = dt.datetime.combine(cutoff_day, dt.time()).timestamp()
    first = db.execute("SELECT MIN(ts) FROM samples WHERE ts < ?", (cutoff,)).fetchone()[0]
    if not first:
        return 0
    d = dt.date.fromtimestamp(first)
    while d < cutoff_day:  # chốt số liệu ngày trước khi xoá mẫu thô
        daily_stats(db, cfg, d.isoformat(), refresh=True)
        d += dt.timedelta(days=1)
    with db:
        n = db.execute("DELETE FROM samples WHERE ts < ?", (cutoff,)).rowcount
    return n


def prune_tables(db):
    now = time.time()
    with db:
        out = {
            "ai_cache": db.execute("DELETE FROM ai_cache WHERE created < ?", (now - 60 * 86400,)).rowcount,
            "quotes": db.execute("DELETE FROM quotes WHERE ts < ?", (now - 90 * 86400,)).rowcount,
            "sent_log": db.execute("DELETE FROM sent_log WHERE ts < ?", (now - 30 * 86400,)).rowcount,
        }
    return out


def _free_ratio(db):
    try:
        pages = db.execute("PRAGMA page_count").fetchone()[0]
        free = db.execute("PRAGMA freelist_count").fetchone()[0]
    except sqlite3.Error:
        return 0
    return free / pages if pages else 0


def checkpoint_wal(db):
    """Ghi hết WAL vào DB rồi cắt file -wal về 0. Tracker đang đọc/ghi dở thì SQLite báo bận, mai thử lại."""
    path = db.execute("PRAGMA database_list").fetchone()[2]
    wal = path + "-wal"
    size = os.path.getsize(wal) if os.path.exists(wal) else 0
    busy = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    after = os.path.getsize(wal) if os.path.exists(wal) else 0
    return f"{fmt_size(size)} -> {fmt_size(after)}" + (" (đang bận, để mai)" if busy else "")


# ------------------------------------------------------------ file

def prune_files(pattern, keep_days):
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for path in glob.glob(pattern):
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    return removed


def prune_tmp(cfg, keep_days=1):
    """*.tmp cũ (ghi dở lúc tắt máy ngang). Chỉ trong thư mục app tạo, không quét report_dir sâu."""
    data = cfg["data_dir"]
    patterns = [os.path.join(data, "*.tmp"), os.path.join(data, "backup", "*.tmp"),
                os.path.join(data, "logs", "*.tmp"), os.path.join(cfg["report_dir"], "focus-*.tmp")]
    return sum(prune_files(p, keep_days) for p in patterns)


def trim_audit(cfg, max_lines=20000, keep=5000):
    path = os.path.join(cfg["data_dir"], "audit.log")
    if not os.path.exists(path):
        return 0
    with logs._AUDIT_LOCK:  # giữ khoá ghi audit: dòng ghi trong lúc cắt không bị mất
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if len(lines) <= max_lines:
            return 0
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(lines[-keep:])
        os.replace(tmp, path)
    return len(lines) - keep


_BOMS = ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"), (b"\xef\xbb\xbf", "utf-8"))


def trim_tail(path, keep_bytes=200 * 1024):
    """Cắt file chữ còn ~keep_bytes cuối, bắt đầu từ đầu một dòng, giữ BOM/mã hoá (launcher-error.txt là UTF-16).
    Ghi đè TẠI CHỖ (không thay file): launchd đang giữ file mở kiểu append vẫn ghi tiếp đúng chỗ."""
    with open(path, "r+b") as f:
        head = f.read(3)
        bom, enc = b"", None
        for b, e in _BOMS:
            if head.startswith(b):
                bom, enc = b, e
                break
        size = f.seek(0, os.SEEK_END)
        start = max(len(bom), size - keep_bytes)
        if enc and enc.startswith("utf-16"):
            start += (start - len(bom)) % 2  # UTF-16: cắt đúng ranh giới 2 byte
        f.seek(start)
        tail = f.read()
        if enc and enc.startswith("utf-16"):
            text = tail.decode(enc, errors="replace")
            text = text[text.find("\n") + 1:] if "\n" in text else text
            tail = text.encode(enc)
        else:
            nl = tail.find(b"\n")  # UTF-8: byte \n không bao giờ nằm giữa ký tự nhiều byte
            tail = tail[nl + 1:] if nl >= 0 else tail
        f.seek(0)
        f.write(bom + tail)
        f.truncate()
    return size - len(bom) - len(tail)


AUDIT_KEEP_DAYS = 30  # nhật ký sự kiện audit-YYYY-MM-DD.log giữ bằng focus.log


def trim_text_logs(cfg, max_bytes=MB, keep_bytes=200 * 1024, idle_days=60, config_error_days=30):
    """data/logs: file ngoài focus.log* (launcher-error.txt, launchd.err.log, ...) không được phình mãi."""
    folder = os.path.join(cfg["data_dir"], "logs")
    out = {"trimmed": [], "deleted": []}
    if not os.path.isdir(folder):
        return out
    now = time.time()
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        low = name.lower()
        if low.startswith("focus.log") or low.endswith(".tmp") or not os.path.isfile(path):
            continue  # focus.log tự xoay; .tmp do prune_tmp lo
        try:
            age = (now - os.path.getmtime(path)) / 86400
            if low.startswith("ai-prompts-"):  # log prompt AI: giữ ai_prompt_log_days ngày, không cắt giữa chừng
                keep = cfg.get("ai_prompt_log_days", 14)
                if age > max(keep, 1):
                    os.remove(path)
                    out["deleted"].append(name)
                elif os.path.getsize(path) > 10 * max_bytes:
                    trim_tail(path, max_bytes)
                    out["trimmed"].append(name)
                continue
            if (low == "config-error.txt" and age > config_error_days) or \
                    (low.startswith("audit-") and age > AUDIT_KEEP_DAYS) or \
                    (low.endswith((".txt", ".log")) and age > idle_days):
                os.remove(path)
                out["deleted"].append(name)
            elif os.path.getsize(path) > max_bytes:
                trim_tail(path, keep_bytes)
                out["trimmed"].append(name)
        except OSError as e:  # file đang bị khoá (Windows): bỏ qua, mai thử lại
            log.warning("Không dọn được %s: %s", path, e)
    return out


def prune_bytecode(root=None, stale_days=30):
    """Xoá .pyc mồ côi trong <app>/focus/__pycache__ và <app>/tests/__pycache__: module đã bị xoá khi cập nhật,
    hoặc .pyc của bản Python cũ không dùng nữa (> stale_days ngày). Không đụng gì ngoài thư mục app."""
    root = os.path.realpath(root or APP_ROOT)
    tag = sys.implementation.cache_tag  # vd cpython-312
    cutoff = time.time() - stale_days * 86400
    removed = []
    for pkg in ("focus", "tests"):
        cache = os.path.join(root, pkg, "__pycache__")
        if not os.path.isdir(cache) or os.path.islink(cache) or \
                not os.path.realpath(cache).startswith(os.path.join(root, "")):
            continue
        for name in os.listdir(cache):
            if not name.endswith(".pyc"):
                continue
            parts = name.split(".")  # module.cpython-312.pyc (hoặc module.cpython-312.opt-1.pyc)
            path = os.path.join(cache, name)
            orphan = not os.path.exists(os.path.join(root, pkg, parts[0] + ".py"))
            old_python = len(parts) >= 3 and parts[1] != tag and os.path.getmtime(path) < cutoff
            if (orphan or old_python) and os.path.isfile(path):
                os.remove(path)
                removed.append(f"{pkg}/{name}")
    return removed


# ------------------------------------------------------------ dung lượng

def _walk_size(folder, recursive=True):
    total = 0
    if not os.path.isdir(folder):
        return 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for n in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, n))
            except OSError:
                pass
        if not recursive:
            break
    return total


def data_usage(cfg):
    """Dung lượng app đang dùng trên đĩa (byte): data_dir + các file trong report_dir."""
    data = cfg["data_dir"]
    db = sum(os.path.getsize(p) for p in (db_path(cfg) + s for s in ("", "-wal", "-shm")) if os.path.exists(p))
    backups = _walk_size(os.path.join(data, "backup"))
    logs_b = _walk_size(os.path.join(data, "logs"))
    audit_p = os.path.join(data, "audit.log")
    if os.path.exists(audit_p):
        logs_b += os.path.getsize(audit_p)
    total = _walk_size(data)
    rep_dir, real_data = os.path.realpath(cfg["report_dir"]), os.path.realpath(data)
    reports = _walk_size(rep_dir, recursive=False)
    if not (rep_dir == real_data or rep_dir.startswith(os.path.join(real_data, ""))):
        total += reports  # report_dir nằm trong data thì đã tính trong total
    return {"total_bytes": total, "db_bytes": db, "backups_bytes": backups, "reports_bytes": reports,
            "logs_bytes": logs_b, "other_bytes": max(0, total - db - backups - reports - logs_b)}


def fmt_size(n):
    """1234567 -> '1.2 MB'."""
    n = float(n or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{sign}{int(n)} B" if unit == "B" else f"{sign}{n:.1f} {unit}"
        n /= 1024
