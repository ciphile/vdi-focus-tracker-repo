"""Ngày lễ Singapore (theo lịch MOM) để tracker KHÔNG chạy ngày nghỉ.

Nguồn, theo thứ tự ưu tiên:
1. Cache riêng của app: data/holidays_<năm>.json ({"year", "dates": {ngày: tên}, "source", "fetched_at"}).
   Đọc thì kiểm: year đúng năm, mọi ngày bắt đầu bằng năm đó; sai thì bỏ qua file.
2. File lịch lễ app timesheet đã tải: <timesheet_data_dir>/sg_holidays_<năm>.json
   Đọc kiểu "chịu lỗi": lấy mọi chuỗi YYYY-MM-DD đúng năm trong file. Đọc được thì chép vào cache riêng.
3. Trang MOM (https://www.mom.gov.sg/employment-practices/public-holidays): CHỈ tải khi thiếu cache riêng,
   tối đa 1 lần/ngày mỗi năm, chạy ở việc nền (không chặn vòng lấy mẫu). Trang có nhiều năm: đọc bảng của
   từng năm theo tiêu đề năm, ngày nào lệch năm thì bỏ cả năm đó (không lưu).
4. Lịch 2026 có sẵn trong code (MOM 2026, 11 ngày). Không ghi vào cache, để vẫn thử lấy bản MOM.
5. "extra_off_days" trong config/settings.json: ngày nghỉ thêm bạn tự khai.

Ngày thường chỉ đọc file trên máy, không gọi mạng. Có cache riêng thì không bao giờ gọi mạng cho năm đó.
Từ 1/12: thử tải lịch năm sau (ensure_next_year_cached). Qua 15/12 vẫn thiếu: bot nhắc 1 lần (tracker).
Thiếu lịch năm nào thì coi như năm đó không có lễ (ghi cảnh báo), KHÔNG làm app sập.

Lễ rơi Chủ nhật -> thứ Hai kế tiếp được nghỉ bù; thứ Hai đó cũng là lễ thì nghỉ bù sang thứ Ba (và cứ thế).
Lễ rơi thứ Bảy -> không tự nghỉ (ngày nghỉ bù bạn tự chọn, báo bằng lệnh /off).
"""
import datetime as dt
import glob
import json
import os
import re
import time
import urllib.request
from html.parser import HTMLParser

from . import net
from .logs import audit, get_logger

log = get_logger()

MOM_URL = "https://www.mom.gov.sg/employment-practices/public-holidays"
FETCH_TIMEOUT = 20
MAX_PAGE_BYTES = 5 * 1024 * 1024
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36 FocusTracker")
MIN_DAYS_PER_YEAR = 5   # Singapore luôn có 11 ngày lễ: đọc ra ít hơn mức này là đọc sai trang
FETCH_STATE_FILE = "holiday_fetch.json"

BUILTIN = {
    2026: {
        "2026-01-01": "New Year's Day",
        "2026-02-17": "Chinese New Year",
        "2026-02-18": "Chinese New Year",
        "2026-03-21": "Hari Raya Puasa",
        "2026-04-03": "Good Friday",
        "2026-05-01": "Labour Day",
        "2026-05-27": "Hari Raya Haji",
        "2026-05-31": "Vesak Day",
        "2026-08-09": "National Day",
        "2026-11-08": "Deepavali",
        "2026-12-25": "Christmas Day",
    },
}

_memo = {}
_lenient = {}          # {năm: True} nếu lịch năm đó lấy từ file timesheet (xem observed)
_missing_checked = {}  # {ngày kiểm tra: kết quả} của next_year_missing: mỗi ngày đọc file / ghi cảnh báo 1 lần


# ------------------------------------------------------------ đọc file trên máy

def _own_path(cfg, year):
    return os.path.join(cfg["data_dir"], f"holidays_{year}.json")


def _read_own(cfg, year):
    """dict ngày của cache riêng, hoặc None nếu chưa có / sai định dạng / lệch năm."""
    path = _own_path(cfg, year)
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.warning("Cache lễ %s hỏng (%s), bỏ qua.", path, e)
        return None
    if (isinstance(payload, dict) and payload.get("year") == year and isinstance(payload.get("dates"), dict)
            and all(isinstance(d, str) and d.startswith(f"{year}-") for d in payload["dates"])):
        return {d: str(n or "Public Holiday") for d, n in payload["dates"].items()}
    log.warning("Cache lễ %s sai định dạng hoặc lệch năm, bỏ qua.", path)
    return None


def _write_own(cfg, year, dates, source):
    """Ghi cache riêng (ghi file tạm rồi đổi tên). Trả True nếu ghi được."""
    path = _own_path(cfg, year)
    payload = {"year": year, "dates": dict(sorted(dates.items())), "source": source,
               "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(path + ".tmp", path)
        log.info("Đã lưu lịch lễ %s (%d ngày, nguồn %s) vào %s", year, len(dates), source, path)
        return True
    except OSError as e:
        log.warning("Không ghi được cache lễ %s: %s", year, e)
        return False


_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")
_LOOSE_DATE = re.compile(r"(?<![\d-])\d{4}-\d{2}-\d{2}(?![\dT:])")  # JSON hỏng: ngày đứng riêng, không phải mốc giờ


def _json_dates(node, out, key=None, in_list=False):
    """Chỉ lấy ngày ở trường ngày thật: phần tử list, khoá dict là ngày, hoặc giá trị của khoá có chữ "date"/"day".
    Bỏ mốc thời gian ("2026-03-02T09:00") và ngày ở trường khác ("generated", "updated"...)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and _DATE_ONLY.fullmatch(k.strip()):
                out.add(k.strip())
            _json_dates(v, out, str(k).lower(), False)
    elif isinstance(node, list):
        for v in node:
            _json_dates(v, out, key, True)
    elif isinstance(node, str) and _DATE_ONLY.fullmatch(node.strip()):
        if in_list or (key is not None and ("date" in key or key in ("day", "ngay", "ngày"))):
            out.add(node.strip())


def _from_timesheet(cfg, year):
    folder = cfg.get("timesheet_data_dir")
    path = os.path.join(folder, f"sg_holidays_{year}.json") if folder else ""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = f.read()
    except OSError as e:
        log.warning("Không đọc được file lễ timesheet %s: %s", path, e)
        return None
    found = set()
    try:
        _json_dates(json.loads(raw), found)
    except ValueError:  # JSON hỏng: đọc "chịu lỗi" các ngày đứng riêng
        found = set(_LOOSE_DATE.findall(raw))
    dates = []
    for d in sorted(found):
        try:
            if d.startswith(f"{year}-") and dt.date.fromisoformat(d):
                dates.append(d)
        except ValueError:
            log.debug("File lễ timesheet %s: bỏ ngày không hợp lệ %s", path, d)
    if not dates:
        log.warning("File lễ timesheet %s không có ngày nào của năm %s, bỏ qua.", path, year)
        return None
    return {d: "Public Holiday" for d in dates}


def holidays(cfg, year):
    """dict {ngày ISO: tên} cho năm đó. Chỉ đọc file trên máy (không gọi mạng). Không bao giờ raise."""
    if year in _memo:
        return _memo[year]
    result = _read_own(cfg, year)
    lenient = result is not None and _own_source(cfg, year) == "timesheet"
    if result is None:
        result = _from_timesheet(cfg, year)
        if result:
            lenient = True
            _write_own(cfg, year, result, "timesheet")
    if result is None and year in BUILTIN:
        result = dict(BUILTIN[year])
        log.debug("Lịch lễ %s: dùng bảng có sẵn trong code (chưa có bản MOM).", year)
    if result:
        log.debug("Lịch lễ %s: %d ngày.", year, len(result))
    if result is None:
        log.warning("Chưa có lịch lễ năm %s: coi như không có lễ.", year)
        audit("HOLIDAYS_MISSING", year)
        result = {}
    _lenient[year] = lenient
    _memo[year] = result
    return result


def _own_source(cfg, year):
    try:
        with open(_own_path(cfg, year), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("source") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def available(cfg, year):
    """Có lịch lễ năm đó trên máy chưa (cache riêng, file timesheet hoặc bảng có sẵn). Không ghi cảnh báo."""
    return _read_own(cfg, year) is not None or bool(_from_timesheet(cfg, year)) or year in BUILTIN


def source_label(cfg, year):
    """Lịch lễ năm đó lấy từ đâu (cho /status). Không ghi cảnh báo, không gọi mạng."""
    try:
        with open(_own_path(cfg, year), encoding="utf-8") as f:
            src = (json.load(f) or {}).get("source")
        if _read_own(cfg, year) is not None:
            return {"mom": "trang MOM", "timesheet": "file app timesheet"}.get(src, "cache trên máy")
    except (OSError, ValueError, AttributeError):
        pass
    if _from_timesheet(cfg, year):
        return "file app timesheet"
    if year in BUILTIN:
        return "bảng có sẵn trong app (chưa tải được bản MOM)"
    return "CHƯA CÓ (coi như không có lễ)"


def next_holiday(cfg, day, within_days=45):
    """(ngày, tên) của ngày lễ / nghỉ bù gần nhất từ day (tính cả day) trong within_days ngày, hoặc None."""
    d = dt.date.fromisoformat(day) if isinstance(day, str) else day
    for i in range(within_days + 1):
        n = d + dt.timedelta(days=i)
        if n.year != d.year and not available(cfg, n.year):
            return None
        hol = holidays(cfg, n.year)
        if n.isoformat() in hol:
            return n, hol[n.isoformat()]
        obs = observed(hol, _lenient.get(n.year, False))
        if n.isoformat() in obs:
            return n, f"nghỉ bù {obs[n.isoformat()]}"
    return None


IN_LIEU_WORDS = ("observed", "in lieu", "in-lieu", "nghỉ bù", "nghi bu", "replacement")


def observed(hol, listed_in_lieu=False):
    """Ngày nghỉ bù: lễ rơi Chủ nhật -> thứ Hai kế tiếp; thứ Hai đó cũng là lễ (hoặc đã là ngày bù) -> thứ Ba...
    Thứ Hai đã có trong danh sách chính là ngày bù (không dời sang thứ Ba) khi: tên có chữ observed / in lieu /
    nghỉ bù, hoặc listed_in_lieu=True (lịch lấy từ file timesheet: file này liệt kê sẵn cả ngày bù)."""
    out = {}
    for day in sorted(hol):
        d = dt.date.fromisoformat(day)
        if d.weekday() != 6:
            continue
        n = d + dt.timedelta(days=1)
        mon = hol.get(n.isoformat())
        if mon is not None and (listed_in_lieu or any(w in str(mon).lower() for w in IN_LIEU_WORDS)):
            continue  # ngày bù đã được liệt kê sẵn: không dời thêm
        while n.isoformat() in hol or n.isoformat() in out:
            n += dt.timedelta(days=1)
        out[n.isoformat()] = hol[day]
    return out


def off_detail(cfg, day):
    """(loại, lý do) nếu là ngày nghỉ, hoặc (None, None).
    loại: weekend | config | holiday | observed (nghỉ bù lễ rơi Chủ nhật)."""
    d = dt.date.fromisoformat(day) if isinstance(day, str) else day
    if d.weekday() >= 5:
        return "weekend", "cuối tuần"
    if d.isoformat() in cfg.get("extra_off_days", []):
        return "config", "ngày nghỉ bạn khai trong config"
    hol = holidays(cfg, d.year)
    if d.isoformat() in hol:
        return "holiday", hol[d.isoformat()]
    obs = observed(hol, _lenient.get(d.year, False))
    if d.isoformat() in obs:
        return "observed", f"nghỉ bù {obs[d.isoformat()]}"
    return None, None


def off_reason(cfg, day):
    """Lý do ngày nghỉ (str), hoặc None nếu là ngày làm việc."""
    return off_detail(cfg, day)[1]


def next_year_missing(cfg, today=None):
    """True nếu đã qua 15/12 mà vẫn chưa có lịch lễ năm sau (để bot nhắc 1 lần)."""
    today = today or dt.date.today()
    if (today.month, today.day) < (12, 15):
        return False
    if today not in _missing_checked:
        # Mỗi ngày kiểm lại 1 lần (để thấy file lịch mới tải), không đọc file + ghi log mỗi 30 giây.
        _memo.pop(today.year + 1, None)
        _missing_checked.clear()
        _missing_checked[today] = not holidays(cfg, today.year + 1)
    return _missing_checked[today]


# ------------------------------------------------------------ đọc trang MOM (chỉ thư viện chuẩn)

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
          "nov": 11, "dec": 12}
_DAYS = r"(?:\d{1,2}(?:st|nd|rd|th)?\s*(?:&|and|,|-|–|—|to)\s*)*\d{1,2}(?:st|nd|rd|th)?"
_MON = r"[A-Za-z]{3,9}\.?"
DAY_FIRST_RE = re.compile(r"(?<!\d)(" + _DAYS + r")\s+(" + _MON + r")(?:,?\s+(\d{4}))?(?!\d)")
MONTH_FIRST_RE = re.compile(r"\b(" + _MON + r")\s+(" + _DAYS + r")(?:,?\s+(\d{4}))?(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
ID_YEAR_RE = re.compile(r"(?i)year[-_ ]?(20\d{2})\b")
WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


FULL_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december")


def _month(word):
    """'Jan', 'January', 'Sept.' -> số tháng; chữ khác (Thursday, day...) -> None."""
    w = word.lower().rstrip(".")
    if w in FULL_MONTHS:
        return FULL_MONTHS.index(w) + 1
    if w in MONTHS:
        return MONTHS[w]
    return 9 if w == "sept" else None


def _day_list(text):
    """'17 & 18' -> [17, 18]; '17-19' -> [17, 18, 19]."""
    nums = [int(n) for n in re.findall(r"\d{1,2}", text)]
    if len(nums) == 2 and re.search(r"\d\s*(?:-|–|—|to)\s*\d", text):
        a, b = nums
        return list(range(a, b + 1)) if 0 < b - a < 10 else nums
    return nums


def parse_dates(text, default_year=None):
    """Các ngày trong một ô: '1 Jan 2026', '1 January 2026', '17 & 18 Feb 2026', 'Jan 1, 2026', 'Thursday, 1 Jan'.
    Thiếu năm thì lấy năm của mốc khác trong ô, không có thì default_year. Trả list dt.date (có thể rỗng).
    Raise ValueError nếu ô có ngày không hợp lệ (31 Feb...)."""
    text = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    found = []  # (vị trí, [ngày], tháng, năm hoặc None)
    for rx, day_first in ((DAY_FIRST_RE, True), (MONTH_FIRST_RE, False)):
        for m in rx.finditer(text):
            days, mon = (m.group(1), m.group(2)) if day_first else (m.group(2), m.group(1))
            month = _month(mon)
            if not month:
                continue
            found.append((m.start(), _day_list(days), month, int(m.group(3)) if m.group(3) else None))
        if found:
            break
    found.sort()
    out = []
    for i, (_, days, month, year) in enumerate(found):
        if year is None:  # "31 Jan & 1 Feb 2027": năm nằm ở mốc sau
            year = next((y for _, _, _, y in found[i + 1:] if y), None) or default_year
        if year is None:
            continue
        for d in days:
            out.append(dt.date(year, month, d))
    return out


def _has_date(text):
    try:
        return bool(parse_dates(text, 2000))
    except ValueError:
        return True


class _MomParser(HTMLParser):
    """Gom theo thứ tự trang: chữ ngắn có năm (tiêu đề / tab) và các bảng (mỗi bảng: list hàng, mỗi hàng list ô)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []      # ("year", năm) | ("table", rows, năm của caption hoặc None)
        self.depth = 0        # bảng lồng nhau: chỉ gom bảng ngoài cùng
        self.rows = None
        self.cell = None
        self.caption = None
        self.text = []        # chữ ngoài bảng của phần tử đang đọc
        self.skip = 0         # trong <script>/<style>

    def handle_starttag(self, tag, attrs):
        m = ID_YEAR_RE.search(dict(attrs).get("id") or "") if self.depth == 0 else None
        if m:  # <div id="Year-2026">: nhãn năm chắc chắn (trang MOM thật dùng kiểu này)
            self._flush_text()
            self.events.append(("anchor", int(m.group(1))))
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag == "table":
            self._flush_text()
            self.depth += 1
            if self.depth == 1:
                self.rows, self.caption = [], None
        elif self.depth == 1 and tag == "tr":
            self.rows.append([])
        elif self.depth == 1 and tag in ("td", "th"):
            if not self.rows:
                self.rows.append([])
            self.cell = []
        elif self.depth == 1 and tag == "caption":
            self.caption = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")
        elif self.depth == 0 and tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "button", "a",
                                         "span", "strong", "b", "summary", "section", "label"):
            self._flush_text()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self._end_cell()
                cap = " ".join(self.caption or [])
                years = set(YEAR_RE.findall(cap))
                self.events.append(("table", [r for r in self.rows if any(c.strip() for c in r)],
                                    int(years.pop()) if len(years) == 1 else None))
                self.rows, self.caption = None, None
        elif self.depth == 1 and tag in ("td", "th"):
            self._end_cell()
        elif self.depth == 1 and tag == "caption":
            self.caption = self.caption if self.caption is not None else []
        elif self.depth == 0:
            self._flush_text()

    def _end_cell(self):
        if self.cell is not None and self.rows is not None:
            self.rows[-1].append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
        self.cell = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.depth >= 1:
            if self.cell is not None:
                self.cell.append(data)
            elif self.caption is not None and self.depth == 1:
                self.caption.append(data)
        else:
            self.text.append(data)

    def _flush_text(self):
        text = re.sub(r"\s+", " ", "".join(self.text)).strip()
        self.text = []
        if not text or len(text) > 80:
            return
        years = set(YEAR_RE.findall(text))
        # Tiêu đề năm: đúng 1 năm, không phải một ngày ("Cập nhật 1 Jan 2026" không tính).
        if len(years) == 1 and not _has_date(text):
            self.events.append(("year", int(years.pop())))

    def close(self):
        super().close()
        self._flush_text()


def _table_dates(rows, year):
    """Hàng của một bảng lễ -> {ngày ISO: tên}. year: năm của bảng (để điền ngày thiếu năm)."""
    name_col = date_col = None
    start = 0
    for i, row in enumerate(rows[:3]):  # dòng tiêu đề: "Holiday | Date | Day"
        low = [c.lower() for c in row]
        dc = next((j for j, c in enumerate(low) if "date" in c), None)
        nc = next((j for j, c in enumerate(low) if "name" in c), None)  # "Holiday name" (không lấy cột "Holiday image")
        if nc is None:
            nc = next((j for j, c in enumerate(low) if "holiday" in c or c == "event"), None)
        if dc is not None and nc is not None and dc != nc:
            name_col, date_col, start = nc, dc, i + 1
            break
    out = {}
    for row in rows[start:]:
        if date_col is not None and len(row) > max(name_col, date_col):
            dates = parse_dates(row[date_col], year)
            name = row[name_col]
        else:  # không có tiêu đề: ô đầu tiên có ngày là ngày, ô chữ còn lại là tên
            dates, name = [], ""
            for cell in row:
                if not dates:
                    dates = parse_dates(cell, year)
                    if dates:
                        continue
                if not name and re.search(r"[A-Za-z]{3}", cell) and cell.lower().strip(" ,.") not in WEEKDAY_NAMES:
                    name = cell
        # Ô tên trang MOM còn chứa lại ngày + ghi chú ("Vesak Day31 May 2026, Sunday Monday, 1 June..."): cắt từ ngày đầu tiên
        name = re.split(r"\s*\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", name or "", 1)[0]
        name = re.sub(r"[\*†‡]+", "", name).strip(" ,.") or "Public Holiday"
        for d in dates:
            out[d.isoformat()] = name
    return out


def parse_mom(html):
    """Trang MOM -> ({năm: {ngày: tên}} các năm đọc đúng, {năm bị loại: lý do}).
    Mỗi bảng thuộc năm của tiêu đề ngay trước nó (hoặc caption). Ngày nào lệch năm -> loại cả năm đó."""
    p = _MomParser()
    p.feed(html)
    p.close()
    years, rejected = {}, {}
    pending = []          # nhãn năm YẾU (chữ quanh bảng, dải tab "2025 2026 2027"), chia lần lượt cho các bảng
    anchor_id = None      # nhãn năm CHẮC (id="Year-2026" ngay trước bảng)
    after_table = False
    for ev in p.events:
        if ev[0] == "anchor":
            anchor_id = ev[1]
            continue
        if ev[0] == "year":
            if after_table:
                pending, after_table = [], False
            pending.append(ev[1])
            continue
        _, rows, cap_year = ev
        after_table = True
        strong = cap_year or anchor_id
        weak = pending.pop(0) if len(pending) > 1 else (pending[0] if pending else None)
        anchor_id = None
        try:
            dates = _table_dates(rows, strong or weak)
        except ValueError as e:
            if strong or weak:
                rejected[strong or weak] = f"ngày không hợp lệ: {e}"
            continue
        if not dates:
            continue
        own = {d[:4] for d in dates}
        if len(own) != 1:  # một bảng lẫn nhiều năm: không tin bảng này
            label = strong or weak or int(min(own))
            rejected[label] = f"bảng năm {label} có ngày lệch năm: {', '.join(sorted(dates)[:3])}"
            continue
        own_year = int(own.pop())
        if strong and strong != own_year:  # nhãn chắc chắn mà lệch: loại, không đoán
            rejected[strong] = f"bảng năm {strong} có ngày lệch năm: {', '.join(sorted(dates)[:3])}"
            continue
        if weak and weak != own_year and not strong:
            log.debug("Nhãn năm quanh bảng (%s) khác năm của các ngày (%s): dùng năm của ngày", weak, own_year)
        years.setdefault(own_year, {}).update(dates)
    for y in list(years):
        if y in rejected:
            years.pop(y)
        elif len(years[y]) < MIN_DAYS_PER_YEAR:
            rejected[y] = f"chỉ đọc được {len(years[y])} ngày"
            years.pop(y)
    return years, rejected


def _download(url, timeout=FETCH_TIMEOUT):
    """Tải trang (tách riêng để test thay bằng bản giả: test không bao giờ gọi mạng thật)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8",
                                               "Accept-Language": "en-SG,en;q=0.9"})
    with net.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_PAGE_BYTES + 1)
        charset = r.headers.get_content_charset() or "utf-8"
    if len(data) > MAX_PAGE_BYTES:
        raise ValueError("trang MOM lớn bất thường")
    return data.decode(charset, "replace")


def fetch_mom(cfg):
    """Tải + đọc trang MOM. Trả {năm: {ngày: tên}} các năm hợp lệ. Lỗi mạng / trang đổi cấu trúc -> raise."""
    url = cfg.get("mom_holidays_url") or MOM_URL
    t0 = time.monotonic()
    html = _download(url, FETCH_TIMEOUT)
    years, rejected = parse_mom(html)
    for y, why in sorted(rejected.items()):
        log.warning("Lịch lễ MOM năm %s bị loại: %s", y, why)
        audit("HOLIDAYS_REJECTED", f"{y}: {why}")
    log.info("Đọc trang MOM (%d KB, %.1fs): các năm %s", len(html) // 1024, time.monotonic() - t0,
             sorted(years) or "không có")
    if not years:
        raise ValueError("không đọc được bảng lễ nào trên trang MOM (trang đổi cấu trúc?)")
    return years


# ------------------------------------------------------------ lấy lịch thiếu (gọi từ việc nền)

def _state_path(cfg):
    return os.path.join(cfg["data_dir"], FETCH_STATE_FILE)


def _read_state(cfg):
    try:
        with open(_state_path(cfg), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _mark_attempt(cfg, year, today):
    data = _read_state(cfg)
    data[str(year)] = today.isoformat()
    data = {k: v for k, v in data.items() if k.isdigit() and int(k) >= today.year - 1}
    try:
        with open(_state_path(cfg), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        log.warning("Không ghi được %s: %s", _state_path(cfg), e)


def ensure_year(cfg, year, today=None):
    """Có cache riêng năm đó thì thôi (không gọi mạng). Thiếu thì tải MOM, tối đa 1 lần/ngày.
    Lưu mọi năm hợp lệ trên trang mà máy chưa có. Trả True nếu năm đó đã có cache riêng. Không raise."""
    today = today or dt.date.today()
    try:
        if _read_own(cfg, year) is not None:
            return True
        if not cfg.get("holiday_fetch_enabled", True):
            log.debug("Tải lịch lễ MOM đang tắt (holiday_fetch_enabled), bỏ qua năm %s.", year)
            return False
        if _read_state(cfg).get(str(year)) == today.isoformat():
            log.debug("Hôm nay đã thử tải lịch lễ %s từ MOM rồi, mai thử lại.", year)
            return False
        _mark_attempt(cfg, year, today)
        log.info("Chưa có lịch lễ %s trên máy: tải từ trang MOM.", year)
        try:
            years = fetch_mom(cfg)
        except Exception as e:
            log.warning("Không tải được lịch lễ %s từ MOM: %s: %s. Sẽ thử lại lần chạy sau (tối đa 1 lần/ngày).",
                        year, type(e).__name__, e)
            audit("HOLIDAYS_FETCH_FAIL", f"{year}: {type(e).__name__}: {e}")
            return False
        for y, dates in sorted(years.items()):
            if _read_own(cfg, y) is None and _write_own(cfg, y, dates, "mom"):
                _memo.pop(y, None)
                audit("HOLIDAYS_FETCHED", f"{y}: {len(dates)} ngày từ MOM")
        if year in years:
            _missing_checked.clear()
            return _read_own(cfg, year) is not None
        log.warning("Trang MOM chưa có lịch lễ năm %s (có: %s). Sẽ thử lại sau.", year, sorted(years))
        audit("HOLIDAYS_FETCH_FAIL", f"{year}: trang MOM chưa có năm này")
        return False
    except Exception as e:  # lớp cuối: việc lấy lịch lễ không bao giờ làm tracker sập
        log.error("Lỗi khi lấy lịch lễ %s: %s", year, e, exc_info=True)
        return False


def ensure_next_year_cached(cfg, today=None):
    """Lớp 1: từ 1/12, chưa có lịch năm sau thì thử tải MOM (lỗi: cảnh báo + audit, lần chạy sau thử lại)."""
    today = today or dt.date.today()
    if today.month != 12:
        return False
    return ensure_year(cfg, today.year + 1, today)


def background_check(cfg, today=None):
    """Việc nền lúc tracker khởi động: năm nay chưa có cache riêng (đang dùng bảng có sẵn) thì lấy bản MOM;
    tháng 12 thì lấy năm sau. Không raise."""
    today = today or dt.date.today()
    try:
        ensure_year(cfg, today.year, today)
        ensure_next_year_cached(cfg, today)
    except Exception as e:
        log.error("Lỗi kiểm tra lịch lễ: %s", e, exc_info=True)


def ensure_today_known(cfg, today=None):
    """Lúc tracker khởi động: năm nay KHÔNG có lịch nào trên máy (kể cả bảng có sẵn) thì tải MOM ngay
    (chặn tối đa FETCH_TIMEOUT giây, tối đa 1 lần/ngày) để không lỡ chạy vào ngày lễ. Không raise."""
    today = today or dt.date.today()
    try:
        if available(cfg, today.year):
            return True
        ok = ensure_year(cfg, today.year, today)
        if ok:
            _memo.pop(today.year, None)
        return ok
    except Exception as e:
        log.error("Lỗi kiểm tra lịch lễ năm nay: %s", e, exc_info=True)
        return False


def prune(cfg, keep_years=2):
    """Xoá cache lễ cũ hơn keep_years năm. Không đụng năm nay và năm sau."""
    removed = []
    this_year = dt.date.today().year
    for path in glob.glob(os.path.join(cfg["data_dir"], "holidays_*.json")):
        m = re.search(r"holidays_(\d{4})\.json$", path)
        if m and int(m.group(1)) < this_year - keep_years:
            os.remove(path)
            removed.append(os.path.basename(path))
    return removed


def clear_memo():
    _memo.clear()
    _lenient.clear()
    _missing_checked.clear()
