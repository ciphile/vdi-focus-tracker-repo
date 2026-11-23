"""Báo giờ tập trung sâu tới lúc này + AI nhận xét ngắn (mốc focus_reports, mặc định 10:17, 12:45, 15:00; /baosau).

Chỉ ĐỌC số liệu app đã tính (analysis.analyze), không đổi cách tính tập trung hay điểm.

    dòng số liệu (code ghép, luôn đúng)  +  nhận xét 2–3 câu (AI viết theo giọng /style)
                                            AI lỗi / tắt -> câu có sẵn luân phiên theo giọng (pace_behind / pace_praise)

"Nhịp cần lúc này" = mục tiêu tập trung sâu x (phút làm đã qua / tổng phút làm trong ngày), trừ nghỉ trưa và phần
nghỉ phép nửa ngày (cùng cách chia với cảnh báo tiến độ, pace.work_minutes).
"""
import json

from . import ai_client, ai_context
from . import persona as _persona
from .analysis import analyze, fmt_dur
from .logs import get_logger
from .pace import work_minutes

log = get_logger()

BEHIND_RATIO = 0.6   # tập trung sâu < 60% nhịp cần lúc này thì coi là chậm (câu dự phòng giọng nhắc)
MAX_WORDS = 60

TASK = """VIỆC CẦN LÀM: viết nhận xét NGẮN về tiến độ tập trung sâu hôm nay tính tới {at}, gửi qua Telegram ngay dưới dòng số liệu (người dùng đã thấy số liệu, không chép lại hết).
- 2 đến 3 câu, tổng không quá {max_words} từ, văn bản thường, không tiêu đề, không gạch đầu dòng, không câu trích dẫn.
- Câu 1: nhận xét tiến độ so với nhịp cần lúc này (deep_hours so với expected_deep_hours), nói thẳng đang kịp hay chậm.
- Câu 2–3: một gợi ý cụ thể cho phần còn lại của ngày (ví dụ còn remaining_work_hours giờ làm thì cần khối tập trung bao lâu); có open_tasks thì có thể nhắc làm việc đầu tiên trong danh sách.
- Đúng giọng và cách xưng hô trong BỐI CẢNH. Không bịa số ngoài SỐ LIỆU."""


def facts(db, cfg, day, at):
    """Số liệu tiến độ lúc at (HH:MM). Dùng cho dòng số liệu và cho AI."""
    a = analyze(db, cfg, day)
    leave = a.get("leave")
    goal = a["goal_h"]
    total = work_minutes(cfg, cfg["work_end"], leave) or 1
    elapsed = work_minutes(cfg, min(at, cfg["work_end"]), leave)
    deep = a["deep"] if a.get("has_data") else 0
    out = {"at": at, "deep_hours": round(deep / 3600, 2), "goal_hours": goal,
           "expected_deep_hours": round(goal * elapsed / total, 2),
           "vdi_hours": round((a.get("vdi") or 0) / 3600, 2) if a.get("has_data") else 0,
           "deep_blocks": len(a.get("blocks") or []), "longest_block_minutes": round((a.get("longest") or 0) / 60),
           "remaining_work_hours": round(max(total - elapsed, 0) / 60, 1),
           "_deep": deep, "_vdi": a.get("vdi") or 0, "_longest": a.get("longest") or 0}
    if leave:
        out["leave"] = leave
    try:
        from . import tasks
        if tasks.since(db):
            rows = tasks.open_tasks(db, day)
            out["open_tasks"] = [t["text"] for t in rows[:5]]
            out["open_task_count"] = len(rows)
            out["done_today_count"] = len(tasks.done_on(db, day))
    except Exception as e:  # danh sách việc lỗi không được làm mất tin báo tập trung
        log.warning("Không đọc được danh sách việc cho báo tiến độ: %s", e)
    return out


def behind(f):
    return f["expected_deep_hours"] > 0 and f["deep_hours"] < BEHIND_RATIO * f["expected_deep_hours"]


def header(f):
    pct = round(100 * f["deep_hours"] / f["goal_hours"]) if f["goal_hours"] else 0
    lines = [f"⏱ {f['at']} · Tập trung chuyên sâu hôm nay: {fmt_dur(f['_deep'])} / mục tiêu {f['goal_hours']:g}h "
             f"({pct}%)",
             f"Nhịp cần lúc này: khoảng {fmt_dur(f['expected_deep_hours'] * 3600)} · làm trong VDI "
             f"{fmt_dur(f['_vdi'])} · {f['deep_blocks']} khối ≥ 20 phút"
             + (f", dài nhất {fmt_dur(f['_longest'])}" if f["deep_blocks"] else "")]
    if "open_task_count" in f:
        lines.append(f"Việc: xong {f['done_today_count']} hôm nay, còn {f['open_task_count']} việc")
    return "\n".join(lines)


def comment(cfg, f, p):
    """Nhận xét: AI viết; AI tắt / lỗi -> câu có sẵn luân phiên theo giọng. Trả (chữ, do_AI)."""
    if ai_client.provider(cfg):
        data = {k: v for k, v in f.items() if not k.startswith("_")}
        prompt = (TASK.format(at=f["at"], max_words=MAX_WORDS) + "\n\n" + ai_context.glossary(data)
                  + "\n\nSỐ LIỆU (JSON):\n" + json.dumps(data, ensure_ascii=False, indent=1))
        try:
            text, _ = ai_client.generate(cfg, prompt, ai_context.system_prompt(cfg), purpose="progress")
            text = " ".join(text.split())
            if text:
                return text, True
        except ai_client.AIError as e:
            log.info("AI nhận xét tiến độ lỗi, dùng câu có sẵn: %s", e)
    return _persona.lead("pace_behind" if behind(f) else "pace_praise", p), False


def report(cfg, db, day, at, p):
    """Tin báo tập trung sâu hoàn chỉnh (chữ thường, chưa đổi xưng hô)."""
    f = facts(db, cfg, day, at)
    text, by_ai = comment(cfg, f, p)
    body = header(f)
    if text:
        body += "\n\n" + ("🤖 " if by_ai else "") + text
    return body
