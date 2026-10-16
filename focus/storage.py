"""SQLite (data/focus.db, chế độ WAL).

Bảng:
- samples      mẫu thô mỗi 5 giây (giữ keep_samples_days ngày)
- notes        kế hoạch / output / issue / giờ AS400 / ngày nghỉ (day_off) / nghỉ nửa ngày (leave_part) /
               năng lượng (energy) và nguồn của nó (energy_source: "auto" = bot tự tính lúc tổng kết) (giữ mãi)
- daily_stats  số liệu tổng kết từng ngày dạng JSON (giữ mãi, vẫn còn khi mẫu thô đã dọn)
- sent_log     đã gửi nhắc gì trong ngày (khởi động lại không gửi trùng)
- quotes       câu khích lệ đã gửi (để không lặp)
- ai_cache     nhận xét AI đã viết (hỏi lại không tốn quota)
- prefs        tuỳ chọn đổi qua Telegram (/aireview, /style), đè lên settings.json / persona.json

Mỗi thread dùng connection riêng. Vòng lấy mẫu ghi theo lô mỗi phút trong một giao dịch rất ngắn,
nên bot Telegram ghi chú cùng lúc không bao giờ bị "database is locked".
"""
import os
import sqlite3
import time

NOTE_FIELDS = ("plan", "output", "issues", "distractions", "energy", "tomorrow",
               "as400_start", "as400_end", "day_off", "leave_part", "energy_source")

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts REAL PRIMARY KEY, dur REAL, idle REAL, locked INTEGER,
    vdi_state TEXT, fg_proc TEXT, fg_title TEXT);
CREATE TABLE IF NOT EXISTS notes (
    day TEXT PRIMARY KEY, plan TEXT, output TEXT, issues TEXT,
    distractions TEXT, energy INTEGER, tomorrow TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS quotes (ts REAL, style TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS ai_cache (key TEXT PRIMARY KEY, created REAL, text TEXT);
CREATE TABLE IF NOT EXISTS daily_stats (day TEXT PRIMARY KEY, data TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS sent_log (day TEXT, kind TEXT, ts REAL, PRIMARY KEY (day, kind));
CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT, updated REAL);
"""


def db_path(cfg):
    return os.path.join(cfg["data_dir"], "focus.db")


def open_db(path):
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")  # WAL + NORMAL: an toàn khi mất điện, ít ghi đĩa hơn
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(notes)")}
    # leave_part: "am" | "pm" (nghỉ nửa ngày). energy_source: "auto" khi bot tự tính năng lượng (energy.py)
    for col in ("as400_start", "as400_end", "day_off", "leave_part", "energy_source"):
        if col not in cols:
            db.execute(f"ALTER TABLE notes ADD COLUMN {col} TEXT")
    if "vdi_full" not in {r[1] for r in db.execute("PRAGMA table_info(samples)")}:
        db.execute("ALTER TABLE samples ADD COLUMN vdi_full INTEGER")
    if "style" not in {r[1] for r in db.execute("PRAGMA table_info(quotes)")}:
        db.execute("ALTER TABLE quotes ADD COLUMN style TEXT")
    db.commit()
    return db


class SampleWriter:
    """Gom mẫu trong RAM, ghi một lô mỗi flush_every mẫu (mặc định 12 x 5s = 1 phút)."""

    def __init__(self, db, store_titles=False, flush_every=12):
        self.db, self.store_titles, self.flush_every = db, store_titles, flush_every
        self.buf = []

    def add(self, ts, dur, s):
        full = s.get("vdi_full")
        self.buf.append((ts, dur, s["idle"], int(bool(s["locked"])), s["vdi_state"], s["fg_proc"],
                         s.get("fg_title") if self.store_titles else None, None if full is None else int(full)))
        if len(self.buf) >= self.flush_every:
            self.flush()

    def flush(self):
        if not self.buf:
            return
        with self.db:  # một giao dịch ngắn, tự commit
            self.db.executemany("INSERT OR REPLACE INTO samples (ts,dur,idle,locked,vdi_state,fg_proc,fg_title,"
                                "vdi_full) VALUES (?,?,?,?,?,?,?,?)", self.buf)
        self.buf.clear()


def mark_sent(db, day, kind):
    """True nếu đây là lần đầu (day, kind) trong ngày."""
    with db:
        cur = db.execute("INSERT OR IGNORE INTO sent_log VALUES (?,?,?)", (day, kind, time.time()))
    return cur.rowcount == 1


def unmark_sent(db, day, kind):
    """Gỡ dấu đã gửi (gửi Telegram thất bại) để lần sau gửi lại."""
    with db:
        db.execute("DELETE FROM sent_log WHERE day=? AND kind=?", (day, kind))


def get_note(db, day):
    row = db.execute("SELECT %s FROM notes WHERE day=?" % ",".join(NOTE_FIELDS), (day,)).fetchone()
    return dict(zip(NOTE_FIELDS, row)) if row else {}


def _update_note(db, day, change):
    """Đọc-sửa-ghi ghi chú trong MỘT giao dịch BEGIN IMMEDIATE: bot và tracker ghi cùng lúc không mất dòng."""
    if db.in_transaction:
        db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        note = get_note(db, day)
        note.update(change(note))
        db.execute("INSERT OR REPLACE INTO notes (day,%s,updated) VALUES (?,%s,?)"
                   % (",".join(NOTE_FIELDS), ",".join("?" * len(NOTE_FIELDS))),
                   [day] + [note.get(k) for k in NOTE_FIELDS] + [time.time()])
        db.commit()
    except BaseException:
        db.rollback()
        raise


def save_note(db, day, values):
    """Cập nhật một vài trường của ghi chú ngày (các trường khác giữ nguyên)."""
    bad = set(values) - set(NOTE_FIELDS)
    if bad:
        raise ValueError(f"Trường ghi chú không hợp lệ: {bad}")
    if "energy" in values and "energy_source" not in values:  # bạn tự chấm: thay số bot tự tính
        values = dict(values, energy_source=None)
    _update_note(db, day, lambda note: values)


def append_note(db, day, field, line):
    if field not in NOTE_FIELDS:
        raise ValueError(f"Trường ghi chú không hợp lệ: {field}")
    _update_note(db, day, lambda note: {field: ((note.get(field) or "") + "\n" + line).strip()})


TOMORROW_MAX_AGE_DAYS = 4  # lời hẹn "sáng mai làm trước" chỉ còn giá trị qua cuối tuần + 1 ngày lễ


def last_tomorrow(db, day, with_day=False):
    """'Việc đầu tiên ngày mai' ghi ở ngày làm việc ngay trước day (tối đa 4 ngày trước, và không có ngày nào ghi
    chú sau nó), để lời hẹn cũ từ nhiều tuần trước không bị coi là "hôm qua hẹn". with_day=True: (ngày ghi, việc)."""
    import datetime as _dt
    oldest = (_dt.date.fromisoformat(day) - _dt.timedelta(days=TOMORROW_MAX_AGE_DAYS)).isoformat()
    row = db.execute("SELECT day, tomorrow FROM notes WHERE day<? AND day>=? AND tomorrow<>'' AND tomorrow IS NOT NULL "
                     "ORDER BY day DESC LIMIT 1", (day, oldest)).fetchone()
    if not row:
        return None
    later = db.execute("SELECT 1 FROM notes WHERE day>? AND day<? AND day_off IS NULL AND "
                       "(COALESCE(plan,'')<>'' OR COALESCE(output,'')<>'') LIMIT 1", (row[0], day)).fetchone()
    if later:  # đã có một ngày làm việc khác sau lời hẹn: lời hẹn đó đã qua
        return None
    return (row[0], row[1]) if with_day else row[1]


def get_pref(db, key, default=None):
    row = db.execute("SELECT value FROM prefs WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_pref(db, key, value):
    with db:
        if value is None:
            db.execute("DELETE FROM prefs WHERE key=?", (key,))
        else:
            db.execute("INSERT OR REPLACE INTO prefs VALUES (?,?,?)", (key, str(value), time.time()))
