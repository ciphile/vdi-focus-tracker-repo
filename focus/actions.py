"""Danh sách mọi thao tác của bot. Mỗi thao tác có:

- name      tên action cố định (AI và rule dự phòng trả về đúng tên này), ví dụ ghi_viec_ngay_mai
- commands  lệnh Telegram tương ứng, ví dụ /tmrtask (lệnh đầu tiên hiện trong menu của Telegram)
- params    tham số: (tên, kiểu, mô tả, bắt buộc). Kiểu: text | date | pastdate (ngày đã qua, để xem lại)
            | times | energy | onoff | tone | encmode
            | leavepart (am = sáng, pm = chiều, full = cả ngày) | nudgelevel (off | nhe | vua | nghiem)
            | health (on | off | mac_dinh | số phút, cho /break, /water)
            | vdiclient (citrix | winapp | ca_hai | mac_dinh, cho /vdi)
            | clock (giờ HH:MM, nhận cả 8h30, 8 rưỡi, 6 giờ chiều; cho /giobot) | flag (true/false)
- writes    True nếu thao tác ghi/đổi dữ liệu: nhắn tự nhiên thì phải bấm OK xác nhận trước
- confirm   câu xác nhận ("Mình hiểu bạn muốn ...")
- keywords  từ khoá (không dấu) cho bóc tách dự phòng khi AI không dùng được
- run       hàm thực hiện: run(bot, args)
- check     (không bắt buộc) kiểm tra thêm: check(args, cfg) -> câu lỗi hoặc None. validate gọi với cfg=None
            (chỉ xét args); bot gọi lại với cfg thật trước khi hỏi OK / chạy.

Thêm thao tác mới: viết hàm _ten(bot, args) và thêm một Action(...) vào ACTIONS. Bot, menu lệnh,
AI và rule dự phòng tự nhận ra, không phải sửa chỗ nào khác.
"""
import datetime as dt
import re
import sys
import unicodedata
from dataclasses import dataclass, field

from . import absence, ai_client, autostart, energy, messages, pace, persona, prefs
from .analysis import analyze, daily_stats, day_goal_hours, golden_hours, off_day, streak
from .config import DEFAULTS, STOP_AFTER_KEYS, VDI_CLIENT_NAMES, norm_hhmm, run_window_conflict
from .logs import audit, get_logger
from .messages import golden_tip
from .report import late_ot, summary_text, write_report
from .schedule import LEAVE_NAMES
from .storage import append_note, get_note, mark_sent, save_note

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*[:hH.]\s*([0-5]\d)(?!\d)")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


@dataclass
class Action:
    name: str
    commands: list
    title: str
    description: str
    run: object
    params: list = field(default_factory=list)
    writes: bool = False
    confirm: str = ""
    keywords: list = field(default_factory=list)
    # True: không kèm tham số thì chỉ XEM trạng thái (không ghi gì) nên không cần bấm OK.
    view_without_args: bool = False
    check: object = None
    # True: gõ lệnh (/tatapp) cũng phải bấm OK, không chạy ngay (việc không làm lại được từ Telegram).
    confirm_command: bool = False

    def needs_confirm(self, args):
        return self.writes and not (self.view_without_args and not args)

    @property
    def command(self):
        return self.commands[0] if self.commands else ""


# ------------------------------------------------------------ đọc & kiểm tra tham số

def _plain(text):
    """Chữ thường, bỏ dấu tiếng Việt."""
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))


ONOFF = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"), ("tat", "off"), ("off", "off"), ("ngung", "off"), ("bat", "on"), ("mo", "on"), ("on", "on"), ("chay lai", "on")]
TONE_WORDS = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"), ("than mat", "than_mat"), ("than_mat", "than_mat"),
              ("vui tuoi", "vui_tuoi"), ("vui_tuoi", "vui_tuoi"), ("vui", "vui_tuoi"), ("hai huoc", "hai_huoc"),
              ("hai_huoc", "hai_huoc"), ("hai", "hai_huoc"), ("sep_kho_tinh", "sep_kho_tinh"),
              ("kho tinh", "sep_kho_tinh"), ("nghiem", "sep_kho_tinh"), ("lanh lung", "sep_kho_tinh"),
              ("sep", "sep_kho_tinh")]
ENC_WORDS = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"),
             ("tat kinh thanh", "quote"), ("ngung kinh thanh", "quote"), ("bat kinh thanh", "both"),
             ("them kinh thanh", "both"),
             ("khong gui kinh thanh", "quote"), ("dung gui kinh thanh", "quote"), ("khong kinh thanh", "quote"), ("bo kinh thanh", "quote"),
             ("tat", "off"), ("off", "off"), ("ngung", "off"),
             ("chi kinh thanh", "bible"), ("kinh thanh", "bible"), ("bible", "bible"),
             ("ca hai", "both"), ("ca 2", "both"), ("both", "both"), ("tat ca", "both"),
             ("danh ngon", "quote"), ("quote", "quote"), ("chi khich le", "quote"), ("dong luc", "quote"),
             ("bat", "on"), ("mo", "on"), ("on", "on")]
ENC_NAMES = {"on": "BẬT", "off": "TẮT", "quote": "chỉ câu khích lệ / danh ngôn (không Kinh Thánh)",
             "bible": "chỉ câu Kinh Thánh Tin Lành", "both": "cả danh ngôn và Kinh Thánh Tin Lành",
             "default": "theo settings.json"}
# Nghỉ phép: từ dài/rõ nghĩa đứng trước. "nửa ngày" không nói sáng/chiều -> "half" (validate hỏi lại).
LEAVE_WORDS = [("ca ngay", "full"), ("nguyen ngay", "full"), ("full day", "full"), ("full", "full"),
               ("buoi sang", "am"), ("nua ngay sang", "am"), ("sang", "am"), ("morning", "am"), ("am", "am"),
               ("buoi chieu", "pm"), ("nua ngay chieu", "pm"), ("chieu", "pm"), ("afternoon", "pm"), ("pm", "pm"),
               ("nua ngay", "half"), ("half", "half")]
LEAVE_LABEL = {"am": "buổi sáng", "pm": "buổi chiều", "full": "cả ngày"}
# Mức nhắc sao nhãng (/nudge). Cụm dài/rõ nghĩa đứng trước. "nhe" bỏ dấu trùng "nhé" (từ đệm) nên xét riêng
# (xem nudge_lookup). "bat" (bật lại) = "on": về mức trong settings.json (settings.json là off thì về "vua").
NUDGE_WORDS = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"),
               ("1 lan moi ngay", "nhe"), ("mot lan moi ngay", "nhe"), ("1 lan 1 ngay", "nhe"),
               ("mot lan mot ngay", "nhe"), ("1 lan", "nhe"), ("mot lan", "nhe"), ("nhe nhang", "nhe"),
               ("light", "nhe"),
               ("nghiem khac", "nghiem"), ("nghiem", "nghiem"), ("strict", "nghiem"), ("chat che", "nghiem"),
               ("chat", "nghiem"), ("gat", "nghiem"), ("manh tay", "nghiem"),
               ("vua phai", "vua"), ("vua", "vua"), ("binh thuong", "vua"), ("normal", "vua"), ("medium", "vua"),
               ("tat", "off"), ("off", "off"), ("ngung", "off"), ("khong nhac", "off"), ("dung nhac", "off")]
NUDGE_ON = [("bat", "on"), ("mo", "on"), ("on", "on")]


def nudge_lookup(text):
    """Mức nhắc trong câu: "nhắc nghiêm khắc hơn nhé" -> nghiem, "nhắc nhẹ thôi" -> nhe, "tắt nhắc nhở" -> off."""
    v = _word_lookup(NUDGE_WORDS, text)
    if v:
        return v
    plain = _plain(text).strip(" .!")
    if re.search(r"(?<![\wÀ-ỹ])nhẹ(?![\wÀ-ỹ])", (text or "").lower()) or plain in ("nhe", "muc nhe"):
        return "nhe"
    return _word_lookup(NUDGE_ON, text) or ("nhe" if re.search(r"(?<![a-z])nhac nhe(?![a-z])", plain) else None)


VDI_WORDS = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"),
             ("ca hai", "ca_hai"), ("ca_hai", "ca_hai"), ("ca 2", "ca_hai"), ("both", "ca_hai"),
             ("windows app", "winapp"), ("window app", "winapp"), ("win app", "winapp"), ("winapp", "winapp"),
             ("windowsapp", "winapp"), ("azure virtual desktop", "winapp"), ("azure", "winapp"), ("avd", "winapp"),
             ("remote desktop", "winapp"), ("msrdc", "winapp"), ("citrix", "citrix")]


def vdi_lookup(text):
    """App VDI trong câu: "chuyển sang windows app" -> winapp, "đo citrix thôi" -> citrix, "cả hai" -> ca_hai.
    Câu nhắc cả hai app ("từ citrix sang windows app") thì lấy app nhắc SAU CÙNG."""
    plain = _plain(text)
    best = None
    for word, value in VDI_WORDS:
        for m in re.finditer(r"(?<![a-z0-9_])" + re.escape(word) + r"(?![a-z0-9_])", plain):
            if value in ("default", "ca_hai"):
                return value
            if best is None or m.start() > best[0]:
                best = (m.start(), value)
    return best[1] if best else None


def health_lookup(text):
    """/break, /water: "45" / "mỗi 45 phút" -> 45; "tắt" -> off; "bật" -> on; "mac_dinh" -> default."""
    word = _word_lookup(ONOFF, text)
    m = re.search(r"(?<!\d)(\d+)(?!\d)", text or "")
    if m and word != "off":
        return int(m.group(1))
    return word


NUDGE_NAMES = {"off": "TẮT (không nhắc sao nhãng)", "nhe": "nhẹ (1 lần/ngày)", "vua": "vừa (1 lần mỗi lần sao nhãng)",
               "nghiem": "nghiêm khắc (nhắc lặp, đếm số lần)", "default": "theo settings.json",
               "on": "bật lại (theo settings.json)"}
TONE_NAMES = {"than_mat": "thân mật", "vui_tuoi": "vui tươi", "hai_huoc": "hài hước",
              "sep_kho_tinh": "sếp 60 tuổi khó tính, lạnh lùng"}


def _word_lookup(table, text):
    plain = _plain(text)
    best = None  # cụm khớp DÀI nhất thắng ("tất cả" thắng "tắt"); bằng nhau thì theo thứ tự bảng
    for word, value in table:
        if (best is None or len(word) > len(best[0])) and \
                re.search(r"(?<![a-z0-9_])" + re.escape(word) + r"(?![a-z0-9_])", plain):
            best = (word, value)
    return best[1] if best else None


def _fold(text):
    """Bỏ dấu, chữ thường, GIỮ NGUYÊN độ dài (để cắt chuỗi gốc theo vị trí)."""
    out = []
    for ch in text or "":
        base = "d" if ch in "đĐ" else unicodedata.normalize("NFD", ch)[0].lower()
        out.append(base if len(base) == 1 else " ")
    return "".join(out)


def _take_word(table, text):
    """Như _word_lookup nhưng cắt luôn từ đó khỏi câu. Trả (giá trị, phần còn lại) hoặc (None, text)."""
    folded = _fold(text)
    best = None  # từ đứng TRƯỚC nhất trong câu thắng ("chiều ... đưa con đi học sáng" là nghỉ chiều)
    for word, value in table:
        m = re.search(r"(?<![a-z0-9_])" + re.escape(word) + r"(?![a-z0-9_])", folded)
        if m and (best is None or (m.start(), -len(word)) < (best[0].start(), -len(best[1]))):
            best = (m, word, value)
    if not best:
        return None, text
    m, _, value = best
    return value, re.sub(r"\s{2,}", " ", (text[:m.start()] + text[m.end():])).strip()


WEEKDAY_WORDS = {"thu hai": 0, "thu 2": 0, "t2": 0, "thu ba": 1, "thu 3": 1, "t3": 1, "thu tu": 2, "thu 4": 2,
                 "t4": 2, "thu nam": 3, "thu 5": 3, "t5": 3, "thu sau": 4, "thu 6": 4, "t6": 4, "thu bay": 5,
                 "thu 7": 5, "t7": 5, "chu nhat": 6, "cn": 6}
REL_DAYS = [("hom nay", 0), ("ngay mai", 1), ("sang mai", 1), ("ngay kia", 2), ("ngay mot", 2), ("mai", 1)]
MOT_RE = re.compile(r"(?<![^\W\d_])mốt(?![^\W\d_])", re.I)  # "mốt" có dấu = ngày kia ("một" thì không)
DMY_RE = re.compile(r"(?<![\d/.:])(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{4}|\d{2}))?(?![\d/:]|\.\d)")
VN_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*thang\s*(\d{1,2})(?:\s*(?:nam\s*)?(\d{4}))?(?!\d)")
NEXT_WEEK_RE = re.compile(r"(?<![a-z])tuan (?:sau|toi)(?![a-z])")
DATE_LIKE_RE = re.compile(r"(?<![\d:])\d{1,4}\s*[/.-]\s*\d{1,2}(?:\s*[/.-]\s*\d{1,4})?(?![\d:])|\d{1,2}\s*th[aá]ng\s*\d{1,2}",
                          re.I)


def parse_day(text, today=None):
    """Tìm ngày trong câu: 2026-10-20, 20/10(/2026), hôm nay, mai, ngày kia/mốt, thứ 6, chủ nhật...
    Thứ trong tuần = lần tới gần nhất (hôm nay là thứ đó thì lấy hôm nay). Trả (ngày ISO, phần còn lại) hoặc (None, text)."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else (today or dt.date.today())
    m = DATE_RE.search(text or "")
    if m:
        return m.group(1), (text[:m.start()] + text[m.end():]).strip()
    folded = _plain(text)  # cùng độ dài với text (bỏ dấu không đổi số ký tự với tiếng Việt dựng sẵn)
    if len(folded) != len(text or ""):
        folded = None
    for regex, src in ((DMY_RE, text or ""), (VN_DATE_RE, folded or "")):  # 20/10, 24.12.26, 20 tháng 10
        m = regex.search(src)
        if not m:
            continue
        try:
            year = m.group(3)
            year = int(year) + (2000 if year and len(year) == 2 else 0) if year else today.year
            day = dt.date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if not m.group(3) and day < today - dt.timedelta(days=180):  # "05/01" gõ vào tháng 12 = năm sau
            day = day.replace(year=day.year + 1)
        return day.isoformat(), (text[:m.start()] + text[m.end():]).strip()
    m = MOT_RE.search(text or "")
    if m:
        return (today + dt.timedelta(days=2)).isoformat(), (text[:m.start()] + text[m.end():]).strip()
    plain = folded or _plain(text)
    next_week = NEXT_WEEK_RE.search(plain)
    for table in (WEEKDAY_WORDS.items(), REL_DAYS):
        for word, val in table:
            m = re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", folded or _plain(text))
            if not m:
                continue
            if table is REL_DAYS:
                day = today + dt.timedelta(days=val)
            elif next_week:  # "thứ 6 tuần sau" = thứ 6 của tuần kế tiếp
                day = today - dt.timedelta(days=today.weekday()) + dt.timedelta(days=7 + val)
            else:
                day = today + dt.timedelta(days=(val - today.weekday()) % 7)
            rest = (text[:m.start()] + text[m.end():]).strip() if folded is not None else text
            if next_week and table is not REL_DAYS and folded is not None:
                rest = re.sub(r"(?i)\s*tu[aầ]n\s+(sau|t[oớ]i)\b", "", rest).strip()
            rest = re.sub(r"^(ngay|ngày|vào|vao)\s+|\s+(ngay|ngày|này|nay|vào|vao)$", "", rest, flags=re.I).strip()
            return day.isoformat(), rest
    return None, text


PAST_DAYS = [("hom qua", 1), ("hom kia", 2)]


def _year_back(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29/02 -> 28/02 năm trước
        return d.replace(year=d.year - 1, day=28)


def _yearless_date(text, plain):
    """Ngày gõ dạng 14/10 hay 14 tháng 10, KHÔNG ghi năm."""
    if DATE_RE.search(text or ""):
        return False
    m = DMY_RE.search(text or "") or VN_DATE_RE.search(plain)
    return bool(m) and not m.group(3)


def parse_past_day(text, today=None):
    """Như parse_day nhưng để XEM LẠI ngày đã qua: hôm qua, hôm kia; "thứ 2" = thứ 2 gần nhất đã qua (hôm nay là
    thứ 2 thì lấy hôm nay); "14/10" chưa tới thì là năm trước. "mai" hay ngày ghi rõ năm mà chưa tới: giữ nguyên,
    nơi dùng báo "chưa tới". Trả (ngày ISO, phần còn lại) hoặc (None, text)."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else (today or dt.date.today())
    plain = _plain(text)
    for word, back in PAST_DAYS:
        m = re.search(r"(?<![a-z0-9])" + word + r"(?![a-z0-9])", plain)
        if m:
            rest = (text[:m.start()] + text[m.end():]).strip() if len(plain) == len(text or "") else text
            return (today - dt.timedelta(days=back)).isoformat(), rest
    day, rest = parse_day(text, today)
    if not day or day <= today.isoformat():
        return day, rest
    d = dt.date.fromisoformat(day)
    if any(re.search(r"(?<![a-z0-9])" + w + r"(?![a-z0-9])", plain) for w in WEEKDAY_WORDS):
        d -= dt.timedelta(days=7)
    elif _yearless_date(text, plain):
        while d > today:
            d = _year_back(d)
    return d.isoformat(), rest


def example(action):
    """Ví dụ lệnh đúng theo kiểu tham số, để báo khi gõ sai."""
    samples = {"times": "08:10 17:35", "energy": "4", "date": "mai", "pastdate": "hôm qua", "onoff": "on", "tone": "vui_tuoi",
               "encmode": "quote", "text": "nội dung", "leavepart": "chieu", "nudgelevel": "nghiem",
               "vdiclient": "winapp", "health": "45", "clock": "08:30 18:00"}
    kinds = [p[1] for p in action.params]
    return f"{action.command} " + " ".join(samples.get(k, "") for k in kinds[:1]) if kinds else action.command


def parse_times(text):
    return [f"{int(h):02d}:{m}" for h, m in TIME_RE.findall(text or "")]


def parse_command_args(action, text, today=None):
    """Chuỗi sau lệnh (/as400 08:10 17:35) -> dict tham số theo khai báo params."""
    text = (text or "").strip()
    args = {}
    for name, kind, _, _ in action.params:
        if kind == "times":
            t = parse_times(text)
            if t:
                args["start"] = t[0]
                if len(t) > 1:
                    args["end"] = t[1]
        elif kind in ("date", "pastdate"):
            day, text = (parse_past_day if kind == "pastdate" else parse_day)(text, today)
            if day:
                args[name] = day
            else:
                m = DATE_LIKE_RE.search(text)
                if m:  # có dạng ngày mà không đọc được: báo lỗi, KHÔNG lặng lẽ lấy hôm nay
                    args[name] = m.group(0)
        elif kind == "leavepart":
            part, text = _take_word(LEAVE_WORDS, text)
            if part:
                args[name] = part
            # bỏ chữ thừa quanh ngày/buổi ("nay", "nghỉ phép"...) để phần còn lại là lý do
            text = re.sub(r"^(?:(?:xin|nghỉ|nghi|phép|phep|nay|này|hôm|hom|ngày|ngay|nửa|nua|buổi|buoi|mình|minh|"
                          r"em|tôi|toi)\s+)+", "", text + " ", flags=re.I).strip()
        elif kind == "energy":
            m = re.search(r"(?<!\d)\d+(?!\d)", text)
            if m:
                args[name] = int(m.group(0))
        elif kind == "onoff" and text:
            args[name] = _word_lookup(ONOFF, text) or text  # không nhận ra -> validate báo lỗi
        elif kind == "encmode" and text:
            args[name] = _word_lookup(ENC_WORDS, text) or text
        elif kind == "tone" and text:
            args[name] = _word_lookup(TONE_WORDS, text) or text  # không nhận ra -> validate báo lỗi
        elif kind == "nudgelevel" and text:
            args[name] = nudge_lookup(text) or text
        elif kind == "vdiclient" and text:
            args[name] = vdi_lookup(text) or text
        elif kind == "health" and text:
            args[name] = health_lookup(text) or text
        elif kind == "clock" and text and name == action.params[0][0]:  # cả cụm giờ bật/tắt đọc một lần
            args.update(parse_bot_hours(text))
        elif kind == "text" and text:
            args[name] = text
    return args


def validate(action, args):
    """Chuẩn hoá args. Trả (args, lỗi) — lỗi là câu tiếng Việt hoặc None."""
    clean = {}
    for name, kind, desc, required in action.params:
        if kind == "times":
            for key in ("start", "end"):
                v = args.get(key)
                if v:
                    t = parse_times(str(v))
                    if not t:
                        return None, f"Giờ \"{v}\" không đúng dạng HH:MM."
                    clean[key] = t[0]
            if required and "start" not in clean:
                return None, "Cần giờ vào AS400, ví dụ 08:10 17:35."
            if "start" in clean and "end" in clean and clean["end"] < clean["start"]:
                return None, "Giờ ra AS400 đang sớm hơn giờ vào."
            continue
        v = args.get(name)
        if isinstance(v, str):
            v = v.strip()
        if v in (None, ""):
            if required:
                return None, f"Thiếu {desc}."
            continue
        if kind == "onoff":
            v = _word_lookup(ONOFF, str(v)) or (str(v) if str(v) in ("on", "off", "default") else None)
            if not v:
                return None, "Chọn on (bật) hoặc off (tắt)."
            clean[name] = v
        elif kind == "encmode":
            v = str(v) if str(v) in ENC_NAMES else _word_lookup(ENC_WORDS, str(v))
            if not v:
                return None, "Chọn một trong: on, off, quote (chỉ khích lệ), bible (chỉ Kinh Thánh), both."
            clean[name] = v
        elif kind == "tone":
            v = str(v) if str(v) in TONE_NAMES or str(v) == "default" else _word_lookup(TONE_WORDS, str(v))
            if not v:
                return None, "Giọng là một trong: " + ", ".join(TONE_NAMES) + "."
            clean[name] = v
        elif kind == "health":
            v = health_lookup(str(v)) if not isinstance(v, int) or isinstance(v, bool) else v
            if v is None:
                return None, "Chọn on (bật), off (tắt) hoặc số phút, ví dụ 45."
            if isinstance(v, int) and not 5 <= v <= 240:
                return None, "Số phút từ 5 đến 240."
            clean[name] = v
        elif kind == "nudgelevel":
            v = str(v) if str(v) in NUDGE_NAMES else nudge_lookup(str(v))
            if not v:
                return None, "Mức nhắc là một trong: off (tắt), nhe (1 lần/ngày), vua, nghiem (hoặc mac_dinh)."
            clean[name] = v
        elif kind == "vdiclient":
            v = str(v) if str(v) in VDI_CLIENT_NAMES or str(v) == "default" else vdi_lookup(str(v))
            if not v:
                return None, "Chọn một trong: citrix, winapp (Windows App), ca_hai (hoặc mac_dinh)."
            clean[name] = v
        elif kind in ("date", "pastdate"):
            try:
                clean[name] = dt.date.fromisoformat(str(v)).isoformat()
            except ValueError:
                return None, (f"Mình chưa đọc được ngày «{v}». Gõ dạng 24/12, 24/12/2026, 2026-12-24, "
                              "mai, thứ 6, thứ 6 tuần sau.")
        elif kind == "leavepart":
            v = str(v) if str(v) in LEAVE_LABEL else _word_lookup(LEAVE_WORDS, str(v))
            if v == "half":
                return None, "Nghỉ nửa ngày buổi sáng hay buổi chiều? Ví dụ: /leave sang hoặc /leave chieu."
            if not v:
                return None, "Chọn sang (buổi sáng), chieu (buổi chiều) hoặc ca_ngay (cả ngày)."
            clean[name] = v
        elif kind == "energy":
            try:
                n = int(v)
            except (TypeError, ValueError):
                return None, "Năng lượng là một số từ 1 đến 5."
            if not 1 <= n <= 5:
                return None, "Năng lượng là một số từ 1 đến 5."
            clean[name] = n
        elif kind == "clock":
            t = norm_hhmm(str(v)) or norm_hhmm(next((x for _, x in _scan_clock(str(v))), ""))
            if not t:
                return None, f"Giờ \"{v}\" không đúng dạng HH:MM (ví dụ 08:30, 18:00)."
            clean[name] = t
        elif kind == "flag":
            if v is True or _plain(str(v)).strip() in ("true", "1", "yes", "co", "mac dinh", "mac_dinh", "default",
                                                       "reset"):
                clean[name] = True
        else:
            clean[name] = str(v).strip()[:2000]
    if action.check:
        error = action.check(clean, None)
        if error:
            return None, error
    return clean, None


ARG_LABELS = {"start": "giờ vào / giờ bật", "end": "giờ ra", "text": "nội dung", "day": "ngày", "reason": "lý do",
              "part": "buổi nghỉ", "state": "trạng thái", "mode": "kiểu", "level": "mức", "tone": "giọng văn",
              "every": "nhắc", "energy": "năng lượng", "stop": "giờ tắt", "time": "giờ", "reset": "về mặc định",
              "mo_ta": "bot sẽ làm"}
SOURCE_NAMES = {"ai": "AI bóc tách", "rule": "từ khoá (AI không dùng được)"}


def _arg_label(action, key):
    """Nhãn ngắn của tham số: lấy từ khai báo params, bỏ phần giải thích dài."""
    for name, kind, desc, _ in action.params:
        if name == key:
            label = re.split(r"[:(]", desc.replace("HH:MM", ""), 1)[0].strip()
            return label or ARG_LABELS.get(key, key)
    return ARG_LABELS.get(key, key)


def _display(action, args):
    """Giá trị tham số dạng dễ đọc (BẬT/TẮT, tên mức nhắc...), dùng cho câu xác nhận."""
    vals = {k: v for k, v in args.items()}
    if "state" in vals:
        vals["state"] = {"on": "BẬT", "off": "TẮT", "default": "theo settings.json"}.get(vals["state"], vals["state"])
    if "mode" in vals:
        vals["mode"] = ENC_NAMES.get(vals["mode"], vals["mode"])
    if "every" in vals:
        v = vals["every"]
        vals["every"] = f"BẬT, mỗi {v} phút" if isinstance(v, int) else {"on": "BẬT", "off": "TẮT",
                                                                           "default": "theo settings.json"}.get(v, v)
    if "level" in vals:
        vals["level"] = NUDGE_NAMES.get(vals["level"], vals["level"])
    if "client" in vals:
        vals["client"] = VDI_CLIENT_NAMES.get(vals["client"], "theo settings.json")
    if "tone" in vals:
        vals["tone"] = TONE_NAMES.get(vals["tone"], "theo persona.json")
    if "reset" in vals:
        vals["reset"] = "có" if vals["reset"] else "không"
    return vals


def describe(action, args, today=None):
    """Câu xác nhận đầy đủ, điền tham số. today: ngày của tin nhắn (tin gửi muộn thuộc ngày gửi)."""
    vals = _display(action, args)
    if action.name == "gio_bot":
        vals["hours"] = hours_phrase(args)
    if action.name == "hoi_ai" and ask_toggle(args.get("text")):
        return {"on": "BẬT", "off": "TẮT"}.get(ask_toggle(args.get("text")), "Về mặc định") + " chế độ hỏi AI"
    vals["part"] = LEAVE_LABEL.get(vals.get("part") or "full", vals.get("part"))
    for k in ("text", "reason"):  # chữ người dùng gõ: không đổi xưng hô ("bạn Lan" giữ nguyên)
        if vals.get(k):
            vals[k] = persona.keep(vals[k])
    vals["note"] = f" ({vals['reason']})" if vals.get("reason") else ""
    vals.setdefault("day", today or dt.date.today().isoformat())
    vals.setdefault("end", "?")
    vals.setdefault("reason", "nghỉ")
    try:
        return action.confirm.format(**vals)
    except (KeyError, IndexError):
        return action.title


def detail_lines(action, args, today=None):
    """Từng tham số đã bóc tách, một dòng mỗi tham số, để người dùng soát lại."""
    vals = _display(action, args)
    for k in ("text", "reason"):
        if vals.get(k):
            vals[k] = persona.keep(_short_val(vals[k]))
    if "part" in vals:
        vals["part"] = LEAVE_LABEL.get(vals["part"], vals["part"])
    lines = [f"   - {_arg_label(action, k)}: {_short_val(vals[k])}" for k in args]
    for name, kind, _, _ in action.params:  # tham số ngày bỏ trống = hôm nay: ghi rõ để khỏi hiểu nhầm
        if kind in ("date", "pastdate") and name not in args:
            lines.append(f"   - {_arg_label(action, name)}: hôm nay {today or dt.date.today().isoformat()} (mặc định)")
    return lines


def _short_val(v, cap=300):
    v = str(v).replace("\n", " / ")
    return v if len(v) <= cap else v[:cap] + "…"


def confirm_card(action, args, original=None, source=None, warning=None, today=None):
    """Thẻ xác nhận: bot hiểu thành action nào, tham số gì, từ câu nào, để người dùng bấm OK trước khi làm."""
    lines = [f"🤖 Mình hiểu bạn muốn: {describe(action, args, today)}",
             f"• Hành động: {action.name} ({action.title}" + (f", lệnh {action.command}" if action.command else "") + ")"]
    details = detail_lines(action, args, today)
    if details:
        lines.append("• Chi tiết đã bóc tách:")
        lines += details
    if original:
        lines.append(f"• Tin bạn nhắn: «{persona.keep(_short_val(original, 200))}»")
    if source in SOURCE_NAMES:
        lines.append(f"• Cách hiểu: {SOURCE_NAMES[source]}")
    if warning:
        lines.append(f"⚠️ {warning}")
    lines.append("Đúng ý bạn chưa? Bấm ✅ OK để thực hiện, ✏️ Sửa lại nếu mình hiểu sai, ❌ Huỷ nếu không làm nữa.")
    return "\n".join(lines)


def understood_line(action, args):
    """Một dòng cho action chỉ xem (không ghi gì nên chạy luôn): vẫn cho người dùng thấy bot hiểu thành gì."""
    extra = "; ".join(l.strip(" -") for l in detail_lines(action, args) if "mặc định" not in l)
    return (f"🔎 Mình hiểu là: {action.title} ({action.name}" + (f", lệnh {action.command}" if action.command else "")
            + ")" + (f": {extra}" if extra else ""))


# ------------------------------------------------------------ thực hiện

def _past_day(bot, args, cmd):
    """Ngày muốn xem (mặc định hôm nay). Ngày chưa tới: báo và trả None."""
    day = args.get("day") or bot.today()
    if day > bot.today():
        bot.send(f"Ngày {day} chưa tới nên chưa có gì để xem. Ví dụ: {cmd} hôm qua, {cmd} thứ 2, {cmd} 14/10.")
        return None
    return day


def _today(bot, args):
    day = _past_day(bot, args, "/today")
    if day:
        bot.send(summary_text(analyze(bot.db, bot.cfg, day), get_note(bot.db, day), streak(bot.db, bot.cfg, day),
                              late_ot(bot.db, bot.cfg, day), ot_deep=True))


def _vang(bot, args):
    """/vang: lần vắng gần nhất + các lần vắng từ 5 phút trong ngày (chỉ đọc số liệu có sẵn)."""
    day = _past_day(bot, args, "/vang")
    if day:
        bot.send(absence.view_text(analyze(bot.db, bot.cfg, day), bot.cfg, getattr(bot, "state", None), day=day))


def _report(bot, args):
    day = _past_day(bot, args, "/report")
    if day:
        path, _ = write_report(bot.db, bot.cfg, day)
        bot.send_file(path, f"Báo cáo {day}")


def _week(bot, args):
    bot.send_weekly(bot.today())


def _golden(bot, args):
    bot.send(golden_tip(golden_hours(bot.db, bot.cfg, bot.today()))
             or "Chưa đủ số liệu (cần ít nhất 5 ngày làm việc) để tìm giờ vàng.")


def _status(bot, args):
    bot.send(bot.status_text())


def _hook(bot, field_name, text):
    """Cùng ghi vào danh sách việc (/viec). Bot giả trong test không có hàm này thì thôi."""
    fn = getattr(bot, "task_note_hook", None)
    return fn(field_name, text) if fn else ""


def _plan(bot, args):
    if args.get("text"):
        save_note(bot.db, bot.today(), {"plan": args["text"]})
        audit("PLAN_SAVED", args["text"])
        extra = _hook(bot, "plan", args["text"])
        bot.send("Đã lưu kế hoạch hôm nay. Bắt đầu với việc số 1 nhé." + (f"\n{extra}" if extra else ""))
    else:
        bot.start_convo("plan", manual=True)


def _note_line(field_name, label):
    def run(bot, args):
        append_note(bot.db, bot.today(), field_name, f"- {args['text']} ({dt.datetime.now():%H:%M})")
        audit("NOTE_" + field_name.upper(), args["text"])
        extra = _hook(bot, field_name, args["text"]) if field_name in ("issues", "output") else ""
        bot.send(f"Đã ghi {label}." + (f"\n{extra}" if extra else ""))
    return run


def _tomorrow(bot, args):
    save_note(bot.db, bot.today(), {"tomorrow": args["text"]})
    audit("TOMORROW_SAVED", args["text"])
    extra = _hook(bot, "tomorrow", args["text"])
    bot.send("Đã ghi. Sáng mai mình nhắc việc này đầu tiên." + (f"\n{extra}" if extra else ""))


def _energy(bot, args):
    save_note(bot.db, bot.today(), {"energy": args["energy"]})
    bot.send(f"Đã ghi năng lượng hôm nay: {args['energy']}/5.")


def _as400(bot, args):
    save_note(bot.db, bot.today(), {"as400_start": args["start"], "as400_end": args.get("end")})
    audit("AS400_TIMES", f"{args['start']}-{args.get('end')}")
    bot.send(f"Đã ghi giờ AS400: {args['start']} – {args.get('end') or '?'}.")


def _review(bot, args):
    bot.start_convo("review", manual=True)


def _poke(bot):
    """Báo tracker (đang chạy cùng tiến trình) đọc lại ngày nghỉ / nghỉ phép ngay ở vòng kế tiếp."""
    ev = (getattr(bot, "state", None) or {}).get("recheck")
    if ev is not None:
        ev.set()


def _off(bot, args):
    day = args.get("day") or bot.today()
    reason = args.get("reason") or "nghỉ"
    save_note(bot.db, day, {"day_off": reason, "leave_part": None})
    audit("DAY_OFF", f"{day} {reason}")
    _poke(bot)
    today = day == dt.date.today().isoformat()
    bot.send(f"Đã ghi {day} là ngày nghỉ ({reason}), mình không nhắc gì ngày đó"
             + (", tắt theo dõi luôn" if today else "") + f". Đổi ý thì gõ /on {day}")


def _on(bot, args):
    day = args.get("day") or bot.today()
    had = get_note(bot.db, day)
    save_note(bot.db, day, {"day_off": None, "leave_part": None})
    audit("DAY_ON", day)
    _poke(bot)
    reason = off_day(bot.db, bot.cfg, day)
    cancelled = ("Đã huỷ " + (LEAVE_NAMES.get(had.get("leave_part")) or f"ngày nghỉ ({had.get('day_off')})") + ". "
                 if had.get("day_off") or had.get("leave_part") else "")
    bot.send(f"{cancelled}{day} là ngày làm việc, mình nhắc như bình thường."
             + (f" (Lưu ý: {day} là {reason}, tracker không tự chạy ngày này.)" if reason else ""))


def _leave(bot, args):
    """Nghỉ phép: cả ngày = như /off; nửa ngày = không theo dõi buổi đó, mục tiêu còn một nửa."""
    day = args.get("day") or bot.today()
    part = args.get("part") or "full"
    reason = args.get("reason") or ""
    if part == "full":
        _off(bot, {"day": day, "reason": reason or "nghỉ phép"})
        return
    cfg = bot.cfg
    save_note(bot.db, day, {"leave_part": part, "day_off": None})
    audit("LEAVE", f"{day} {part} {reason}".strip())
    today = day == dt.date.today().isoformat()
    if today:
        mark_sent(bot.db, day, "leave_notice")  # tracker không báo lại lần nữa
    elif day < dt.date.today().isoformat():
        daily_stats(bot.db, cfg, day, refresh=True)  # báo nghỉ cho ngày đã qua: tính lại số liệu ngày đó
    _poke(bot)
    half = day_goal_hours(cfg, part)
    if part == "am":
        detail = (f"không theo dõi tới {cfg['lunch_end']}; chào + hỏi kế hoạch khi bạn bắt đầu buổi chiều")
    else:
        detail = (f"không theo dõi từ {cfg['lunch_start']}; tổng kết ngày gửi lúc {cfg['lunch_start']}")
    reason_txt = f" ({reason})" if reason else ""
    bot.send(f"Đã ghi {day}: {LEAVE_NAMES[part]}{reason_txt}. {detail[0].upper() + detail[1:]}. "
             f"Mục tiêu ngày đó còn {half:g}h. Huỷ: /on {day}")


def _pause(bot, args):
    bot.state["paused"].set()
    audit("PAUSE")
    bot.send("Đã tạm dừng theo dõi. Gõ /resume khi quay lại.")


def _resume(bot, args):
    bot.state["paused"].clear()
    audit("RESUME")
    bot.send(bot.persona_text("Theo dõi lại rồi. ") + bot.encourage("vừa quay lại làm việc sau giờ nghỉ"), raw=True)


def _quote(bot, args):
    bot.send(bot.encourage(f"người dùng xin một câu truyền động lực; {bot.stats_line()}", "motivation"), raw=True)


def _bible(bot, args):
    bot.send(bot.encourage(f"người dùng xin một câu Kinh Thánh khích lệ; {bot.stats_line()}", "bible"), raw=True)


def _chat(bot, args):
    text = args.get("text") or ""
    bot.send(bot.encourage(f"người dùng vừa nhắn: \"{text[:300]}\"; {bot.stats_line()}"), raw=True)


def _aistatus(bot, args):
    bot.send(ai_client.status_text(bot.cfg))


def _clearcache(bot, args):
    with bot.db:
        n = bot.db.execute("DELETE FROM ai_cache").rowcount
    ai_client.clear_cache(bot.cfg)
    audit("CLEAR_CACHE", n)
    bot.send(f"Đã xoá cache model AI và {n} nhận xét đã lưu. Lần gọi sau sẽ dò model lại từ đầu.")


def _perf(bot, args):
    bot.send(bot.state.get("perf") or "Chưa đo xong, đợi 10 phút sau khi tracker chạy.")


def _cancel(bot, args):
    had = bot.cancel_pending()
    bot.send("Đã huỷ." if had else "Không có gì đang chờ để huỷ.")


def _aireview(bot, args):
    state = args.get("state")
    if state == "default":
        prefs.set_pref(bot.db, "ai_review_enabled", None)
        bot.cfg["ai_review_enabled"] = bool(bot.cfg.get("_file_ai_review_enabled", True))
    elif state:
        prefs.set_ai_review(bot.cfg, bot.db, state == "on")
    on = bot.cfg.get("ai_review_enabled", True)
    if state:
        audit("AI_REVIEW", "on" if on else "off")
    msg = (f"AI tự đánh giá cuối ngày ({bot.cfg['daily_summary_at']}) và cuối tuần: {'ĐANG BẬT' if on else 'ĐANG TẮT'}.")
    if on and not ai_client.provider(bot.cfg):
        msg += " Nhưng chưa có API key AI nên chưa có đánh giá AI, bot chỉ gửi số liệu (xem README phần AI)."
    if not on:
        msg += " Bot vẫn gửi số liệu và lời chúc cuối ngày, không gọi AI."
    bot.send(msg + "\nĐổi: /aireview on hoặc /aireview off")


def _style(bot, args):
    tone = args.get("tone")
    if tone == "default":
        prefs.set_pref(bot.db, "giong", None)
        bot.cfg["persona"] = dict(bot.cfg["persona"], giong=bot.cfg.get("_file_tone") or "than_mat")
    elif tone:
        prefs.set_tone(bot.cfg, bot.db, tone)
    cur = bot.cfg["persona"]["giong"]
    if tone:
        audit("STYLE", cur)
        bot.send(bot.persona_text(f"Đã đổi giọng: {TONE_NAMES[cur]}. ")
                 + bot.encourage("người dùng vừa đổi giọng văn của bot, chào một câu bằng giọng mới"), raw=True)
        return
    bot.send(f"Giọng hiện tại: {TONE_NAMES[cur]}.\nĐổi: " + ", ".join(f"/style {k}" for k in TONE_NAMES)
             + "\n(/style mac_dinh để quay về persona.json)")


STYLE_LABEL = {"motivation": "danh ngôn", "family": "vì gia đình", "bible": "Kinh Thánh Tin Lành"}


def _encourage(bot, args):
    mode = args.get("mode")
    if mode:
        prefs.set_encouragement(bot.cfg, bot.db, mode)
        audit("ENCOURAGE", mode)
    on = bot.cfg.get("encouragement_enabled", True)
    kinds = ", ".join(STYLE_LABEL.get(x, x) for x in bot.cfg.get("encouragement_styles") or [])
    bot.send(f"Tự gửi lời khích lệ (đầu ngày, buổi chiều {bot.cfg['afternoon_boost_at'] or 'tắt'}, kèm cảnh báo): "
             f"{'ĐANG BẬT' if on else 'ĐANG TẮT'}.\nLoại câu: {kinds}.\n"
             "Đổi: /encourage on | off | quote (không Kinh Thánh) | bible (chỉ Kinh Thánh) | both")


def _kinhthanh(bot, args):
    """Nút gạt Kinh Thánh của lời khích lệ: on = chỉ Kinh Thánh, off = danh ngôn (không Kinh Thánh, mặc định khi cài lần đầu).
    Không kèm gì: đảo trạng thái hiện tại."""
    state = args.get("state")
    if state == "default":
        prefs.set_encouragement(bot.cfg, bot.db, "default")
    else:
        if state not in ("on", "off"):
            state = "off" if "bible" in (bot.cfg.get("encouragement_styles") or []) else "on"
        prefs.set_encouragement(bot.cfg, bot.db, "bible" if state == "on" else "quote")
    audit("KINH_THANH", state)
    on = "bible" in (bot.cfg.get("encouragement_styles") or [])
    bot.send(("📖 Kinh Thánh: BẬT. Lời chào buổi sáng và lời khích lệ dùng câu Kinh Thánh Tin Lành."
              if on else "💬 Kinh Thánh: TẮT. Lời chào buổi sáng, lời khích lệ, nhắc nhở và đánh giá AI chỉ dùng châm ngôn "
              "của người thành đạt, danh nhân xưa; không tin nào dùng Kinh Thánh (trừ khi bạn tự xin /bible).")
             + "\nGõ /kinhthanh lần nữa để đổi lại.")


def ask_toggle(text):
    """Chỉ bật/tắt khi CẢ nội dung là một từ bật/tắt ("on", "tắt", "bật chế độ"...); "mơ thấy rắn" là câu hỏi.
    Trả "on" / "off" / "default" hoặc None."""
    plain = _plain(text or "").strip(" .!")
    word = dict(ONOFF).get(plain)
    if word is None and re.fullmatch(r"(bat|tat|mo|on|off)( che do( hoi ai)?)?", plain):
        word = _word_lookup(ONOFF, text)
    return word if word in ("on", "off", "default") else None


def _ask(bot, args):
    text = (args.get("text") or "").strip()
    word = ask_toggle(text)
    if word:
        prefs.set_ask_mode(bot.cfg, bot.db, word == "on")
        audit("ASK_MODE", word)
        if word == "on":
            bot.send("Đã BẬT chế độ hỏi AI. Từ giờ mọi tin nhắn thường (không phải lệnh) sẽ được gửi cho AI trả lời. "
                     "Mỗi câu hỏi là độc lập (AI không nhớ câu trước), nên hỏi đủ ý trong một tin.\n"
                     "Lệnh /... vẫn dùng bình thường. Tắt: /ask off")
        else:
            bot.send("Đã TẮT chế độ hỏi AI. Tin nhắn thường lại được hiểu thành thao tác (ghi issue, việc mai...). "
                     "Hỏi nhanh 1 câu: /ask câu hỏi")
        return
    if text:
        bot.answer_question(text)
        return
    bot.send(f"Chế độ hỏi AI: {'ĐANG BẬT' if bot.ask_mode() else 'ĐANG TẮT'}.\n"
             "/ask on: mọi tin nhắn thường gửi cho AI · /ask off: tắt · /ask câu hỏi: hỏi nhanh 1 câu")


NUDGE_HELP = {
    "off": "không nhắc khi sao nhãng (ngoài VDI, điện thoại, VDI không toàn màn hình); vẫn nhắc nghỉ giải lao, "
           "rời máy và cảnh báo tiến độ",
    "nhe": "chỉ 1 lần/ngày: lần đầu ra ngoài VDI (hoặc thu nhỏ VDI) quá {light} phút; sau đó im cả ngày",
    "vua": "mỗi lần sao nhãng quá {mid} phút nhắc 1 lần (giờ vàng: {gold} phút), không nhắc lặp",
    "nghiem": "nhắc sau {strict} phút, còn ở ngoài thì {strict} phút nhắc lại, kèm số lần sao nhãng + tổng phút mất "
              "hôm nay, giọng gắt hơn",
}


def nudge_desc(cfg, level=None):
    level = level or cfg.get("nudge_level", "vua")
    return NUDGE_HELP[level].format(light=cfg["nudge_light_minutes"], mid=cfg["nudge_out_of_vdi_minutes"],
                                    gold=cfg["golden_nudge_minutes"] or cfg["nudge_out_of_vdi_minutes"],
                                    strict=cfg["nudge_strict_minutes"])


def _nudge(bot, args):
    level = args.get("level")
    cfg = bot.cfg
    if level == "on":
        file_level = cfg.get("_file_nudge_level") or "vua"
        level = "default" if file_level != "off" else "vua"
    if level:
        prefs.set_nudge_level(cfg, bot.db, level)
        audit("NUDGE_LEVEL", cfg["nudge_level"])
    cur = cfg.get("nudge_level", "vua")
    lines = [f"{'Đã đổi' if level else 'Đang dùng'} mức nhắc khi sao nhãng: {NUDGE_NAMES[cur]}.",
             nudge_desc(cfg)[0].upper() + nudge_desc(cfg)[1:] + "."]
    al = (getattr(bot, "state", None) or {}).get("alerts")
    if al is not None and not level:
        t = al.today()
        lines.append(f"Hôm nay: {t['count']} lần sao nhãng (≥ 1 phút), mất {t['minutes']} phút, đã nhắc {t['nudges']} lần.")
    if not level:
        lines += ["", "4 mức:"] + [f"/nudge {k} — {nudge_desc(cfg, k)}" for k in NUDGE_HELP]
        lines.append("/nudge mac_dinh — quay về settings.json. Câu nhắc theo giọng /style đang dùng.")
    bot.send("\n".join(lines))


def _vdi(bot, args):
    client = args.get("client")
    cfg = bot.cfg
    if client:
        prefs.set_vdi_client(cfg, bot.db, client)
        audit("VDI_CLIENT", cfg["vdi_client"])
    cur = cfg.get("vdi_client", "ca_hai")
    lines = [f"{'Đã đổi' if client else 'Đang đo'} VDI mở bằng: {VDI_CLIENT_NAMES[cur]}."]
    if client:
        lines.append("Có hiệu lực ngay, không cần khởi động lại. Cửa sổ của app còn lại từ giờ tính là ngoài VDI.")
    else:
        lines += ["", "/vdi citrix — chỉ đo cửa sổ Citrix (Desktop Viewer)",
                  "/vdi winapp — chỉ đo Windows App / Remote Desktop (Azure Virtual Desktop)",
                  "/vdi ca_hai — app nào cũng đo", "/vdi mac_dinh — quay về settings.json"]
    bot.send("\n".join(lines))


def _pace(bot, args):
    state = args.get("state")
    cfg = bot.cfg
    if state:
        prefs.set_pace_check(cfg, bot.db, state)
        audit("PACE_CHECK", "on" if cfg["pace_check_enabled"] else "off")
        bot.send(f"Cảnh báo tiến độ tự động: {'ĐANG BẬT' if cfg['pace_check_enabled'] else 'ĐANG TẮT'} (mốc "
                 + ", ".join(cfg["pace_checkpoints"]) + "). Xem tiến độ lúc này: /pace")
        return
    day = bot.today()
    info = None
    if not off_day(bot.db, cfg, day):
        info = pace.today_status(bot.db, cfg, day, dt.datetime.now().strftime("%H:%M"))
    bot.send(messages.pace_view(info, cfg.get("pace_check_enabled", True), cfg["pace_checkpoints"]))


TASK_SWITCH = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"), ("tat", "off"),
               ("off", "off"), ("bat", "on"), ("on", "on")]


def _switch_word(text):
    """"on" | "off" | "default" khi CẢ tin chỉ là chữ bật/tắt (để «bỏ 2» không bị hiểu là tắt)."""
    plain = _plain(text).strip(" .!")
    return next((v for w, v in TASK_SWITCH if plain == w), None)


def _viec_check(args, cfg):
    """Kiểm cú pháp trước khi hỏi OK / chạy; ghi mo_ta (bot sẽ làm gì) lên thẻ xác nhận."""
    from . import tasks  # import trễ: tasks -> intent -> actions
    text = (args.get("text") or "").strip()
    if not text:
        return None
    state = _switch_word(text)
    if state:
        args["mo_ta"] = {"on": "BẬT", "off": "TẮT", "default": "theo settings.json"}[state] + \
            " gửi danh sách việc + hỏi cập nhật (đầu ngày và các mốc " + ", ".join((cfg or DEFAULTS).get("task_checkins") or []) + ")"
        return None
    try:
        ops = tasks.parse(text)
    except tasks.TaskError as e:
        return str(e)
    if not ops:  # chữ không phải cú pháp ("danh sách việc hôm nay" -> text "hôm nay"): chỉ xem danh sách
        args.pop("text", None)
        return None
    args["mo_ta"] = tasks.describe(ops)
    return None


def _viec(bot, args):
    from . import tasks
    text = (args.get("text") or "").strip()
    if not text:
        bot.send(tasks.list_text(bot.db, bot.tasks_ready()))
        return
    state = _switch_word(text)
    if state:
        prefs.set_switch(bot.cfg, bot.db, "task_checkin_enabled", state)
        on = bot.cfg["task_checkin_enabled"]
        audit("TASK_CHECKIN", "on" if on else "off")
        bot.send(("Đã BẬT" if on else "Đã TẮT") + " gửi danh sách việc + hỏi cập nhật (đầu ngày, mốc "
                 + ", ".join(bot.cfg.get("task_checkins") or []) + "). "
                 + ("" if on else "Bot quay lại hỏi «3 việc quan trọng» đầu ngày như trước. ")
                 + "Danh sách vẫn xem / sửa được bằng /viec.")
        return
    ops = tasks.parse(text, bot.today())
    if ops:
        bot.apply_tasks(ops)


def _baosau(bot, args):
    from . import progress
    state = args.get("state")
    cfg = bot.cfg
    if state:
        prefs.set_switch(cfg, bot.db, "focus_report_enabled", state)
        on = cfg["focus_report_enabled"]
        audit("FOCUS_REPORT_SET", "on" if on else "off")
        bot.send(f"Báo giờ tập trung sâu + AI nhận xét: {'ĐANG BẬT' if on else 'ĐANG TẮT'} (mốc "
                 + ", ".join(cfg.get("focus_reports") or []) + "). Xem ngay lúc nào cũng được: /baosau")
        return
    day = bot.today()
    if off_day(bot.db, cfg, day):
        bot.send("Hôm nay là ngày nghỉ nên không báo tiến độ tập trung. Xem số liệu: /today")
        return
    p = cfg.get("persona") or persona.DEFAULT
    bot.send(progress.report(cfg, bot.db, day, dt.datetime.now().strftime("%H:%M"), p)
             + f"\n\nTự báo ở các mốc {', '.join(cfg.get('focus_reports') or [])}: "
             + ("đang bật" if cfg.get("focus_report_enabled", True) else "đang tắt") + " (/baosau on | off)",
             raw=True)


def _autoenergy(bot, args):
    state = args.get("state")
    cfg = bot.cfg
    if state:
        prefs.set_energy_auto(cfg, bot.db, state)
        audit("ENERGY_AUTO_SET", "on" if cfg["energy_auto_enabled"] else "off")
    on = cfg.get("energy_auto_enabled", True)
    lines = [f"{'Đã chuyển' if state else 'Đang'} tự tính năng lượng: {'BẬT' if on else 'TẮT'}. "
             + (f"Lúc tổng kết {cfg['daily_summary_at']} mà bạn chưa chấm (/energy) thì bot tự tính từ số liệu tập "
                "trung rồi báo bạn kèm cách tính." if on else "Bạn không chấm thì năng lượng để trống."),
             f"Công thức: tải = tập trung sâu + 0,5 × làm vụn trong VDI + 0,5 × phần quá {energy.LONG_BLOCK_MINUTES} "
             f"phút của mỗi khối làm liền; năng lượng = 5 − 4 × min(tải / {cfg.get('energy_capacity_hours', 4):g}h, 1)."]
    if not state:
        day = bot.today()
        note = get_note(bot.db, day)
        est = energy.estimate(analyze(bot.db, cfg, day), cfg.get("energy_capacity_hours", 4))
        if note.get("energy") not in (None, ""):
            lines.append(f"Hôm nay: {note['energy']}/5 ("
                         + ("bot tự tính" if note.get("energy_source") == "auto" else "bạn tự chấm") + ").")
        elif est:
            lines.append(f"Nếu tính lúc này: {est['energy']}/5 ({energy.label(est['energy'])}), "
                         f"tải {energy.dur(est['load_h'])}.")
        lines.append("/autoenergy on · /autoenergy off · /autoenergy mac_dinh (theo settings.json)")
    bot.send("\n".join(lines))


HEALTH_TEXT = {"break": ("Nhắc đứng dậy, đi lại, vươn vai, tập mắt 20-20-20 khi ngồi làm liên tục", "/break"),
               "water": ("Nhắc uống nước trong giờ làm", "/water")}


def health_line(cfg, kind):
    en, mins = prefs.HEALTH[kind]
    on = cfg.get(en, True) and cfg.get(mins)
    return f"{HEALTH_TEXT[kind][0]}: " + (f"ĐANG BẬT, mỗi {cfg[mins]} phút." if on else "ĐANG TẮT.")


def _health(kind):
    def run(bot, args):
        value = args.get("every")
        if value is not None:
            prefs.set_health(bot.cfg, bot.db, kind, value)
            en, mins = prefs.HEALTH[kind]
            audit(kind.upper() + "_REMINDER", f"{'on' if bot.cfg[en] else 'off'} {bot.cfg[mins]}")
        cmd = HEALTH_TEXT[kind][1]
        bot.send(health_line(bot.cfg, kind) + f"\nĐổi: {cmd} on | {cmd} off | {cmd} 45 (số phút) | {cmd} mac_dinh"
                 + "\n(Nhắc sức khoẻ không phụ thuộc mức nhắc sao nhãng /nudge.)")
    return run


# ------------------------------------------------------------ giờ bot tự bật / tự tắt (/giobot)

log = get_logger()

# Giờ trong câu (đã bỏ dấu): 8:30, 08h30, 8h, 8g15, 8 giờ 15, 8 rưỡi, 6 giờ chiều, 18h, 8 (lệnh gõ tắt).
CLOCK_RE = re.compile(r"(?<![\d:])(\d{1,2})(?:\s*(gio|:|h|g|\.)\s*(\d{1,2})?)?(?:\s*(ruoi))?(?:\s*phut)?"
                      r"(?:\s*(sang|trua|chieu|toi|dem))?(?![\d])")
# Từ đứng trước giờ cho biết là giờ bật hay giờ tắt ("từ 8h đến 18h": từ = bật, đến = tắt). Từ gần giờ nhất thắng.
HOUR_LABEL_RE = re.compile(r"(?<![a-z])(khoi dong|bat dau|bat|mo|start|on|tu|ket thuc|tat|dung|ngung|stop|off|den|"
                           r"toi|nghi)(?![a-z])")
START_LABELS = {"khoi dong", "bat dau", "bat", "mo", "start", "on", "tu"}
RESET_WORDS = [("mac dinh", "default"), ("mac_dinh", "default"), ("default", "default"), ("reset", "default")]
STOP_AFTER_NAMES = {"daily_summary_at": "gửi tổng kết ngày", "weekly_report_at": "gửi tổng kết tuần",
                    "review_prompt_at": "hỏi tổng kết cuối ngày", "plan_prompt_after": "hỏi kế hoạch buổi sáng"}
WORK_DAYS = "thứ 2 – thứ 6"


def _scan_clock(text):
    """Mọi giờ trong câu, theo thứ tự: [(nhãn "start" | "stop" | None, "HH:MM")]. Giờ sai (25:00) vẫn trả để báo lỗi."""
    folded = _fold(text)
    out, prev = [], 0
    for m in CLOCK_RE.finditer(folded):
        h, sep, mins, half, period = m.groups()
        before = folded[prev:m.start()]
        if not (sep or half or period) and re.search(r"(?<![a-z])(thu|t)\s*$", before):
            prev = m.end()  # "thứ 2", "t6": không phải giờ; "từ/đến" đứng trước nó là của thứ, không phải của giờ
            continue
        h = int(h)
        mins = int(mins) if mins else (30 if half else 0)
        if period in ("chieu", "toi") and 1 <= h <= 11:
            h += 12
        elif period == "trua" and 1 <= h <= 3:
            h += 12
        elif period == "dem" and 6 <= h <= 12:
            h += 12
        labels = HOUR_LABEL_RE.findall(before)
        label = None if not labels else ("start" if labels[-1] in START_LABELS else "stop")
        raw = f"{h}:{mins:02d}"
        out.append((label, norm_hhmm(raw) or raw))
        prev = m.end()
    return out


def parse_bot_hours(text):
    """"/giobot 08:30 18:00", "bat 08:30", "tat 19:00", "mac_dinh", "cho bot chạy từ 8h đến 18h" ->
    {"start", "stop"} | {"reset": True} | {"time": ...} (một giờ không rõ bật hay tắt) | {} (không có giờ: xem)."""
    if _word_lookup(RESET_WORDS, text):
        return {"reset": True}
    start = stop = None
    loose = []
    for label, t in _scan_clock(text):
        if label == "start":
            start = t
        elif label == "stop":
            stop = t
        else:
            loose.append(t)
    if loose:
        if start is None and stop is None and len(loose) >= 2:
            start, stop = loose[:2]
        elif start is None and stop is not None:
            start = loose[0]
        elif stop is None and start is not None:
            stop = loose[0]
        elif start is None and stop is None:
            return {"time": loose[0]}
    return {k: v for k, v in (("start", start), ("stop", stop)) if v}


def hours_phrase(args):
    if args.get("reset"):
        return "về giờ trong settings.json"
    if args.get("start") and args.get("stop"):
        return f"bật {args['start']}, tắt {args['stop']} ({WORK_DAYS})"
    if args.get("start"):
        return f"bật {args['start']} (giờ tắt giữ nguyên)"
    if args.get("stop"):
        return f"tắt {args['stop']} (giờ bật giữ nguyên)"
    return "xem giờ hiện tại"


def hours_problem(cfg, start, stop):
    """Khung start–stop có dùng được với cfg không (cùng luật với settings.json). Trả câu lỗi hoặc None."""
    bad = run_window_conflict(cfg, start, stop)
    if bad == "auto_start_at":
        return f"giờ bật ({start}) phải trước giờ tắt ({stop})."
    if bad:
        what = STOP_AFTER_NAMES.get(bad, bad)
        return (f"giờ tắt {stop} phải sau giờ {what} ({cfg[bad]}), nếu không bot tắt trước khi kịp {what}. "
                f"Chọn giờ tắt sau {cfg[bad]}, hoặc đổi \"{bad}\" trong settings.json.")
    return None


def _giobot_check(args, cfg):
    if args.get("reset"):
        return None
    if args.get("time") and not (args.get("start") or args.get("stop")):
        t = args["time"]
        return f"{t} là giờ BẬT hay giờ TẮT bot? Gõ /giobot bat {t} hoặc /giobot tat {t}."
    if cfg is None:
        if args.get("start") and args.get("stop") and args["start"] >= args["stop"]:
            return f"Giờ bật ({args['start']}) phải trước giờ tắt ({args['stop']})."
        return None
    if not (args.get("start") or args.get("stop")):
        return None
    err = hours_problem(cfg, args.get("start") or cfg["auto_start_at"], args.get("stop") or cfg["auto_stop_at"])
    return err[0].upper() + err[1:] if err else None


def _latest_job(cfg):
    key = max(STOP_AFTER_KEYS, key=lambda k: cfg[k])
    return key, cfg[key]


def _hours_warnings(cfg, start, stop):
    out = []
    if start > cfg["work_start"]:
        out.append(f"⚠️ Giờ bật {start} muộn hơn giờ bắt đầu làm ({cfg['work_start']}): từ {cfg['work_start']} tới "
                   f"{start} bot chưa chạy nên không đo, không nhắc, không hỏi gì.")
    if stop < cfg["work_end"]:
        out.append(f"⚠️ Giờ tắt {stop} sớm hơn giờ hết làm ({cfg['work_end']}): sau {stop} không đo, không nhắc.")
    return out


def hours_line(cfg):
    """Một dòng cho /status."""
    if run247_on(cfg):
        return "Bot chạy 24/24 (00:00 – 24:00, cả ngày nghỉ) · /chay247"
    return (f"Bot bật {cfg['auto_start_at']} – tắt {cfg['auto_stop_at']} ({WORK_DAYS}"
            + (", chạy cả ngày nghỉ" if cfg.get("run_on_off_days") else "") + ") · /giobot")


def hours_view(cfg, db):
    start, stop = cfg["auto_start_at"], cfg["auto_stop_at"]
    if prefs.hours_changed(db):
        orig = prefs.hours_orig(db) or {}
        before = "–".join(orig.get(k) or DEFAULTS[k] for k in prefs.HOURS) if orig else ""
        source = "đổi qua Telegram" + (f"; settings.json lúc trước: {before}" if before else "")
    else:
        source = "theo settings.json"
    key, at = _latest_job(cfg)
    lines = [f"⏰ Giờ bot: bật {start} – tắt {stop}, {WORK_DAYS} ({source}).",
             f"• Bật: máy tự bật bot lúc {start}. Mở máy / đăng nhập muộn hơn thì bot bật ngay lúc đó; sớm hơn thì bot "
             f"chờ tới {start} mới chạy.",
             f"• Tắt: {stop} bot chốt số liệu rồi tự tắt. Cuối tuần, ngày lễ, ngày /off: không chạy.",
             f"• Giờ làm {cfg['work_start']}–{cfg['work_end']}. Giờ tắt phải sau {at} ({STOP_AFTER_NAMES[key]}).",
             *_hours_warnings(cfg, start, stop),
             "Đổi: /giobot 08:30 18:00 · /giobot bat 08:30 · /giobot tat 19:00 · /giobot mac_dinh (về settings.json)",
             "Nhắn tự nhiên cũng được: «bật bot lúc 8 rưỡi», «cho bot chạy từ 8h đến 18h»."]
    return "\n".join(lines)


def _now_hhmm():
    return dt.datetime.now().strftime("%H:%M")


def _reset_target(cfg, db, file_vals):
    """/giobot mac_dinh: (giờ bật, giờ tắt, các khoá cần ghi lại vào settings.json hoặc None = không đụng file).
    - settings.json đang là bản /giobot đã ghi -> trả lại đúng giờ trước lần đổi đầu tiên (hours_orig).
    - settings.json bị sửa tay sau đó (khác giờ /giobot) -> dùng luôn giờ trong file, không ghi đè."""
    pref = tuple(prefs.get_pref(db, k) for k in prefs.HOURS)
    orig = prefs.hours_orig(db)
    if file_vals is not None:
        cur = tuple(norm_hhmm(file_vals[k]) if file_vals.get(k) else DEFAULTS[k] for k in prefs.HOURS)
        if orig is not None and all(pref) and cur == pref:
            updates = {k: orig.get(k) for k in prefs.HOURS}
            vals = tuple(norm_hhmm(orig[k]) if orig.get(k) else DEFAULTS[k] for k in prefs.HOURS)
            if all(vals):
                return vals[0], vals[1], updates
        if all(cur):
            return cur[0], cur[1], None
    vals = tuple(cfg.get("_file_" + k) or cfg[k] for k in prefs.HOURS)
    return vals[0], vals[1], None


def _giobot(bot, args):
    """Xem / đổi giờ bot tự bật – tự tắt. Thứ tự: kiểm tra -> lưu prefs -> settings.json -> lịch tự bật của máy ->
    trả lời -> đổi cfg SAU CÙNG (tracker đọc cfg mỗi vòng: giờ tắt mới đã qua thì vòng kế tiếp chốt số liệu rồi
    thoát, nên câu trả lời phải đi trước)."""
    cfg, db = bot.cfg, bot.db
    if not args:
        bot.send(hours_view(cfg, db))
        return
    err = _giobot_check(args, cfg)
    if err:
        log.info("/giobot từ chối %s: %s", args, err)
        audit("BOT_HOURS_REJECT", f"{args} {err}"[:300])
        bot.send(f"Chưa đổi giờ bot: {err[0].lower() + err[1:]}")
        return
    old_start, old_stop = cfg["auto_start_at"], cfg["auto_stop_at"]
    path = cfg.get("_settings_path")
    file_vals = autostart.read_settings(path) if path else None
    reset = bool(args.get("reset"))
    if reset:
        start, stop, updates = _reset_target(cfg, db, file_vals)
        problem = hours_problem(cfg, start, stop)
        if problem:
            bot.send(f"Chưa đổi được: giờ trong settings.json ({start}–{stop}) không dùng được, {problem}")
            return
        prefs.clear_bot_hours(db)
    else:
        start, stop = args.get("start") or old_start, args.get("stop") or old_stop
        orig = {k: (file_vals.get(k) if file_vals is not None else cfg.get("_file_" + k)) for k in prefs.HOURS}
        prefs.set_bot_hours(cfg, db, start, stop, orig)
        updates = {"auto_start_at": start, "auto_stop_at": stop}
    log.info("/giobot: %s–%s -> %s–%s%s", old_start, old_stop, start, stop, " (mặc định)" if reset else "")
    audit("BOT_HOURS", f"{start}-{stop}" + (" reset" if reset else ""))
    head = (f"↩️ Về giờ trong settings.json: bật {start} – tắt {stop} ({WORK_DAYS})." if reset
            else f"✅ Giờ bot mới: bật {start} – tắt {stop} ({WORK_DAYS}).")
    lines = [head] + _hours_warnings(cfg, start, stop)
    now = _now_hhmm()
    if now >= stop:
        lines.append(f"Đã quá {stop}: bot chốt số liệu hôm nay rồi tắt ngay (không gửi gì thêm). "
                     f"Ngày làm việc tới tự bật lúc {start}.")
    elif now < start:
        lines.append(f"Hôm nay bot đang chạy nên chạy tiếp tới {stop}; giờ bật {start} áp dụng từ ngày làm việc tới.")
    elif stop != old_stop:
        lines.append(f"Hôm nay bot tắt lúc {stop}.")
    if updates is not None:
        if path:
            ok, why = autostart.write_settings(path, updates)
            lines.append("Đã lưu vào config/settings.json (bản cũ: settings.json.bak)." if ok else
                         f"⚠️ Không ghi được config/settings.json ({why}). Giờ mới vẫn có hiệu lực (lưu trong DB), "
                         "nhưng nếu chạy lại file cài tự khởi động thì máy dùng giờ bật cũ trong settings.json.")
        else:
            log.info("/giobot: cấu hình không có đường dẫn settings.json, không ghi file.")
    if reset or args.get("start"):
        _, line = autostart.update_start_time(cfg, start)
        lines.append(line)
    else:
        lines.append(f"Giờ bật không đổi ({start}): không cần sửa lịch tự bật của máy.")
    bot.send("\n".join(lines))
    cfg.update({"auto_start_at": start, "auto_stop_at": stop})  # một lần: tracker không thấy khung nửa cũ nửa mới


# ------------------------------------------------------------ tắt app, chế độ làm bù, chạy 24/24

RUN247 = ("00:00", "24:00")


def _start_hint(cfg):
    launcher = "start_tracker.command" if sys.platform == "darwin" else "start_tracker.vbs"
    return (f"Bật lại: nhấp đúp {launcher} trong thư mục app (ngày nghỉ: lam_bu_ngoai_gio), hoặc để máy tự bật lúc "
            f"{cfg['auto_start_at']} ngày làm việc tới / lần đăng nhập hay mở máy tới (trong khung giờ chạy).")


def _tatapp(bot, args):
    """Tắt hẳn app (tracker + bot) như khoi_dong_lai nhưng không bật lại. Báo trước, đặt cờ sau: tracker thấy cờ ở
    vòng kế tiếp (~5 giây) thì chốt số liệu rồi thoát."""
    ev = (getattr(bot, "state", None) or {}).get("quit")
    if ev is None:
        bot.send("Chưa tắt được: app chưa chạy xong bước khởi động. Thử lại sau ít giây nhé.")
        return
    audit("QUIT", "telegram")
    log.info("/tatapp: người dùng tắt app qua Telegram.")
    bot.send("👋 Đang tắt app: mình chốt số liệu hôm nay rồi thoát trong vài giây. Từ lúc này không đo, không nhắc, "
             "bot không trả lời tin nhắn nữa (vì bot nằm trong app).\n" + _start_hint(bot.cfg))
    ev.set()


def lambu_on(bot):
    return bool((getattr(bot, "state", None) or {}).get("manual"))


def _lambu(bot, args):
    """Chế độ làm bù (OT) của lần chạy này: như bật bằng lam_bu_ngoai_gio. Chỉ đổi cờ trong RAM (hết khi app tắt)."""
    state = args.get("state")
    cfg, st = bot.cfg, getattr(bot, "state", None)
    if st is None:
        bot.send("Chưa đổi được: app chưa chạy xong bước khởi động. Thử lại sau ít giây nhé.")
        return
    day = bot.today()
    off = off_day(bot.db, cfg, day)
    stop = cfg["auto_stop_at"]
    if state == "on":
        st["manual"] = True
        audit("LAMBU", "on")
        _poke(bot)
        bot.send("🌙 Đã bật chế độ làm bù (OT), giống bật app bằng lam_bu_ngoai_gio: ngày nghỉ (cuối tuần, lễ, /off) "
                 "app vẫn chạy và chỉ ghi giờ làm trong VDI (có gõ phím / rê chuột), không nhắc, không tính sao nhãng. "
                 "Ngày làm việc thì trong giờ làm vẫn đo, nhắc như thường; ngoài giờ làm tính là OT."
                 + (f"\nHôm nay nghỉ ({off}): đang ghi giờ làm bù." if off else "")
                 + f"\nGiữ tới khi app tắt (tự tắt lúc {stop}). Về chế độ thường: /lambu off")
        return
    if state in ("off", "default"):
        st["manual"] = False
        audit("LAMBU", "off")
        if off and not cfg["run_on_off_days"]:
            text = (f"Đã về chế độ thường. Hôm nay nghỉ ({off}) nên mình chốt số liệu làm bù rồi tắt app ngay. "
                    + _start_hint(cfg))
        elif off:
            text = (f"Đã về chế độ thường. Hôm nay nghỉ ({off}) nhưng app đang chạy cả ngày nghỉ (/chay247) nên vẫn "
                    "chạy và vẫn ghi giờ làm trong VDI, không nhắc.")
        else:
            text = ("Đã về chế độ thường: ngày làm việc đo và nhắc như bình thường; ngày nghỉ app không chạy "
                    "(trừ khi bật /chay247 on).")
        bot.send(text)
        _poke(bot)  # gửi câu trả lời trước: ngày nghỉ thì tracker thoát ngay ở vòng kế tiếp
        return
    on = lambu_on(bot)
    lines = [f"Chế độ đang dùng: {'LÀM BÙ (OT)' if on else 'THƯỜNG'}.",
             "• Làm bù (OT): giống bật app bằng lam_bu_ngoai_gio. Ngày nghỉ (cuối tuần, lễ, /off) app vẫn chạy, chỉ "
             "ghi giờ làm trong VDI, không nhắc, không tính sao nhãng.",
             "• Thường: ngày nghỉ app không chạy (trừ khi /chay247 on). Ngày làm việc hai chế độ đo như nhau: trong "
             "giờ làm đo và nhắc, ngoài giờ làm tính là OT.",
             "/lambu on · /lambu off (đổi có hiệu lực ngay, giữ tới khi app tắt)"]
    if off:
        lines.insert(1, f"Hôm nay nghỉ ({off}).")
    bot.send("\n".join(lines))


def run247_on(cfg):
    return bool(cfg.get("run_on_off_days")) and (cfg["auto_start_at"], cfg["auto_stop_at"]) == RUN247


def _run247_restore_target(cfg, db):
    """(giờ bật, giờ tắt, chạy ngày nghỉ) khi /chay247 off: cài đặt trước lần bật, không có thì settings.json gốc,
    settings.json gốc cũng là 24/24 thì giờ mặc định của app."""
    prev = prefs.run247_prev(db)
    if prev:
        return prev["auto_start_at"], prev["auto_stop_at"], prev["run_on_off_days"]
    start = cfg.get("_file_auto_start_at") or DEFAULTS["auto_start_at"]
    stop = cfg.get("_file_auto_stop_at") or DEFAULTS["auto_stop_at"]
    if (start, stop) == RUN247:
        start, stop = DEFAULTS["auto_start_at"], DEFAULTS["auto_stop_at"]
    return start, stop, False


def run247_view(cfg):
    if run247_on(cfg):
        head = "🔁 App đang chạy 24/24: bật 00:00 – tắt 24:00, cả cuối tuần và ngày lễ."
    elif cfg.get("run_on_off_days"):
        head = (f"App chạy cả ngày nghỉ, giờ chạy {cfg['auto_start_at']} – {cfg['auto_stop_at']} (chưa phải 24/24).")
    else:
        head = (f"App KHÔNG chạy 24/24: bật {cfg['auto_start_at']} – tắt {cfg['auto_stop_at']}, {WORK_DAYS}; cuối "
                "tuần, ngày lễ không chạy.")
    return "\n".join([head,
                      "• 24/24: bật 00:00 – tắt 24:00, chạy cả ngày nghỉ. Ngày nghỉ và ngoài giờ làm chỉ ghi giờ làm "
                      "trong VDI, không nhắc; trong giờ làm ngày làm việc vẫn đo, nhắc như thường.",
                      "• Máy phải luôn bật: Windows Settings > System > Power & sleep (Power & battery) > Sleep = Never, "
                      "và gập nắp = Do nothing. Máy ngủ hay tắt thì app cũng dừng.",
                      "/chay247 on · /chay247 off (trả lại giờ cũ)"])


def _chay247(bot, args):
    """Bật/tắt chạy 24/24 = giờ bot 00:00–24:00 + chạy cả ngày nghỉ. Cùng thứ tự với /giobot: lưu prefs ->
    settings.json -> lịch tự bật của máy -> trả lời -> đổi cfg SAU CÙNG (tracker đọc cfg mỗi vòng, có thể thoát ngay)."""
    state = args.get("state")
    cfg, db = bot.cfg, bot.db
    if not state:
        bot.send(run247_view(cfg))
        return
    path = cfg.get("_settings_path")
    if state == "on":
        if run247_on(cfg):
            bot.send("App đang chạy 24/24 rồi, không cần đổi gì.\n" + run247_view(cfg))
            return
        start, stop, run_off = RUN247[0], RUN247[1], True
        file_vals = autostart.read_settings(path) if path else None
        orig = {k: (file_vals.get(k) if file_vals is not None else cfg.get("_file_" + k)) for k in prefs.HOURS}
        prefs.set_run_on_off_days(db, True, prev={"auto_start_at": cfg["auto_start_at"],
                                                  "auto_stop_at": cfg["auto_stop_at"],
                                                  "run_on_off_days": bool(cfg.get("run_on_off_days"))})
        prefs.set_bot_hours(cfg, db, start, stop, orig)
        lines = ["🔁 Đã bật chạy 24/24: bật 00:00 – tắt 24:00, chạy cả cuối tuần và ngày lễ.",
                 "Ngày nghỉ và ngoài giờ làm: chỉ ghi giờ làm trong VDI, không nhắc. Giờ làm ngày làm việc: đo, nhắc "
                 "như thường.",
                 "⚠️ Nhớ cho máy không ngủ: Settings > System > Power & sleep > Sleep = Never, gập nắp = Do nothing."]
    else:
        start, stop, run_off = _run247_restore_target(cfg, db)
        if not cfg.get("run_on_off_days") and (cfg["auto_start_at"], cfg["auto_stop_at"]) != RUN247:
            bot.send("App đang không chạy 24/24, không cần tắt.\n" + run247_view(cfg))
            return
        problem = hours_problem(cfg, start, stop)
        if problem:
            bot.send(f"Chưa tắt được 24/24: giờ cũ ({start}–{stop}) không dùng được, {problem} "
                     "Đặt giờ khác bằng /giobot rồi gõ lại /chay247 off.")
            return
        prefs.set_run_on_off_days(db, run_off, prev=False)
        prefs.set_bot_hours(cfg, db, start, stop)
        lines = [f"↩️ Đã tắt chạy 24/24: bot bật {start} – tắt {stop}, {WORK_DAYS}"
                 + ("; vẫn chạy cả ngày nghỉ (như trước khi bật 24/24)." if run_off else
                    "; cuối tuần, ngày lễ không chạy.")]
        now = _now_hhmm()
        off = off_day(db, cfg, bot.today())
        if now >= stop:
            lines.append(f"Đã quá {stop}: app chốt số liệu hôm nay rồi tắt ngay. Ngày làm việc tới tự bật lúc {start}.")
        elif off and not run_off and not lambu_on(bot):
            lines.append(f"Hôm nay nghỉ ({off}): app chốt số liệu rồi tắt ngay. Ngày làm việc tới tự bật lúc {start}.")
        elif now < start:
            lines.append(f"Hôm nay app đang chạy nên chạy tiếp tới {stop}; giờ bật {start} áp dụng từ ngày làm việc tới.")
        else:
            lines.append(f"Hôm nay app tắt lúc {stop}.")
    audit("RUN_247", f"{state} {start}-{stop} off_days={run_off}")
    log.info("/chay247 %s: %s–%s, chạy ngày nghỉ = %s", state, start, stop, run_off)
    updates = {"auto_start_at": start, "auto_stop_at": stop, "run_on_off_days": True if run_off else None}
    if path:
        ok, why = autostart.write_settings(path, updates)
        lines.append("Đã lưu vào config/settings.json (bản cũ: settings.json.bak)." if ok else
                     f"⚠️ Không ghi được config/settings.json ({why}). Cài đặt mới vẫn có hiệu lực (lưu trong DB).")
        if ok and state != "on":  # đã trả lại vào file: file là nguồn, sau này sửa tay settings.json vẫn có tác dụng
            prefs.set_pref(db, "run_on_off_days", None)
    else:
        log.info("/chay247: cấu hình không có đường dẫn settings.json, không ghi file.")
    if start != cfg["auto_start_at"]:
        lines.append(autostart.update_start_time(cfg, start)[1])
    lines.append("Xem lại: /chay247 · /giobot")
    bot.send("\n".join(lines))
    cfg.update({"auto_start_at": start, "auto_stop_at": stop, "run_on_off_days": run_off})  # một lần, sau câu trả lời
    _poke(bot)


def _help(bot, args):
    bot.send(full_help(bot.cfg))


TEXT = ("text", "text", "nội dung", True)

ACTIONS = [
    Action("xem_hom_nay", ["/today", "/score"], "Tổng kết hôm nay",
           "Xem số liệu tập trung, điểm, chuỗi ngày, kế hoạch đầu ngày, năng lượng, output, issue của hôm nay "
           "hoặc một ngày đã qua", _today,
           params=[("day", "pastdate", "ngày đã qua muốn xem lại (bỏ trống = hôm nay)", False)],
           keywords=["xem hom nay", "hom nay the nao", "tong ket ngay", "diem", "streak", "tap trung duoc bao",
                     "lam duoc bao", "xem ke hoach", "xem plan", "ke hoach hom nay", "ke hoach hom qua",
                     "xem nang luong", "nang luong hom nay", "nang luong hom qua", "hom qua the nao",
                     "tong ket hom qua", "xem hom qua", "xem lai ngay", "hom nay", "hom qua"]),
    # "hom nay", "hom qua" là từ khoá YẾU (intent: thua mọi từ khoá khác)
    Action("gui_bao_cao", ["/report"], "Gửi file báo cáo HTML",
           "Gửi file báo cáo HTML chi tiết của hôm nay hoặc một ngày đã qua", _report,
           params=[("day", "pastdate", "ngày đã qua muốn xem lại (bỏ trống = hôm nay)", False)],
           keywords=["bao cao", "report", "file html"]),
    Action("xem_tuan", ["/week"], "Tổng kết tuần",
           "Tổng kết tuần: giờ vàng, ngày tốt/kém nhất, issue lặp lại", _week,
           keywords=["tuan nay", "tong ket tuan", "bao cao tuan"]),
    Action("xem_gio_vang", ["/golden"], "Giờ vàng", "Xem khung giờ tập trung tốt nhất 14 ngày gần nhất",
           _golden, keywords=["gio vang"]),
    Action("xem_trang_thai", ["/status"], "Trạng thái lúc này", "Lúc này đang trong VDI hay ngoài, idle bao lâu",
           _status, keywords=["trang thai", "dang lam gi", "status"]),
    Action("xem_vang", ["/vang"], "Vừa vắng bao lâu",
           "Xem lần vắng gần nhất (không chạm phím/chuột, khoá máy, máy ngủ: từ mấy giờ tới mấy giờ, bao lâu), lúc "
           "này có đang vắng không, và các lần vắng từ 5 phút trong ngày; trả lời câu hỏi kiểu 'mình vừa inactive / "
           "đi vắng bao lâu'", _vang,
           params=[("day", "pastdate", "ngày đã qua muốn xem lại (bỏ trống = hôm nay)", False)],
           keywords=["vua inactive", "inactive bao lau", "vua vang", "vang bao lau", "vang may lan", "vang mat",
                     "vua roi may", "roi may bao lau", "roi may may lan", "di vang bao lau", "di dau bao lau",
                     "ngoi yen bao lau", "khong cham phim bao lau"]),
    Action("ghi_ke_hoach", ["/plan"], "Ghi kế hoạch hôm nay",
           "Ghi kế hoạch / 3 việc quan trọng hôm nay (không có nội dung thì bot hỏi từng câu)", _plan,
           params=[("text", "text", "nội dung kế hoạch", False)], writes=True,
           confirm="Ghi kế hoạch hôm nay: «{text}»",
           keywords=["ke hoach", "hom nay se lam", "hom nay can lam", "viec hom nay", "plan", "se lam",
                     "hom nay se", "hom nay minh se"]),
    Action("ghi_output", ["/output"], "Ghi việc đã xong", "Ghi nhanh một việc vừa làm xong (output)",
           _note_line("output", "output"), params=[("text", "text", "việc đã xong", True)], writes=True,
           confirm="Ghi output (việc đã xong): «{text}»",
           keywords=["da xong", "xong viec", "lam xong", "hoan thanh", "output", "da fix", "da deploy",
                     "vua xong", "vua lam xong", "vua fix", "vua deploy"]),
    Action("ghi_issue", ["/issue"], "Ghi issue / bị chặn",
           "Ghi ngay một issue, blocker, việc bị chặn (VDI chậm, thiếu quyền, chờ người khác)",
           _note_line("issues", "issue"), params=[("text", "text", "nội dung issue", True)], writes=True,
           confirm="Ghi issue: «{text}»",
           keywords=["issue", "bi chan", "blocker", "bi block", "vdi cham", "thieu quyen", "cho review"]),
    Action("ghi_phan_tam", ["/distraction"], "Ghi điều làm mất tập trung",
           "Ghi điều làm mất tập trung hoặc lý do vừa bị gián đoạn hôm nay (con khóc, việc nhà, họp đột xuất, "
           "người hỏi chuyện, điện thoại...)", _note_line("distractions", "điều làm mất tập trung"),
           params=[("text", "text", "điều làm mất tập trung", True)], writes=True,
           confirm="Ghi điều làm mất tập trung: «{text}»",
           keywords=["mat tap trung", "phan tam", "xao nhang", "sao nhang", "gian doan", "ngat quang",
                     "bi lam phien", "con khoc", "be khoc", "trong em be", "trong con nho", "goi di hop",
                     "bi goi di", "bi keo di"]),
    Action("ghi_viec_ngay_mai", ["/tmrtask", "/mai"], "Ghi việc đầu tiên sáng mai",
           "Ghi việc đầu tiên sẽ làm sáng mai (sáng mai bot nhắc lại)", _tomorrow,
           params=[TEXT], writes=True, confirm="Ghi việc đầu tiên sáng mai: «{text}»",
           keywords=["ngay mai", "sang mai", "mai can lam", "mai lam", "viec mai", "tomorrow"]),
    Action("ghi_nang_luong", ["/energy"], "Ghi năng lượng 1–5", "Ghi mức năng lượng hôm nay từ 1 đến 5",
           _energy, params=[("energy", "energy", "mức năng lượng 1–5", True)], writes=True,
           confirm="Ghi năng lượng hôm nay: {energy}/5", keywords=["nang luong", "energy", "met moi muc"]),
    Action("ghi_gio_as400", ["/as400"], "Ghi giờ vào/ra AS400",
           "Ghi giờ vào và ra AS400 hôm nay (HH:MM). Có thể gửi ảnh spooled file thay vì gõ", _as400,
           params=[("times", "times", "giờ vào/ra AS400", True)], writes=True,
           confirm="Ghi giờ AS400 hôm nay: vào {start}, ra {end}", keywords=["as400", "as/400", "spool"]),
    Action("tong_ket_ngay", ["/review"], "Tổng kết cuối ngày",
           "Bắt đầu hỏi tổng kết cuối ngày từng câu (output, issue, AS400, việc mai, năng lượng)", _review,
           keywords=["tong ket cuoi ngay", "review", "ket thuc ngay", "cuoi ngay"]),
    Action("bao_nghi", ["/off"], "Báo ngày nghỉ",
           "Báo một ngày nghỉ (hôm nay hoặc ngày khác) để bot không nhắc gì ngày đó", _off,
           params=[("day", "date", "ngày nghỉ", False), ("reason", "text", "lý do", False)], writes=True,
           confirm="Đánh dấu {day} là ngày nghỉ ({reason})",
           keywords=["nghi phep", "xin nghi", "ngay nghi", "nghi om", "off"]),
    Action("nghi_phep", ["/leave", "/nghiphep"], "Nghỉ phép (sáng / chiều / cả ngày)",
           "Báo nghỉ phép nửa ngày buổi sáng, nửa ngày buổi chiều, hoặc cả ngày (hôm nay hoặc ngày khác): bot không "
           "theo dõi, không nhắc trong phần nghỉ; nghỉ nửa ngày thì mục tiêu còn một nửa", _leave,
           params=[("part", "leavepart", "buổi nghỉ: am (buổi sáng) | pm (buổi chiều) | full (cả ngày, mặc định)",
                    False),
                   ("day", "date", "ngày nghỉ (mặc định hôm nay)", False), ("reason", "text", "lý do", False)],
           writes=True, confirm="Ghi nghỉ phép {part} ngày {day}{note}",
           keywords=["nghi nua ngay", "nghi buoi sang", "nghi buoi chieu", "nghi phep buoi", "nghi phep nua ngay",
                     "nghi phep sang", "nghi phep chieu", "nghi sang", "nghi chieu", "leave", "nghiphep"]),
    Action("bao_di_lam", ["/on"], "Huỷ ngày nghỉ / nghỉ phép",
           "Huỷ ngày nghỉ hoặc nghỉ phép (cả ngày hay nửa ngày) đã báo, làm việc lại bình thường", _on,
           params=[("day", "date", "ngày", False)], writes=True, confirm="Đánh dấu {day} là ngày làm việc",
           keywords=["di lam lai", "huy nghi", "khong nghi nua", "huy nghi phep"]),
    Action("tam_dung", ["/pause"], "Tạm dừng theo dõi", "Tạm dừng theo dõi (ví dụ việc riêng)", _pause,
           writes=True, confirm="Tạm dừng theo dõi tập trung", keywords=["tam dung", "pause", "dung theo doi"]),
    Action("tiep_tuc", ["/resume"], "Theo dõi lại", "Theo dõi lại sau khi tạm dừng", _resume, writes=True,
           confirm="Theo dõi lại từ bây giờ", keywords=["tiep tuc", "resume", "theo doi lai"]),
    Action("xin_cau_dong_luc", ["/quote"], "Câu truyền động lực", "Xin một câu nói truyền động lực", _quote,
           keywords=["dong luc", "truyen cam hung", "quote", "danh ngon"]),
    Action("xin_cau_kinh_thanh", ["/bible"], "Câu Kinh Thánh", "Xin một câu Kinh Thánh khích lệ", _bible,
           keywords=["kinh thanh", "bible", "loi chua", "cau goc"]),
    Action("xem_ai", ["/aistatus"], "Tình trạng AI", "Xem AI đang dùng model nào, đã gọi bao nhiêu lần",
           _aistatus, keywords=["tinh trang ai", "ai status", "model ai"]),
    Action("xoa_cache_ai", ["/clearcache"], "Xoá cache AI", "Xoá cache model AI và các nhận xét AI đã lưu",
           _clearcache, writes=True, confirm="Xoá cache AI (model đã chọn + nhận xét đã lưu)",
           keywords=["xoa cache"]),
    Action("xem_hieu_nang", ["/perf"], "Hiệu năng tracker", "Xem tracker tốn bao nhiêu CPU/RAM", _perf,
           keywords=["hieu nang", "cpu", "ram", "perf"]),
    Action("bat_tat_ai_danh_gia", ["/aireview"], "Bật/tắt AI tự đánh giá",
           "Bật hoặc tắt việc AI tự đọc báo cáo và nhắn đánh giá cuối ngày, cuối tuần; không kèm on/off thì xem trạng thái",
           _aireview, params=[("state", "onoff", "on (bật) / off (tắt)", False)], writes=True,
           confirm="Chuyển AI tự đánh giá cuối ngày/tuần sang: {state}",
           keywords=["ai danh gia", "ai review", "aireview", "danh gia tu dong", "ai tong ket"],
           view_without_args=True),
    Action("hoi_ai", ["/ask", "/hoi"], "Hỏi AI",
           "Hỏi AI bất kỳ câu gì (tập trung, công việc, AS400, sức khoẻ, thu nhập...) và nhận câu trả lời; "
           "hoặc bật/tắt chế độ hỏi AI (text = on / off); không kèm gì thì xem trạng thái",
           _ask, params=[("text", "text", "câu hỏi, hoặc on / off", False)],
           keywords=["hoi ai", "che do hoi ai", "ask ai", "hoi chatbot", "hoi gemini", "hoi claude",
                     "gia vang", "ty gia", "thoi tiet", "gia xang", "chung khoan", "lam sao de", "tai sao",
                     "nhu the nao", "co nen", "thu nhap", "kiem tien"]),
    Action("cai_khich_le", ["/encourage"], "Bật/tắt lời khích lệ tự động",
           "Bật/tắt tự gửi lời khích lệ đầu ngày, buổi chiều; chọn chỉ danh ngôn (không Kinh Thánh), chỉ Kinh Thánh, "
           "hoặc cả hai; không kèm lựa chọn thì xem cài đặt hiện tại", _encourage,
           params=[("mode", "encmode", "on | off | quote | bible | both", False)], writes=True,
           confirm="Đổi lời khích lệ tự động sang: {mode}",
           keywords=["khich le tu dong", "tin nhan khich le", "khich le dau ngay", "gui khich le", "encourage",
                     "tat khich le", "bat khich le", "chi gui kinh thanh", "khong gui kinh thanh",
                     "dung gui kinh thanh", "chi khich le", "loi khich le", "tat kinh thanh",
                     "khong kinh thanh", "bo kinh thanh", "ngung kinh thanh", "bat kinh thanh",
                     "chuyen sang danh ngon", "doi sang danh ngon", "dong vien dau ngay"], view_without_args=True),
    Action("bat_tat_kinh_thanh", ["/kinhthanh"], "Bật/tắt Kinh Thánh trong lời khích lệ",
           "Nút gạt Kinh Thánh: on = lời chào buổi sáng và lời khích lệ dùng Kinh Thánh, off (mặc định khi cài lần đầu) = mọi tin chỉ dùng "
           "châm ngôn người thành đạt, danh nhân xưa (cho người không theo đạo); không kèm gì thì đảo trạng thái hiện tại", _kinhthanh,
           params=[("state", "onoff", "on (Kinh Thánh) / off (danh ngôn)", False)], writes=True,
           confirm="Kinh Thánh trong lời khích lệ: {state}",
           keywords=["kinhthanh", "gat kinh thanh", "nut kinh thanh", "doi kinh thanh"]),
    Action("doi_giong", ["/style"], "Đổi giọng văn của bot",
           "Đổi giọng nói của bot và AI: than_mat, vui_tuoi, hai_huoc, sep_kho_tinh; không kèm giọng thì xem giọng hiện tại",
           _style, params=[("tone", "tone", "giọng: than_mat | vui_tuoi | hai_huoc | sep_kho_tinh", False)],
           writes=True, confirm="Đổi giọng văn của bot sang: {tone}",
           keywords=["doi giong", "giong van", "giong noi", "style", "noi chuyen kieu"], view_without_args=True),
    Action("doi_muc_nhac", ["/nudge", "/nhac"], "Mức nhắc khi sao nhãng",
           "Đổi mức nhắc khi sao nhãng (ra ngoài VDI, thu nhỏ VDI): off (tắt hẳn), nhe (1 lần/ngày), vua "
           "(1 lần mỗi lần sao nhãng), nghiem (nhắc lặp, gắt hơn); không kèm mức thì xem mức hiện tại", _nudge,
           params=[("level", "nudgelevel", "mức: off | nhe | vua | nghiem | mac_dinh", False)], writes=True,
           confirm="Đổi mức nhắc khi sao nhãng sang: {level}",
           keywords=["nhac nho sao nhang", "nhac sao nhang", "nhac khi sao nhang", "nhac nghiem", "nhac chat",
                     "nhac nhe", "nhac vua", "nhac 1 lan", "nhac mot lan", "1 lan moi ngay", "mot lan moi ngay",
                     "tat nhac nho", "bat nhac nho", "muc nhac", "muc do nhac", "che do nhac", "nudge",
                     "nhac ngoai vdi", "nhac nho"],
           view_without_args=True),
    Action("chon_app_vdi", ["/vdi"], "Đo VDI bằng Citrix hay Windows App",
           "Chọn app mở VDI mà bot đo: citrix (chỉ Citrix), winapp (chỉ Windows App / Remote Desktop, tức Azure "
           "Virtual Desktop), ca_hai (cả hai); không kèm gì thì xem đang đo app nào", _vdi,
           params=[("client", "vdiclient", "app: citrix | winapp | ca_hai | mac_dinh", False)], writes=True,
           confirm="Đổi app VDI cần đo sang: {client}",
           keywords=["sang citrix", "qua citrix", "sang windows app", "qua windows app", "sang window app",
                     "qua window app", "sang winapp", "qua winapp", "sang avd", "qua avd",
                     "chuyen sang citrix", "chuyen qua citrix", "doi sang citrix", "chi do citrix", "do citrix",
                     "dung citrix", "chuyen sang windows app", "chuyen qua windows app", "doi sang windows app",
                     "chi do windows app", "do windows app", "dung windows app", "chuyen sang window app",
                     "chuyen qua window app", "do window app", "dung window app", "chuyen sang winapp",
                     "chuyen sang avd", "chuyen qua avd", "do avd", "dung avd", "azure virtual desktop",
                     "app vdi", "loai vdi", "dang do vdi nao", "do vdi bang"],
           view_without_args=True),
    Action("canh_bao_tien_do", ["/pace", "/tiendo"], "Tiến độ hôm nay / cảnh báo tiến độ",
           "Xem tiến độ hôm nay (giờ làm thật trong VDI so với nhịp cần để đạt mục tiêu và về đúng giờ); "
           "on/off bật tắt cảnh báo tiến độ tự động ở các mốc trong ngày", _pace,
           params=[("state", "onoff", "on (bật) / off (tắt)", False)], writes=True,
           confirm="Chuyển cảnh báo tiến độ tự động sang: {state}",
           keywords=["canh bao tien do", "tien do hom nay the nao", "tien do hom nay sao", "tien do the nao",
                     "tien do sao roi", "tien do", "tiendo", "pace", "kip gio ve", "ve dung gio", "kip tien do"],
           view_without_args=True),
    Action("danh_sach_viec", ["/viec", "/tasks", "/todo"], "Danh sách việc cần làm",
           "Danh sách việc cần làm (giống Google Tasks): không kèm gì = xem danh sách đánh số; kèm text = cập nhật. "
           "text viết theo cú pháp: «xong 1 3» (đã xong việc số 1, 3), «xong: tên việc» (xong việc có tên giống vậy, "
           "dùng khi người dùng nói tên việc mà không nói số), «mới: nội dung» (thêm việc; nhiều việc cách nhau ;), "
           "«hoãn 2» (để sang ngày làm việc kế), «bỏ 4» (xoá), «sửa 2: nội dung mới», «ưu tiên 3» (làm trước), "
           "«hạn 2 25/11», «issue: nội dung», «hoàn tác»; nhiều lệnh cách nhau bằng ;. text «on»/«off» = bật/tắt bot "
           "tự gửi danh sách hỏi cập nhật. Khác ghi_output: ghi_output là ghi việc đã làm ngoài danh sách", _viec,
           params=[("text", "text", "lệnh cập nhật theo cú pháp, ví dụ «xong 1 3; mới: gọi anh A»", False)],
           writes=True, confirm="Cập nhật danh sách việc: {mo_ta}", check=_viec_check, view_without_args=True,
           keywords=["danh sach viec", "viec can lam", "todo", "to do", "task list", "danh sach task",
                     "cap nhat viec", "cap nhat task", "viec hom nay con gi", "con viec gi"]),
    Action("bao_tap_trung_sau", ["/baosau", "/focusreport"], "Báo giờ tập trung sâu + AI nhận xét",
           "Báo ngay giờ tập trung sâu hôm nay tới lúc này so với nhịp cần, kèm AI nhận xét ngắn; on/off bật tắt tự "
           "báo ở các mốc trong ngày (mặc định 10:17, 12:45, 15:00)", _baosau,
           params=[("state", "onoff", "on (bật) / off (tắt)", False)], writes=True,
           confirm="Chuyển tự báo giờ tập trung sâu sang: {state}",
           keywords=["bao tap trung sau", "bao tap trung", "tap trung sau toi gio", "tap trung duoc bao nhieu gio roi",
                     "focus report"],
           view_without_args=True),
    Action("tu_tinh_nang_luong", ["/autoenergy", "/tunangluong"], "Tự tính năng lượng khi chưa chấm",
           "Xem / bật / tắt việc bot tự tính năng lượng 1–5 lúc tổng kết cuối ngày khi bạn chưa chấm, dựa trên số "
           "liệu tập trung (càng tập trung sâu lâu càng cạn)", _autoenergy,
           params=[("state", "onoff", "on (bật) / off (tắt)", False)], writes=True,
           confirm="Chuyển tự tính năng lượng sang: {state}",
           keywords=["tu tinh nang luong", "nang luong tu dong", "tinh nang luong", "autoenergy", "tunangluong"],
           view_without_args=True),
    Action("nhac_nghi_ngoi", ["/break", "/nghingoi"], "Nhắc đứng dậy, vận động, tập mắt",
           "Bật/tắt nhắc đứng dậy đi lại, vươn vai, tập mắt (chống cận) khi ngồi làm liên tục lâu, hoặc đổi số phút; "
           "không kèm gì thì xem cài đặt", _health("break"),
           params=[("every", "health", "on | off | số phút (ví dụ 45) | mac_dinh", False)], writes=True,
           confirm="Đổi nhắc nghỉ (đứng dậy, vận động, tập mắt) sang: {every}",
           keywords=["nhac dung day", "nhac nghi ngoi", "nhac nghi giai lao", "nhac van dong", "nhac tap mat",
                     "nhac nghi moi", "nhac nghi", "ngoi lau", "nghingoi", "giai lao"],
           view_without_args=True),
    Action("nhac_uong_nuoc", ["/water", "/uongnuoc"], "Nhắc uống nước",
           "Bật/tắt nhắc uống nước trong giờ làm, hoặc đổi số phút; không kèm gì thì xem cài đặt", _health("water"),
           params=[("every", "health", "on | off | số phút (ví dụ 45) | mac_dinh", False)], writes=True,
           confirm="Đổi nhắc uống nước sang: {every}",
           keywords=["nhac uong nuoc", "uong nuoc", "uongnuoc", "water"], view_without_args=True),
    Action("gio_bot", ["/giobot", "/hours"], "Giờ bot tự bật / tự tắt",
           "Xem hoặc đổi giờ bot (tracker) tự bật và tự tắt mỗi ngày làm việc thứ 2 – thứ 6: start = giờ bật HH:MM, "
           "stop = giờ tắt HH:MM, reset = true để về giờ trong settings.json; không kèm gì thì xem giờ hiện tại",
           _giobot,
           params=[("start", "clock", "giờ BẬT bot HH:MM (24h)", False),
                   ("stop", "clock", "giờ TẮT bot HH:MM (24h)", False),
                   ("time", "clock", "giờ HH:MM khi câu không nói rõ là bật hay tắt", False),
                   ("reset", "flag", "true = về giờ trong settings.json", False)],
           writes=True, confirm="Đổi giờ bot: {hours}", check=_giobot_check,
           keywords=["gio bot", "giobot", "gio bat bot", "gio tat bot", "bat bot", "tat bot", "mo bot",
                     "cho bot chay", "bot chay tu", "bot bat luc", "bot tat luc", "bot tu bat", "bot tu tat",
                     "khung gio chay", "gio chay bot"],
           view_without_args=True),
    Action("chay_24_24", ["/chay247"], "Chạy 24/24",
           "Bật/tắt chạy 24/24: bot bật 00:00 – tắt 24:00 và chạy cả cuối tuần, ngày lễ (ngày nghỉ và ngoài giờ làm "
           "chỉ ghi giờ làm trong VDI, không nhắc); off = trả lại giờ cũ; không kèm gì thì xem đang chạy thế nào",
           _chay247, params=[("state", "onoff", "on (bật 24/24) / off (tắt, về giờ cũ)", False)], writes=True,
           confirm="Chuyển chạy 24/24 sang: {state}",
           keywords=["chay 24/24", "chay 24 24", "chay 247", "chay 24 7", "chay 24h", "24/24", "24 24", "chay247",
                     "chay ca ngay nghi", "chay suot ngay dem", "chay ca cuoi tuan"],
           view_without_args=True),
    Action("che_do_lam_bu", ["/lambu"], "Chế độ làm bù (OT) / thường",
           "Bật/tắt chế độ làm bù (OT) như khi bật app bằng lam_bu_ngoai_gio: on = ngày nghỉ vẫn ghi giờ làm trong "
           "VDI, không nhắc; off = về chế độ thường (ngày nghỉ thì app tắt luôn); không kèm gì thì xem chế độ đang "
           "dùng", _lambu, params=[("state", "onoff", "on (làm bù / OT) / off (chế độ thường)", False)], writes=True,
           confirm="Chuyển chế độ làm bù (OT) sang: {state}",
           keywords=["che do lam bu", "che do ot", "mode ot", "lambu", "che do thuong", "mode thuong",
                     "bat lam bu", "tat lam bu"],
           view_without_args=True),
    Action("tat_app", ["/tatapp"], "Tắt hẳn app",
           "Tắt hẳn app (tracker + bot) từ Telegram: chốt số liệu rồi thoát; luôn hỏi OK trước. Bật lại phải làm "
           "trên máy (hoặc máy tự bật giờ tự bật tới)", _tatapp, writes=True, confirm_command=True,
           confirm="Tắt hẳn app (chốt số liệu rồi thoát, bot ngừng trả lời tới lần bật sau)",
           keywords=["tat app", "tat han app", "thoat app", "tat tracker", "thoat tracker", "dung app", "tatapp",
                     "tat ung dung", "thoat ung dung", "tat focus tracker"]),
    Action("huy", ["/cancel"], "Huỷ", "Huỷ thao tác đang chờ xác nhận hoặc đang hỏi dở", _cancel,
           keywords=["huy bo", "thoi khong", "cancel"]),
    Action("tro_giup", ["/help", "/start"], "Danh sách lệnh", "Xem danh sách lệnh", _help,
           keywords=["tro giup", "help", "huong dan", "lenh gi"]),
    Action("tro_chuyen", [], "Trò chuyện / động viên",
           "Tâm sự, than mệt, chán, cần động viên, hoặc tin nhắn không thuộc thao tác nào ở trên", _chat,
           params=[("text", "text", "tin nhắn", False)],
           keywords=["chan qua", "met qua", "nan qua", "buon", "stress", "dong vien", "met moi"]),
]

BY_NAME = {a.name: a for a in ACTIONS}
BY_COMMAND = {c: a for a in ACTIONS for c in a.commands}


def help_text(cfg=None):
    lines = ["Nhắn tự nhiên (ví dụ \"mai làm tiếp job đối soát\") hoặc dùng lệnh:"]
    for a in ACTIONS:
        if a.name == "ghi_gio_as400" and cfg is not None and not cfg.get("as400_enabled", True):
            continue
        if a.commands and a.name not in ("tro_giup",):
            extra = " nội dung" if any(p[3] for p in a.params) and a.params[0][1] == "text" else ""
            lines.append(f"{a.command}{extra}  {a.title}")
    lines.append("Thao tác ghi dữ liệu từ tin nhắn tự nhiên sẽ hỏi lại để bạn bấm OK.")
    return "\n".join(lines)


# /help: nhóm lệnh + giải thích + ví dụ cụ thể. Thêm action mới thì thêm ví dụ ở đây (thiếu cũng không lỗi).
HELP_GROUPS = [
    ("📊 XEM SỐ LIỆU", ["xem_hom_nay", "xem_trang_thai", "xem_vang", "gui_bao_cao", "xem_tuan", "xem_gio_vang"]),
    ("📝 GHI CHÉP TRONG NGÀY", ["ghi_ke_hoach", "ghi_output", "ghi_issue", "ghi_phan_tam", "ghi_viec_ngay_mai",
                               "ghi_nang_luong", "ghi_gio_as400", "tong_ket_ngay", "danh_sach_viec"]),
    ("🌴 NGÀY NGHỈ, NGHỈ PHÉP, TẠM DỪNG", ["nghi_phep", "bao_nghi", "bao_di_lam", "tam_dung", "tiep_tuc"]),
    ("🤖 AI, ĐỘNG VIÊN, CÀI ĐẶT", ["hoi_ai", "xin_cau_dong_luc", "xin_cau_kinh_thanh", "bat_tat_ai_danh_gia",
                                  "cai_khich_le", "doi_giong", "doi_muc_nhac", "canh_bao_tien_do", "bao_tap_trung_sau",
                                  "tu_tinh_nang_luong", "nhac_nghi_ngoi", "nhac_uong_nuoc"]),
    ("🛠 HỆ THỐNG", ["gio_bot", "chay_24_24", "che_do_lam_bu", "tat_app", "xem_ai", "xoa_cache_ai", "xem_hieu_nang", "huy", "tro_giup"]),
]

EXAMPLES = {
    "xem_hom_nay": ("Giờ tập trung sâu, trong/ngoài VDI, điểm, streak, kế hoạch đầu ngày, năng lượng, output, issue. "
                    "Kèm ngày để xem lại ngày đã qua",
                    ["/today", "/today hôm qua", "/today 14/10", "hôm nay mình tập trung được bao nhiêu rồi",
                     "xem kế hoạch hôm nay"]),
    "xem_trang_thai": ("Tình trạng đầy đủ: lúc này trong hay ngoài VDI, số liệu hôm nay, số lần đã nhắc, cài đặt, "
                       "AI đã dùng bao nhiêu lượt/từ, còn bao nhiêu quota, CPU/RAM", ["/status"]),
    "xem_vang": ("Lần vắng gần nhất (không chạm phím/chuột, khoá máy, máy ngủ): mấy giờ tới mấy giờ, bao lâu; lúc này "
                 "có đang vắng không; các lần vắng từ 5 phút trong ngày. Kèm ngày để xem ngày đã qua",
                 ["/vang", "/vang hôm qua", "mình vừa inactive bao lâu", "hôm nay mình rời máy mấy lần"]),
    "gui_bao_cao": ("File báo cáo HTML chi tiết (biểu đồ theo giờ, khối tập trung). Kèm ngày để lấy ngày đã qua",
                    ["/report", "/report hôm qua"]),
    "xem_tuan": ("Tổng kết tuần: giờ vàng, ngày tốt/kém, issue lặp lại", ["/week"]),
    "xem_gio_vang": ("Khung giờ bạn tập trung tốt nhất 14 ngày qua, nên chặn lịch Outlook", ["/golden"]),
    "ghi_ke_hoach": ("Ghi kế hoạch hôm nay. Không kèm nội dung: bot hiện kế hoạch đã lưu rồi hỏi lại (gõ /cancel "
                     "để giữ nguyên). Xem lại kế hoạch: /today",
                     ["/plan fix job đối soát, viết spec API", "hôm nay mình sẽ fix job đối soát"]),
    "danh_sach_viec": ("Danh sách việc cần làm (như Google Tasks), một nơi chung cho /plan, /issue, /tmrtask. "
                       "Việc chưa xong tự sang hôm sau. Gõ thẳng không cần /viec cũng được: xong 1 3 · mới: việc mới · "
                       "hoãn 2 · bỏ 4 · sửa 2: chữ mới · ưu tiên 3 · hạn 2 25/11 · hoàn tác. /viec off: thôi tự hỏi",
                       ["/viec", "/viec xong 1 3", "/viec mới: test batch ABC; gửi mail SH", "/viec hoãn 2",
                        "/viec off", "danh sách việc hôm nay"]),
    "bao_tap_trung_sau": ("Giờ tập trung sâu tới lúc này so với nhịp cần, kèm AI nhận xét. Bot tự báo lúc 10:17, 12:45, "
                          "15:00 (12:45 gộp với hỏi cập nhật việc)",
                          ["/baosau", "/baosau off", "báo tập trung sâu"]),
    "ghi_output": ("Ghi việc vừa làm xong", ["/output xong test CL0123", "vừa xong deploy UAT"]),
    "ghi_issue": ("Ghi ngay khi bị chặn: VDI chậm, thiếu quyền, chờ người khác",
                  ["/issue VDI chậm từ 9h", "bị chặn vì thiếu quyền vào thư viện PRDLIB"]),
    "ghi_phan_tam": ("Ghi điều làm bạn mất tập trung", ["/distraction Zalo nhóm", "mất tập trung vì họp kéo dài",
                                                         "nãy giờ bận trông em bé khóc"]),
    "ghi_viec_ngay_mai": ("Việc đầu tiên sáng mai, sáng mai bot nhắc lại",
                          ["/tmrtask làm tiếp job đối soát", "mai làm tiếp spec API thanh toán"]),
    "ghi_nang_luong": ("Tự chấm sức lực hôm nay 1–5 (thường trả lời lúc tổng kết cuối ngày). AI dùng để tìm quy "
                       "luật năng lượng với số liệu tập trung. Không chấm thì 17:00 bot tự tính (/autoenergy). "
                       "Xem lại: /today", ["/energy 4"]),
    "tu_tinh_nang_luong": ("Tới giờ tổng kết mà bạn chưa chấm năng lượng: bot tự tính từ số liệu (tập trung càng sâu, "
                           "càng lâu thì càng cạn; sao nhãng thì còn dư) rồi báo kèm cách tính. Không kèm on/off: "
                           "xem công thức và số tính được lúc này",
                           ["/autoenergy", "/autoenergy off", "/autoenergy on", "bot tự tính năng lượng thế nào"]),
    "ghi_gio_as400": ("Giờ vào/ra AS400 (hoặc gửi ảnh spooled file, AI đọc giờ)",
                      ["/as400 08:10 17:35", "AS400 vào 8h10 ra 17h35"]),
    "tong_ket_ngay": ("Bot hỏi từng câu: output, issue, giờ AS400, việc mai, năng lượng", ["/review"]),
    "bao_nghi": ("Báo nghỉ để bot không nhắc gì ngày đó", ["/off", "/off 2026-12-24 nghỉ phép", "mai mình xin nghỉ phép"]),
    "nghi_phep": ("Nghỉ phép sáng / chiều / cả ngày: phần nghỉ không theo dõi, không nhắc; nửa ngày thì mục tiêu "
                  "còn một nửa. Cả ngày thì tracker tắt luôn, mai bật lại",
                  ["/leave sang", "/leave chieu mai đi khám", "/leave ca ngay 2026-12-24", "/nghiphep chieu thứ 6",
                   "hôm nay mình nghỉ nửa ngày sáng", "chiều nay nghỉ phép", "mai nghỉ phép cả ngày",
                   "thứ 6 nghỉ buổi chiều"]),
    "bao_di_lam": ("Huỷ ngày nghỉ / nghỉ phép đã báo", ["/on", "/on 2026-12-24"]),
    "tam_dung": ("Tạm dừng theo dõi (họp dài, việc riêng)", ["/pause", "tạm dừng theo dõi nhé"]),
    "tiep_tuc": ("Theo dõi lại", ["/resume"]),
    "hoi_ai": ("Hỏi AI bất cứ gì; AI biết bạn là ai, làm gì, và tra web cho giá vàng, tỷ giá, tin tức. "
               "/ask on: mọi tin nhắn thường đều gửi AI · /ask off: tắt",
               ["/ask giá vàng SJC hôm nay bao nhiêu", "/ask làm sao để kiếm thêm thu nhập", "/ask on"]),
    "xin_cau_dong_luc": ("Một câu nói truyền động lực", ["/quote"]),
    "xin_cau_kinh_thanh": ("Một câu Kinh Thánh Tin Lành khích lệ", ["/bible"]),
    "bat_tat_ai_danh_gia": ("Bật/tắt AI tự đánh giá cuối ngày (17:00) và cuối tuần",
                            ["/aireview", "/aireview off", "/aireview on"]),
    "cai_khich_le": ("Bật/tắt lời khích lệ tự động; chọn chỉ danh ngôn, chỉ Kinh Thánh hoặc cả hai",
                     ["/encourage off", "/encourage bible", "/encourage quote", "/encourage both"]),
    "bat_tat_kinh_thanh": ("Nút gạt Kinh Thánh: bật = lời chào sáng dùng Kinh Thánh, "
                           "tắt (mặc định khi cài lần đầu) = mọi tin dùng câu danh nhân, hiền triết",
                           ["/kinhthanh", "/kinhthanh off", "/kinhthanh on"]),
    "doi_giong": ("Đổi giọng bot và AI: than_mat, vui_tuoi, hai_huoc, sep_kho_tinh",
                  ["/style hai_huoc", "/style sep_kho_tinh", "/style mac_dinh"]),
    "doi_muc_nhac": ("Mức nhắc khi sao nhãng: off (tắt hẳn), nhe (1 lần/ngày), vua (1 lần mỗi lần sao nhãng, "
                     "mặc định), nghiem (nhắc lặp + đếm số lần, gắt hơn). Không kèm mức: xem mức hiện tại",
                     ["/nudge", "/nudge nghiem", "/nhac nhe", "/nudge off", "/nudge mac_dinh", "nhắc nghiêm khắc hơn",
                      "chỉ nhắc 1 lần mỗi ngày thôi", "tắt nhắc nhở sao nhãng"]),
    "canh_bao_tien_do": ("Tiến độ hôm nay: giờ làm thật trong VDI so với nhịp cần để đạt mục tiêu và về đúng giờ; "
                         "on/off bật tắt cảnh báo tự động ở các mốc",
                         ["/pace", "/pace off", "/tiendo on", "tiến độ hôm nay sao rồi", "tắt cảnh báo tiến độ"]),
    "nhac_nghi_ngoi": ("Nhắc đứng dậy đi lại, vươn vai, tập mắt 20-20-20 khi ngồi làm liên tục; bật/tắt hoặc đổi "
                       "số phút. Không phụ thuộc /nudge",
                       ["/break", "/break off", "/break 45", "/nghingoi on", "tắt nhắc đứng dậy",
                        "nhắc nghỉ mỗi 45 phút"]),
    "nhac_uong_nuoc": ("Nhắc uống nước trong giờ làm (trưa, nghỉ phép, khoá máy thì không); bật/tắt hoặc đổi số phút",
                       ["/water", "/water off", "/water 45", "/uongnuoc on", "nhắc uống nước", "tắt nhắc uống nước"]),
    "gio_bot": ("Giờ bot tự bật / tự tắt (thứ 2 – thứ 6). Không kèm giờ: xem. Đổi xong máy tự bật bot đúng giờ mới "
                "từ hôm sau (Task Scheduler / launchd); giờ tắt có hiệu lực ngay",
                ["/giobot", "/giobot 08:30 18:00", "/giobot bat 08:30", "/giobot tat 19:00", "/giobot mac_dinh",
                 "bật bot lúc 8 rưỡi", "tắt bot lúc 6 giờ chiều", "cho bot chạy từ 8h đến 18h"]),
    "chay_24_24": ("Chạy 24/24: bot bật 00:00 – tắt 24:00, chạy cả cuối tuần, ngày lễ (ngày nghỉ, ngoài giờ làm chỉ "
                   "ghi giờ làm trong VDI, không nhắc). Máy phải để không ngủ. off: về giờ cũ",
                   ["/chay247", "/chay247 on", "/chay247 off", "cho app chạy 24/24"]),
    "che_do_lam_bu": ("Chế độ làm bù (OT) như lam_bu_ngoai_gio: on = ngày nghỉ vẫn ghi giờ làm trong VDI, không nhắc; "
                      "off = chế độ thường (ngày nghỉ thì app tắt luôn). Giữ tới khi app tắt",
                      ["/lambu", "/lambu on", "/lambu off", "bật chế độ OT"]),
    "tat_app": ("Tắt hẳn app từ Telegram (luôn hỏi OK). Bật lại: start_tracker trên máy, hoặc máy tự bật giờ tự bật tới",
                ["/tatapp", "tắt app đi"]),
    "xem_ai": ("AI đang dùng model nào, đã gọi bao nhiêu lần, bao nhiêu từ", ["/aistatus"]),
    "xoa_cache_ai": ("Xoá cache model và nhận xét AI đã lưu (khi AI trả lời lạ)", ["/clearcache"]),
    "xem_hieu_nang": ("Tracker đang tốn bao nhiêu CPU/RAM", ["/perf"]),
    "huy": ("Huỷ thao tác đang chờ xác nhận hoặc đang hỏi dở", ["/cancel"]),
    "tro_giup": ("Hướng dẫn này", ["/help"]),
}

AUTO_FEATURES = """🎯 FOCUS TRACKER: bot theo dõi thời gian tập trung thật sự của bạn trong VDI.

BOT TỰ LÀM (bạn không cần gõ gì):
• Thứ 2 – thứ 6: tự bật lúc {start}, tự tắt lúc {stop} (/giobot để đổi). Cuối tuần, ngày lễ: không chạy (/chay247 on: chạy 24/24).
• Lần đầu dùng máy sau {plan}: chào buổi sáng + câu khích lệ / Kinh Thánh, nhắc việc hôm qua hẹn làm trước, rồi hỏi kế hoạch.
• Trong giờ làm {ws}–{we} (trừ trưa {ls}–{le}):
  – Sao nhãng (dùng app ngoài VDI, kể cả VDI bị thu nhỏ hoặc nằm sau app khác), mức {level} (/nudge): {nudge}.
  – Cảnh báo tiến độ lúc {pace}: giờ làm thật trong VDI chậm so với nhịp cần để đạt {target}h trước {we} thì nhắc ngay (/pace).
  – Rời máy quá {away} phút: nhắc; quay lại thì báo đã rời bao lâu.
  – Cửa sổ VDI biến mất (VDI tự ngắt khi không dùng 10–20 phút): báo ngay, ghi vào tổng kết ngày.
  – Ngồi làm liên tục {brk}: nhắc đứng dậy đi lại, vươn vai, tập mắt 20-20-20 (/break).
  – Uống nước: {water} (/water). Nhắc sức khoẻ vẫn chạy khi tắt nhắc sao nhãng.
  – Ngồi yên 1–5 phút nhiều lần (thường là điện thoại): nhắc cất điện thoại.
  – VDI không toàn màn hình lâu: gợi ý phóng to.
• {boost}: một câu khích lệ buổi chiều.
• {review}: hỏi tổng kết ngày (không trả lời cũng được).
• {summary}: tổng kết số liệu + AI đánh giá: việc pending ngày mai, vì sao mất tập trung, cần khắc phục gì, cải thiện gì.
• Thứ Sáu {weekly}: tổng kết tuần + AI phân tích.
• Ngoài giờ làm, cuối tuần, ngày lễ Singapore (lịch MOM, lễ rơi Chủ nhật thì nghỉ bù thứ Hai), ngày /off, /leave:
  không nhắc gì; ngày nghỉ cả ngày thì tracker tự tắt, ngày làm việc tới tự bật lại.
• Nghỉ phép nửa ngày (/leave sang hoặc /leave chieu): buổi đó không theo dõi, mục tiêu còn một nửa.

NÓI CHUYỆN VỚI BOT: gõ lệnh, hoặc nhắn tự nhiên. Nhắn tự nhiên mà có ghi dữ liệu, bot hỏi lại để bạn bấm ✅ OK, ✏️ Sửa lại hoặc ❌ Huỷ. Mất mạng hay AI lỗi, bot vẫn hiểu bằng từ khoá."""


def full_help(cfg):
    """/start, /help: mọi tính năng + mọi lệnh, kèm giải thích và ví dụ."""
    lines = [AUTO_FEATURES.format(
        plan=cfg["plan_prompt_after"], ws=cfg["work_start"], we=cfg["work_end"], ls=cfg["lunch_start"],
        le=cfg["lunch_end"], nudge=nudge_desc(cfg), level=NUDGE_NAMES[cfg.get("nudge_level", "vua")].split(" (")[0],
        pace=(", ".join(cfg["pace_checkpoints"]) if cfg.get("pace_check_enabled", True) else "(đã tắt)"),
        target=f"{cfg['pace_target_vdi_hours']:g}", away=cfg["away_alert_minutes"],
        brk=(f"{cfg['break_reminder_minutes']} phút" if cfg.get("break_reminder_enabled", True)
             and cfg["break_reminder_minutes"] else "(đã tắt)"),
        water=(f"mỗi {cfg['water_reminder_minutes']} phút" if cfg.get("water_reminder_enabled", True)
               and cfg.get("water_reminder_minutes") else "(đã tắt)"), boost=cfg["afternoon_boost_at"] or "(đã tắt)",
        review=cfg["review_prompt_at"], summary=cfg["daily_summary_at"], weekly=cfg["weekly_report_at"],
        start=cfg["auto_start_at"], stop=cfg["auto_stop_at"])]
    shown = set()
    for title, names in HELP_GROUPS:
        lines += ["", title]
        for name in names:
            a = BY_NAME.get(name)
            if not a or (name == "ghi_gio_as400" and not cfg.get("as400_enabled", True)):
                continue
            shown.add(name)
            desc, examples = EXAMPLES.get(name, (a.description, []))
            lines.append(f"{' '.join(a.commands)} — {desc}")
            if examples:
                lines.append("   Ví dụ: " + " · ".join(f"«{e}»" if not e.startswith("/") else e for e in examples))
    rest = [a for a in ACTIONS if a.commands and a.name not in shown and a.name != "ghi_gio_as400"]
    if rest:
        lines += ["", "KHÁC"] + [f"{' '.join(a.commands)} — {a.description}" for a in rest]
    lines += ["", "Chi tiết cài đặt: README.md trong thư mục app."]
    return "\n".join(lines)


def bot_commands():
    """Danh sách cho setMyCommands (menu lệnh trong Telegram)."""
    return [{"command": a.command[1:], "description": a.title[:256]} for a in ACTIONS if a.commands]


def catalog():
    """Mô tả gọn các action cho AI."""
    out = []
    for a in ACTIONS:
        params = {p[0]: f"{p[1]}: {p[2]}" + ("" if p[3] else " (không bắt buộc)") for p in a.params}
        if params.get("times"):
            params = {"start": "HH:MM giờ vào", "end": "HH:MM giờ ra (không bắt buộc)"}
        out.append({"action": a.name, "mo_ta": a.description, "tham_so": params})
    return out
