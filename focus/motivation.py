"""Nội dung động viên và nhận xét: gọi AI nếu có, không thì dùng nội dung có sẵn.

- encouragement(): câu nói nổi tiếng / câu Kinh Thánh (Tin Lành) / lời nhắc vì gia đình, xoay vòng.
  Tắt Kinh Thánh (/kinhthanh off) thì không chỗ nào dùng Kinh Thánh: chỉ châm ngôn của người thành đạt, danh nhân xưa.
- break_message(): nhắc nghỉ kèm bài tập vận động và mắt (không cần AI).
- review_day(), review_week(): AI đọc báo cáo, viết đánh giá (chỉ AI viết, không có câu soạn sẵn). Có cache.
- read_as400_times(): AI đọc ảnh spooled file AS400, lấy giờ bắt đầu / kết thúc.
"""
import datetime as dt
import hashlib
import json
import random
import re
import time

from . import ai_client, ai_context, scoring
from .logs import get_logger

log = get_logger()

QUOTES = [
    ("Đường tuy ngắn, không đi không bao giờ đến; việc tuy nhỏ, không làm chẳng bao giờ nên.", "Tuân Tử"),
    ("Thất bại là mẹ thành công.", "Tục ngữ"),
    ("Hành trình vạn dặm bắt đầu từ một bước chân.", "Lão Tử"),
    ("Không có việc gì khó, chỉ sợ lòng không bền. Đào núi và lấp biển, quyết chí ắt làm nên.", "Hồ Chí Minh"),
    ("Có công mài sắt, có ngày nên kim.", "Tục ngữ"),
    ("Ngã bảy lần, đứng dậy tám lần.", "Ngạn ngữ Nhật Bản"),
    ("Chúng ta là những gì chúng ta làm lặp đi lặp lại. Xuất sắc không phải là một hành động, mà là một thói quen.",
     "Will Durant"),
    ("Kỷ luật là cầu nối giữa mục tiêu và thành tựu.", "Jim Rohn"),
    ("Việc khó nhất là quyết định hành động, phần còn lại chỉ là sự kiên trì.", "Amelia Earhart"),
    ("Tôi không thất bại. Tôi chỉ tìm ra 10.000 cách không hiệu quả.", "Thomas Edison"),
    ("Ví như đắp núi, chỉ còn thiếu một sọt đất mà dừng, ấy là tự ta dừng.", "Khổng Tử, Luận Ngữ 9.19"),
    ("Trời sắp giao trọng trách cho người nào, ắt trước hết làm khổ tâm chí, nhọc gân cốt người ấy.",
     "Mạnh Tử, Cáo Tử hạ"),
    ("Không phải vì việc khó mà ta không dám làm; chính vì ta không dám làm nên việc mới khó.",
     "Seneca, Thư gửi Lucilius 104"),
    ("Cái cản đường hành động lại thúc đẩy hành động. Chướng ngại trên đường trở thành con đường.",
     "Marcus Aurelius, Suy Tưởng 5.20"),
    ("Làm tốt hơn nói hay.", "Benjamin Franklin"),
    ("Cách duy nhất để làm được việc tuyệt vời là yêu điều bạn làm.", "Steve Jobs, Stanford 2005"),
]

# Bản dịch Kinh Thánh Truyền Thống (1926).
BIBLE = [
    ("Tôi làm được mọi sự nhờ Đấng ban thêm sức cho tôi.", "Phi-líp 4:13"),
    ("Chớ mệt nhọc về sự làm lành, vì nếu chúng ta không trễ nải, thì đến kỳ chúng ta sẽ gặt.", "Ga-la-ti 6:9"),
    ("Nhưng ai trông đợi Đức Giê-hô-va thì chắc được sức mới, cất cánh bay cao như chim ưng; "
     "chạy mà không mệt nhọc, đi mà không mòn mỏi.", "Ê-sai 40:31"),
    ("Hãy vững lòng bền chí, chớ run sợ, chớ kinh khủng; vì Giê-hô-va Đức Chúa Trời ngươi "
     "vẫn ở cùng ngươi trong mọi nơi ngươi đi.", "Giô-suê 1:9"),
    ("Hễ làm việc gì, hãy hết lòng mà làm, như làm cho Chúa, chớ không phải làm cho người ta.", "Cô-lô-se 3:23"),
    ("Hỡi những kẻ mệt mỏi và gánh nặng, hãy đến cùng ta, ta sẽ cho các ngươi được yên nghỉ.", "Ma-thi-ơ 11:28"),
    ("Hãy phó các việc mình cho Đức Giê-hô-va, thì những mưu ý mình sẽ được thành công.", "Châm-ngôn 16:3"),
    ("Đừng sợ, vì ta ở với ngươi; chớ kinh khiếp, vì ta là Đức Chúa Trời ngươi! Ta sẽ bổ sức cho ngươi.",
     "Ê-sai 41:10"),
    ("Ân điển ta đủ cho ngươi rồi, vì sức mạnh của ta nên trọn vẹn trong sự yếu đuối.", "II Cô-rinh-tô 12:9"),
    ("Kìa, con cái là cơ nghiệp bởi Đức Giê-hô-va mà ra; bông trái của tử cung là phần thưởng.", "Thi-thiên 127:3"),
]

FAMILY = [
    "Mỗi giờ tập trung hôm nay là thêm một viên gạch cho tổ ấm. Gia đình đang chờ bạn về với một ngày làm việc trọn vẹn.",
    "Con cái học từ cách bố mẹ làm việc, không phải từ lời dạy. Làm cho xong việc trước mắt đã nhé.",
    "Bạn không cần phải giỏi nhất, chỉ cần không bỏ cuộc. Người thân của bạn tự hào vì điều đó.",
    "Mệt thì nghỉ một chút, nhưng đừng dừng hẳn. Cuộc sống bạn đang xây là cho những người bạn thương.",
]

EXERCISES = [
    "Mắt: quy tắc 20-20-20. Nhìn một vật xa ít nhất 6 mét (ngoài cửa sổ càng tốt) trong 20 giây, chớp mắt chậm 10 lần.",
    "Mắt: xoa hai lòng bàn tay cho ấm rồi úp nhẹ lên mắt nhắm 30 giây. Sau đó nhìn xa, đảo mắt theo hình số 8 năm lần.",
    "Vận động: đứng dậy đi tới lui 2–3 phút, rót một ly nước. Xoay vai ra sau 10 lần.",
    "Cổ vai: nghiêng đầu sang trái giữ 15 giây, sang phải 15 giây. Rụt vai lên tai rồi thả xuống 10 lần.",
    "Lưng: đứng thẳng, đan tay vươn lên trần giữ 15 giây, rồi cúi người chạm gối. Lặp lại 5 lần.",
    "Cổ tay: duỗi tay ra trước, dùng tay kia kéo nhẹ các ngón về phía mình 15 giây mỗi bên. Xoay cổ tay 10 vòng.",
    "Chân: đứng lên ngồi xuống ghế 10 lần, rồi nhón gót 15 lần. Máu lưu thông, đầu tỉnh hơn.",
    "Mắt + hít thở: nhìn xa ra cửa sổ, hít vào 4 giây, giữ 4 giây, thở ra 6 giây. Làm 5 vòng.",
]

STYLE_PROMPTS = {
    "motivation": "Chọn MỘT châm ngôn / câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa "
                  "(ví dụ Khổng Tử, Mạnh Tử, Lão Tử, Seneca, Marcus Aurelius, Edison) về kiên trì, không bỏ cuộc, "
                  "tập trung. Ghi đúng tác giả; câu nước ngoài thì dịch sang tiếng Việt tự nhiên. Không chắc tác giả "
                  "thì chọn câu khác. KHÔNG dùng Kinh Thánh.",
    "bible": "Chọn MỘT câu Kinh Thánh của Tin Lành (Cơ Đốc giáo Tin Lành) về đừng bỏ cuộc, đừng nản lòng, sức mới, "
             "phó thác, bình an, hoặc làm việc hết lòng. Chỉ dùng 66 sách Kinh Thánh Tin Lành, KHÔNG dùng các sách "
             "Thứ Kinh/Đệ Nhị Kinh (Tô-bi-a, Giu-đi-tha, Khôn Ngoan, Huấn Ca, Ma-ca-bê, Ba-rúc) và không dùng tên "
             "sách theo bản Công giáo. Trích nguyên văn theo bản dịch Truyền Thống 1926 (bản Hội Thánh Tin Lành Việt "
             "Nam dùng), ghi đúng sách chương câu (ví dụ Ga-la-ti 6:9). Không chắc chữ chính xác thì chọn câu quen "
             "thuộc khác.",
    "family": "Viết MỘT lời khích lệ ngắn về cố gắng vì gia đình, vì con cái, vì cuộc sống. "
              "Có thể kèm một châm ngôn có thật của người thành đạt hoặc danh nhân xưa nếu hợp, ghi rõ nguồn. "
              "KHÔNG dùng Kinh Thánh.",
}
FAMILY_BIBLE = ("Viết MỘT lời khích lệ ngắn về cố gắng vì gia đình, vì con cái, vì cuộc sống. "
                "Có thể kèm một câu nói nổi tiếng có thật hoặc câu Kinh Thánh nếu hợp, ghi rõ nguồn.")


def style_prompt(cfg, style):
    """Lời dặn AI cho kiểu câu khích lệ. Tắt Kinh Thánh thì không kiểu nào được nhắc tới Kinh Thánh."""
    if style == "family" and ai_context.bible_on(cfg):
        return FAMILY_BIBLE
    return STYLE_PROMPTS[style]

POSITIVE = ("Lời khích lệ LUÔN tích cực, ấm áp, đầy hy vọng: không chê trách, không nhắc thất bại, "
            "không so sánh tiêu cực, không doạ nạt (kể cả giọng sếp khó tính: nghiêm nhưng vẫn khích lệ).")

MODES = {"quote": ["motivation", "family"], "bible": ["bible"], "both": ["motivation", "bible", "family"]}


def auto_on(cfg):
    """Có tự gửi lời khích lệ không (đầu ngày, buổi chiều, kèm cảnh báo). /encourage off để tắt."""
    return bool(cfg.get("encouragement_enabled", True))


def system_prompt(cfg, extra=""):
    """Ngữ cảnh đầy đủ (app, công việc, giờ làm, luật tập trung, giọng văn). Xem ai_context.py."""
    return ai_context.system_prompt(cfg, extra)


RECENT_QUOTE_DAYS = 2   # "đừng lặp lại" chỉ gồm câu gửi hôm nay và hôm qua; câu cũ hơn lặp lại cũng được
RECENT_QUOTE_MAX = 30   # chặn trên phòng khi một ngày gửi quá nhiều


def quote_of(text):
    """Chỉ lấy câu trích (kèm nguồn) trong tin AI viết, bỏ lời chào / lời dặn: dòng có dấu ngoặc kép, không có thì dòng
    có câu Kinh Thánh dạng 40:31; không thấy thì giữ nguyên cả tin."""
    lines = [l.strip() for l in str(text or "").splitlines() if l.strip()]
    for pattern in (r'["“”«»]', r"\b\d+:\d+\b"):
        for line in lines:
            if len(line) > 15 and re.search(pattern, line):
                return line
    return "\n".join(lines)


def _db_recent(db, limit=RECENT_QUOTE_MAX, days=RECENT_QUOTE_DAYS, now=None):
    """Câu khích lệ / Kinh Thánh đã gửi từ 0h của (days - 1) ngày trước tới giờ, mới nhất trước, đầy đủ không cắt,
    không trùng. Không tính bài tập mắt / vận động (style exercise)."""
    since = dt.datetime.combine(dt.date.fromtimestamp(now or time.time()) - dt.timedelta(days=days - 1),
                                dt.time()).timestamp()
    out = []
    for (text,) in db.execute("SELECT text FROM quotes WHERE ts >= ? AND COALESCE(style, '') != 'exercise' "
                              "ORDER BY ts DESC", (since,)):
        q = quote_of(text)
        if q and q not in out:
            out.append(q)
    return out[:limit]


def _recent_exercises(db, limit=6):
    return [r[0] for r in db.execute("SELECT text FROM quotes WHERE style = 'exercise' ORDER BY ts DESC LIMIT ?",
                                     (limit,))]


def _avoid_block(recent):
    return ("\n\nĐừng lặp lại các câu đã gửi hôm nay và hôm qua (nguyên văn):\n" + "\n".join(f"- {r}" for r in recent)
            if recent else "")


def _remember(db, style, text):
    if style != "exercise":
        text = quote_of(text)  # chỉ lưu câu trích, không lưu cả lời chào
    with db:
        db.execute("INSERT INTO quotes (ts, style, text) VALUES (?,?,?)", (time.time(), style, text))


def _local(style, recent):
    """Câu có sẵn (không AI). Chỉ kiểu "bible" mới có Kinh Thánh; danh ngôn và "vì gia đình" không bao giờ có."""
    joined = " ".join(recent)
    if style == "bible":
        pool = [q for q in BIBLE if q[0][:30] not in joined] or BIBLE
        text, ref = random.choice(pool)
        return f'"{text}" ({ref})'
    if style == "family":
        pool = [q for q in FAMILY if q[:30] not in joined] or FAMILY
        return random.choice(pool)
    pool = [q for q in QUOTES if q[0][:30] not in joined] or QUOTES
    text, author = random.choice(pool)
    return f'"{text}" — {author}'


def pick_style(cfg, db):
    styles = cfg.get("encouragement_styles") or ["motivation", "family"]  # cấu hình rỗng: không tự thêm Kinh Thánh
    last = db.execute("SELECT style FROM quotes ORDER BY ts DESC LIMIT 1").fetchone()
    if last and last[0] in styles and len(styles) > 1:
        styles = [s for s in styles if s != last[0]]
    return random.choice(styles)


def encouragement(cfg, db, situation, style=None):
    """Một câu khích lệ hợp tình huống. Không bao giờ raise."""
    style = style or pick_style(cfg, db)
    recent = _db_recent(db)
    text = None
    if ai_client.provider(cfg):
        prompt = (f"VIỆC CẦN LÀM: viết một lời khích lệ gửi qua Telegram.\n{style_prompt(cfg, style)}\n{POSITIVE}\n\n"
                  f"Tình huống lúc này: {situation}\n\n"
                  "Trả lời đúng 2 dòng: dòng 1 là câu trích (kèm nguồn), dòng 2 là một câu ngắn gắn với "
                  "tình huống, gợi ý một bước nhỏ làm ngay.")
        prompt += _avoid_block(recent)
        try:
            text, _ = ai_client.generate(cfg, prompt, system_prompt(cfg), purpose=f"encourage:{style}")
        except ai_client.AIError:
            text = None
    text = text or _local(style, recent)
    _remember(db, style, text)
    return text


MORNING_TASK = """VIỆC CẦN LÀM: viết tin nhắn chào buổi sáng, gửi tự động qua Telegram lúc người dùng bắt đầu ngày làm việc.
{style}
{positive}

THÔNG TIN (JSON, app đã tách sẵn theo ngày):
- "today": thông tin của hôm nay {today}. Ngày làm việc mới bắt đầu nên CHƯA có số liệu tập trung hôm nay.
- "previous_workday" (nếu có): báo cáo ngắn của ngày làm việc trước, có ghi rõ ngày. Đó là chuyện đã qua,
  không phải số liệu hôm nay; nhắc tới thì nói rõ là hôm đó (ví dụ "hôm qua" hoặc "thứ Sáu tuần trước").
{info}

Viết 3–5 dòng, văn bản thường:
1. Một câu chào buổi sáng ngắn, đúng giọng văn và cách xưng hô.
2. Câu trích (nguyên văn, kèm nguồn) trên một dòng riêng.
3. Một câu nối ý câu trích với hôm nay: nếu today có first_task thì khích lệ bắt đầu ngay bằng việc đó; nếu có
   previous_workday thì chỉ nhắc điểm tốt của ngày đó (không nhắc điểm yếu).
4. Nếu today có pending_from_previous_workday (việc trong kế hoạch và issue các ngày trước chưa thấy ghi xong, cộng
   dồn, việc tồn lâu có ghi "tồn từ ..."):
   app sẽ TỰ gửi nguyên danh sách ngay dưới tin nhắn của bạn, nên bạn KHÔNG chép lại danh sách; chỉ thêm một câu nhẹ
   nhàng khích lệ xử lý dứt điểm các việc còn tồn (có thể nêu tên 1 việc quan trọng nhất), không trách móc.
Không chèn số liệu khô khan, không lên lớp."""


def morning_payload(info):
    """Tách thông tin buổi sáng: "today" (hôm nay) và "previous_workday" (ngày làm việc trước, có ngày rõ ràng)."""
    today = {("date" if k == "today" else k): v for k, v in info.items() if k != "yesterday"}
    out = {"today": today}
    prev = info.get("yesterday")
    if prev:
        m = re.match(r"(\d{4}-\d{2}-\d{2}):\s*(.*)", str(prev), re.S)
        out["previous_workday"] = {"date": m.group(1), "summary": m.group(2)} if m else {"summary": str(prev)}
    return out


def morning_message(cfg, db, info, style=None):
    """Tin chào buổi sáng có câu khích lệ / Kinh Thánh. Luôn tích cực. Không bao giờ raise."""
    style = style or pick_style(cfg, db)
    recent = _db_recent(db)
    text = None
    if ai_client.provider(cfg):
        data = morning_payload(info)
        prompt = MORNING_TASK.format(style=style_prompt(cfg, style), positive=POSITIVE, today=data["today"].get("date", ""),
                                     info=json.dumps(data, ensure_ascii=False, indent=1))
        prompt += _avoid_block(recent)
        try:
            text, _ = ai_client.generate(cfg, prompt, system_prompt(cfg), purpose=f"morning:{style}")
        except ai_client.AIError as e:
            log.warning("AI lời chào buổi sáng lỗi: %s", e)
            text = None
    if text:
        _remember(db, style, text)
        return text
    quote = _local(style, recent)
    _remember(db, style, quote)
    lines = ["Chào buổi sáng! Chúc bạn một ngày làm việc nhẹ nhàng và hiệu quả.", quote]
    if info.get("first_task"):
        lines.append(f"Bắt đầu ngay với: {info['first_task']}. Bạn làm được!")
    return "\n".join(lines)


ASK_TASK = """VIỆC CẦN LÀM: người dùng đang ở chế độ "hỏi AI" của bot và gửi câu hỏi dưới đây. Câu hỏi có thể về
bất kỳ chủ đề nào (tập trung, công việc, AS400/COBOL/Life Asia, sức khoẻ, tài chính, kiếm thêm thu nhập, gia đình...).
- Mỗi câu hỏi độc lập: bạn KHÔNG thấy các câu hỏi trước. Nếu câu hỏi nhắc tới "câu trước", nói ngắn rằng bạn không xem
  được câu trước và nhờ người dùng hỏi lại đầy đủ.
- Trả lời thẳng vào câu hỏi, cụ thể, làm được; ưu tiên bước hành động. Tối đa khoảng 250 từ trừ khi câu hỏi cần dài hơn.
- Câu hỏi cần thông tin mới nhất (giá vàng, tỷ giá, giá xăng, tin tức, thời tiết, lịch sự kiện...): dùng công cụ tìm
  kiếm web nếu có, ưu tiên nơi người dùng sống, ghi rõ nguồn và thời điểm của số liệu. Không tra được thì nói thẳng là
  không có số liệu thời gian thực và gợi ý nơi xem (ví dụ trang SJC, PNJ, ngân hàng); TUYỆT ĐỐI không bịa số.
- Dùng thông tin về người dùng (tên, tuổi, nơi sống, công việc, hệ thống đang làm, số liệu hôm nay) khi liên quan để
  trả lời sát hoàn cảnh; không liên quan thì bỏ qua.
- Việc nhạy cảm (y tế, pháp lý, đầu tư): đưa thông tin chung và khuyên hỏi chuyên gia; không hứa lợi nhuận.
- Giữ đúng cách xưng hô và giọng văn đã dặn.

Thông tin lúc này (JSON): {live}

Câu hỏi của người dùng: \"\"\"{question}\"\"\"
"""


def ask_ai(cfg, question, live=None):
    """Hỏi AI một câu bất kỳ, kèm ngữ cảnh đầy đủ. Trả (text, thành_công). Không bao giờ raise."""
    prompt = ASK_TASK.format(live=json.dumps(live or {}, ensure_ascii=False), question=question[:3000])
    try:
        text, _ = ai_client.generate(cfg, prompt, system_prompt(cfg), purpose="ask", web=True)
        return text, True
    except ai_client.AIError as e:
        log.warning("Hỏi AI lỗi: %s", e)
        # Câu hỏi không có "nội dung có sẵn" thay thế: bỏ vế đó cho khỏi hiểu nhầm.
        msg = re.sub(r"[,.]?\s*(bot|mình) dùng nội dung có sẵn", "", str(e), flags=re.I).strip()
        return f"AI chưa trả lời được: {msg}", False


def break_message(db, minutes, p=None, water=False):
    """Nhắc nghỉ sau khi ngồi làm liên tục: đứng dậy đi lại, vươn vai, tập mắt (20-20-20 chống cận), kèm một bài
    tập không lặp 6 lần gần nhất. p: persona (câu mở đầu theo giọng). water=True: gộp luôn nhắc uống nước."""
    from . import persona as _persona  # import trễ: persona -> config
    recent = _recent_exercises(db)
    pool = [e for e in EXERCISES if e[:25] not in " ".join(recent)] or EXERCISES
    tip = random.choice(pool)
    _remember(db, "exercise", tip)
    lead = _persona.lead("break", p) if p else ""
    body = (f"Bạn đã tập trung liên tục {minutes} phút, giỏi lắm. Đứng dậy nghỉ 3–5 phút: đi lại vài vòng, vươn vai, "
            "cho mắt nghỉ theo quy tắc 20-20-20 (nhìn xa 6 mét trong 20 giây) để đỡ mỏi mắt, đỡ cận.")
    if water:
        body += "\n💧 Tiện thể rót một ly nước uống luôn nhé."
    from .messages import SITTING_SCIENCE, science_line  # import trễ
    return (f"{lead}\n{body}" if lead else body) + f"\n\n{tip}\n\n{science_line(SITTING_SCIENCE)}"


# ------------------------------------------------------------ AI nhận xét (có cache)

def _cached(db, key):
    row = db.execute("SELECT text FROM ai_cache WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _store(db, key, text):
    with db:
        db.execute("INSERT OR REPLACE INTO ai_cache (key, created, text) VALUES (?,?,?)", (key, time.time(), text))


def _key(prefix, payload):
    return prefix + ":" + hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


DAILY_TASK = """VIỆC CẦN LÀM: viết tin nhắn đánh giá cuối ngày làm việc {day} ({weekday}) của người dùng, gửi qua Telegram.

CẤU TRÚC SỐ LIỆU (app đã tính sẵn và tách theo ngày, không cần tính lại):
- "report_date": ngày bạn đang đánh giá, {day} ({weekday}). Bạn chỉ đánh giá ĐÚNG ngày này.
- "today": số liệu và ghi chú CHỈ của ngày {day}. Mọi con số bạn nói về "hôm nay" phải lấy từ phần này.
- "previous_days_context" (nếu có): báo cáo tóm tắt các ngày TRƯỚC {day}, mỗi mục ghi rõ "date". Phần này CHỈ để so
  sánh xu hướng, tìm issue lặp lại và kiểm tra lời hẹn hôm trước. TUYỆT ĐỐI không lấy số liệu ở đây làm số liệu hôm
  nay, không cộng dồn vào hôm nay. Khi nhắc tới ngày trước, ghi rõ ngày đó (ví dụ "thứ Ba 13/10").
- Trường không có mặt nghĩa là app không ghi nhận hoặc người dùng không ghi: không suy đoán, không bịa.
- "energy" là năng lượng còn lại cuối ngày 1–5 (1 = kiệt sức, 5 = còn rất sung). Có "energy_source": "app_uoc_tinh"
  thì người dùng KHÔNG tự chấm, app ước tính từ số giờ tập trung (càng tập trung sâu lâu càng thấp): đừng nói như thể
  đó là cảm nhận của người dùng.

{score_guide}

Viết tối đa 19 dòng, đúng thứ tự 7 mục sau (mỗi mục mở đầu bằng emoji và tên mục ngắn do bạn tự đặt, không markdown):
1. Điểm tổng hôm nay (BẮT BUỘC, 3–5 dòng, viết cho người chưa từng nghe tới điểm tổng):
   - Câu đầu: điểm tổng hôm nay là today.total_score/100 (today.total_score_10/10), nghĩa là mức gì (lấy từ
     today.total_score_explained.meaning), kèm robot quà today.gift_robot cho vui.
   - Giải thích vì sao ra số đó: điểm tổng gộp từ các thành phần nào, nêu số từng thành phần và nó đến từ số liệu gốc
     nào (today.total_score_explained.parts), ví dụ "điểm tập trung chỉ 14/100 vì tập trung sâu 0,1h so với mục tiêu
     4h", "ít bị cắt ngang 12/100 vì bị cắt ngang 17,6 lần mỗi giờ".
   - Nói rõ phần nào kéo điểm xuống nhiều nhất (today.total_score_explained.biggest_loss) và muốn tăng điểm thì làm gì,
     tăng khoảng bao nhiêu (today.total_score_explained.how_to_raise).
   - Rồi đánh giá chung tốt / ổn / chưa tốt: deep_hours so với mục tiêu {goal}h, so với previous_days_context
     (avg_deep_hours_7d, recent_days). Có overtime_vdi_minutes thì ghi nhận việc làm bù ngoài giờ. Nếu today có
     "leave" thì đánh giá theo mục tiêu nửa ngày.
2. Việc pending cho ngày mai: lấy today.pending_carry (app đã tính sẵn: việc kế hoạch và issue của hôm nay và các ngày
   trước chưa thấy ghi xong, cộng dồn, kèm "tồn từ" ngày nào; việc tồn nhiều ngày thì nhắc ưu tiên xử lý hoặc báo bot
   nếu đã xong), thêm việc hẹn ở previous_days_context.promised_yesterday chưa thấy làm hôm nay, và today.tomorrow nếu
   có. Không có dữ liệu thì nhắc ghi /tmrtask.
3. Mất tập trung vì đâu: 1–2 nguyên nhân chiếm nhiều phút / nhiều lần nhất trong today (app ngoài VDI
   outside_vdi_minutes, VDI thu nhỏ vdi_minimized_minutes / vdi_minimize_count, ngồi yên 1–5 phút nhiều lần = điện
   thoại, rời máy away_minutes / away_count, today.vdi_closed = VDI tự ngắt vì bỏ VDI quá lâu, VDI không toàn màn hình,
   distractions người dùng ghi). App ngoài VDI có thể là việc liên quan công việc (ghi chú, tra cứu, công cụ AI, chat
   với đồng nghiệp): nói là "thời gian ngoài VDI", không khẳng định người dùng đang chơi.
4. Cần khắc phục: với từng issue/blocker quan trọng của today (hoặc lặp lại trong previous_days_context.recent_issues,
   ghi rõ đã gặp ngày nào), gợi ý một bước xử lý cụ thể, sát bối cảnh công việc (AS400/COBOL/Life Asia nếu liên quan).
   Không có issue nào thì chỉ viết một dòng ngắn "hôm nay chưa ghi issue nào" và nhắc /issue, không tự nghĩ ra việc
   cần khắc phục chung chung.
5. Ngày mai cải thiện: 1–2 hành động rất cụ thể, làm được, có giờ giấc (ví dụ chặn khung giờ vàng, tắt app nào, để điện thoại ở đâu).
   Nếu today có "science_advice" (điểm tổng dưới 50): thêm đúng một câu dựa trên dữ kiện đó (giữ tên tác giả, năm,
   con số như đã cho), nối với lý do làm việc vì gia đình. Không có trường này thì KHÔNG tự nêu nghiên cứu nào.
6. Một câu khích lệ ngắn hợp giọng văn{quote_hint}. Câu phải nâng đỡ, tích cực, cho thêm sức (kể cả khi ngày kém):
   không chọn câu răn đe, chê trách (ví dụ câu về sự biếng nhác). Câu trích phải đúng nguyên văn; không chắc nguyên
   văn thì chọn câu khác.
7. Dòng cuối: {wish}
Không chép lại toàn bộ số liệu (riêng điểm tổng ở mục 1 thì phải giải thích đủ). Thiếu số liệu ở mục nào thì nói
ngắn gọn rồi bỏ qua, không bịa."""

WEEKLY_TASK = """VIỆC CẦN LÀM: tổng kết tuần {week} ({start} → {end}) cho người dùng.
Bạn KHÔNG nhớ gì về các ngày trong tuần, nên dưới đây là TOÀN BỘ báo cáo của tuần, app đã tính sẵn và tách theo ngày:
- "week_summary": tổng hợp cả tuần (giờ tập trung sâu, điểm trung bình, điểm tổng trung bình avg_total_score, ngày
  tốt/kém nhất, giờ vàng). "week_summary.total_score_explained" đã tính sẵn: meaning (điểm tổng trung bình nghĩa là
  mức gì), avg_parts (điểm thành phần trung bình), by_day (điểm tổng và thành phần từng ngày), best_day, worst_day,
  biggest_loss (phần kéo điểm cả tuần xuống nhiều nhất). Issue nằm trong từng ngày ở "days".
- "days": báo cáo đầy đủ TỪNG ngày làm việc theo thứ tự thời gian: số liệu tập trung, khối tập trung, app ngoài VDI,
  kế hoạch đầu ngày (plan), việc đã xong (output), issue, điều làm mất tập trung, năng lượng 1–5 (có
  "energy_source": "app_uoc_tinh" là app tự ước tính vì người dùng không chấm, không phải cảm nhận), giờ AS400, việc hẹn
  làm đầu tiên sáng hôm sau (tomorrow), và "ai_daily_review" là lời đánh giá AI đã gửi cuối ngày đó (nếu có).
- "days_off": ngày nghỉ trong tuần và lý do. "previous_week": số liệu tuần trước, CHỈ để so sánh (nếu có).
Mỗi phần tử trong "days" là báo cáo của ĐÚNG MỘT ngày (trường "day" / "weekday"): số liệu ngày nào chỉ thuộc ngày đó,
không trộn hay chuyển số giữa các ngày; khi nêu số liệu luôn kèm ngày. "ai_daily_review" là lời nhận xét đã gửi hôm
đó, không phải số liệu. Số tổng của tuần lấy từ "week_summary", không tự cộng lại.

Cách đọc trước khi viết (không cần viết ra các bước này):
- So plan với output từng ngày: việc nào xong, việc nào kéo dài qua nhiều ngày, việc nào chưa thấy xong tới cuối tuần.
- So "tomorrow" của ngày này với plan/output của ngày làm việc kế tiếp: có giữ lời hẹn không.
- Gom issue giống nhau qua các ngày (cùng hệ thống, cùng nguyên nhân) và đếm số lần lặp.
- Xem lời khuyên trong ai_daily_review các ngày trước có được làm theo không (số liệu ngày sau có tốt lên không).
- Tìm quy luật: ngày/giờ nào tập trung tốt, năng lượng thấp đi cùng số liệu nào, ngoài VDI / thu nhỏ VDI / ngồi yên 1–5 phút (thường là điện thoại) tăng vào lúc nào.

{score_guide}

Viết tin nhắn Telegram tối đa 24 dòng, theo thứ tự (mỗi mục mở đầu bằng emoji và tên mục ngắn do bạn tự đặt, không markdown):
1. Điểm tổng của tuần (BẮT BUỘC, 3–5 dòng, viết cho người chưa từng nghe tới điểm tổng): điểm tổng trung bình
   week_summary.avg_total_score/100 nghĩa là mức gì (total_score_explained.meaning); điểm tổng gộp từ những thành phần
   nào và trung bình mỗi phần bao nhiêu (avg_parts); ngày điểm cao nhất, thấp nhất và vì sao, dựa trên thành phần của
   chính ngày đó (by_day); phần nào kéo điểm cả tuần xuống nhiều nhất (biggest_loss) và tuần sau cải thiện gì để tăng
   điểm. So với tuần trước nếu có.
2. Đánh giá chung: tuần tốt/ổn/chưa tốt, số ngày đạt mục tiêu, giờ tập trung sâu, xu hướng trong tuần.
3. Ngày tốt nhất và kém nhất: nguyên nhân dựa trên số liệu và ghi chú của chính ngày đó (gộp với mục 1 nếu đã nói).
4. Việc đã xong và việc còn pending sang tuần sau: dựa trên plan/output/tomorrow/issue, nêu tên việc cụ thể.
5. Issue lặp lại: mỗi nhóm 1 dòng kèm số lần và một bước khắc phục cụ thể sát bối cảnh công việc.
6. Mất tập trung: quy luật chính của tuần và cách giảm.
7. Mục tiêu tuần sau: 1–2 mục tiêu nhỏ, đo được, có ngày giờ cụ thể (ví dụ giữ giờ vàng cho việc gì).
8. Một câu khích lệ ngắn hợp giọng văn{quote_hint}: nâng đỡ, tích cực, không răn đe chê trách; câu trích đúng
   nguyên văn.
9. Dòng cuối: {wish}
Chỉ dùng số liệu và ghi chú được cung cấp; thiếu thì nói ngắn rồi bỏ qua, không bịa."""

WEEK_FIELD_CAP = 900  # cắt mỗi ghi chú dài cho prompt gọn


def _short(v, cap=WEEK_FIELD_CAP):
    return v if not isinstance(v, str) or len(v) <= cap else v[:cap] + "…"


def _last_daily_review(db, day):
    row = db.execute("SELECT text FROM ai_cache WHERE key LIKE ? ORDER BY created DESC LIMIT 1",
                     (f"review:{day}:%",)).fetchone()
    return row[0] if row else None


def week_context(cfg, db, facts):
    """Báo cáo đầy đủ cả tuần cho AI (AI không nhớ các ngày trước): tổng hợp + từng ngày + tuần trước."""
    import datetime as dt
    from .analysis import day_facts, off_day, week_facts
    start, end = dt.date.fromisoformat(facts["from"]), dt.date.fromisoformat(facts["to"])
    days, offs = [], []
    d = start
    while d <= end:
        ds = d.isoformat()
        reason = off_day(db, cfg, ds)
        if reason:
            offs.append(f"{ds} ({reason})")
        else:
            f = day_facts(db, cfg, ds)
            # mọi ngày làm việc có số liệu (kể cả ngày 0h tập trung sâu: đó thường là ngày kém nhất) hoặc có ghi chú
            if "work_from_to" in f or f.get("deep_hours") or any(f.get(k) for k in ("plan", "output", "issues",
                                                                                     "tomorrow", "energy")):
                for k in ("recent_days", "recent_issues", "avg_deep_hours_7d", "streak_days", "goal_hours",
                          "total_score_explained"):
                    f.pop(k, None)  # đã có ở cấp tuần (total_score_explained.by_day), bớt lặp
                review = _last_daily_review(db, ds)
                if review:
                    f["ai_daily_review"] = review
                days.append({k: _short(v) for k, v in f.items()})
        d += dt.timedelta(days=1)
    out = {"week_summary": {k: v for k, v in facts.items() if k != "issues"}, "days": days}
    explained = scoring.explain_week(days)
    if explained:
        out["week_summary"]["total_score_explained"] = explained  # AI giải thích lại điểm tổng tuần cho người dùng
    if offs:
        out["days_off"] = offs
    prev = week_facts(db, cfg, (start - dt.timedelta(days=1)).isoformat())
    if prev.get("work_days"):
        out["previous_week"] = {k: prev[k] for k in ("week", "work_days", "deep_hours_total", "deep_hours_avg",
                                                     "avg_score", "avg_total_score", "days_reached_goal") if k in prev}
    return out


def evening_wish_hint(day):
    """Lời dặn AI chúc cuối ngày: từ thứ Sáu trở đi chúc cuối tuần, ngày khác chúc buổi tối."""
    import datetime as dt
    d = dt.date.fromisoformat(day)
    if d.weekday() >= 4:
        return ("lời chúc cuối tuần vui vẻ, nghỉ ngơi trọn vẹn bên gia đình, ấm áp, tự nhiên, hợp giọng văn "
                "(sếp khó tính thì chúc ngắn gọn nhưng vẫn chân thành).")
    return ("lời chúc buổi tối ấm áp, thư giãn bên gia đình, tự nhiên, hợp giọng văn "
            "(sếp khó tính thì chúc ngắn gọn nhưng vẫn chân thành).")


WISHES = {"evening": ["Chúc bạn buổi tối thật ấm áp bên gia đình nhé 🏡", "Tắt máy thôi, chúc bạn buổi tối vui vẻ bên người thân.",
                      "Hôm nay vậy là đủ rồi. Chúc bạn buổi tối bình yên, ấm áp bên gia đình."],
          "weekend": ["Chúc bạn cuối tuần vui vẻ, nghỉ ngơi trọn vẹn bên gia đình nhé 🌿",
                      "Hết tuần rồi! Chúc bạn cuối tuần thật thư giãn và ấm áp bên người thân.",
                      "Cuối tuần sạc lại năng lượng bên gia đình nhé, tuần sau mình lại cùng cố gắng."]}


def local_wish(day, weekend=None):
    """Lời chúc có sẵn khi AI không viết được (để báo cáo nào cũng có lời chúc). Tổng kết tuần: weekend=True."""
    import datetime as dt
    if weekend is None:
        weekend = dt.date.fromisoformat(day).weekday() >= 4
    return random.choice(WISHES["weekend" if weekend else "evening"])


def _quote_hint(cfg):
    if ai_context.bible_on(cfg):
        return " (có thể là câu Kinh Thánh Tin Lành bản Truyền Thống 1926 hoặc câu nói nổi tiếng có thật, ghi nguồn)"
    return (" (là châm ngôn / câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa, ghi đúng "
            "tác giả; người dùng đã TẮT Kinh Thánh nên KHÔNG dùng Kinh Thánh)")


def ai_review_on(cfg):
    return bool(cfg.get("ai_review_enabled", True)) and bool(ai_client.provider(cfg))


PREVIOUS_DAY_KEYS = ("avg_deep_hours_7d", "recent_days", "recent_issues")


def daily_payload(facts, promised=None):
    """Tách số liệu gửi AI: "today" chỉ chứa ngày đang đánh giá; các ngày trước nằm riêng trong
    "previous_days_context", mỗi mục có ngày, để AI không bao giờ lấy số ngày trước làm số hôm nay.
    promised: (ngày ghi, việc) hẹn làm đầu tiên, ghi từ hôm trước."""
    day = facts["day"]
    today = {k: v for k, v in facts.items() if k not in PREVIOUS_DAY_KEYS and k != "promised_yesterday"}
    out = {"report_date": f"{day} ({facts.get('weekday', '')})".replace(" ()", ""), "today": today}
    prev = {k: facts[k] for k in PREVIOUS_DAY_KEYS if facts.get(k)}
    if promised:
        prev["promised_yesterday"] = {"written_on": promised[0], "task": _short(promised[1])}
    if prev:
        out["previous_days_context"] = dict(
            {"note": f"Báo cáo các ngày TRƯỚC {day}, chỉ để so sánh. KHÔNG phải số liệu ngày {day}."}, **prev)
    return out


def _review_prompt(task, facts):
    keys = dict(facts)
    for day in facts.get("days") or []:  # báo cáo tuần: giải thích cả các trường của từng ngày
        keys.update(day)
    for part in ("week_summary", "today", "previous_days_context"):
        keys.update(facts.get(part) or {})
    return (f"{task}\n\n{ai_context.glossary(keys)}\n\n"
            f"SỐ LIỆU (JSON):\n{json.dumps(facts, ensure_ascii=False, indent=1)}")


def daily_review(cfg, db, facts):
    return review_day(cfg, db, facts)[0]  # None nếu AI tắt / lỗi


class ReviewError(str):
    """Lý do AI chưa đánh giá được (là chuỗi để in ra). permanent=True: thử lại cũng vô ích (thiếu/sai key)."""
    permanent = False

    @classmethod
    def of(cls, text, permanent=False):
        e = cls(text)
        e.permanent = permanent
        return e


def review_day(cfg, db, facts):
    """AI đọc báo cáo ngày và viết đánh giá. Trả (text, lỗi).
    Đánh giá CHỈ do AI viết (không có câu soạn sẵn): AI tắt -> (None, None); AI lỗi -> (None, lý do)."""
    if not cfg.get("ai_review_enabled", True):
        return None, None
    if not ai_client.provider(cfg):
        return None, ReviewError.of("chưa có API key AI", permanent=True)
    from .storage import last_tomorrow
    payload = daily_payload(facts, last_tomorrow(db, facts["day"], with_day=True))  # AI không nhớ hôm qua
    key = _key(f"review:{facts['day']}", {"facts": payload, "ctx": ai_context.fingerprint(cfg)})
    hit = _cached(db, key)
    if hit:
        return hit, None
    task = DAILY_TASK.format(day=facts["day"], weekday=facts.get("weekday", ""), goal=facts.get("goal_hours"),
                             wish=evening_wish_hint(facts["day"]),
                             quote_hint=_quote_hint(cfg), score_guide=scoring.score_guide())
    try:
        text, _ = ai_client.generate(cfg, _review_prompt(task, payload), system_prompt(cfg), purpose="daily_review")
    except ai_client.AIError as e:
        log.warning("AI đánh giá ngày lỗi: %s", e)
        return None, ReviewError.of(str(e), getattr(e, "permanent", False))
    _store(db, key, text)
    return text, None


def weekly_review(cfg, db, facts):
    return review_week(cfg, db, facts)[0]


def review_week(cfg, db, facts):
    """Như review_day, cho tuần. Trả (text, lỗi)."""
    if not cfg.get("ai_review_enabled", True):
        return None, None
    if not ai_client.provider(cfg):
        return None, ReviewError.of("chưa có API key AI", permanent=True)
    full = week_context(cfg, db, facts)  # khoá cache theo ĐÚNG dữ liệu gửi AI: thêm ghi chú ngày nào thì đánh giá lại
    key = _key(f"week:{facts['week']}", {"facts": full, "ctx": ai_context.fingerprint(cfg)})
    hit = _cached(db, key)
    if hit:
        return hit, None
    task = WEEKLY_TASK.format(week=facts["week"], start=facts.get("from"), end=facts.get("to"),
                              quote_hint=_quote_hint(cfg), wish=evening_wish_hint(facts.get("to") or facts["from"]),
                              score_guide=scoring.score_guide())
    try:
        text, _ = ai_client.generate(cfg, _review_prompt(task, full), system_prompt(cfg), purpose="weekly_review")
    except ai_client.AIError as e:
        log.warning("AI tổng kết tuần lỗi: %s", e)
        return None, ReviewError.of(str(e), getattr(e, "permanent", False))
    _store(db, key, text)
    return text, None


# ------------------------------------------------------------ AS400

AS400_PROMPT = """Ảnh này là màn hình AS400 (ví dụ danh sách spooled file / job log) của ngày {day}.
Tìm thời điểm SỚM NHẤT và MUỘN NHẤT của ngày {day} xuất hiện trong ảnh (giờ:phút).
Chỉ trả về JSON một dòng, không giải thích:
{{"start": "HH:MM" hoặc null, "end": "HH:MM" hoặc null, "note": "ghi chú ngắn nếu ảnh mờ/không rõ"}}"""


def read_as400_times(cfg, image, day):
    """Trả (start, end, note). Raise ai_client.AIError nếu không có AI hoặc lỗi."""
    text, _ = ai_client.generate(cfg, AS400_PROMPT.format(day=day), image=image, purpose="as400_photo")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ai_client.AIError("AI không đọc ra giờ trong ảnh.")
    try:
        data = json.loads(m.group(0))
    except ValueError:
        raise ai_client.AIError("AI trả về dữ liệu giờ không hợp lệ.")
    if not isinstance(data, dict):
        raise ai_client.AIError("AI trả về dữ liệu giờ không hợp lệ.")
    ok = lambda v: v if isinstance(v, str) and re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", v) else None
    return ok(data.get("start")), ok(data.get("end")), data.get("note") or ""
