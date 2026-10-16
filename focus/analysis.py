"""Biến mẫu thô thành số liệu: timeline, khối tập trung, điểm, streak, tổng kết tuần.

Quy tắc:
- Một mẫu ghi trạng thái của khoảng thời gian `dur` giây kết thúc tại `ts`.
- Khoảng trống lớn giữa 2 mẫu (tracker tắt, máy ngủ) và lúc khoá máy = rời máy.
- Không chạm phím/chuột >= idle_threshold: inactive; dài >= away_threshold: rời máy.
- Còn lại: "vdi" nếu VDI ở trước (hoặc app trong extra_focus_processes), không thì "other" (sao nhãng).
- Bảng "app ngoài VDI" không liệt kê chính app VDI (citrix.desktopviewer.app.exe...): khi VDI thu nhỏ mà Windows vẫn
  giữ cửa sổ VDI đã thu nhỏ làm cửa sổ "đang chọn" (bấm nút thu nhỏ rồi chỉ cuộn chuột / đọc app khác, chưa bấm vào
  app nào), thời gian đó vẫn là VDI thu nhỏ (không tập trung) nhưng không biết app thật đang xem là app nào.
- Khối tập trung = các đoạn "vdi" nối nhau (ngắt <= focus_gap), dài >= min_focus_block_minutes.
- Tập trung sâu = tổng thời gian "vdi" bên trong các khối tập trung.
- Nghỉ phép nửa ngày (ghi chú leave_part): mẫu nằm trong phần nghỉ không tính (tracker vốn không ghi; báo nghỉ
  muộn thì bỏ qua mẫu đã ghi), mục tiêu ngày còn một nửa (điểm, streak, tổng kết tuần đều theo mục tiêu này).
"""
import bisect
import datetime as dt
import json
import threading
import time

from . import holidays
from .logs import get_logger
from .schedule import is_lunch
from .storage import get_note

log = get_logger()

VDI_CLOSED_MIN_SECONDS = 60  # cửa sổ VDI mất ít hơn chừng này (kết nối lại, đổi toàn màn hình) không tính
DAY_NAMES = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]

_memo = {}
_memo_lock = threading.Lock()


def day_bounds(day):
    d = dt.datetime.strptime(day, "%Y-%m-%d")
    return d.timestamp(), (d + dt.timedelta(days=1)).timestamp()


def hour_end(t):
    d = dt.datetime.fromtimestamp(t).replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    return d.timestamp()


def fmt_dur(sec):
    m = int(round((sec or 0) / 60))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def fmt_t(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%H:%M")


def leave_part(db, day):
    """"am" | "pm" nếu ngày đó nghỉ phép nửa ngày, không thì None."""
    v = get_note(db, day).get("leave_part")
    return v if v in ("am", "pm") else None


def leave_bounds(cfg, day, leave):
    """(từ, đến) epoch của phần nghỉ phép: sáng = đầu ngày -> lunch_end, chiều = lunch_start -> hết ngày."""
    d0, d1 = day_bounds(day)
    def at(hhmm):
        h, m = map(int, hhmm.split(":"))
        return d0 + h * 3600 + m * 60
    if leave == "am":
        return d0, at(cfg["lunch_end"])
    if leave == "pm":
        return at(cfg["lunch_start"]), d1
    return None


def day_goal_hours(cfg, leave):
    """Mục tiêu tập trung sâu của ngày: nghỉ nửa ngày thì còn một nửa."""
    return cfg["daily_focus_goal_hours"] / 2 if leave in ("am", "pm") else cfg["daily_focus_goal_hours"]


def analyze(db, cfg, day):
    """Số liệu 1 ngày. Kết quả được nhớ lại cho tới khi có mẫu mới (gọi nhiều lần không tốn CPU)."""
    d0, d1 = day_bounds(day)
    leave = leave_part(db, day)
    off = off_day(db, cfg, day)  # ngày nghỉ (cuối tuần, lễ, /off) mà vẫn bật tracker tay: chỉ tính làm bù trong VDI
    sig = db.execute("SELECT COUNT(*), MAX(ts), TOTAL(dur), TOTAL(idle), TOTAL(locked) FROM samples "
                     "WHERE ts > ? AND ts < ?", (d0, d1 + 3600)).fetchone()
    dbfile = db.execute("PRAGMA database_list").fetchone()[2]
    key = (dbfile, day, sig, cfg["sample_seconds"], cfg["idle_threshold_seconds"], cfg["away_threshold_seconds"],
           cfg["focus_gap_seconds"], cfg["min_focus_block_minutes"], cfg["daily_focus_goal_hours"],
           tuple(cfg["extra_focus_processes"]), tuple(sorted(vdi_processes(cfg))), leave, cfg["lunch_start"],
           cfg["lunch_end"], cfg["work_start"], cfg["work_end"], off)
    with _memo_lock:
        hit = _memo.get(key)
    if hit is not None:
        return hit
    rows = db.execute("SELECT ts,dur,idle,locked,vdi_state,fg_proc,vdi_full FROM samples "
                      "WHERE ts > ? AND ts < ? ORDER BY ts", (d0, d1 + 3600)).fetchall()
    if leave:
        lo, hi = leave_bounds(cfg, day, leave)
        rows = [r for r in rows if not lo < r[0] <= hi]  # mẫu trong phần nghỉ phép không tính
    result = _analyze_rows(rows, cfg, day, d0, d1, [] if off else official_windows(cfg, day, leave),
                           None if off else lunch_window(cfg, day))  # ngày nghỉ làm bù: không có giờ trưa
    result["goal_h"] = day_goal_hours(cfg, leave)
    result["leave"] = leave
    if off:
        result["off"] = off
    with _memo_lock:
        if len(_memo) > 64:
            _memo.clear()
        _memo[key] = result
    return result


def vdi_processes(cfg):
    """Tên tiến trình của chính app VDI (khung Desktop Viewer, MockWindow): không bao giờ là "app ngoài VDI"."""
    return set(cfg.get("vdi_processes") or []) | set(cfg.get("vdi_session_processes") or [])


MIN_EPISODE_SECONDS = 10  # thu nhỏ VDI dưới 10 giây (bấm nhầm, chuyển cửa sổ) không tính là một lần


def official_windows(cfg, day, leave=None):
    """Các khoảng giờ làm chính thức (epoch) của ngày: work_start–lunch_start và lunch_end–work_end, bỏ phần nghỉ
    phép nửa ngày. Chỉ trong các khoảng này mới đo sao nhãng / ngồi yên / rời máy; ngoài ra (trưa, sau giờ làm) chỉ
    cộng thời gian làm trong VDI (OT)."""
    d0, _ = day_bounds(day)
    def at(hhmm):
        h, m = map(int, hhmm.split(":"))
        return d0 + h * 3600 + m * 60
    ws, ls, le, we = (at(cfg[k]) for k in ("work_start", "lunch_start", "lunch_end", "work_end"))
    wins = []
    if leave != "am":
        wins.append((ws, min(ls, we)))
    if leave != "pm":
        wins.append((max(le, ws), we))
    return [(a, b) for a, b in wins if b > a]


def lunch_window(cfg, day):
    """Giờ nghỉ trưa (epoch) của ngày làm việc. Giờ trưa không tính gì cả: không sao nhãng, cũng không phải OT."""
    d0, _ = day_bounds(day)
    at = lambda hhmm: d0 + int(hhmm[:2]) * 3600 + int(hhmm[3:5]) * 60
    return at(cfg["lunch_start"]), at(cfg["lunch_end"])


def _split_official(raw, windows, skip=None):
    """Cắt các đoạn theo giờ làm chính thức. Trong giờ: giữ nguyên. Ngoài giờ: đoạn làm trong VDI thành "ot" (làm
    ngoài giờ, chỉ cộng giờ làm), các đoạn khác (ngoài VDI, ngồi yên, rời máy) bỏ: không đo sao nhãng ngoài giờ.
    skip (bắt đầu, kết thúc): khoảng bỏ hẳn, kể cả làm trong VDI (giờ nghỉ trưa không tính OT)."""
    if skip and skip[1] > skip[0]:
        cut = []
        for r in raw:
            if r[1] <= skip[0] or r[0] >= skip[1]:
                cut.append(r)
                continue
            if r[0] < skip[0]:
                cut.append((r[0], skip[0]) + tuple(r[2:]))
            if r[1] > skip[1]:
                cut.append((skip[1], r[1]) + tuple(r[2:]))
        raw = cut
    out = []
    for s, e, kind, vdi_state, proc in raw:
        cur = s
        for a, b in windows:
            if b <= cur or a >= e:
                continue
            if a > cur and kind == "vdi":
                out.append((cur, a, "ot", vdi_state, proc))
            lo, hi = max(cur, a), min(e, b)
            out.append((lo, hi, kind, vdi_state, proc))
            cur = hi
        if cur < e and kind == "vdi":
            out.append((cur, e, "ot", vdi_state, proc))
    return out


def _analyze_rows(rows, cfg, day, d0, d1, windows=None, skip=None):
    step = cfg["sample_seconds"]
    gap_limit = max(3 * step, step + 30)
    idle_thr, away_thr = cfg["idle_threshold_seconds"], cfg["away_threshold_seconds"]
    extra = cfg["extra_focus_processes"]
    vdi_apps = vdi_processes(cfg)

    slices, inactive = [], []  # inactive: (start, end, hard); hard = khoá máy / tracker tắt / máy ngủ
    closed, seen_at, gone = [], None, None  # cửa sổ VDI đã thấy rồi biến mất (Citrix tự ngắt / bị đóng)
    used = False  # đã làm trong VDI hôm nay chưa: VDI mở sẵn chưa đụng tới mà tự ngắt thì không tính (như alerts.py)
    prev_ts = None
    for ts, dur, idle, locked, vdi_state, proc, full in rows:
        contiguous = prev_ts is not None and dur <= gap_limit and ts - prev_ts <= gap_limit
        prev_ts = ts
        if vdi_state == "absent":
            if seen_at is not None and gone is None:
                # có khoảng trống trước mẫu (tracker tắt / máy ngủ): VDI mất từ lúc nào không rõ, tính từ mẫu này
                gone = seen_at if contiguous else ts - step
        else:
            if gone is not None and used:
                closed.append((gone, ts - dur))
            seen_at, gone = ts, None
            used = used or (vdi_state == "foreground" and not locked and idle < idle_thr)
        a = ts - dur
        if dur > gap_limit:
            inactive.append((a, ts - step, True))
            a = ts - step
        if locked:
            inactive.append((a, ts, True))
        elif idle >= idle_thr:
            inactive.append((ts - idle, ts, False))
        focus_app = vdi_state == "foreground" or (proc or "") in extra
        if vdi_state == "foreground" and full == 0:
            vdi_state = "windowed"  # VDI ở trước nhưng không toàn màn hình
        slices.append((a, ts, "vdi" if focus_app else "other", vdi_state, proc or "?"))

    if gone is not None and used and rows:
        closed.append((gone, rows[-1][0]))
    vdi_closed = [(a, b) for a, b in closed if b - a >= VDI_CLOSED_MIN_SECONDS
                  and cfg["work_start"] <= fmt_t(a) < cfg["work_end"] and not is_lunch(cfg, fmt_t(a))]

    # Hai quãng ngồi yên chỉ cách nhau một lần chạm lẻ (mọi lần chạm nằm gọn trong 1 mẫu rồi lại ngồi yên >= idle_thr:
    # đi ngang bàn đụng chuột, chuột Bluetooth tự gửi tín hiệu) là một quãng: vắng 8 phút có 1 lần chạm ở giữa là rời
    # máy 8 phút, không phải 2 lần ngồi yên ngắn. Cùng quy tắc với cảnh báo (alerts.py).
    inactive.sort()
    merged = []
    for s, e, hard in inactive:
        if merged and s <= merged[-1][1] + step + 1:
            ps, pe, ph = merged[-1]
            merged[-1] = (ps, max(pe, e), ph or hard)
        else:
            merged.append((s, e, hard))
    starts = [m[0] for m in merged]

    raw = []  # (start, end, kind, vdi_state, proc)
    for a, b, kind, vdi_state, proc in slices:
        a, b = max(a, d0), min(b, d1)
        if b <= a:
            continue
        i = max(bisect.bisect_right(starts, a) - 1, 0)
        cur = a
        while i < len(merged) and merged[i][0] < b:
            s, e, _ = merged[i]
            if e > cur:
                if s > cur:
                    raw.append((cur, min(s, b), kind, vdi_state, proc))
                cur = max(cur, e)
            i += 1
        if cur < b:
            raw.append((cur, b, kind, vdi_state, proc))
    for s, e, hard in merged:
        s, e = max(s, d0), min(e, d1)
        if e > s:
            raw.append((s, e, "away" if hard or e - s >= away_thr else "idle", "", ""))
    raw.sort()
    if windows is not None:
        raw = _split_official(raw, windows, skip)

    active = [r for r in raw if r[2] in ("vdi", "other", "ot")]
    result = {"day": day, "has_data": bool(active), "goal_h": cfg["daily_focus_goal_hours"]}
    if not active:
        return result
    first, last = active[0][0], active[-1][1]
    raw = [(max(r[0], first), min(r[1], last)) + r[2:] for r in raw if r[1] > first and r[0] < last]

    timeline = []
    for s, e, kind, _, _ in raw:
        if timeline and timeline[-1][2] == kind and s - timeline[-1][1] < 1:
            timeline[-1][1] = max(timeline[-1][1], e)
        else:
            timeline.append([s, e, kind])

    tot = {"vdi": 0.0, "other": 0.0, "idle": 0.0, "away": 0.0, "ot": 0.0}
    minimized = background = windowed = 0.0
    apps, hourly = {}, {}
    min_eps, min_cur, prev_min = [], 0.0, False  # các lần VDI bị thu nhỏ (trong giờ làm)
    min_spans = []  # khoảng VDI bị thu nhỏ, để tô riêng màu trên dòng thời gian của báo cáo HTML
    for s, e, kind, vdi_state, proc in raw:
        d = e - s
        tot[kind] += d
        if kind == "vdi" and vdi_state == "windowed":
            windowed += d
        if kind == "other" and proc not in vdi_apps:
            apps[proc] = apps.get(proc, 0) + d
        if kind == "other":
            if vdi_state == "minimized":
                minimized += d
                if min_spans and s - min_spans[-1][1] < 1:
                    min_spans[-1][1] = max(min_spans[-1][1], e)
                else:
                    min_spans.append([s, e])
            elif vdi_state == "background":
                background += d
        if kind in ("vdi", "other"):  # ngồi yên giữa chừng mà VDI vẫn thu nhỏ: vẫn là cùng một lần thu nhỏ
            is_min = kind == "other" and vdi_state == "minimized"
            if is_min:
                min_cur = min_cur + d if prev_min else d
            elif prev_min:
                min_eps.append(min_cur)
            prev_min = is_min
        if kind in ("vdi", "other", "ot"):
            t = s
            while t < e:
                h = dt.datetime.fromtimestamp(t).hour
                nxt = min(e, hour_end(t))
                hourly.setdefault(h, {"vdi": 0.0, "other": 0.0, "ot": 0.0})[kind] += nxt - t
                t = nxt
    if prev_min:
        min_eps.append(min_cur)

    # Số lần rời VDI sang app khác (bỏ qua các cú chuyển < 10 giây).
    exits, last_work = 0, None
    for s, e, kind in timeline:
        if kind == "other" and e - s >= 10:
            exits += last_work == "vdi"
            last_work = "other"
        elif kind == "vdi":
            last_work = "vdi"

    blocks, cur = [], None  # làm ngoài giờ (ot) liền mạch trong VDI cũng là khối tập trung (làm bù giờ thiếu)
    for s, e, kind in timeline:
        if kind not in ("vdi", "ot"):
            continue
        ot = e - s if kind == "ot" else 0.0
        if cur and s - cur["end"] <= cfg["focus_gap_seconds"]:
            cur["breaks"] += s - cur["end"] > 1  # vdi -> ot nối liền (17:00) không phải ngắt quãng
            cur["end"] = e
            cur["focus"] += e - s
            cur["ot"] += ot
        else:
            cur = {"start": s, "end": e, "focus": e - s, "breaks": 0, "ot": ot}
            blocks.append(cur)
    blocks = [b for b in blocks if b["end"] - b["start"] >= cfg["min_focus_block_minutes"] * 60]

    result.update({
        "first": first, "last": last, "span": last - first, "timeline": timeline,
        "vdi": tot["vdi"], "other": tot["other"], "idle": tot["idle"], "away": tot["away"],
        "active": tot["vdi"] + tot["other"], "minimized": minimized, "background": background,
        "exits": exits, "blocks": blocks, "deep": sum(b["focus"] for b in blocks),
        "longest": max((b["end"] - b["start"] for b in blocks), default=0),
        "apps": sorted(apps.items(), key=lambda x: -x[1])[:8], "hourly": hourly,
        "away_count": sum(1 for t in timeline if t[2] == "away"),
        # Ngồi yên 1–5 phút rồi làm tiếp: thường là cầm điện thoại/iPad.
        "short_idle_count": sum(1 for t in timeline if t[2] == "idle"),
        "inactive_10m_count": sum(1 for t in timeline if t[2] in ("idle", "away") and t[1] - t[0] >= 600),
        "minimize_count": sum(1 for x in min_eps if x >= MIN_EPISODE_SECONDS),
        "ot": tot["ot"], "deep_ot": sum(b["ot"] for b in blocks),
        "windowed": windowed,
        "vdi_closed": vdi_closed, "minimized_spans": min_spans,
    })
    return result


OT_RANGE_GAP_SECONDS = 600  # hai đoạn làm ngoài giờ cách nhau dưới 10 phút: gộp thành một khoảng


def ot_ranges(a, gap=OT_RANGE_GAP_SECONDS):
    """Các khoảng giờ làm ngoài giờ trong VDI (OT) của ngày: [(bắt đầu, kết thúc)], đoạn gần nhau gộp lại."""
    out = []
    for s, e, kind in a.get("timeline") or []:
        if kind != "ot":
            continue
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(x) for x in out]


def focus_score(a):
    """0–100: 70 điểm cho tập trung sâu so với mục tiêu + 30 điểm cho tỉ lệ thời gian trong VDI."""
    if not a.get("has_data"):
        return 0
    goal = a["goal_h"] * 3600 or 1
    ratio = a["vdi"] / a["active"] if a["active"] else 0
    return round(70 * min(a["deep"] / goal, 1) + 30 * ratio)


STATS_VERSION = 4  # đổi cách tính số liệu ngày thì tăng số này: daily_stats cũ được tính lại từ mẫu thô


def daily_stats(db, cfg, day, refresh=False):
    """Số liệu gọn của 1 ngày (dict) hoặc None. Lưu vào bảng daily_stats để giữ lâu dài."""
    today = dt.date.today().isoformat()
    row = db.execute("SELECT data, updated FROM daily_stats WHERE day=?", (day,)).fetchone()
    stale = False
    if row and not refresh and json.loads(row[0]).get("v") != STATS_VERSION:
        refresh = True  # số liệu lưu theo cách tính cũ (trước 2.3.0: chưa tách giờ làm / ngoài giờ): tính lại
        log.info("Số liệu ngày %s lưu theo cách tính cũ, tính lại theo bản mới.", day)
    if row and not refresh and day != today:
        # Ngày cũ: số liệu lưu giữa ngày (/today...) mà sau đó còn mẫu mới (tracker bị tắt ngang, không kịp
        # chốt cuối ngày) thì tính lại, không để "đóng băng" số liệu hôm qua.
        d0, d1 = day_bounds(day)
        max_ts = db.execute("SELECT MAX(ts) FROM samples WHERE ts > ? AND ts < ?", (d0, d1 + 3600)).fetchone()[0]
        stale = max_ts is not None and max_ts > (row[1] or 0)
        if not stale:
            return json.loads(row[0])
        log.info("Số liệu ngày %s lưu lúc %s đã cũ (còn mẫu tới %s), tính lại.", day,
                 fmt_t(row[1] or 0), fmt_t(max_ts))
    a = analyze(db, cfg, day)
    if not a["has_data"]:
        if row:
            old = json.loads(row[0])
            if old.get("v") != STATS_VERSION:  # mẫu thô đã dọn: giữ số cũ, đánh dấu để khỏi tính lại mỗi lần
                old["v"] = STATS_VERSION
                with db:
                    db.execute("UPDATE daily_stats SET data=?, updated=? WHERE day=?", (json.dumps(old), time.time(), day))
                return old
        if stale:  # mẫu mới chỉ là khoá máy / ngồi yên: giữ số liệu cũ, đánh dấu đã kiểm
            with db:
                db.execute("UPDATE daily_stats SET updated=? WHERE day=?", (time.time(), day))
        return json.loads(row[0]) if row else None
    rec = {"v": STATS_VERSION, "day": day, "deep": a["deep"], "vdi": a["vdi"], "other": a["other"], "idle": a["idle"],
           "away": a["away"], "first": a["first"], "last": a["last"], "exits": a["exits"],
           "minimized": a["minimized"], "longest": a["longest"], "score": focus_score(a),
           "short_idle_count": a["short_idle_count"], "windowed": a["windowed"],
           "blocks": [[b["start"], b["end"]] for b in a["blocks"]],
           "hourly": {str(h): round(v["vdi"]) for h, v in a["hourly"].items()},
           "hourly_other": {str(h): round(v["other"]) for h, v in a["hourly"].items() if v["other"]},
           "apps": [[p, round(t)] for p, t in a["apps"][:5]], "goal_h": a["goal_h"],
           "ot": a["ot"], "deep_ot": a["deep_ot"], "away_count": a["away_count"],
           "minimize_count": a["minimize_count"], "inactive_10m_count": a["inactive_10m_count"],
           "ot_ranges": [[round(s), round(e)] for s, e in ot_ranges(a)]}
    if a.get("off"):  # ngày nghỉ bật tracker tay: chỉ có giờ làm bù trong VDI, không chấm điểm
        rec["off"] = a["off"]
    else:
        from .scoring import total_score  # import trễ: scoring -> analysis
        sc = total_score(a, get_note(db, day))
        rec["total"] = sc["total"] if sc else 0
    if a.get("leave"):
        rec["leave"] = a["leave"]
    data = json.dumps(rec)
    if not row or row[0] != data or stale:
        with db:
            db.execute("INSERT OR REPLACE INTO daily_stats VALUES (?,?,?)", (day, data, time.time()))
    return rec


def off_detail(db, cfg, day):
    """(loại, lý do) nếu là ngày nghỉ, không thì (None, None).
    loại: leave (/off, /leave cả ngày) | weekend | config (extra_off_days) | holiday | observed (nghỉ bù)."""
    note = get_note(db, day)
    if note.get("day_off"):
        return "leave", note["day_off"]
    return holidays.off_detail(cfg, day)


def off_day(db, cfg, day):
    """Lý do nghỉ (/off, cuối tuần, lễ) hoặc None nếu là ngày làm việc."""
    return off_detail(db, cfg, day)[1]


def streak(db, cfg, day):
    """Số ngày làm việc liên tiếp đạt mục tiêu, tính tới day. Bỏ qua ngày nghỉ.
    Hôm nay chưa đạt thì chưa cộng nhưng không làm đứt chuỗi. Ngày nghỉ nửa ngày: mục tiêu một nửa."""
    d, count = dt.date.fromisoformat(day), 0
    for _ in range(400):
        ds = d.isoformat()
        d -= dt.timedelta(days=1)
        if off_day(db, cfg, ds):
            continue
        rec = daily_stats(db, cfg, ds)
        goal = day_goal_hours(cfg, leave_part(db, ds)) * 3600
        if rec and rec["deep"] >= goal:
            count += 1
        elif ds != day:
            break
    return count


def golden_hour(hourly):
    """'HH:00–HH:00' của giờ có nhiều thời gian trong VDI nhất."""
    if not hourly:
        return ""
    def vdi(k):
        v = hourly[k]
        return v["vdi"] if isinstance(v, dict) else v
    h = int(max(hourly, key=vdi))
    return f"{h:02d}:00–{h + 1:02d}:00"


def day_facts(db, cfg, day):
    """Số liệu + ghi chú 1 ngày, đã làm tròn, để đưa cho AI nhận xét."""
    a = analyze(db, cfg, day)
    note = get_note(db, day)
    base = dt.date.fromisoformat(day)
    prev = [daily_stats(db, cfg, (base - dt.timedelta(days=i)).isoformat()) for i in range(1, 8)]
    prev = [r for r in prev if r]
    facts = {"day": day, "weekday": DAY_NAMES[base.weekday()], "goal_hours": a["goal_h"]}
    if a.get("leave"):
        facts["leave"] = f"{'nghỉ phép buổi sáng' if a['leave'] == 'am' else 'nghỉ phép buổi chiều'}, mục tiêu còn một nửa"
    if a["has_data"]:
        facts.update({
            "work_from_to": f"{fmt_t(a['first'])}–{fmt_t(a['last'])}",
            "deep_hours": round(a["deep"] / 3600, 1), "vdi_hours": round(a["vdi"] / 3600, 1),
            "outside_vdi_minutes": round(a["other"] / 60), "vdi_minimized_minutes": round(a["minimized"] / 60),
            "idle_minutes": round(a["idle"] / 60), "away_minutes": round(a["away"] / 60),
            "out_of_vdi_exits": a["exits"], "short_idle_count_1_5min": a["short_idle_count"],
            "vdi_not_fullscreen_minutes": round(a["windowed"] / 60),
            "vdi_closed": [f"{fmt_t(x)}–{fmt_t(y)}" for x, y in a.get("vdi_closed", [])], "score": focus_score(a), "streak_days": streak(db, cfg, day),
            "focus_blocks": [f"{fmt_t(b['start'])}–{fmt_t(b['end'])}" for b in a["blocks"]],
            "golden_hour": golden_hour(a["hourly"]),
            "top_apps_outside_vdi": [f"{p} {round(t / 60)}m" for p, t in a["apps"][:3]],
            "vdi_minimize_count": a["minimize_count"], "inactive_over_10min_count": a["inactive_10m_count"],
            "away_count": a["away_count"],
        })
        if a["ot"]:
            facts["overtime_vdi_minutes"] = round(a["ot"] / 60)
            facts["overtime_deep_minutes"] = round(a["deep_ot"] / 60)
        from .scoring import advice, explain, total_score  # import trễ: scoring -> analysis
        sc = total_score(a, note)
        facts["total_score"] = sc["total"]
        facts["total_score_explained"] = explain(a, sc)  # AI giải thích lại điểm tổng bằng đúng các số này
        facts["total_score_10"] = sc["ten"]
        facts["total_score_parts"] = sc["parts"]
        facts["interruptions_per_hour"] = sc["per_hour"]
        facts["gift_robot"] = f"{sc['tier']['grade']} {sc['tier']['name']} ({sc['tier']['desc']})"
        tip = advice(a, sc)
        if tip:
            facts["science_advice"] = tip
    else:
        facts["deep_hours"] = 0
    if prev:
        facts["avg_deep_hours_7d"] = round(sum(r["deep"] for r in prev) / len(prev) / 3600, 1)
    for k in ("plan", "output", "issues", "distractions", "energy", "tomorrow"):
        if note.get(k):
            facts[k] = note[k]
    if note.get("energy") and note.get("energy_source") == "auto":
        facts["energy_source"] = "app_uoc_tinh"
    from . import pending  # import trễ: pending -> intent -> actions
    carry = pending.pending_after(db, cfg, day, off_day)
    if carry:
        facts["pending_carry"] = [pending.item_label(it) for it in carry[:pending.MAX_ITEMS]]
    if note.get("as400_start"):
        facts["as400"] = f"{note['as400_start']}–{note.get('as400_end') or '?'}"
    if prev:
        facts["recent_days"] = [{"date": r["day"], "weekday": DAY_NAMES[dt.date.fromisoformat(r["day"]).weekday()],
                                 "deep_hours": round(r["deep"] / 3600, 1), "score": r.get("score", 0)}
                                for r in prev[:5]]  # có ngày đầy đủ để AI không nhầm với hôm nay
    recent_issues = []
    for i in range(1, 8):
        ds = (base - dt.timedelta(days=i)).isoformat()
        for line in (get_note(db, ds).get("issues") or "").splitlines():
            if line.strip(" -"):
                recent_issues.append({"date": ds, "issue": line.strip(" -")[:200]})
    if recent_issues:
        facts["recent_issues"] = recent_issues[:15]
    return facts


def week_facts(db, cfg, day):
    """Tổng kết tuần, từ thứ Hai tới day."""
    d = dt.date.fromisoformat(day)
    monday = d - dt.timedelta(days=d.weekday())
    days, issues, hourly, off_ot = [], [], {}, []
    for i in range((d - monday).days + 1):
        ds = (monday + dt.timedelta(days=i)).isoformat()
        note = get_note(db, ds)
        if note.get("issues"):
            issues += [f"{ds[5:]}: {line.strip(' -')}" for line in note["issues"].splitlines() if line.strip(" -")]
        if off_day(db, cfg, ds):
            rec = daily_stats(db, cfg, ds)  # ngày nghỉ mà bật tracker làm bù: chỉ cộng giờ làm ngoài giờ
            if rec and rec.get("ot"):
                off_ot.append(rec)
            continue
        rec = daily_stats(db, cfg, ds)
        if rec:
            days.append(rec)
            for h, sec in rec["hourly"].items():
                hourly[h] = hourly.get(h, 0) + sec
    iso = monday.isocalendar()
    facts = {"week": f"{iso[0]}-W{iso[1]:02d}", "from": monday.isoformat(), "to": day,
             "goal_hours_per_day": cfg["daily_focus_goal_hours"], "work_days": len(days),
             "issues": issues, "streak_days": streak(db, cfg, day)}
    if off_ot:
        facts["off_day_overtime"] = [
            f"{DAY_NAMES[dt.date.fromisoformat(r['day']).weekday()]} {r['day'][5:]} ({r['off']}): làm bù trong VDI "
            f"{round(r['ot'] / 3600, 1)}h, tập trung sâu {round(r['deep'] / 3600, 1)}h" for r in off_ot]
        facts["overtime_hours"] = round(sum(r["ot"] for r in off_ot) / 3600, 1)
    if days:
        best = max(days, key=lambda r: r["deep"])
        worst = min(days, key=lambda r: r["deep"])
        label = lambda r: f"{DAY_NAMES[dt.date.fromisoformat(r['day']).weekday()]} {r['day'][5:]} ({round(r['deep'] / 3600, 1)}h)"
        facts.update({
            "deep_hours_total": round(sum(r["deep"] for r in days) / 3600, 1),
            "deep_hours_avg": round(sum(r["deep"] for r in days) / len(days) / 3600, 1),
            "avg_score": round(sum(r.get("score", 0) for r in days) / len(days)),
            "avg_total_score": round(sum(r.get("total", 0) for r in days) / len(days)),
            "overtime_hours": round(sum(r.get("ot", 0) for r in days + off_ot) / 3600, 1),
            "days_reached_goal": sum(1 for r in days
                                     if r["deep"] >= day_goal_hours(cfg, leave_part(db, r["day"])) * 3600),
            "best_day": label(best), "worst_day": label(worst),
            "golden_hours": [f"{int(h):02d}:00–{int(h) + 1:02d}:00"
                             for h in sorted(hourly, key=lambda h: -hourly[h])[:2] if hourly[h] > 0],
            "per_day": [f"{r['day'][5:]} {round(r['deep'] / 3600, 1)}h điểm {r.get('score', 0)} điểm tổng {r.get('total', 0)}"
                        for r in days],
        })
    return facts


def golden_hours(db, cfg, day, days=14, min_days=5):
    """2 khung giờ tập trung tốt nhất trong `days` ngày làm việc gần nhất (trước day), dạng "HH:00-HH:00".
    Chưa đủ min_days ngày có số liệu thì trả []."""
    if cfg["golden_hours"] != "auto":
        return list(cfg["golden_hours"])
    base = dt.date.fromisoformat(day)
    hourly, n = {}, 0
    for i in range(1, days * 2):
        ds = (base - dt.timedelta(days=i)).isoformat()
        if off_day(db, cfg, ds):
            continue
        rec = daily_stats(db, cfg, ds)
        if not rec:
            continue
        n += 1
        for h, sec in rec["hourly"].items():
            hourly[int(h)] = hourly.get(int(h), 0) + sec
        if n >= days:
            break
    if n < min_days:
        return []
    top = [h for h in sorted(hourly, key=lambda h: -hourly[h])[:2] if hourly[h] > 0]
    return [f"{h:02d}:00-{h + 1:02d}:00" for h in sorted(top)]


def in_golden(ranges, hhmm):
    return any(r[:5] <= hhmm < r[6:] for r in ranges)
