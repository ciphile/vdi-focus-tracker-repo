"""Vắng mặt gần nhất và các lần vắng trong ngày (/vang, câu hỏi "mình vừa inactive bao lâu?").

Chỉ ĐỌC số liệu đã có: các quãng không chạm phím/chuột mà analysis đã gộp (analyze(...)["inactive_spans"]) cộng mẫu
mới nhất trong RAM (state["last"], mẫu chưa kịp ghi xuống DB). Không đổi cách đo, không đổi điểm.

- Quãng vắng: không chạm phím/chuột >= idle_threshold_seconds (mặc định 60 giây), hoặc khoá máy / máy ngủ /
  tracker tắt. Hai quãng chỉ cách nhau một lần chạm lẻ là một quãng (cùng quy tắc với báo cáo).
- "Lần vắng gần nhất" = quãng đã kết thúc gần đây nhất (>= 1 phút). Đang vắng lúc hỏi thì báo riêng "đang vắng từ".
- Danh sách trong ngày chỉ lấy quãng >= LIST_MIN_SECONDS (5 phút), kể cả giờ trưa và ngoài giờ làm.
"""
import datetime as dt
import time

from .analysis import fmt_dur, fmt_t

LIST_MIN_SECONDS = 5 * 60
SHOW_MAX = 10      # /vang liệt kê tối đa chừng này lần gần nhất
AI_MAX = 5         # gửi AI tối đa chừng này lần (bối cảnh AI có độ dài cố định, không phình theo ngày)


def _kind(span, cfg):
    if span["hard"]:
        return "khoá máy / máy ngủ / tắt app"
    if span["secs"] >= cfg["away_threshold_seconds"]:
        return "rời máy, không chạm phím/chuột"
    return "ngồi yên, không chạm phím/chuột"


def _live_since(state, cfg, now):
    """Đang vắng lúc này: trả thời điểm bắt đầu vắng (theo mẫu mới nhất trong RAM), không thì None."""
    state = state or {}
    paused = state.get("paused")
    if paused is not None and paused.is_set():
        return None
    s = state.get("last")
    if not s:
        return None
    idle = float(s.get("idle") or 0)
    if s.get("locked") or idle >= cfg["idle_threshold_seconds"]:
        return now - idle
    return None


def summarize(a, cfg, state=None, now=None):
    """{"last": quãng xong gần nhất | None, "ongoing": quãng đang vắng | None, "listed": [quãng >= 5 phút],
    "count", "total"}. Mỗi quãng: {"start", "end", "secs", "hard", "kind"}."""
    now = time.time() if now is None else now
    step = cfg["sample_seconds"]
    first = a.get("first") if a.get("has_data") else None
    spans = []
    for s, e, hard in a.get("inactive_spans") or []:
        if first is not None and e <= first:
            continue  # trước lần đầu dùng máy trong ngày (bật máy rồi chưa tới bàn): không phải "vắng"
        spans.append({"start": s, "end": e, "secs": e - s, "hard": hard})
    since = _live_since(state, cfg, now)
    ongoing = None
    if since is not None:
        start = since
        while spans and spans[-1]["end"] >= since - 2 * step:  # quãng trong DB là phần đầu của lần đang vắng
            start = min(start, spans.pop()["start"])
        ongoing = {"start": start, "end": now, "secs": now - start, "hard": False}
    for sp in spans + ([ongoing] if ongoing else []):
        sp["kind"] = _kind(sp, cfg)
    done = [sp for sp in spans if sp["secs"] >= 60]
    listed = [sp for sp in done if sp["secs"] >= LIST_MIN_SECONDS]
    return {"last": done[-1] if done else None, "ongoing": ongoing, "listed": listed,
            "count": len(listed), "total": sum(sp["secs"] for sp in listed)}


def _span_text(sp):
    return f"{fmt_t(sp['start'])}–{fmt_t(sp['end'])}, {fmt_dur(sp['secs'])} ({sp['kind']})"


def view_text(a, cfg, state=None, now=None, day=None):
    """Tin /vang."""
    info = summarize(a, cfg, state, now)
    today = day is None or day == dt.date.today().isoformat()
    lines = []
    if info["ongoing"] and today:
        lines.append(f"⏳ Lúc này máy đang không ai chạm từ {fmt_t(info['ongoing']['start'])} "
                     f"({fmt_dur(info['ongoing']['secs'])}).")
    if info["last"]:
        lines.append(f"🚶 Lần vắng gần nhất: {_span_text(info['last'])}.")
    else:
        lines.append("🚶 Chưa có lần vắng nào từ 1 phút trở lên" + (" hôm nay." if today else " ngày này."))
    if info["listed"]:
        lines += ["", f"Các lần vắng từ 5 phút: {info['count']} lần, tổng {fmt_dur(info['total'])}"]
        shown = info["listed"][-SHOW_MAX:]
        if len(shown) < info["count"]:
            lines.append(f"  (chỉ hiện {len(shown)} lần gần nhất)")
        lines += [f"  • {fmt_t(sp['start'])}–{fmt_t(sp['end'])} · {fmt_dur(sp['secs'])} · {sp['kind']}" for sp in shown]
    lines += ["", "Đo bằng phím/chuột trên máy này: chỉ đọc màn hình hay gõ trên điện thoại cũng tính là vắng. "
              "Kể cả giờ trưa và ngoài giờ làm. Mẫu mới nhất ghi xuống DB chậm tối đa 1 phút."]
    return "\n".join(lines)


def ai_facts(a, cfg, state=None, now=None):
    """Vài dòng độ dài cố định gửi kèm câu hỏi AI để trả lời "vừa vắng / inactive bao lâu"."""
    info = summarize(a, cfg, state, now)
    out = {"lan_vang_gan_nhat": _span_text(info["last"]) if info["last"] else "chưa có lần vắng nào từ 1 phút",
           "may_luc_nay": (f"đang không ai chạm phím/chuột từ {fmt_t(info['ongoing']['start'])} "
                           f"({fmt_dur(info['ongoing']['secs'])})" if info["ongoing"] else "đang có người dùng"),
           "cac_lan_vang_tu_5_phut_hom_nay": (f"{info['count']} lần, tổng {fmt_dur(info['total'])}"
                                              + ("; gần nhất: " + "; ".join(_span_text(sp) for sp in
                                                                            info["listed"][-AI_MAX:])
                                                 if info["listed"] else ""))}
    out["cach_do"] = ("vắng = không chạm phím/chuột trên laptop từ 1 phút, hoặc khoá máy / máy ngủ; tính cả giờ trưa; "
                      "người dùng hỏi 'vừa vắng / inactive / đi đâu bao lâu' thì trả lời bằng lan_vang_gan_nhat "
                      "(nếu may_luc_nay đang vắng thì nói thêm)")
    return out
