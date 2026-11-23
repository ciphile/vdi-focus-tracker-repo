"""Danh sách việc cần làm (kiểu Google Tasks thu nhỏ), một nguồn duy nhất cho /viec, /plan, /issue, /tmrtask.

Mỗi việc là một dòng trong bảng tasks (data/focus.db):

| Cột         | Nghĩa                                                                     |
|-------------|---------------------------------------------------------------------------|
| text        | nội dung việc (chữ người dùng gõ, giữ nguyên)                             |
| kind        | "task" (việc) hoặc "issue" (vướng mắc / bị chặn, ghi bằng /issue)          |
| created_day | ngày thêm vào (để ghi "tồn từ T4 14/10")                                   |
| start_day   | ngày việc bắt đầu hiện trong danh sách (/tmrtask, "hoãn": ngày làm việc kế) |
| due         | hạn chót YYYY-MM-DD (tuỳ chọn, "hạn 2 25/11")                              |
| first       | 1 = làm trước (đứng đầu danh sách: /tmrtask, "ưu tiên 3")                  |
| done_day    | ngày đánh dấu xong (NULL = chưa xong)                                      |
| dropped_day | ngày bỏ việc (NULL = còn)                                                  |

Việc tồn = việc chưa xong, chưa bỏ: tự mang sang ngày sau, không cần đoán theo chữ như bản cũ (pending.py).
Số thứ tự 1, 2, 3... là vị trí trong danh sách việc còn mở ĐANG hiện (làm trước, rồi theo thứ tự thêm vào).
Sau mỗi lần cập nhật bot gửi lại danh sách nên số luôn khớp với tin mới nhất.

Cú pháp cập nhật (mỗi dòng một lệnh, hoặc cách nhau bằng dấu ;):
    xong 1 3        xong 1-3        xong: spec UAT      (đánh dấu xong; theo tên thì tìm việc giống nhất)
    mới: nội dung   thêm: nội dung  + nội dung          (thêm việc; "mới: a; b" = thêm 2 việc)
    issue: nội dung                                     (thêm issue)
    hoãn 2          (để sang ngày làm việc kế)
    bỏ 4            (xoá khỏi danh sách)
    sửa 2: nội dung mới
    ưu tiên 3       (đưa lên đầu)
    hạn 2 25/11     (đặt hạn; "mới: X hạn 25/11" cũng được)
    hoàn tác        (huỷ lần cập nhật vừa rồi)
"""
import datetime as dt
import json
import re
import time

from .intent import fold
from .storage import append_note, get_note, get_pref, last_tomorrow, save_note, set_pref

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'task',
    created_day TEXT NOT NULL, start_day TEXT NOT NULL, due TEXT, first INTEGER NOT NULL DEFAULT 0,
    done_day TEXT, dropped_day TEXT, updated REAL);
CREATE INDEX IF NOT EXISTS tasks_open ON tasks (done_day, dropped_day, start_day);
"""
MAX_TEXT = 300          # một việc dài quá thì cắt
MAX_OPEN = 60           # giới hạn số việc mở (chặn dán nhầm cả trang)
SHOW_DONE = 10          # số việc "đã xong hôm nay" hiện cuối danh sách
UNDO_PREF = "tasks_undo"
SINCE_PREF = "tasks_since"   # ngày bắt đầu dùng danh sách (đã chép việc tồn cũ sang)
NOOP_WORDS = {"khong", "ko", "k", "khong co", "khong can", "no", "ok", "oke", "okay", "bo qua", "skip",
              "chua", "giu nguyen", "van vay", "khong doi", "nope", "thoi"}

_NUMS = r"(\d{1,3}(?:\s*(?:-|–|,|\s|va|và)\s*\d{1,3})*)"
_DATE = r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?"
_OPS = [
    ("done", re.compile(r"^(?:xong|done|da xong|hoan thanh)\s+" + _NUMS + r"\s*$")),
    ("done_name", re.compile(r"^(?:xong|done|da xong|hoan thanh)\s*:\s*(.+)$")),
    ("later", re.compile(r"^(?:hoan|de mai|mai|doi sang mai)\s+" + _NUMS + r"\s*$")),
    ("drop", re.compile(r"^(?:bo|xoa|huy)\s+" + _NUMS + r"\s*$")),
    ("first", re.compile(r"^(?:uu tien|lam truoc|len dau)\s+" + _NUMS + r"\s*$")),
    ("edit", re.compile(r"^(?:sua|doi)\s+(\d{1,3})\s*:\s*(.+)$")),
    ("due", re.compile(r"^(?:han)\s+(\d{1,3})\s+" + _DATE + r"\s*$")),
    ("add", re.compile(r"^(?:moi|them|viec moi|task)\s*:\s*(.+)$|^\+\s*(.+)$")),
    ("issue", re.compile(r"^(?:issue|van de|vuong)\s*:\s*(.+)$")),
    ("undo", re.compile(r"^(?:hoan tac|undo)$")),
]
_DUE_TAIL = re.compile(r"\s+(?:han|hạn)\s+" + _DATE + r"\s*$", re.I)
WEEK = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


class TaskError(ValueError):
    """Lỗi cú pháp / số thứ tự: câu báo tiếng Việt cho người dùng."""


def ensure_schema(db):
    db.executescript(SCHEMA)


# ------------------------------------------------------------ đọc cú pháp (hàm thuần, không đụng DB)

def _numbers(text):
    out = []
    for a, b in re.findall(r"(\d{1,3})\s*(?:(?:-|–)\s*(\d{1,3}))?", text):
        lo, hi = int(a), int(b or a)
        if hi < lo or hi - lo > MAX_OPEN:
            raise TaskError(f"Khoảng số {a}-{b} không hợp lệ.")
        out.extend(range(lo, hi + 1))
    return list(dict.fromkeys(out))


def _date(d, m, y, today):
    year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
    try:
        when = dt.date(year, int(m), int(d))
    except ValueError:
        raise TaskError(f"Ngày {d}/{m} không có thật.")
    if not y and when < today - dt.timedelta(days=60):  # 05/01 gõ vào tháng 12 = tháng 1 năm sau
        when = when.replace(year=year + 1)
    return when.isoformat()


def _clean_text(raw):
    text = re.sub(r"\s+", " ", raw).strip(" .;")
    if not text:
        raise TaskError("Nội dung việc đang trống.")
    return text[:MAX_TEXT]


def _split_due(text, today):
    """"Viết spec hạn 25/11" -> ("Viết spec", "2026-11-25")."""
    m = _DUE_TAIL.search(fold(text))
    if not m:
        return text, None
    return text[:m.start()].strip(), _date(m.group(1), m.group(2), m.group(3), today)


def is_noop(text):
    return fold(text or "").strip(" .!") in NOOP_WORDS


def parse(text, today=None):
    """Cú pháp cập nhật -> danh sách lệnh [(loại, ...)]. Không phải cú pháp danh sách việc -> None.
    Sai số / ngày -> TaskError. Mọi dòng phải đúng cú pháp (một dòng lạ = cả tin không phải cú pháp)."""
    today = today or dt.date.today()
    if isinstance(today, str):
        today = dt.date.fromisoformat(today)
    pieces = [p.strip() for p in re.split(r"[\n;]+", text or "") if p.strip()]
    if not pieces or len(pieces) > 40:
        return None
    ops, last_add = [], None
    for piece in pieces:
        folded = fold(piece).strip()
        hit = None
        for kind, rx in _OPS:
            m = rx.match(folded)
            if m:
                hit = (kind, m)
                break
        if not hit:
            if last_add:  # "mới: a; b; c": các phần sau dấu ; cũng là việc mới
                body, due = _split_due(piece, today)
                ops.append((last_add, _clean_text(body), due))
                continue
            return None
        kind, m = hit
        last_add = None
        if kind in ("done", "later", "drop", "first"):
            ops.append((kind, _numbers(m.group(1))))
        elif kind == "done_name":
            ops.append((kind, _clean_text(piece[m.start(1):])))  # chữ gốc có dấu (fold giữ độ dài)
        elif kind == "edit":
            ops.append((kind, int(m.group(1)), _clean_text(piece[m.start(2):])))
        elif kind == "due":
            ops.append((kind, int(m.group(1)), _date(m.group(2), m.group(3), m.group(4), today)))
        elif kind in ("add", "issue"):
            grp = 1 if m.group(1) is not None else 2
            body, due = _split_due(piece[m.start(grp):], today)
            ops.append((kind, _clean_text(body), due))
            last_add = kind
        elif kind == "undo":
            if len(pieces) > 1:
                raise TaskError("«hoàn tác» gõ riêng một tin nhé.")
            ops.append(("undo",))
    return ops


def describe(ops):
    """Mô tả ngắn các lệnh (thẻ xác nhận, nhật ký)."""
    names = {"done": "xong việc", "later": "hoãn sang ngày làm việc kế việc", "drop": "bỏ việc",
             "first": "làm trước việc"}
    out = []
    for op in ops:
        k = op[0]
        if k in names:
            out.append(f"{names[k]} " + ", ".join(map(str, op[1])))
        elif k == "done_name":
            out.append(f"xong việc giống «{op[1]}»")
        elif k == "edit":
            out.append(f"sửa việc {op[1]} thành «{op[2]}»")
        elif k == "due":
            out.append(f"hạn việc {op[1]}: {_short(op[2])}")
        elif k in ("add", "issue"):
            out.append(("thêm issue" if k == "issue" else "thêm việc") + f" «{op[1]}»"
                       + (f" (hạn {_short(op[2])})" if op[2] else ""))
        elif k == "undo":
            out.append("hoàn tác lần cập nhật vừa rồi")
    return "; ".join(out)


def _short(day):
    d = dt.date.fromisoformat(day)
    return f"{WEEK[d.weekday()]} {d:%d/%m}"


# ------------------------------------------------------------ đọc danh sách

_COLS = "id, text, kind, created_day, start_day, due, first, done_day, dropped_day"


def _rows(db, sql, params=()):
    ensure_schema(db)
    return [dict(zip(_COLS.replace(" ", "").split(","), r)) for r in db.execute(
        f"SELECT {_COLS} FROM tasks {sql}", params)]


def open_tasks(db, day):
    """Việc còn mở hiện trong ngày day, đúng thứ tự đánh số (làm trước, rồi theo thứ tự thêm)."""
    return _rows(db, "WHERE done_day IS NULL AND dropped_day IS NULL AND start_day<=? ORDER BY first DESC, id",
                 (day,))


def done_on(db, day):
    return _rows(db, "WHERE done_day=? AND dropped_day IS NULL ORDER BY id", (day,))


def later_tasks(db, day):
    """Việc đã hoãn / hẹn cho ngày sau (start_day > day), chưa xong."""
    return _rows(db, "WHERE done_day IS NULL AND dropped_day IS NULL AND start_day>? ORDER BY start_day, id", (day,))


def open_at_end_of(db, day):
    """Việc còn mở lúc HẾT ngày day (xem lại ngày cũ: việc xong / bỏ sau day vẫn tính là còn mở hôm đó)."""
    return _rows(db, "WHERE start_day<=? AND (done_day IS NULL OR done_day>?) AND (dropped_day IS NULL OR "
                     "dropped_day>?) ORDER BY first DESC, id", (day, day, day))


def since(db):
    ensure_schema(db)
    return get_pref(db, SINCE_PREF)


def item(t):
    """Dạng việc tồn cũ (pending.py) để báo cáo HTML / AI dùng chung: (kind, việc, ngày bắt đầu tồn)."""
    return ("issue" if t["kind"] == "issue" else "plan", t["text"], t["created_day"])


def carry_after(db, cfg, day, off_day):
    """Việc tồn sau khi hết ngày day. Ngày trước khi bắt đầu dùng danh sách: cách tính cũ (pending.py)."""
    start = since(db)
    if start and day >= start:
        return [item(t) for t in open_at_end_of(db, day)]
    from . import pending
    return pending.pending_after(db, cfg, day, off_day)


def next_workday(db, cfg, day, off_day):
    d = dt.date.fromisoformat(day)
    for _ in range(31):
        d += dt.timedelta(days=1)
        if not off_day(db, cfg, d.isoformat()):
            return d.isoformat()
    return (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()


# ------------------------------------------------------------ ghi

def add(db, day, text, kind="task", start_day=None, due=None, first=False, created_day=None):
    """Thêm một việc (bỏ qua nếu đã có việc mở giống hệt chữ). Trả id hoặc None."""
    ensure_schema(db)
    text = _clean_text(text)
    key = fold(text).lower()
    for t in _rows(db, "WHERE done_day IS NULL AND dropped_day IS NULL"):
        if fold(t["text"]).lower() == key:
            if first and not t["first"]:
                with db:
                    db.execute("UPDATE tasks SET first=1, updated=? WHERE id=?", (time.time(), t["id"]))
            return None
    if len(open_tasks(db, "9999-12-31")) >= MAX_OPEN:
        raise TaskError(f"Danh sách đã có {MAX_OPEN} việc chưa xong. Gõ «xong ...» hoặc «bỏ ...» bớt rồi thêm.")
    with db:
        cur = db.execute("INSERT INTO tasks (text, kind, created_day, start_day, due, first, updated) "
                         "VALUES (?,?,?,?,?,?,?)", (text, kind, created_day or day, start_day or day, due,
                                                     1 if first else 0, time.time()))
    return cur.lastrowid


def lines_of(text):
    """Tách đoạn kế hoạch nhiều dòng ("1. A\n2. B" hoặc "A; B") thành từng việc."""
    from .pending import _lines
    return _lines(text)


def ensure_started(db, cfg, day, off_day):
    """Lần đầu dùng danh sách: chép việc tồn cũ (kế hoạch / issue chưa thấy xong), kế hoạch hôm nay và việc hẹn
    sáng nay sang bảng tasks, để không mất gì. Chỉ chạy một lần."""
    if since(db):
        return 0
    from . import pending
    n = 0
    _, old = pending.previous_pending(db, cfg, day, off_day)
    for kind, text, from_day in old:
        n += add(db, day, text, "issue" if kind == "issue" else "task", created_day=from_day) is not None
    for kind, text in pending.pending_of(get_note(db, day), limit=None):
        n += add(db, day, text, "issue" if kind == "issue" else "task") is not None
    first = last_tomorrow(db, day)
    if first:
        n += add(db, day, first, first=True) is not None
    set_pref(db, SINCE_PREF, day)
    return n


def _snapshot(db, ids):
    return [dict(r) for r in _rows(db, "WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)] if ids else []


def apply(db, cfg, day, ops, off_day):
    """Thực hiện các lệnh trên danh sách đang hiện. Trả list câu kết quả. Sai số thứ tự -> TaskError (chưa ghi gì)."""
    ensure_schema(db)
    if ops == [("undo",)]:
        return [undo(db)]
    current = open_tasks(db, day)
    n = len(current)

    def pick(num):
        if not 1 <= num <= n:
            raise TaskError(f"Không có việc số {num} (danh sách đang có {n} việc). Gõ /viec để xem số.")
        return current[num - 1]

    plan = []  # kiểm tra hết số thứ tự trước, rồi mới ghi (không ghi dở dang)
    for op in ops:
        k = op[0]
        if k in ("done", "later", "drop", "first"):
            plan += [(k, pick(i)) for i in op[1]]
        elif k == "done_name":
            plan.append(("done", _best_match(current, op[1])))
        elif k in ("edit", "due"):
            plan.append((k, pick(op[1]), op[2]))
        else:
            plan.append(op)
    touched = list(dict.fromkeys(p[1]["id"] for p in plan if isinstance(p[1], dict)))
    undo_rec = {"day": day, "before": _snapshot(db, touched), "added": [],
                "output": get_note(db, day).get("output"), "issues": get_note(db, day).get("issues")}
    out, nxt = [], next_workday(db, cfg, day, off_day)
    for p in plan:
        k = p[0]
        if k in ("add", "issue"):
            new_id = add(db, day, p[1], "issue" if k == "issue" else "task", due=p[2])
            if new_id:
                undo_rec["added"].append(new_id)
                if k == "issue":  # issue cũng vào ghi chú ngày như /issue (báo cáo, AI đánh giá đọc ở đó)
                    append_note(db, day, "issues", f"- {p[1]} ({dt.datetime.now():%H:%M})")
                out.append(("➕ Thêm issue: " if k == "issue" else "➕ Thêm: ") + p[1])
            else:
                out.append(f"(Đã có trong danh sách: {p[1]})")
            continue
        t = p[1]
        if k == "done":
            _set(db, t["id"], done_day=day)
            append_note(db, day, "output", f"- {t['text']} ({dt.datetime.now():%H:%M})")
            out.append(f"✅ Xong: {t['text']}")
        elif k == "later":
            _set(db, t["id"], start_day=nxt, first=0)
            out.append(f"⏭ Hoãn sang {_short(nxt)}: {t['text']}")
        elif k == "drop":
            _set(db, t["id"], dropped_day=day)
            out.append(f"🗑 Bỏ: {t['text']}")
        elif k == "first":
            _set(db, t["id"], first=1)
            out.append(f"⬆️ Làm trước: {t['text']}")
        elif k == "edit":
            _set(db, t["id"], text=p[2])
            out.append(f"✏️ Sửa: {t['text']} → {p[2]}")
        elif k == "due":
            _set(db, t["id"], due=p[2])
            out.append(f"📅 Hạn {_short(p[2])}: {t['text']}")
    set_pref(db, UNDO_PREF, json.dumps(undo_rec, ensure_ascii=False))
    return out


def _set(db, task_id, **values):
    cols = ", ".join(f"{k}=?" for k in values)
    with db:
        db.execute(f"UPDATE tasks SET {cols}, updated=? WHERE id=?", list(values.values()) + [time.time(), task_id])


def undo(db):
    """Huỷ lần cập nhật gần nhất (một lần, không hoàn tác chồng nhiều lớp)."""
    raw = get_pref(db, UNDO_PREF)
    if not raw:
        return "Không có gì để hoàn tác."
    try:
        rec = json.loads(raw)
    except ValueError:
        set_pref(db, UNDO_PREF, None)
        return "Không có gì để hoàn tác."
    with db:
        for tid in rec.get("added") or []:
            db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        for t in rec.get("before") or []:
            db.execute("UPDATE tasks SET text=?, kind=?, created_day=?, start_day=?, due=?, first=?, done_day=?, "
                       "dropped_day=?, updated=? WHERE id=?",
                       (t["text"], t["kind"], t["created_day"], t["start_day"], t["due"], t["first"],
                        t["done_day"], t["dropped_day"], time.time(), t["id"]))
    if rec.get("day"):
        save_note(db, rec["day"], {"output": rec.get("output"), "issues": rec.get("issues")})
    set_pref(db, UNDO_PREF, None)
    return "↩️ Đã hoàn tác lần cập nhật vừa rồi."


def _best_match(current, name):
    """Việc giống tên nhất (cùng cách khớp chữ với việc tồn cũ). Không thấy / lưỡng lự -> TaskError."""
    from .pending import MATCH_RATIO, _words
    want = _words(name)
    scored = []
    for t in current:
        have = _words(t["text"])
        if not want or not have:
            continue
        common = len(want & have)
        if common >= MATCH_RATIO * min(len(want), len(have)):
            scored.append((common / max(len(want), len(have)), t))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        raise TaskError(f"Không thấy việc nào giống «{name}». Gõ /viec để xem số rồi gõ «xong <số>».")
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        raise TaskError(f"Có vài việc giống «{name}». Gõ «xong <số>» cho chắc nhé (xem số: /viec).")
    return scored[0][1]


def match_hint(db, day, text):
    """Dòng output vừa ghi giống việc nào đang mở: (số, việc) hoặc None (để gợi ý gõ «xong N», không tự đánh)."""
    from .pending import _done
    for i, t in enumerate(open_tasks(db, day), 1):
        if _done(t["text"], [text]):
            return i, t
    return None


# ------------------------------------------------------------ hiện

HOWTO = ("Cập nhật: xong 1 3 · mới: việc mới · hoãn 2 · bỏ 4 · sửa 2: chữ mới · ưu tiên 3 · hạn 2 25/11 · "
         "hoàn tác. Không cần đổi gì thì gõ «không».")


def _label(t, day):
    bits = []
    if t["kind"] == "issue":
        bits.append("issue")
    if t["created_day"] < day:
        bits.append(f"tồn từ {_short(t['created_day'])}")
    if t["due"]:
        bits.append(("⚠️ quá hạn " if t["due"] < day else "hạn ") + _short(t["due"]))
    return t["text"] + (f" ({', '.join(bits)})" if bits else "")


def list_text(db, day, title="📋 Việc cần làm hôm nay", howto=True):
    """Danh sách việc dạng tin Telegram. Chữ người dùng gõ bọc persona.keep() ở nơi gọi nếu cần."""
    from .persona import keep
    rows = open_tasks(db, day)
    lines = [f"{title} ({_short(day)}):"]
    if rows:
        for i, t in enumerate(rows, 1):
            lines.append(f"{i}. {'⭐ ' if t['first'] else ''}{keep(_label(t, day))}")
    else:
        lines.append("(chưa có việc nào, gõ «mới: nội dung» để thêm)")
    done = done_on(db, day)
    if done:
        lines.append("")
        lines.append(f"Đã xong hôm nay ({len(done)}):")
        lines += [f"✓ {keep(t['text'])}" for t in done[-SHOW_DONE:]]
    later = later_tasks(db, day)
    if later:
        lines.append(f"Hẹn ngày sau: {len(later)} việc")
    if howto:
        lines += ["", HOWTO]
    return "\n".join(lines)


def counts(db, day):
    return {"open": len(open_tasks(db, day)), "done_today": len(done_on(db, day))}
