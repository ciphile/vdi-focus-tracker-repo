"""Cách bot xưng hô và giọng nói. Cấu hình trong config/persona.json (file riêng, sửa xong chạy lại tracker).

{
  "ten": "Minh",                  tên của bạn
  "tuoi": "35",                   tuổi (để AI khuyên hợp hoàn cảnh)
  "noi_song": "TP.HCM, Việt Nam", nơi sống (giá vàng, tỷ giá, thời tiết... đúng nơi)
  "goi_nguoi_dung": "bro",        bot gọi bạn là gì: "bạn", "bro", "anh", "chị", tên riêng...
  "bot_xung": "tui",              bot tự xưng: "mình", "em", "tui", "tôi"...
  "ten_sep": "anh Tuấn",          để trống nếu không muốn bot nhắc tới sếp
  "giong": "hai_huoc",            than_mat | vui_tuoi | hai_huoc | sep_kho_tinh
  "mo_ta": "..."                  vài dòng về bạn để AI nói chuyện hợp hơn (nghề, gia đình, niềm tin...)
}

- Mọi câu bot tự viết đều dùng cách xưng hô này (chữ "bạn"/"mình" trong code được thay tự động).
- Câu AI viết: AI được dặn đúng giọng và cách xưng hô.
- Câu trích dẫn (danh ngôn, Kinh Thánh) giữ nguyên, không bị đổi chữ.
"""
import json
import os
import random
import re

from .config import CONFIG_DIR
from .logs import get_logger

log = get_logger()
PATH = os.path.join(CONFIG_DIR, "persona.json")
TONES = ("than_mat", "vui_tuoi", "hai_huoc", "sep_kho_tinh")
DEFAULT = {"ten": "", "tuoi": "", "noi_song": "", "goi_nguoi_dung": "bạn", "bot_xung": "mình", "ten_sep": "", "giong": "than_mat", "mo_ta": ""}
SHOULD_FILL = ("ten", "tuoi", "noi_song", "mo_ta")  # để trống app vẫn chạy, nhưng AI khuyên chung chung hơn
# Lỗi JSON (tiếng Anh, từ thư viện json) -> câu dễ hiểu. Khớp theo đầu câu; không khớp thì giữ nguyên câu gốc.
JSON_HINTS = (
    ("Expecting ',' delimiter", "thiếu dấu phẩy cuối dòng trước"),
    ("Illegal trailing comma", "dư dấu phẩy ở dòng cuối, trước dấu }"),
    ("Expecting property name", "tên khoá phải nằm trong ngoặc kép, hoặc dư dấu phẩy ở dòng cuối trước dấu }"),
    ("Expecting ':' delimiter", "thiếu dấu hai chấm sau tên khoá"),
    ("Expecting value", "thiếu giá trị (file trống, hoặc chữ không có ngoặc kép)"),
    ("Unterminated string", "thiếu dấu ngoặc kép đóng"),
    ("Invalid control character", "giá trị bị xuống dòng giữa chừng, viết liền trên một dòng"),
    ("Extra data", "có chữ thừa sau dấu } cuối cùng"),
)

TONE_PROMPT = {
    "than_mat": "Giọng thân mật, ấm áp như một người bạn thân.",
    "vui_tuoi": "Giọng vui tươi, nhiều năng lượng, tích cực, có thể dùng 1 emoji.",
    "hai_huoc": "Giọng hài hước, dí dỏm, chọc nhẹ cho vui nhưng không xúc phạm, vẫn có ý khuyên rõ ràng.",
    "sep_kho_tinh": ("Giọng một ông sếp 60 tuổi khó tính, lạnh lùng, nói ngắn, cộc, nghiêm khắc, không emoji, "
                     "không khen suông; nhưng không xúc phạm, không chửi thề."),
}

# Câu mở đầu của cảnh báo theo giọng. {u} = cách gọi người dùng, {me} = bot tự xưng, {boss} = tên sếp.
LEADS = {
    "out_of_vdi": {
        "than_mat": ["Ê {u}, quay lại VDI thôi nào."],
        "vui_tuoi": ["Ối {u} ơi, VDI đang nhớ {u} kìa! 🏃"],
        "hai_huoc": ["{U} ơi, Chrome không trả lương cho {u} đâu nha 😄", "Báo động: {u} đã đi lạc khỏi VDI 🧭"],
        "sep_kho_tinh": ["Làm việc hay lướt web đấy?", "Tôi không trả lương cho việc ngồi ngoài VDI."],
    },
    # Mức nhắc sao nhãng (/nudge): <loại>_nhe (nhẹ, 1 lần/ngày), <loại> (vừa), <loại>_nghiem (nghiêm, nhắc lặp).
    # minimized = VDI đang thu nhỏ; out_of_vdi = app khác đang ở trước VDI.
    "minimized": {
        "than_mat": ["{U} ơi, VDI đang bị thu nhỏ kìa, mở lại làm tiếp nha."],
        "vui_tuoi": ["VDI bị thu nhỏ xíu xiu rồi {u} ơi, phóng to lên quẩy tiếp nào! 🚀"],
        "hai_huoc": ["VDI bị {u} cất vào túi quần rồi à? Lôi ra đi 😄", "VDI đang thu nhỏ, chắc nó đi ngủ trưa sớm 😴"],
        "sep_kho_tinh": ["VDI thu nhỏ. Mở lên.", "Thu nhỏ VDI là nghỉ làm à?"],
    },
    "out_of_vdi_nhe": {
        "than_mat": ["{U} ơi, nhắc nhẹ một câu thôi: mình quay lại VDI nhé."],
        "vui_tuoi": ["Nhắc xinh một lần thôi nè {u}: về VDI nha! 🌱"],
        "hai_huoc": ["Tin nhắn nhẹ như lông hồng: VDI vẫn đang chờ {u} đó 🪶"],
        "sep_kho_tinh": ["Nhắc một lần. Về VDI."],
    },
    "minimized_nhe": {
        "than_mat": ["{U} ơi, VDI đang thu nhỏ đó, mở lại khi sẵn sàng nhé."],
        "vui_tuoi": ["VDI đang thu nhỏ nè {u}, mở to ra là vào guồng liền! 🌱"],
        "hai_huoc": ["VDI đang trốn dưới thanh taskbar / Dock, {u} kéo nó ra nhẹ nhàng thôi 🪶"],
        "sep_kho_tinh": ["VDI đang thu nhỏ. Nhắc một lần."],
    },
    "out_of_vdi_nghiem": {
        "than_mat": ["{U}, nói thẳng nhé: ngoài VDI vậy là lâu rồi. Quay lại ngay."],
        "vui_tuoi": ["Dừng lại {u}! Không lướt nữa, về VDI ngay bây giờ nha!"],
        "hai_huoc": ["Hết giờ ra chơi rồi {u}. Chrome không chấm KPI đâu, về VDI ngay!"],
        "sep_kho_tinh": ["Lại ra ngoài VDI. Tôi nói lần nữa: quay lại làm việc.",
                         "Không chấp nhận. Đóng app kia, về VDI ngay."],
    },
    "minimized_nghiem": {
        "than_mat": ["{U}, VDI vẫn đang thu nhỏ. Mở lại và làm ngay nhé, đừng để trôi nữa."],
        "vui_tuoi": ["VDI vẫn thu nhỏ đó {u}! Phóng to lên và làm liền, không chần chừ!"],
        "hai_huoc": ["VDI thu nhỏ lâu thế này chắc nó tưởng bị sa thải rồi. Mở ra ngay {u}!"],
        "sep_kho_tinh": ["VDI vẫn thu nhỏ. Mở lên, làm việc. Ngay.", "Thu nhỏ VDI không làm việc thay được."],
    },
    # Cảnh báo tiến độ (/pace).
    "pace_behind": {
        "than_mat": ["{U} ơi, xem nhanh tiến độ hôm nay nè."],
        "vui_tuoi": ["Tăng tốc chút nào {u}! Vẫn kịp về đúng giờ nếu bắt đầu ngay 💪"],
        "hai_huoc": ["Đồng hồ chạy nhanh hơn {u} rồi đó, rượt theo thôi 🏃"],
        "sep_kho_tinh": ["Tiến độ chậm.", "Số giờ làm hôm nay chưa đạt."],
    },
    "pace_behind_nghiem": {
        "than_mat": ["{U}, nói thẳng: hôm nay đang chậm nhiều, phải dồn sức ngay."],
        "vui_tuoi": ["Báo động đỏ {u}! Chậm tiến độ rồi, vào VDI chiến ngay!"],
        "hai_huoc": ["Tiến độ đang đi bộ, deadline đang chạy xe máy. {U} vào VDI ngay!"],
        "sep_kho_tinh": ["Chậm quá. Không có lý do. Làm ngay.", "Thế này thì tối nay ngồi lại. Muốn vậy không?"],
    },
    "pace_praise": {
        "than_mat": ["Giỏi lắm {u}, đang đúng nhịp."],
        "vui_tuoi": ["Tuyệt vời {u} ơi, đang đúng nhịp nè! 🎉"],
        "hai_huoc": ["Ơ kìa, {u} đang chạy đúng lịch như tàu Nhật 🚄"],
        "sep_kho_tinh": ["Được. Giữ vậy."],
    },
    # Nhắc sức khoẻ (/break, /water): không phụ thuộc mức nhắc sao nhãng.
    "break": {
        "than_mat": ["{U} ơi, ngồi lâu rồi, mình nghỉ chân chút nha.", "Đứng dậy duỗi người chút đi {u}."],
        "vui_tuoi": ["Giờ vận động tới rồi {u} ơi! 🤸", "Đứng lên lắc lư chút nào {u}! 🎶"],
        "hai_huoc": ["Cái ghế than là {u} ngồi lâu quá rồi đó 😄", "Lưng {u} vừa gửi đơn khiếu nại 🪑"],
        "sep_kho_tinh": ["Ngồi lâu rồi. Đứng dậy.", "Nghỉ 5 phút. Rồi làm tiếp."],
    },
    "water": {
        "than_mat": ["{U} ơi, uống ngụm nước đi nè.", "Nhắc nhỏ: {u} uống nước chưa?", "Uống miếng nước rồi làm tiếp nha {u}."],
        "vui_tuoi": ["Đến giờ nạp nước rồi {u} ơi! 💧", "Một ly nước mát cho {u} tỉnh táo nè! 🥤",
                     "Cạn ly nước nào {u}! 💦"],
        "hai_huoc": ["Cây xương rồng còn được tưới, {u} cũng cần nước đó 🌵", "Não {u} 75% là nước, đổ thêm vào đi 🧠💧",
                     "Ly nước trên bàn đang buồn vì bị bỏ rơi 🥲"],
        "sep_kho_tinh": ["Uống nước.", "Uống nước rồi làm tiếp.", "Một ly nước. Không bàn."],
    },
    "away": {
        "than_mat": ["{U} đi đâu lâu thế?"],
        "vui_tuoi": ["{U} ơi, ghế đang trống nè! 🪑"],
        "hai_huoc": ["Toilet hôm nay có wifi hả {u}? 😄", "{U} bị ai bắt cóc rồi à? 🛸"],
        "sep_kho_tinh": ["Bàn trống. Người đâu?", "Đi đâu mà lâu vậy?"],
    },
    "boss": {
        "than_mat": ["Lỡ {boss} đi ngang thì hơi ngại đó."],
        "vui_tuoi": ["{boss} mà ghé ngang là toang á!"],
        "hai_huoc": ["{boss} đang đi tuần đó, cẩn thận 👀"],
        "sep_kho_tinh": ["{boss} mà thấy thì tôi không bênh đâu."],
    },
}


def _clean(data):
    """Giá trị đọc từ file -> persona đầy đủ khoá, giọng sai / trống về mặc định."""
    p = dict(DEFAULT)
    if isinstance(data, dict):
        p.update({k: str(v).strip() for k, v in data.items() if k in DEFAULT and v is not None})
    if p["giong"] not in TONES:
        p["giong"] = "than_mat"
    p["goi_nguoi_dung"] = p["goi_nguoi_dung"] or "bạn"
    p["bot_xung"] = p["bot_xung"] or "mình"
    return p


def load(path=PATH):
    data = None
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:  # sai cú pháp / không phải UTF-8: dùng mặc định, ghi log (lệnh check báo rõ)
        log.warning("Không đọc được %s, dùng xưng hô mặc định: %s", path, e)
    return _clean(data)


def inspect(path):
    """Kiểm tra persona.json cho lệnh check / kiem_tra_may. Trả dict: state "missing" | "error" | "ok", error (câu lỗi
    tiếng Việt), persona (giá trị app đang dùng), unknown (khoá lạ, gõ sai tên: app bỏ qua), empty (khoá nên điền còn
    trống), bad_tone (giọng gõ sai, app dùng than_mat)."""
    info = {"state": "ok", "error": "", "persona": dict(DEFAULT), "unknown": [], "empty": [], "bad_tone": ""}
    if not os.path.exists(path):
        info["state"] = "missing"
        return info
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError:  # trước ValueError (là lớp con của nó)
        info.update(state="error", error="không lưu dạng UTF-8 (Notepad: File > Save As > Encoding: UTF-8)")
        return info
    except ValueError as e:
        where = f" ở dòng {e.lineno}, cột {e.colno}" if getattr(e, "lineno", None) else ""
        msg = str(getattr(e, "msg", e))
        hint = next((vi for en, vi in JSON_HINTS if msg.startswith(en)), msg)
        info.update(state="error", error=f"sai cú pháp JSON{where} ({hint})")
        return info
    except OSError as e:
        info.update(state="error", error=f"không đọc được ({type(e).__name__}: {e})")
        return info
    if not isinstance(data, dict):
        info.update(state="error", error="phải là một khối { ... } như file mẫu persona.example.json")
        return info
    info["persona"] = _clean(data)
    info["unknown"] = [k for k in data if k not in DEFAULT and not str(k).startswith("_")]
    info["empty"] = [k for k in SHOULD_FILL if not info["persona"][k]]
    tone = str(data.get("giong") or "").strip()
    if tone and tone not in TONES:
        info["bad_tone"] = tone
    return info


def check_lines(path):
    """Các dòng in trong lệnh check về persona.json. Trả (ok, [dòng])."""
    info = inspect(path)
    rel = "config/persona.json"
    if info["state"] == "missing":
        return False, [f"✗ Chưa có {rel}: bot sẽ gọi bạn chung chung là «bạn» và AI không biết bạn là ai. Chép "
                       "config/persona.example.json thành persona.json rồi điền (README mục 2.4, bước 6)."]
    if info["state"] == "error":
        return False, [f"✗ {rel} {info['error']}: app đang bỏ qua cả file, dùng mặc định. So với file mẫu "
                       "persona.example.json, sửa xong chạy lại kiem_tra_may (phần check)."]
    p = info["persona"]
    bits = [f"bot gọi bạn «{p['goi_nguoi_dung']}», tự xưng «{p['bot_xung']}», giọng {p['giong']}"]
    if p["ten"]:
        bits.append(f"tên {p['ten']}")
    if p["ten_sep"]:
        bits.append(f"sếp {p['ten_sep']}")
    lines = [f"✓ {rel}: " + ", ".join(bits)]
    if info["bad_tone"]:
        lines.append(f"  ! giong «{info['bad_tone']}» không có, đang dùng than_mat. Chọn một trong: {', '.join(TONES)}")
    if info["unknown"]:
        lines.append(f"  ! Khoá lạ (gõ sai tên?), app bỏ qua: {', '.join(info['unknown'])}")
    if info["empty"]:
        lines.append(f"  ! Chưa điền: {', '.join(info['empty'])} (không bắt buộc, nhưng AI sẽ khuyên chung chung hơn)")
    return True, lines


def _cap(s):
    return s[:1].upper() + s[1:]


_WORD = r"(?<![\wÀ-ỹ]){}(?![\wÀ-ỹ])"


KEEP_OPEN, KEEP_CLOSE = "\ue000", "\ue001"
_KEEP_RE = re.compile("(\ue000.*?\ue001)", re.S)


def keep(text):
    """Bọc chữ của NGƯỜI DÙNG (ghi chú, issue...) để apply() không đổi "bạn"/"mình" bên trong."""
    return f"{KEEP_OPEN}{text}{KEEP_CLOSE}" if text not in (None, "") else text


def strip_keep(text):
    return text.replace(KEEP_OPEN, "").replace(KEEP_CLOSE, "") if text else text


def _apply_part(text, p):
    u, me = p["goi_nguoi_dung"], p["bot_xung"]
    for word, repl in (("bạn", u), ("mình", me)):
        if repl == word:
            continue
        text = re.sub(_WORD.format(word), lambda m: repl, text)  # lambda: "\\" trong tên không bị hiểu là nhóm regex
        text = re.sub(_WORD.format(_cap(word)), lambda m: _cap(repl), text)
    return text


def apply(text, p):
    """Đổi "bạn"/"mình" trong câu bot tự viết sang cách xưng hô đã chọn (giữ chữ hoa đầu câu).
    Phần bọc bằng keep() (chữ người dùng tự gõ) giữ nguyên."""
    if not text:
        return text
    parts = _KEEP_RE.split(text)
    return "".join(part if part.startswith(KEEP_OPEN) else _apply_part(part, p) for part in parts).replace(
        KEEP_OPEN, "").replace(KEEP_CLOSE, "")


def lead(kind, p):
    """Câu mở đầu ngẫu nhiên theo giọng cho một loại cảnh báo ("" nếu không có)."""
    options = LEADS.get(kind, {}).get(p["giong"]) or []
    if kind == "boss" and not p["ten_sep"]:
        return ""
    if not options:
        return ""
    return random.choice(options).format(u=p["goi_nguoi_dung"], U=_cap(p["goi_nguoi_dung"]),
                                         me=p["bot_xung"], boss=p["ten_sep"])


def ai_instructions(p):
    """Dặn AI xưng hô và giọng nói."""
    text = (f"Gọi người dùng là \"{p['goi_nguoi_dung']}\", tự xưng là \"{p['bot_xung']}\". "
            f"{TONE_PROMPT[p['giong']]}")
    if p["ten"]:
        text += f" Người dùng tên {p['ten']}."
    if p.get("tuoi"):
        text += f" Tuổi: {p['tuoi']}."
    if p.get("noi_song"):
        text += f" Sống ở: {p['noi_song']}."
    if p["mo_ta"]:
        text += f" Về người dùng: {p['mo_ta'][:500]}"
    if p["ten_sep"]:
        text += f" Sếp của người dùng là {p['ten_sep']}; thỉnh thoảng có thể nhắc tới khi phù hợp."
    return text
