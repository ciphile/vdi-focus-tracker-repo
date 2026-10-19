"""Báo cáo: file HTML từng ngày (reports/focus-YYYY-MM-DD.html), từng tuần (reports/focus-week-YYYY-Www.html) và
tóm tắt chữ cho Telegram. Giao diện HTML nằm ở report_html.py.

Không gọi AI ở đây: chỉ chèn nhận xét AI nếu đã có sẵn trong cache.
"""
import datetime as dt
import html
import os
import re

from . import persona, scoring
from .analysis import (DAY_NAMES, analyze, daily_stats, day_bounds, fmt_dur, fmt_t, focus_score, off_day, ot_ranges,
                       streak, time_breakdown)
from .schedule import LEAVE_NAMES
from .storage import get_note


def esc(x):
    return html.escape(str(x if x is not None else "")).replace("\n", "<br>")


KIND_LABEL = {"vdi": "Làm trong VDI", "other": "Ngoài VDI (sao nhãng)",
              "idle": "Inactive ngắn", "away": "Rời máy / khoá màn hình", "ot": "Làm ngoài giờ trong VDI (OT)"}


def avg_dur(total, count):
    return fmt_dur(total / count) if count else "–"


def distraction_stats(db, cfg, day, days=14):
    """Thống kê sao nhãng của `days` ngày làm việc gần nhất (tính cả day): trung bình giờ sao nhãng / ngày (ngoài VDI
    + thu nhỏ VDI, đo trong giờ làm), số lần thu nhỏ VDI trung bình, giờ hay sao nhãng nhất (đo được), và các điều làm
    mất tập trung bạn tự ghi: số lần, giờ hay ghi nhất."""
    base = dt.date.fromisoformat(day)
    recs, hourly, noted, note_hours = [], {}, 0, {}
    for i in range(days * 2):
        ds = (base - dt.timedelta(days=i)).isoformat()
        if off_day(db, cfg, ds):
            continue
        rec = daily_stats(db, cfg, ds)
        if not rec:
            continue
        recs.append(rec)
        for h, sec in (rec.get("hourly_other") or {}).items():
            hourly[int(h)] = hourly.get(int(h), 0) + sec
        for line in (get_note(db, ds).get("distractions") or "").splitlines():
            if line.strip(" -"):
                noted += 1
                m = re.search(r"\((\d{1,2}):\d{2}\)\s*$", line)
                if m:
                    note_hours[int(m.group(1))] = note_hours.get(int(m.group(1)), 0) + 1
        if len(recs) >= days:
            break
    if not recs:
        return None
    top = lambda d: [f"{h:02d}:00–{h + 1:02d}:00" for h in sorted(d, key=lambda h: -d[h])[:2] if d[h] > 0]
    return {"days": len(recs), "avg_other": sum(r["other"] for r in recs) / len(recs),
            "avg_minimize_count": sum(r.get("minimize_count", 0) for r in recs) / len(recs),
            "top_hours": top(hourly), "noted": noted, "noted_hours": top(note_hours)}


OT_HISTORY_DAYS = 14
OT_MIN_SECONDS = 60  # dưới 1 phút ngoài giờ (chạm chuột lúc 17:00) không tính là ngày có OT


def ot_history(db, cfg, day, days=OT_HISTORY_DAYS):
    """OT (làm trong VDI ngoài giờ: trước/sau giờ làm, ngày nghỉ bật bot làm bù) của `days` ngày gần nhất tính cả
    day, CHỈ các ngày có OT, cũ trước mới sau. Trả {"days": [{day, ot, off, ranges}], "total", "count", "span"}."""
    base = dt.date.fromisoformat(day)
    rows = []
    for i in range(days - 1, -1, -1):
        ds = (base - dt.timedelta(days=i)).isoformat()
        rec = daily_stats(db, cfg, ds)
        if not rec or (rec.get("ot") or 0) < OT_MIN_SECONDS:
            continue
        rows.append({"day": ds, "ot": rec["ot"], "off": rec.get("off") or "",
                     "ranges": [tuple(r) for r in rec.get("ot_ranges") or []]})
    return {"days": rows, "total": sum(r["ot"] for r in rows), "count": len(rows), "span": days}


LATE_OT_MAX_DAYS = 7  # nhìn lùi tối đa chừng này ngày để tìm ngày làm việc trước


def late_ot(db, cfg, day, max_days=LATE_OT_MAX_DAYS):
    """OT chưa có trong báo cáo cuối ngày trước: các ngày từ ngày làm việc trước tới hôm qua (cũ trước mới sau).
    Ngày làm việc: chỉ phần OT sau giờ gửi tổng kết (daily_summary_at), vì phần trước đó đã nằm trong báo cáo hôm đó.
    Ngày nghỉ (cuối tuần, lễ, /off) có bật bot làm bù: cả ngày. OT luôn thuộc ngày nó xảy ra (theo lịch, qua 00:00 là
    ngày mới): ở đây chỉ nhắc lại để thấy đủ, không cộng vào hôm nay.
    Trả [{"day", "off", "late" (giây), "ranges", "total" (giây thực làm trong VDI cả ngày đó = trong giờ + OT)}]."""
    base = dt.date.fromisoformat(day)
    h, m = map(int, cfg["daily_summary_at"].split(":"))
    rows = []
    for i in range(1, max_days + 1):
        ds = (base - dt.timedelta(days=i)).isoformat()
        off = off_day(db, cfg, ds)
        a = analyze(db, cfg, ds)
        if a.get("has_data"):
            cut = day_bounds(ds)[0] if off else day_bounds(ds)[0] + h * 3600 + m * 60
            late = sum(e - max(s, cut) for s, e, kind in a["timeline"] if kind == "ot" and e > cut)
            if late >= OT_MIN_SECONDS:
                rows.append({"day": ds, "off": off or "", "late": late,
                             "total": round(a["vdi"] / 60) * 60 + round(a.get("ot", 0) / 60) * 60,
                             "ranges": [(max(s, cut), e) for s, e in ot_ranges(a) if e > cut]})
        if not off:
            break
    return rows[::-1]


def real_work_line(a):
    """'💼 Thực làm trong VDI: 5h 00m (trong giờ 2h 00m + OT 3h 00m)': OT của chính ngày này, không lấy ngày khác."""
    vdi, ot = (int(round((a.get(k) or 0) / 60)) for k in ("vdi", "ot"))  # cộng theo phút đã làm tròn: cộng tay khớp
    if not ot:
        return f"💼 Thực làm trong VDI: {fmt_dur(vdi * 60)} (chưa có OT)"
    return f"💼 Thực làm trong VDI: {fmt_dur((vdi + ot) * 60)} (trong giờ {fmt_dur(vdi * 60)} + OT {fmt_dur(ot * 60)})"


def late_ot_texts(rows):
    """Mỗi dòng: OT ngày trước làm sau giờ báo cáo + tổng thực làm cả ngày đó."""
    out = []
    for r in rows:
        d = dt.date.fromisoformat(r["day"])
        name = f"{['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'][d.weekday()]} {d:%d/%m}"
        ranges = ", ".join(f"{fmt_t(s)}–{fmt_t(e)}" for s, e in r["ranges"])
        what = f"làm bù {name} ({r['off']})" if r["off"] else f"OT {name} sau giờ báo cáo"
        out.append(f"🌙 {what}: {fmt_dur(r['late'])}" + (f" ({ranges})" if ranges else "")
                   + f" → {name} thực làm trong VDI tổng {fmt_dur(r['total'])}")
    return out


def ot_label(row):
    """'T7 10/10 (cuối tuần): 2h 10m (09:05–11:20, 14:00–14:55)'"""
    d = dt.date.fromisoformat(row["day"])
    name = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"][d.weekday()]
    ranges = ", ".join(f"{fmt_t(s)}–{fmt_t(e)}" for s, e in row["ranges"])
    return (f"{name} {d:%d/%m}" + (f" ({row['off']})" if row["off"] else "") + f": {fmt_dur(row['ot'])}"
            + (f" ({ranges})" if ranges else ""))


def ot_history_text(hist):
    """Khối chữ cho Telegram. Không có ngày nào OT -> ""."""
    if not hist["days"]:
        return ""
    return "\n".join([f"🌙 OT {hist['span']} ngày gần nhất: tổng {fmt_dur(hist['total'])} trong {hist['count']} ngày"]
                     + [f"  • {ot_label(r)}" for r in hist["days"]])


def leave_line(a):
    """'Nghỉ phép buổi sáng: mục tiêu còn 2h' cho ngày nghỉ nửa ngày, không thì ""."""
    if not a.get("leave"):
        return ""
    name = LEAVE_NAMES.get(a["leave"], "nghỉ phép")
    return f"{name[0].upper() + name[1:]}: buổi đó không theo dõi, mục tiêu còn {a['goal_h']:g}h."


def insights(a):
    out = []
    goal = a["goal_h"] * 3600
    pct = a["deep"] / goal * 100 if goal else 0
    out.append(f"Tập trung sâu {fmt_dur(a['deep'])}, đạt {pct:.0f}% mục tiêu {a['goal_h']:g}h.")
    if a["blocks"]:
        b = max(a["blocks"], key=lambda b: b["end"] - b["start"])
        out.append(f"Khối dài nhất {fmt_dur(b['end'] - b['start'])} ({fmt_t(b['start'])}–{fmt_t(b['end'])}).")
    if a["hourly"]:
        h = max(a["hourly"], key=lambda h: a["hourly"][h]["vdi"])
        out.append(f"Giờ vàng hôm nay: {h:02d}:00–{h + 1:02d}:00. Thử chặn lịch họp vào khung này.")
    if a["exits"] >= 20:
        out.append(f"Rời VDI {a['exits']} lần, khá nhiều. Gom chat/email vào 2–3 khung cố định.")
    if a["apps"]:
        out.append("App ngoài VDI tốn thời gian nhất: " + ", ".join(
            f"{p} ({fmt_dur(s)})" for p, s in a["apps"][:3]) + ".")
    return out


def render_html(cfg, a, note, week, extra=None):
    """HTML báo cáo ngày (giao diện ở report_html.py)."""
    from .report_html import render_day  # import trễ: report_html dùng các hàm ở đây
    return render_day(cfg, a, note, week, extra)


def _write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)  # ghi file tạm rồi đổi tên: trình duyệt không bao giờ thấy file viết dở


def write_report(db, cfg, day):
    """Tạo file HTML (không gọi AI: chỉ chèn lời khuyên AI nếu đã có sẵn trong cache)."""
    from . import pending  # import trễ: pending -> intent -> actions -> report
    a = analyze(db, cfg, day)
    base = dt.date.fromisoformat(day)
    week = [daily_stats(db, cfg, (base - dt.timedelta(days=i)).isoformat()) for i in range(6, -1, -1)]
    review = db.execute("SELECT text FROM ai_cache WHERE key LIKE ? ORDER BY created DESC LIMIT 1",
                        (f"review:{day}:%",)).fetchone()
    extra = {"streak": streak(db, cfg, day), "review": review[0] if review else "",
             "distractions": distraction_stats(db, cfg, day), "ot_history": ot_history(db, cfg, day),
             "late_ot": late_ot(db, cfg, day), "pending": pending.pending_after(db, cfg, day, off_day)}
    path = os.path.join(cfg["report_dir"], f"focus-{day}.html")
    _write(path, render_html(cfg, a, get_note(db, day), [w for w in week if w], extra))
    return path, a


def week_report_data(db, cfg, day):
    """Số liệu cho báo cáo tuần HTML: tổng kết tuần (week_facts) + từng ngày từ thứ Hai tới day (số liệu gọn,
    phân tích chi tiết nếu còn mẫu thô, ghi chú, điểm tổng), app ngoài VDI cả tuần, đánh giá AI tuần đã có sẵn."""
    from .analysis import week_facts
    facts = week_facts(db, cfg, day)
    d = dt.date.fromisoformat(day)
    monday = d - dt.timedelta(days=d.weekday())
    days, apps, rows = [], {}, []
    for i in range((d - monday).days + 1):
        ds = (monday + dt.timedelta(days=i)).isoformat()
        off = off_day(db, cfg, ds)
        rec = daily_stats(db, cfg, ds)
        a = analyze(db, cfg, ds) if rec else None
        note = get_note(db, ds)
        if off and not (rec and rec.get("ot")) and not any(note.values()):
            continue  # cuối tuần / ngày lễ không bật bot: không hiện
        sc = scoring.total_score(a, note) if a and a.get("has_data") and not off else None
        days.append({"day": ds, "off": off or "", "rec": rec, "a": a, "note": note, "sc": sc})
        if rec and not off:
            for proc, sec in rec.get("apps") or []:
                apps[proc] = apps.get(proc, 0) + sec
        if sc:
            rows.append({"day": ds, "weekday": DAY_NAMES[dt.date.fromisoformat(ds).weekday()],
                         "total_score": sc["total"], "total_score_parts": sc["parts"]})
    review = db.execute("SELECT text FROM ai_cache WHERE key LIKE ? ORDER BY created DESC LIMIT 1",
                        (f"week:{facts['week']}:%",)).fetchone()
    return {"facts": facts, "days": days, "apps": sorted(apps.items(), key=lambda x: -x[1])[:8],
            "ot_history": ot_history(db, cfg, day),
            "explain": scoring.explain_week(rows), "review": review[0] if review else ""}


def write_week_report(db, cfg, day):
    """Tạo file HTML báo cáo tuần (thứ Hai tới day). Trả (đường dẫn, week_facts)."""
    from .report_html import render_week
    wk = week_report_data(db, cfg, day)
    path = os.path.join(cfg["report_dir"], f"focus-week-{wk['facts']['week']}.html")
    _write(path, render_week(cfg, wk))
    return path, wk["facts"]


def note_lines(note):
    """Phần bạn tự ghi trong ngày: năng lượng, kế hoạch đầu ngày, output, issue."""
    lines = []
    if note.get("energy") not in (None, ""):
        if note.get("energy_source") == "auto":
            lines.append(f"Năng lượng bot tự tính: {note['energy']}/5 (bạn chưa chấm; sửa: /energy 1–5)")
        else:
            lines.append(f"Năng lượng tự chấm: {note['energy']}/5")
    for key, label in (("plan", "Kế hoạch đầu ngày"), ("output", "Output"), ("issues", "Issue")):
        if note.get(key):
            lines.append(f"\n{label}:\n{persona.keep(note[key])}")
    return lines


def breakdown_parts(a, now=None):
    """(phép cộng, chú thích) cho dòng "Cộng giờ làm" của báo cáo ngày; None khi không có giờ làm chính thức."""
    b = time_breakdown(a, now)
    if not b:
        return None
    terms = [f"trong VDI {fmt_dur(b['vdi'] * 60)}", f"ngoài VDI {fmt_dur(b['other'] * 60)}",
             f"inactive {fmt_dur(b['idle'] * 60)}", f"rời máy {fmt_dur(b['away'] * 60)}"]
    if b["unrecorded"]:
        terms.append(f"không ghi {fmt_dur(b['unrecorded'] * 60)}")
    h = a["hours"]
    span = ("giờ làm chính thức, đã trừ trưa và phần nghỉ phép" if a.get("leave")
            else f"giờ làm {h['work_start']}–{h['work_end']} trừ trưa {h['lunch_start']}–{h['lunch_end']}")
    if b["until"]:
        span += f", tính tới {b['until']}"
    notes = [span]
    if b["minimized"]:
        notes.append(f"thu nhỏ VDI {fmt_dur(b['minimized'] * 60)} đã nằm trong ngoài VDI")
    if b["unrecorded"]:
        notes.append("không ghi = tạm dừng /pause, tắt tracker, hoặc trước lần đầu / sau lần cuối dùng máy trong giờ làm")
    text = " + ".join(terms) + f" = {fmt_dur(b['total'] * 60)}"
    ot = int(round((a.get("ot") or 0) / 60))  # OT của CHÍNH ngày này (qua 00:00 là ngày mới), không lấy ngày khác
    if ot:
        text += f" + OT {fmt_dur(ot * 60)} (ngoài giờ làm) = {fmt_dur((b['total'] + ot) * 60)}"
        notes.append("OT chỉ tính phần làm trong VDI ngoài giờ làm của đúng ngày này")
    return text, "; ".join(notes)


RULE = "------------------------------"


def _section(title, rows):
    """Một mục của tin Telegram: tiêu đề, gạch ngang, các dòng (đã thụt lề), dòng trống phía sau."""
    return [title, RULE] + rows + [""]


def _late_rows(rows):
    """OT ngày trước làm sau giờ báo cáo (chỉ nhắc lại, đã cộng vào đúng ngày đó), dạng bullet không emoji."""
    out = []
    for r in rows:
        d = dt.date.fromisoformat(r["day"])
        name = f"{['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'][d.weekday()]} {d:%d/%m}"
        ranges = ", ".join(f"{fmt_t(s)}–{fmt_t(e)}" for s, e in r["ranges"])
        what = f"Làm bù {name} ({r['off']})" if r["off"] else f"OT {name} sau giờ báo cáo"
        out.append(f"  • {what}: {fmt_dur(r['late'])}" + (f" ({ranges})" if ranges else ""))
        out.append(f"      {name} thực làm trong VDI tổng {fmt_dur(r['total'])}")
    return out


def summary_text(a, note, streak_days=None, late=None, now=None):
    """Tổng kết dạng chữ cho Telegram (/today, tổng kết cuối ngày): chia mục, gạch ngang, bullet, thụt lề, ít emoji.
    late: late_ot() (OT ngày trước làm sau giờ báo cáo, chỉ nhắc lại, không cộng vào ngày này)."""
    if not a["has_data"]:
        return "\n".join([f"{a['day']}: chưa có dữ liệu." + (f"\n{leave_line(a)}" if a.get("leave") else "")]
                         + note_lines(note))
    d = dt.date.fromisoformat(a["day"])
    head = f"TỔNG KẾT {DAY_NAMES[d.weekday()].upper()} {d:%d/%m/%Y}"
    if a.get("off"):  # ngày nghỉ bật tracker làm bù: chỉ có giờ làm trong VDI, không chấm sao nhãng / điểm
        lines = _section(head, [f"  Ngày nghỉ ({a['off']}), bạn bật bot làm bù {fmt_t(a['first'])}–{fmt_t(a['last'])}"])
        rows = [f"  • Làm bù trong VDI: {fmt_dur(a['ot'])}", f"  • Tập trung sâu: {fmt_dur(a['deep'])}"]
        if a["blocks"]:
            rows.append("  • Khối tập trung: " + ", ".join(f"{fmt_t(b['start'])}–{fmt_t(b['end'])}" for b in a["blocks"]))
        rows.append("  Ngày nghỉ bot chỉ cộng giờ làm trong VDI, không tính sao nhãng, không chấm điểm.")
        return "\n".join(lines + _section("LÀM BÙ", rows) + note_lines(note)).rstrip()
    sc = scoring.total_score(a, note)
    mins = lambda sec: int(round((sec or 0) / 60))
    lines = [head, f"Dữ liệu từ {fmt_t(a['first'])} đến {fmt_t(a['last'])}", RULE, ""]
    if a.get("leave"):
        lines += [leave_line(a), ""]

    rows = [f"  • Điểm tổng: {sc['total']}/100 ({sc['ten']:.1f}/10)",
            f"  • Quà robot: {sc['tier']['grade']} {sc['tier']['name']}",
            f"  • Tập trung sâu: {fmt_dur(a['deep'])} / mục tiêu {a['goal_h']:g}h",
            f"  • Điểm tập trung: {focus_score(a)}/100",
            f"  • Bị cắt ngang: {sc['per_hour']:g} lần/giờ làm"]
    if streak_days is not None:
        rows.append(f"  • Chuỗi ngày đạt mục tiêu: {streak_days} ngày")
    lines += _section("ĐIỂM", rows)

    vdi_m, ot_m = mins(a.get("vdi")), mins(a.get("ot"))
    rows = [f"  • Trong giờ làm: {fmt_dur(vdi_m * 60)}",
            f"  • Làm ngoài giờ (OT): {fmt_dur(ot_m * 60)}" if ot_m else "  • Làm ngoài giờ (OT): chưa có"]
    if ot_m:
        rows.append("      OT tính cho đúng ngày làm (qua 00:00 là ngày mới)")
    lines += _section(f"THỰC LÀM TRONG VDI: {fmt_dur((vdi_m + ot_m) * 60)}", rows)

    b = time_breakdown(a, now)
    h = a.get("hours") or {}
    title = "GIỜ LÀM"
    if h and not a.get("leave"):
        title += f" {h['work_start']}–{h['work_end']} (trừ trưa {h['lunch_start']}–{h['lunch_end']})"
    elif a.get("leave"):
        title += " (đã trừ trưa và phần nghỉ phép)"
    if b and b["until"]:
        title += f", tính tới {b['until']}"
    val = (lambda k: fmt_dur(b[k] * 60)) if b else (lambda k: fmt_dur(a.get(k, 0)))
    rows = [f"  • Trong VDI: {val('vdi')}",
            f"  • Ngoài VDI: {val('other')}",
            f"      {a['exits']} lần rời; thu nhỏ VDI {fmt_dur(a['minimized'])} ({a.get('minimize_count', 0)} lần)"
            + (", đã nằm trong ngoài VDI" if a.get("minimized") else ""),
            f"  • Inactive phím/chuột: {val('idle')}",
            f"      {a.get('short_idle_count', 0)} lần, TB {avg_dur(a['idle'], a.get('short_idle_count', 0))};"
            f" ≥ 10 phút: {a.get('inactive_10m_count', 0)} lần",
            f"  • Rời máy: {val('away')}",
            f"      {a['away_count']} lần, TB {avg_dur(a['away'], a['away_count'])}"]
    if b:
        if b["unrecorded"]:
            rows += [f"  • Không ghi: {fmt_dur(b['unrecorded'] * 60)}",
                     "      tạm dừng /pause, tắt tracker, hoặc trước lần đầu / sau lần cuối dùng máy trong giờ làm"]
        rows += ["  ------------", f"  = Cộng giờ làm: {fmt_dur(b['total'] * 60)}"]
        if ot_m:
            rows += [f"  + OT (ngoài giờ làm): {fmt_dur(ot_m * 60)}", f"  = Tổng: {fmt_dur((b['total'] + ot_m) * 60)}"]
    lines += _section(title, rows)

    if late:
        lines += _section("OT NGÀY TRƯỚC (đã cộng vào ngày đó, không cộng hôm nay)", _late_rows(late))

    rows = []
    if a.get("vdi_closed"):
        rows.append("  • VDI đã đóng (rời VDI quá lâu): "
                    + ", ".join(f"{fmt_t(x)}–{fmt_t(y)}" for x, y in a["vdi_closed"]))
    if a["blocks"]:
        rows.append("  • Khối tập trung: " + ", ".join(f"{fmt_t(b['start'])}–{fmt_t(b['end'])}" for b in a["blocks"]))
    if note.get("as400_start"):
        rows.append(f"  • AS400: {note['as400_start']}–{note.get('as400_end') or '?'}")
    rows += [f"  • {x}" for x in note_lines(note) if not x.startswith("\n")]
    if rows:
        lines += _section("KHÁC", rows)
    for x in note_lines(note):  # kế hoạch, output, issue: nguyên văn người dùng ghi, mỗi phần cách 1 dòng
        if x.startswith("\n"):
            lines += [x[1:], ""]
    return "\n".join(lines).rstrip()


def week_text(facts):
    if not facts.get("work_days"):
        return f"Tuần {facts['week']}: chưa có dữ liệu."
    lines = [f"Tuần {facts['week']} ({facts['from'][5:]} → {facts['to'][5:]})",
             f"Tập trung sâu: {facts['deep_hours_total']}h, trung bình {facts['deep_hours_avg']}h/ngày",
             f"Đạt mục tiêu: {facts['days_reached_goal']}/{facts['work_days']} ngày · điểm TB {facts['avg_score']}"
             f" · điểm tổng TB {facts.get('avg_total_score', 0)}"
             + (f" · làm ngoài giờ {facts['overtime_hours']:g}h" if facts.get("overtime_hours") else ""),
             f"Chuỗi hiện tại: {facts['streak_days']} ngày",
             *([f"Làm bù ngày nghỉ: {'; '.join(facts['off_day_overtime'])}"] if facts.get("off_day_overtime") else []),
             (f"Ngày tốt / kém nhất: {facts['best_day']}" if facts.get("days_tied") else
              f"Ngày tốt nhất: {facts['best_day']} · kém nhất: {facts['worst_day']}"),
             f"Giờ vàng: {', '.join(facts['golden_hours'])}",
             "", "Từng ngày:"] + [f"  {x}" for x in facts["per_day"]]
    return "\n".join(lines)
