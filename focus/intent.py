"""Hiểu tin nhắn tự nhiên -> (action, args).

1. Gọi AI với danh sách action (actions.catalog), AI trả JSON {"action": ..., "args": {...}}.
2. AI không dùng được (mất mạng, hết quota, chưa có key) hoặc trả về lạ -> rule dự phòng theo từ khoá.
3. Rule cũng không hiểu -> trả None để bot báo lại.

Kết quả luôn được kiểm tra lại bằng actions.validate trước khi dùng.
"""
import datetime as dt
import json
import re
import unicodedata

from . import ai_client
from . import ai_context
from .actions import (ACTIONS, BY_NAME, ENC_WORDS, LEAVE_WORDS, ONOFF, TONE_WORDS, _take_word, _word_lookup, catalog,
                      health_lookup, nudge_lookup, parse_bot_hours, parse_command_args, parse_day, validate)
from .logs import get_logger

log = get_logger()

SYSTEM = """Bạn là bộ phân tích lệnh cho bot Telegram theo dõi tập trung của một người làm việc trong máy ảo VDI.
Nhiệm vụ: đọc tin nhắn tiếng Việt và chọn ĐÚNG MỘT action trong danh sách, kèm tham số.
Chỉ trả về JSON một dòng, không giải thích, không markdown."""

PROMPT = """Hôm nay là {today} ({weekday}). Danh sách action:
{catalog}

Tin nhắn của người dùng: \"\"\"{text}\"\"\"

Quy tắc:
- Chọn action khớp nhất. Câu HỎI cần được trả lời (kiến thức, lời khuyên, giá vàng, tỷ giá, cách làm...) -> "hoi_ai"
  với text là nguyên câu hỏi. Tin nhắn tâm sự, than mệt/chán hoặc không thuộc action nào -> "tro_chuyen".
- Kể lý do vừa bị gián đoạn, bận việc khác, bị kéo khỏi việc ("nãy giờ bận trông em bé khóc", "bị sếp gọi đi họp gấp",
  "hàng xóm khoan tường ồn quá") -> "ghi_phan_tam" với text là nguyên câu, KHÔNG phải "tro_chuyen".
- Tham số text: giữ nguyên ý và từ ngữ của người dùng, bỏ phần dẫn như "ghi giúp", "việc ngày mai là".
- Ngày dạng YYYY-MM-DD (tự tính "mai", "thứ 6 này"...). Giờ dạng HH:MM 24h.
- Không đoán bừa tham số bắt buộc; thiếu thì vẫn chọn action và để trống.
- Nghỉ phép / nghỉ nửa ngày ("chiều nay nghỉ phép", "mai nghỉ buổi sáng") -> "nghi_phep" với part = am (sáng) |
  pm (chiều) | full (cả ngày); "sáng mai"/"chiều mai" = buổi đó của NGÀY MAI. Huỷ nghỉ -> "bao_di_lam".
- Giờ bot (tracker) tự bật / tự tắt ("bật bot lúc 8 rưỡi", "cho bot chạy từ 8h đến 18h") -> "gio_bot" với start / stop
  HH:MM 24h ("6 giờ chiều" = 18:00); hỏi bot chạy mấy giờ -> "gio_bot" không tham số.
Trả về: {{"action": "<tên>", "args": {{...}}}}"""

WEEKDAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]
LEAD_RE = re.compile(r"^[\s:,\-–>]*(?:(?:la|là)(?=[\s:,]|$))?[\s:,\-–>]*", re.I)


def fold(text):
    """Bỏ dấu tiếng Việt, chữ thường, GIỮ NGUYÊN độ dài (để cắt chuỗi gốc theo vị trí)."""
    out = []
    for ch in text:
        if ch in "đĐ":
            out.append("d")
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        out.append(base.lower() if len(base.lower()) == 1 else ch.lower()[:1] or " ")
    return "".join(out)


QUESTION_WORDS = ("bao nhieu", "lam sao", "the nao", "nhu the nao", "la gi", "tai sao", "vi sao", "co nen",
                  "nen lam gi", "o dau", "khi nao", "cach nao", "lam gi de", "the nao de", "gia vang", "ty gia")


# Nhận ra buổi nghỉ trong câu tự nhiên: bỏ "am" (trùng "âm", "ấm" khi bỏ dấu).
NL_LEAVE_WORDS = [(w, v) for w, v in LEAVE_WORDS if w != "am"]
CANCEL_RE = re.compile(r"(?<![a-z])(huy|khong nghi nua|thoi khong nghi|khong nghi phep nua)(?![a-z])")
FILLER = ("", "nhe", "nha", "a", "nhe ban", "ban nhe", "nghe", "di", "luon")

VIEW_QUESTIONS = {"canh_bao_tien_do", "doi_muc_nhac", "nhac_nghi_ngoi", "nhac_uong_nuoc", "gio_bot",
                  "tu_tinh_nang_luong"}
FILLER = r"(?:(?:minh|em|toi|anh|chi|se|da|cu)\s+)?"  # "mai MÌNH làm", "nhắc MÌNH nghỉ ngơi"
_KW_CACHE = {}


def _kw_regex(kw):
    """Từ khoá nhiều chữ cho phép chen một từ đệm (mình/em/sẽ...) giữa các chữ. Vị trí khớp vẫn trên chuỗi gốc."""
    rx = _KW_CACHE.get(kw)
    if rx is None:
        body = (r"\s+" + FILLER).join(re.escape(w) for w in kw.split())
        rx = _KW_CACHE[kw] = re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")
    return rx


VIEW_VERB_RE = re.compile(r"(?<![a-z])xem(?! xet)(?![a-z])")  # "xem kế hoạch"; "xem xét" là việc, không phải xem
WEAK_KEYWORDS = {"hom nay", "hom qua"}  # có trong rất nhiều câu ("nghỉ ốm hôm nay"): chỉ thắng khi không có từ khoá nào khác


def _looks_like_question(folded):
    folded = folded.strip()
    return folded.endswith("?") or any(re.search(r"(?<![a-z])" + w + r"(?![a-z])", folded) for w in QUESTION_WORDS)


def looks_like_question(text):
    return _looks_like_question(fold(text))


def by_rules(text, today=None):
    """Bóc tách dự phòng bằng từ khoá. Trả (action, args) hoặc None."""
    folded = fold(text)
    best = None  # (độ dài từ khoá, vị trí kết thúc, action)
    best_write = None  # từ khoá mạnh nhất của action GHI (ưu tiên hơn action chỉ xem)
    for a in ACTIONS:
        for kw in a.keywords:
            m = _kw_regex(kw).search(folded)
            score = 0 if kw in WEAK_KEYWORDS else len(kw)
            if m and (best is None or score > best[0]):
                best = (score, m.end(), a, kw)
            if m and a.writes and score and (best_write is None or score > best_write[0]):
                best_write = (score, m.end(), a, kw)
    # "đã xong báo cáo tuần cho sếp": khớp cả "báo cáo tuần" (xem) lẫn "đã xong" (ghi) -> là ghi output.
    # Câu hỏi thì vẫn là xem ("báo cáo tuần xong chưa?"), có chữ "xem" cũng vậy ("xem kế hoạch hôm nay").
    if (best and best_write and not best[2].writes and not _looks_like_question(folded)
            and not VIEW_VERB_RE.search(folded)):
        best = best_write
    # Câu hỏi ("tại sao...", "...bao nhiêu?") không phải lệnh ghi: gửi AI trả lời. Riêng hỏi xem tiến độ / mức nhắc
    # ("tiến độ hôm nay thế nào?") là xem trạng thái.
    viewing = best and best[2].name in VIEW_QUESTIONS and not _word_lookup(ONOFF, text) and not nudge_lookup(text)
    if best and best[2].name == "gio_bot":  # "bot tắt lúc mấy giờ?" là xem; có giờ cụ thể là đổi
        viewing = not parse_bot_hours(text)
    if (not best or best[2].name == "tro_chuyen" or best[2].writes) and not viewing and _looks_like_question(folded):
        return BY_NAME["hoi_ai"], {"text": text.strip()}
    if not best:
        return None
    _, end, action, kw = best
    if kw == "mai lam":  # "mai làm tiếp X": giữ chữ "làm" trong nội dung
        end -= 3
    rest = text[end:]
    rest = LEAD_RE.sub("", rest, count=1).strip()
    for lead in ("can lam la", "can lam", "se lam la", "lam la"):  # "mai cần làm là X" -> X
        if fold(rest).startswith(lead + " "):
            rest = rest[len(lead) + 1:].strip()
            rest = LEAD_RE.sub("", rest, count=1).strip()
            break
    if action.name == "tro_chuyen":
        return action, {"text": text}
    if action.name == "gio_bot":  # từ bật/tắt/từ/đến nằm trước giờ: đọc cả câu, không cắt từ khoá
        return action, parse_bot_hours(text)
    if action.name == "hoi_ai":  # "hỏi AI: X" -> X; câu hỏi thường -> cả câu
        word = fold(rest).strip()
        if word in ("on", "off", "bat", "tat", "mo"):
            return action, {"text": word}
        if "che do" in folded:  # "bật/tắt chế độ hỏi AI"
            value = _word_lookup(ONOFF, text)
            return action, ({"text": value} if value in ("on", "off") else {})
        return action, {"text": rest if fold(text[:end]).strip().endswith(("hoi ai", "ask ai")) and rest
                        else text.strip()}
    if action.params and action.params[0][1] == "health":
        # "tắt nhắc đứng dậy", "nhắc nghỉ mỗi 45 phút", "nhắc uống nước" (= bật); không có gì khác là xem cài đặt.
        value = health_lookup(text)
        if value is None and folded.strip().startswith("nhac "):
            value = "on"
        return action, ({"every": value} if value is not None else {})
    if action.params and action.params[0][1] in ("onoff", "tone", "encmode", "nudgelevel"):
        # "tắt AI đánh giá", "đổi giọng sang hài hước", "nhắc nghiêm khắc hơn": từ bật/tắt/giọng/mức nằm đâu trong
        # câu cũng được; không có thì là hỏi xem trạng thái.
        name, kind = action.params[0][:2]
        value = (nudge_lookup(text) if kind == "nudgelevel"
                 else _word_lookup({"onoff": ONOFF, "tone": TONE_WORDS, "encmode": ENC_WORDS}[kind], text))
        return action, ({name: value} if value else {})
    if action.name in ("bao_nghi", "nghi_phep"):
        found = _leave_by_rules(text, folded, rest, kw, today)
        if found:
            return found
    if action.name == "ghi_phan_tam" or (action.name == "ghi_issue" and kw != action.keywords[0]):
        rest = text.strip()  # "VDI chậm quá chờ restart": cả câu là nội dung, không cắt từ khoá
    args = parse_command_args(action, rest, today)
    if not args and action.params and action.params[0][1] != "text":
        args = parse_command_args(action, text, today)  # giờ / số có thể nằm trước từ khoá
    if (not args and action.params and action.params[0][1] == "text"
            and fold(text).strip(" .!?") != action.keywords[0]):
        args = parse_command_args(action, text.strip(), today)  # "VDI chậm" -> cả câu là nội dung issue
    if action.name in ("bao_nghi", "bao_di_lam") and "day" not in args:  # "xin nghỉ phép mai": ngày nằm trước từ khoá
        day, _ = parse_day(text, today)
        if day:
            args["day"] = day
    if action.name == "bao_nghi" and args.get("reason") and (
            kw in fold(args["reason"]) or fold(args["reason"]).strip(" .!") in ("", "nhe", "nha", "a")):
        args.pop("reason")  # "mai mình xin nghỉ phép": cả câu không phải lý do
    return action, args


def _leave_by_rules(text, folded, rest, kw, today):
    """Câu báo nghỉ: có buổi (sáng/chiều/cả ngày/nửa ngày) -> nghi_phep; có "huỷ" -> bao_di_lam.
    Không có buổi -> None (để bao_nghi xử lý như cũ: "mai mình xin nghỉ phép")."""
    if CANCEL_RE.search(folded):
        day, _ = parse_day(text, today)
        return BY_NAME["bao_di_lam"], ({"day": day} if day else {})
    part, _ = _take_word(NL_LEAVE_WORDS, text)
    if not part:
        return None
    leave = BY_NAME["nghi_phep"]
    args = parse_command_args(leave, rest, today)  # phần sau từ khoá: buổi, ngày, lý do
    args["part"] = part
    if "day" not in args:  # "chiều mai nghỉ phép": ngày nằm trước từ khoá
        _, without_part = _take_word(NL_LEAVE_WORDS, text)
        day, _ = parse_day(without_part, today)
        if day:
            args["day"] = day
    reason = fold(args.get("reason") or "").strip(" .!,")
    if reason in FILLER or "nghi" in reason or kw in reason:
        args.pop("reason", None)  # "hôm nay mình nghỉ nửa ngày sáng nhé": không có lý do
    log.debug("Rule nghỉ phép: %s", args)
    return leave, args


def by_ai(cfg, text, today=None):
    today = today or dt.date.today()
    prompt = PROMPT.format(today=today.isoformat(), weekday=WEEKDAYS[today.weekday()],
                           catalog=json.dumps(catalog(), ensure_ascii=False), text=text[:1000])
    system = ai_context.system_prompt(cfg, SYSTEM)  # đủ ngữ cảnh (công việc, thuật ngữ) để hiểu đúng tin nhắn
    raw, _ = ai_client.generate(cfg, prompt, system, purpose="intent")
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("AI không trả JSON")
    data = json.loads(m.group(0))
    action = BY_NAME.get(str(data.get("action", "")))
    if not action:
        raise ValueError(f"AI trả action lạ: {data.get('action')}")
    args = data.get("args") or {}
    if not isinstance(args, dict):
        raise ValueError("args không phải object")
    if action.name == "tro_chuyen":
        args = {"text": text}
    return action, args


def understand(cfg, text, today=None):
    """Trả (action, args, nguồn, lỗi). nguồn: "ai" | "rule" | None. lỗi: câu báo khi tham số sai."""
    text = unicodedata.normalize("NFC", text or "")
    action = None
    source = None
    if ai_client.provider(cfg):
        try:
            action, args = by_ai(cfg, text, dt.date.fromisoformat(today) if today else None)
            source = "ai"
        except Exception as e:  # mất mạng, hết quota, JSON lạ... -> rule dự phòng
            log.info("AI không bóc tách được (%s), dùng rule dự phòng.", e)
        if action is not None and action.name == "tro_chuyen":
            # AI coi là tán gẫu nhưng từ khoá rõ ràng là một lệnh GHI ("nãy giờ bận trông em bé khóc" = phân tâm):
            # theo từ khoá, vẫn qua thẻ xác nhận nên ghi nhầm thì người dùng bấm Sửa.
            found = by_rules(text, today)
            if found and found[0].writes:
                log.info("AI chọn tro_chuyen nhưng từ khoá là %s: theo từ khoá.", found[0].name)
                action, args = found
                source = "rule"
    if action is None:
        found = by_rules(text, today)
        if not found:
            return None, {}, None, None
        action, args = found
        source = "rule"
    clean, error = validate(action, args)
    return action, (clean or {}), source, error


SKIP_CROSS_CHECK = ("hoi_ai", "tro_chuyen")


def cross_check(text, action, args, source, today=None):
    """AI đôi khi hiểu nhầm: đối chiếu với cách đọc bằng từ khoá. Khác hành động, hoặc cùng hành động mà khác
    ngày / giờ / buổi / mức đã bóc tách -> trả câu cảnh báo để in lên thẻ xác nhận. Giống hoặc không đối chiếu được -> None."""
    if source != "ai":
        return None
    try:
        found = by_rules(text, today)
    except Exception:  # pragma: no cover - đối chiếu chỉ là phụ, lỗi thì bỏ qua
        return None
    if not found or found[0].name in SKIP_CROSS_CHECK:
        return None
    rule_action, rule_args = found
    if rule_action.name != action.name:
        return (f"Theo từ khoá thì tin này lại giống «{rule_action.title}» (lệnh {rule_action.command}). "
                "Nếu ý bạn là việc đó, bấm ✏️ Sửa lại hoặc gõ thẳng lệnh.")
    clean, error = validate(rule_action, rule_args)
    if error or not clean:
        return None
    structured = {name for name, kind, _, _ in action.params if kind != "text"}
    structured |= {"start", "end"} if any(k == "times" for _, k, _, _ in action.params) else set()
    diff = [k for k in sorted(structured) if k in clean and str(clean[k]) != str(args.get(k))]
    if not diff:
        return None
    from .actions import _arg_label
    shown = ", ".join(f"{_arg_label(action, k)} = {clean[k]}" for k in diff)
    return (f"Đọc theo từ khoá thì ra {shown}, khác với chi tiết ở trên. "
            "Kiểm tra kỹ; sai thì bấm ✏️ Sửa lại.")

