"""Việc còn tồn, để sáng nay bot nhắc lại (không cần AI, không bao giờ thiếu).

Việc còn tồn của một ngày = việc trong kế hoạch (plan) chưa thấy trong output + các issue đã ghi. Việc tồn **cộng dồn**
qua các ngày làm việc: việc tồn hôm qua mà hôm nay chưa thấy ghi xong (không có dòng output nào khớp) thì thành việc tồn
hôm nay, giữ ngày bắt đầu tồn, tối đa CARRY_WORKDAYS ngày làm việc. Issue cũng vậy: hết tồn khi một dòng output của ngày
sau khớp với nó. App không biết chắc việc đã xong hay chưa (chỉ dựa vào những gì bạn ghi), nên tin nhắn nói rõ "chưa
thấy ghi xong".

Khớp plan với output: bỏ dấu, bỏ số thứ tự, so từng từ; một việc coi là đã xong khi >= 60% từ có nghĩa của nó nằm
trong cùng một dòng output (ví dụ plan "Gởi estimation UAT release cho SH" và output "đã gửi estimation UAT cho SH").
"""
import datetime as dt
import re

from .intent import fold
from .storage import get_note

LOOKBACK_DAYS = 31     # tìm ngày làm việc trước trong chừng này ngày lịch
CARRY_WORKDAYS = 10    # việc tồn quá 10 ngày làm việc (khoảng 2 tuần) thì thôi nhắc
MATCH_RATIO = 0.6
MAX_ITEMS = 10         # số dòng hiện trong tin nhắn; còn nữa thì ghi "và N việc nữa"
STOP_WORDS = {"cho", "va", "cua", "voi", "the", "nhung", "cac", "mot", "da", "xong", "lam", "viec", "roi", "nha",
              "nhe", "a", "o", "di", "de", "can", "phai", "check", "gui", "goi"}
_NUM_RE = re.compile(r"^\s*(?:[-*•–]|\d+[.)/:-]|[a-z][.)])\s*", re.I)
_TIME_RE = re.compile(r"\s*\(\d{1,2}:\d{2}\)\s*$")


def _lines(text):
    out = []
    for raw in re.split(r"[\n;]+", text or ""):
        line = _TIME_RE.sub("", _NUM_RE.sub("", raw.strip())).strip(" .")
        if len(line) >= 2:
            out.append(line)
    return out


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", fold(text).lower()) if w not in STOP_WORDS and len(w) > 1}


def _done(item, outputs):
    words = _words(item)
    if not words:
        return any(fold(item).lower() in fold(o).lower() for o in outputs)
    return any(len(words & _words(o)) >= MATCH_RATIO * len(words) for o in outputs)


def pending_of(note, limit=MAX_ITEMS):
    """Từ ghi chú một ngày: [("plan", việc), ("issue", việc)] còn tồn, theo thứ tự đã ghi, không trùng."""
    outputs = _lines(note.get("output"))
    items, seen = [], set()
    for kind, field in (("plan", "plan"), ("issue", "issues")):
        for line in _lines(note.get(field)):
            key = fold(line).lower()
            if key in seen or (kind == "plan" and _done(line, outputs)):
                continue
            seen.add(key)
            items.append((kind, line))
    return items[:limit] if limit else items


def _workdays_before(db, cfg, day, off_day):
    """Tối đa CARRY_WORKDAYS ngày làm việc ngay trước day (trong LOOKBACK_DAYS ngày lịch), cũ -> mới."""
    d = dt.date.fromisoformat(day)
    out = []
    for i in range(1, LOOKBACK_DAYS + 1):
        prev = (d - dt.timedelta(days=i)).isoformat()
        if not off_day(db, cfg, prev):
            out.append(prev)
            if len(out) >= CARRY_WORKDAYS:
                break
    return out[::-1]


def _carry(db, days):
    """Cộng dồn việc tồn qua các ngày (cũ -> mới): [(kind, việc, ngày bắt đầu tồn)]."""
    items = []
    for ds in days:
        note = get_note(db, ds)
        outputs = _lines(note.get("output"))
        if outputs:  # ngày không ghi output: việc tồn giữ nguyên (chưa có cập nhật)
            items = [it for it in items if not _done(it[1], outputs)]
        keys = {fold(it[1]).lower() for it in items}
        for kind, text in pending_of(note, limit=None):
            if fold(text).lower() not in keys:
                keys.add(fold(text).lower())
                items.append((kind, text, ds))
    return items


def previous_pending(db, cfg, day, off_day):
    """Việc tồn mang sang day: (ngày làm việc gần nhất có ghi chú, [(kind, việc, ngày bắt đầu tồn)]) hoặc (None, []).
    off_day(db, cfg, ngày) -> True nếu ngày nghỉ."""
    days = _workdays_before(db, cfg, day, off_day)
    last = next((ds for ds in reversed(days) if any(get_note(db, ds).get(k) for k in ("plan", "output", "issues"))),
                None)
    if last is None:
        return None, []
    return last, _carry(db, days)


def pending_after(db, cfg, day, off_day):
    """Việc tồn sau khi xong ngày day (tính cả kế hoạch / output / issue của chính day): chuyển sang ngày làm việc kế.
    Dùng cho báo cáo HTML và đánh giá AI cuối ngày. [(kind, việc, ngày bắt đầu tồn)]."""
    days = _workdays_before(db, cfg, day, off_day) + ([] if off_day(db, cfg, day) else [day])
    return _carry(db, days)


WEEKDAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]
SHORT_DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def since_label(ds):
    d = dt.date.fromisoformat(ds)
    return f"{SHORT_DAYS[d.weekday()]} {d:%d/%m}"


def item_label(item, with_since=True):
    """("plan", "Tạo wu", "2026-10-14") -> "Tạo wu (tồn từ T4 14/10)"; issue có tiền tố "issue: "."""
    kind, text, since = item
    return ("" if kind == "plan" else "issue: ") + text + (f" (tồn từ {since_label(since)})" if with_since else "")


def pending_text(prev_day, items):
    """Khối tin nhắn cố định gắn dưới lời chào sáng. Không có việc tồn -> ""."""
    if not items:
        return ""
    same = all(it[2] == prev_day for it in items)
    if same:
        d = dt.date.fromisoformat(prev_day)
        head = f"📌 Việc còn tồn từ {WEEKDAYS[d.weekday()]} {d:%d/%m} (chưa thấy ghi xong):"
    else:
        head = "📌 Việc còn tồn, cộng dồn từ các ngày trước (chưa thấy ghi xong):"
    lines = []
    for it in items[:MAX_ITEMS]:
        label = it[1] + ("" if same or it[2] == prev_day else f" (tồn từ {since_label(it[2])})")
        lines.append(f"• {label}" if it[0] == "plan" else f"• ⚠️ issue: {label}")
    if len(items) > MAX_ITEMS:
        lines.append(f"• … và {len(items) - MAX_ITEMS} việc nữa")
    return "\n".join([head] + lines + ["Xong việc nào thì báo bot (ví dụ «xong gửi estimation») để bot ghi output. "
                                         "Chưa ghi xong thì mai bot nhắc tiếp."])
