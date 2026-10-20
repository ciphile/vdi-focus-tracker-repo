"""Câu chữ của các cảnh báo. Giọng và cách xưng hô lấy từ config/persona.json (xem persona.py).

Viết câu ở đây với "bạn"/"mình"; bot tự đổi sang cách xưng hô đã chọn khi gửi.
"""
import datetime as dt
import random

from . import persona as _persona

WHERE = {"minimized": "VDI đang thu nhỏ", "background": "VDI nằm sau app khác", "absent": "chưa mở VDI"}


def _join(*parts):
    return "\n".join(p for p in parts if p)


# Câu chốt theo mức nhắc (/nudge). Giọng sếp khó tính có câu riêng, các giọng khác dùng câu thường.
LEVEL_TAIL = {
    "nhe": {"sep_kho_tinh": "Hôm nay tôi chỉ nhắc một lần này. Còn lại tự giác.",
            "": "Hôm nay mình chỉ nhắc một lần này thôi, phần còn lại bạn tự giữ nhịp nhé."},
    "nghiem": {"sep_kho_tinh": "Còn ở ngoài thì {every} phút nữa tôi nhắc tiếp.",
               "": "Còn ở ngoài VDI thì {every} phút nữa mình nhắc tiếp, tới khi bạn quay lại."},
}


def _tone(p):
    return p.get("giong") if p.get("giong") == "sep_kho_tinh" else ""


def out_of_vdi(data, plan=None, p=_persona.DEFAULT):
    """Nhắc sao nhãng. Câu mở đầu theo mức nhắc (nhẹ / vừa / nghiêm), loại (VDI thu nhỏ / app khác) và giọng."""
    level = data.get("level") or "vua"
    where = WHERE.get(data["vdi_state"], "ngoài VDI")
    first = (plan or "").strip().splitlines()[:1]
    kind = "minimized" if data["vdi_state"] == "minimized" else "out_of_vdi"
    lead = _persona.nudge_lead(kind, level, p)
    tail = LEVEL_TAIL.get(level, {}).get(_tone(p), LEVEL_TAIL.get(level, {}).get("", ""))
    count = ""
    if level == "nghiem":
        count = (f"📌 Hôm nay: lần sao nhãng thứ {data.get('today_count', 1)}, "
                 f"đã mất tổng {data.get('today_minutes', data['minutes'])} phút ngoài VDI.")
    return _join(
        lead,
        f"⚠️ {data['minutes']} phút làm việc ngoài VDI ({where}, đang dùng {data['proc'] or 'app khác'}).",
        count,
        "Đây là giờ vàng của bạn, giữ nó cho việc khó nhất nhé." if data.get("golden") and level != "nhe" else "",
        _persona.lead("boss", p) if data["nth"] >= 2 else "",
        tail.format(every=data.get("every") or 5) if tail else "",
        f"Quay lại: {first[0]}" if first else "",
        "Bị chặn (VDI chậm, thiếu quyền, chờ người khác)? Ghi ngay: /issue nội dung")


def away(data, p=_persona.DEFAULT):
    since = dt.datetime.fromtimestamp(data["since"]).strftime("%H:%M")
    note = ("Máy đang khoá." if data["locked"] else
            "(Đang họp chỉ nghe trong VDI thì bỏ qua tin này, hoặc gõ /pause.)" if data["in_vdi"] else "")
    return _join(_persona.lead("away", p),
                 f"⏰ Bạn đã rời máy {data['minutes']} phút (từ {since}). Xong việc thì quay lại bàn nhé. {note}".strip(),
                 _persona.lead("boss", p))


def back(data, p=_persona.DEFAULT):
    """Quay lại sau khi rời máy: câu theo giọng bot, luân phiên (persona.LEADS["back"])."""
    return (_persona.lead("back", p, m=data["minutes"])
            or f"Chào mừng quay lại. Bạn rời máy {data['minutes']} phút. Vào VDI làm tiếp nhé.")


def phone(data, p=_persona.DEFAULT):
    return (f"📱 {data['count']} lần trong {data['window']} phút bạn ngồi yên 1–5 phút trước VDI rồi mới làm tiếp. "
            "Thường là đang cầm điện thoại/iPad. Úp điện thoại xuống, để ngoài tầm tay cho tới giờ nghỉ nhé. "
            "(Đang đọc code/tài liệu thì bỏ qua tin này.)")


def not_fullscreen(data, p=_persona.DEFAULT):
    return (f"🖥️ Bạn đã làm {data['minutes']} phút trong VDI mà VDI không toàn màn hình. Phóng to VDI trên một màn hình, "
            "để Chrome/Zalo ở màn hình kia hoặc tắt hẳn: ít thấy thì ít bấm.")


WATER_TIPS = ["Uống từng ngụm, đừng uống ừng ực một lần.", "Để sẵn bình nước trên bàn, trong tầm mắt.",
              "Nước lọc là tốt nhất; trà, cà phê không thay được nước.",
              "Đi rót nước cũng là dịp đứng dậy, đi lại một chút.",
              "Đừng đợi khát mới uống: thấy khát là cơ thể đã hơi thiếu nước rồi.",
              "Nước tiểu vàng sậm là dấu hiệu nên uống thêm; vàng nhạt là ổn.",
              "Mỗi lần mở một cuộc họp, làm một ngụm trước.",
              "Dùng bình có vạch chia, nhìn là biết hôm nay đã uống bao nhiêu.",
              "Uống một ly ngay sau khi ăn trưa, đầu giờ chiều đỡ uể oải hơn.",
              "Nước ấm hay nước mát đều được, miễn là uống đều trong ngày.",
              "Rót ly nhỏ, uống hết rồi đi rót tiếp: vừa uống đủ vừa có cớ đứng dậy.",
              "Thêm lát chanh hay vài lá bạc hà nếu thấy nước lọc nhạt quá.",
              "Đang chờ chạy job / compile thì nhấp vài ngụm, không phí phút nào.",
              "Cà phê, trà đặc làm đi tiểu nhiều hơn, nhớ uống bù thêm nước lọc."]

# Bệnh hay gặp khi ngồi nhiều, ít vận động, uống ít nước: viết chung chung, đúng hiểu biết y khoa phổ thông, không doạ.
WATER_HEALTH = ["Ngồi nhiều, uống ít là hai yếu tố hay gặp ở người bị sỏi thận.",
                "Uống ít và nhịn tiểu lâu dễ bị viêm đường tiết niệu, nhất là khi ngồi cả ngày.",
                "Thiếu nước cộng ít vận động là nguyên nhân thường gặp của táo bón.",
                "Mất nước nhẹ đã đủ gây đau đầu, mệt và khó tập trung về chiều.",
                "Uống ít làm nước tiểu đậm đặc, cặn dễ lắng lại thành sỏi.",
                "Ngồi liền nhiều giờ không cử động làm máu ở chân lưu thông chậm, tăng nguy cơ huyết khối tĩnh mạch "
                "sâu. Đứng dậy rót nước là cách cử động đơn giản nhất.",
                "Ngồi lâu ít vận động làm cổ, vai, lưng dưới cứng và đau; mỗi lần đi rót nước là một lần giãn cơ.",
                "Ngồi nhiều, ít vận động nhiều năm làm tăng nguy cơ tiểu đường type 2 và bệnh tim mạch.",
                "Ngồi lâu ít đi lại làm chân dễ phù, tê mỏi về chiều.",
                "Thiếu nước có thể làm da và mắt khô hơn, nhất là khi ngồi máy lạnh nhìn màn hình cả ngày.",
                "Ngồi lì một chỗ còn làm cơ mông, cơ đùi yếu dần, về lâu dài dễ đau lưng.",
                "Cơn uể oải đầu giờ chiều có khi do thiếu nước chứ không phải thiếu cà phê."]


WATER_SCIENCE = ("water_kidney", "water_brain", "water_uti")   # dữ kiện đã kiểm chứng trong scoring.SCIENCE
SITTING_SCIENCE = ("sitting_glucose", "sitting_mortality", "micro_breaks")


def science_line(keys):
    """Một dữ kiện nghiên cứu có thật (xoay vòng ngẫu nhiên), dạng «🔬 ...»."""
    from .scoring import SCIENCE  # import trễ: scoring -> analysis
    return "🔬 " + SCIENCE[random.choice(keys)]


def water(data, p=_persona.DEFAULT):
    """Nhắc uống nước: câu theo giọng + một mẹo hoặc một bệnh hay gặp khi ngồi nhiều / uống ít + một nghiên cứu có thật.
    Cả ba phần luân phiên (dùng hết mới lặp) nên nhắc nhiều lần trong ngày vẫn không lặp câu."""
    from .scoring import SCIENCE
    extra = _persona._rotate(("water_extra",), [f"💧 {t}" for t in WATER_TIPS] + [f"🩺 {t}" for t in WATER_HEALTH])
    study = _persona._rotate(("water_science",), list(WATER_SCIENCE))
    return _join(_persona.lead("water", p) or "Uống nước nhé.", extra, "🔬 " + SCIENCE[study])


def golden_tip(ranges):
    if not ranges:
        return ""
    return ("Giờ vàng của bạn (14 ngày gần nhất): " + ", ".join(r.replace("-", "–") for r in ranges)
            + ". Đặt một lịch \"Focus\" lặp lại vào khung này trong Outlook để người khác khó xếp họp.")


# ------------------------------------------------------------ tiến độ (/pace)

def _h(hours):
    m = int(round(hours * 60))
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} phút"


def pace_need_line(info):
    """Câu "cần bao nhiêu phút VDI mỗi giờ còn lại" (hoặc báo không kịp nữa)."""
    if info["left_h"] <= 0:
        return "Đã đủ mục tiêu hôm nay, giữ nhịp tới cuối giờ là đẹp."
    if info["remaining_min"] <= 0:
        return f"Đã hết giờ làm, còn thiếu {_h(info['left_h'])} so với mục tiêu."
    need = info["need_per_hour"]
    if need <= 60:
        return (f"Để đạt {info['target_h']:g}h và về đúng {info['end']} không OT: mỗi giờ còn lại cần "
                f"{need:.0f} phút làm trong VDI.")
    best = info["actual_h"] + info["remaining_min"] / 60
    return (f"Kể cả ở VDI liền tay {_h(info['remaining_min'] / 60)} còn lại cũng chỉ được khoảng {_h(best)}: "
            "dồn hết sức cho việc quan trọng nhất, tắt Zalo/Chrome, họp thì /pause.")


def pace_behind(info, p=_persona.DEFAULT, level="vua"):
    """Cảnh báo chậm tiến độ ở một mốc. info: pace.status(). Mức nghiem: câu gắt hơn."""
    strict = level == "nghiem"
    lead = _persona.lead("pace_behind_nghiem" if strict else "pace_behind", p)
    hard = _persona.lead("pace_hard", p) if strict else ""   # cùng một ý, đổi câu theo giọng, luân phiên
    return _join(
        lead,
        f"📉 {info['at']}: mới làm thật trong VDI {_h(info['actual_h'])}, lúc này cần khoảng "
        f"{_h(info['expected_h'])} để kịp {info['target_h']:g}h trước {info['end']}. Chậm {_h(info['behind_h'])}.",
        f"Còn {_h(info['remaining_min'] / 60)} giờ làm.",
        pace_need_line(info),
        hard)


def pace_praise(info, p=_persona.DEFAULT):
    return _join(_persona.lead("pace_praise", p),
                 f"✅ {info['at']}: đã làm thật trong VDI {_h(info['actual_h'])} (cần khoảng "
                 f"{_h(info['expected_h'])} lúc này). Giữ nhịp này là đạt {info['target_h']:g}h, về đúng "
                 f"{info['end']}.")


def pace_view(info, enabled, checkpoints):
    """/pace không kèm gì: tiến độ lúc này."""
    if info is None:
        state = "Chưa tới giờ làm hoặc hôm nay không phải ngày làm việc."
    else:
        mark = "đúng nhịp ✅" if not info["behind"] else f"chậm {_h(info['behind_h'])} ⚠️"
        state = _join(
            f"📈 Tiến độ lúc {info['at']}: làm thật trong VDI {_h(info['actual_h'])} / cần khoảng "
            f"{_h(info['expected_h'])} lúc này ({mark}).",
            f"Mục tiêu {info['target_h']:g}h trong VDI trước {info['end']}" + (" (nghỉ phép nửa ngày: mục tiêu một nửa)"
                                                                               if info.get("leave") else "")
            + f" · còn {_h(max(info['remaining_min'], 0) / 60)} giờ làm.",
            pace_need_line(info))
    return _join(state, f"Cảnh báo tiến độ tự động: {'ĐANG BẬT' if enabled else 'ĐANG TẮT'} (mốc "
                 + ", ".join(checkpoints) + ").", "Đổi: /pace on hoặc /pace off")


def vdi_closed(data, p=_persona.DEFAULT):
    """Cửa sổ VDI biến mất trong giờ làm (thường do Citrix tự ngắt khi không dùng 10–20 phút)."""
    hm = lambda t: dt.datetime.fromtimestamp(t).strftime("%H:%M")
    last = (f"Lần cuối bạn làm trong VDI lúc {hm(data['last_input'])}, cách đây {data['minutes']} phút."
            if data.get("last_input") else "")
    return _join(_persona.lead("away", p),
                 f"🔌 Cửa sổ VDI đã đóng từ {hm(data['since'])} (VDI tự ngắt khi không dùng 10–20 phút, hoặc bị đóng).",
                 last,
                 "Thời gian không có VDI không tính là giờ làm. Quay lại thì mở lại VDI nhé."
                 + (" Máy đang khoá." if data.get("locked") else ""))
