"""Cấu hình: mặc định trong code, ghi đè bằng config/settings.json, bí mật trong config/secrets.env.

Cấu hình sai (giờ không đúng dạng HH:MM, số âm...) thì báo lỗi rõ ràng ngay lúc khởi động,
không để tracker chạy với giá trị lạ.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
SECRETS_PATH = os.path.join(CONFIG_DIR, "secrets.env")

DEFAULTS = {
    "data_dir": "data",
    "report_dir": "reports",
    # Hệ điều hành: "auto" (tự nhận), "windows" hoặc "mac". Cách nhận cửa sổ VDI khác nhau trên mỗi hệ.
    "platform": "auto",
    "sample_seconds": 5,
    # Không chạm bàn phím/chuột lâu hơn mức này thì tính là "inactive".
    "idle_threshold_seconds": 60,
    # Inactive lâu hơn mức này (hoặc khoá màn hình) thì tính là "rời máy" trong báo cáo.
    "away_threshold_seconds": 300,
    # Hai đoạn làm trong VDI cách nhau không quá mức này thì vẫn tính là cùng một khối tập trung.
    "focus_gap_seconds": 120,
    "min_focus_block_minutes": 20,
    "daily_focus_goal_hours": 4,
    # Cách nhận ra cửa sổ VDI: tên process hoặc từ khoá trong tiêu đề cửa sổ.
    # Windows: citrix.desktopviewer.app.exe (Citrix Desktop Viewer bản mới, đã thấy trên máy thật), cdviewer.exe (bản cũ),
    # wfica32.exe, msrdc.exe/mstsc.exe (Remote Desktop).
    # Mac: "citrix viewer", "windows app", "microsoft remote desktop".
    "vdi_processes": ["citrix.desktopviewer.app.exe", "cdviewer.exe", "wfica32.exe", "msrdc.exe", "mstsc.exe",
                      "citrix viewer", "windows app", "microsoft remote desktop"],
    # Cửa sổ "mặt phiên" của Citrix (đã thấy trên máy thật: Citrix.EngineUI.App.exe, tiêu đề "MockWindow", tool window,
    # nằm đè lên vùng làm việc của Desktop Viewer). Gõ phím trong VDI thì cửa sổ này (hoặc Desktop Viewer) ở trước;
    # lúc VDI ở chế độ Full screen của Citrix, cửa sổ Desktop Viewer chính biến mất và chỉ còn nó.
    "vdi_session_processes": ["citrix.engineui.app.exe"],
    "vdi_title_keywords": ["Desktop Viewer"],
    # Citrix mở bằng trình duyệt (Citrix Workspace web, bản HTML5): tab VDI nằm trong Chrome/Edge/Safari,
    # nên chỉ nhận ra được qua tiêu đề tab (tab VDI mang tên máy ảo, ví dụ «AZ-WIN11-SGLIFE-REGULAR»).
    # Mặc định là phần đầu tên máy ảo VDI công ty, khớp mọi máy ảo AZ-WIN11-SGLIFE-...; máy ảo tên khác thì sửa
    # trong settings.json. Để trống [] = không tính tab trình duyệt nào là VDI. App Citrix không dùng khoá này.
    "vdi_browser_title_keywords": ["AZ-WIN11-SGLIFE"],
    "browser_processes": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
                          "google chrome", "microsoft edge", "safari", "firefox", "arc", "brave browser"],
    # App trên máy local cũng được tính là "đang làm việc" (ví dụ ["code.exe"]).
    "extra_focus_processes": [],
    # Lưu tiêu đề cửa sổ vào DB (mặc định không, chỉ lưu tên process).
    "store_window_titles": False,
    # Giờ làm việc: chỉ cảnh báo/nhắc trong khung này, trừ nghỉ trưa.
    "work_start": "08:00",
    "work_end": "17:00",
    "lunch_start": "11:15",
    "lunch_end": "12:30",
    # Tracker chạy trong khung này (Task Scheduler bật lúc auto_start_at, tracker tự thoát lúc auto_stop_at).
    "auto_start_at": "08:00",  # sớm quá có khi chưa mở laptop; Task Scheduler / launchd chỉ bật thứ 2 – thứ 6
    "auto_stop_at": "23:59",
    # Cuối tuần / lễ / ngày /off: tracker không chạy. Đặt true nếu muốn vẫn ghi số liệu.
    "run_on_off_days": False,
    "plan_prompt_after": "08:00",
    "review_prompt_at": "16:45",
    "daily_summary_at": "17:00",
    # Mức nhắc khi sao nhãng (ra ngoài VDI / thu nhỏ VDI mà vẫn dùng máy). Đổi nhanh qua Telegram: /nudge.
    #   "off"    tắt mọi nhắc sao nhãng (ngoài VDI, điện thoại, VDI không toàn màn hình); vẫn nhắc nghỉ giải lao,
    #            rời máy / quay lại (sức khoẻ, có mặt) và cảnh báo tiến độ (/pace, độc lập)
    #   "nhe"    chỉ 1 lần/ngày: lần sao nhãng đầu tiên kéo dài >= nudge_light_minutes; sau đó im cả ngày
    #   "vua"    (mặc định) mỗi lần sao nhãng >= nudge_out_of_vdi_minutes nhắc 1 lần, không nhắc lặp trong cùng lần
    #   "nghiem" nhắc sau nudge_strict_minutes, còn ở ngoài thì nhắc lại mỗi nudge_strict_minutes, kèm đếm số lần
    #            sao nhãng + tổng phút mất hôm nay
    # Nhận cả: tat, light, normal/medium, strict/chat.
    "nudge_level": "vua",
    # Ngưỡng mức "vua" (tên cũ giữ nguyên để settings.json cũ vẫn chạy; 0 = mức vua không nhắc).
    "nudge_out_of_vdi_minutes": 15,
    "nudge_light_minutes": 15,
    "nudge_strict_minutes": 5,
    # Cảnh báo khi rời máy (không chạm phím/chuột hoặc khoá máy) quá N phút (0 = tắt).
    "away_alert_minutes": 15,
    # Cửa sổ VDI biến mất trong giờ làm (Citrix tự ngắt sau 10–20 phút không dùng, hoặc bị đóng): báo ngay qua
    # Telegram, 1 lần mỗi lần mất, và ghi vào số liệu ngày (vdi_closed). Không báo lúc nghỉ trưa / ngoài giờ làm.
    "vdi_closed_alert": True,
    # Giờ vàng: "auto" = 2 giờ tập trung tốt nhất trong 14 ngày gần nhất (cần ≥ 5 ngày số liệu),
    # hoặc tự đặt ["09:00-11:00"], [] = tắt. Trong giờ vàng cảnh báo ngoài VDI chặt hơn.
    "golden_hours": "auto",
    "golden_nudge_minutes": 5,   # chỉ áp dụng cho mức vua / nghiem
    # Ngồi yên 1–5 phút trước VDI lặp lại >= N lần trong 30 phút: nhắc cất điện thoại (0 = tắt).
    "phone_pattern_count": 3,
    # VDI không toàn màn hình liên tục N phút trong giờ làm: gợi ý phóng to (1 lần/ngày, 0 = tắt).
    "fullscreen_tip_minutes": 15,
    # Nhắc đứng dậy, đi lại, vươn vai, tập mắt (20-20-20) khi ngồi làm liên tục N phút; chưa nghỉ thì nhắc lại mỗi
    # N phút (0 = tắt). Bật/tắt, đổi phút nhanh qua Telegram: /break on | off | 45.
    "break_reminder_enabled": True,
    "break_reminder_minutes": 60,
    # Nhắc uống nước mỗi N phút trong giờ làm (0 = tắt; không nhắc lúc trưa, nghỉ phép, khoá máy / rời máy: gửi khi
    # bạn quay lại). Trùng lúc nhắc nghỉ thì gộp vào một tin. Đổi nhanh: /water on | off | 45.
    # Nhắc nghỉ và uống nước là nhắc sức khoẻ: KHÔNG phụ thuộc nudge_level (/nudge off vẫn nhắc).
    # Mặc định TẮT khi cài lần đầu (giống Kinh Thánh: ai muốn thì tự bật bằng /water on).
    "water_reminder_enabled": False,
    "water_reminder_minutes": 60,
    # Cảnh báo tiến độ: tại mỗi mốc, giờ làm thật trong VDI (VDI ở trước + có dùng phím/chuột) so với nhịp cần
    # để đạt pace_target_vdi_hours trước work_end (thời gian làm trừ nghỉ trưa). Thực tế < (1 - pace_behind_ratio)
    # x mức cần lúc đó thì nhắc ngay; đúng nhịp ở mốc 14:00 thì khen 1 câu. Bật/tắt: /pace on|off.
    "pace_check_enabled": True,
    "pace_target_vdi_hours": 6,
    "pace_checkpoints": ["10:30", "14:00", "15:30"],
    "pace_behind_ratio": 0.4,
    # Tới giờ tổng kết (daily_summary_at) mà chưa chấm năng lượng (/energy, câu cuối tổng kết 16:45): bot tự tính
    # từ số liệu tập trung (focus/energy.py) và báo bạn. energy_capacity_hours: số giờ tập trung sâu một ngày thì
    # coi là cạn sức. Bật/tắt nhanh: /autoenergy on|off.
    "energy_auto_enabled": True,
    "energy_capacity_hours": 4,
    # Một câu khích lệ buổi chiều ("" = tắt).
    "afternoon_boost_at": "14:30",
    "weekly_report_day": "fri",
    "weekly_report_at": "16:50",
    # Làm mới file báo cáo HTML mỗi N phút (0 = chỉ tạo khi cần: /report, tổng kết, bao_cao_hom_nay.bat).
    "report_refresh_minutes": 0,
    # Lịch lễ Singapore có sẵn trong code. Nếu máy có app khác đã tải lịch lễ (file sg_holidays_<năm>.json)
    # thì điền thư mục đó vào đây để dùng chung. Ngày nghỉ thêm: ["2026-12-24"].
    "timesheet_data_dir": "",
    # Lịch lễ Singapore, thứ tự: data/holidays_<năm>.json > file sg_holidays_<năm>.json của timesheet > trang MOM > bảng 2026 có sẵn.
    # Tự tải từ trang MOM khi máy chưa có lịch năm đó (tối đa 1 lần/ngày; từ 1/12 tải năm sau).
    "holiday_fetch_enabled": True,
    "mom_holidays_url": "https://www.mom.gov.sg/employment-practices/public-holidays",
    "extra_off_days": [],
    # AI: auto = Gemini nếu có GEMINI_API_KEY, không thì Claude nếu có ANTHROPIC_API_KEY, "off" = tắt.
    "ai_provider": "auto",
    "gemini_model": "auto",
    "claude_model": "claude-opus-5-5",
    "ai_timeout_seconds": 60,
    # Hạn mức tự đặt số lượt gọi AI mỗi ngày, chỉ để /status hiện "còn bao nhiêu" (0 = không đặt).
    "ai_daily_call_budget": 0,
    # Ghi nguyên văn mọi prompt gửi AI + câu trả lời vào data/logs/ai-prompts-YYYY-MM-DD.log (xem lại khi AI trả lời
    # lạ). Giữ N ngày rồi housekeeping tự xoá (0 = không ghi).
    "ai_prompt_log_days": 14,
    # Gói free Gemini: khoảng 20 lượt gọi/ngày cho MỖI model. /status dùng số này để ước tính còn bao nhiêu.
    "gemini_free_calls_per_model": 20,
    # Cuối mỗi ngày làm việc (daily_summary_at) và cuối tuần (weekly_report_at), AI tự đọc báo cáo rồi nhắn
    # đánh giá: việc pending cho ngày mai, cần khắc phục gì, vì sao mất tập trung, nên cải thiện gì.
    # Người dùng không cần làm gì. Tắt/bật nhanh qua Telegram: /aireview off | /aireview on.
    "ai_review_enabled": True,
    # Bối cảnh công việc gửi kèm MỌI lần gọi AI (AI không nhớ gì giữa các lần gọi). Sửa cho đúng việc của bạn.
    "work_context": ("Lập trình viên/BA hệ thống lõi bảo hiểm nhân thọ Life Asia (LifeAsia, CSC/DXC) chạy trên "
                     "IBM i (AS400), viết bằng COBOL (ILE COBOL), CL, DB2 for i; việc hằng ngày gồm sửa và test "
                     "chương trình, batch job, spooled file, đối soát dữ liệu hợp đồng, xử lý yêu cầu nghiệp vụ "
                     "(phát hành, thu phí, bồi thường, đáo hạn); làm việc qua máy ảo VDI Citrix."),
    # Tự gửi lời khích lệ: đầu ngày (lần đầu dùng máy trong giờ làm, sau plan_prompt_after), buổi chiều
    # (afternoon_boost_at) và kèm cảnh báo. Bật/tắt nhanh qua Telegram: /encourage on | /encourage off.
    "encouragement_enabled": True,
    # Kiểu câu khích lệ: motivation (danh ngôn), bible (Kinh Thánh Tin Lành), family (vì gia đình).
    # Mặc định TẮT Kinh Thánh khi cài lần đầu: danh ngôn người thành đạt, danh nhân, hiền triết xưa + vì gia đình.
    # Bật Kinh Thánh: /kinhthanh on (hoặc ghi "encouragement_styles": ["bible"] trong settings.json).
    # Khác: /encourage quote (không Kinh Thánh), /encourage bible (chỉ Kinh Thánh), /encourage both.
    "encouragement_styles": ["motivation", "family"],
    # Ghi giờ vào/ra AS400 (dành cho ai làm AS400). Tắt thì bot không hỏi giờ AS400.
    "as400_enabled": True,
    # Cho phép gửi ảnh spooled file AS400 lên AI để đọc giờ. Xem cảnh báo trong README.
    "as400_photo_ai": True,
    # Dọn dẹp.
    "keep_samples_days": 35,   # mẫu thô ~0,55 MB/ngày làm việc; số liệu từng ngày giữ mãi trong daily_stats
    "keep_reports_days": 30,   # HTML tạo lại được từ DB
    "keep_db_backups": 3,      # bản .db.zip (nén ~3 lần)
    # Bí mật (đọc từ secrets.env hoặc biến môi trường).
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "gemini_api_key": "",
    "anthropic_api_key": "",
}

SECRET_KEYS = {"TELEGRAM_BOT_TOKEN": "telegram_bot_token", "TELEGRAM_CHAT_ID": "telegram_chat_id",
               "GEMINI_API_KEY": "gemini_api_key", "ANTHROPIC_API_KEY": "anthropic_api_key"}

TIME_KEYS = ("work_start", "work_end", "lunch_start", "lunch_end", "auto_start_at", "auto_stop_at",
             "plan_prompt_after", "review_prompt_at", "daily_summary_at", "weekly_report_at")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
STYLES = ("motivation", "bible", "family")
NUDGE_LEVELS = ("off", "nhe", "vua", "nghiem")
NUDGE_ALIASES = {"off": "off", "tat": "off", "tắt": "off", "false": "off", "0": "off",
                 "nhe": "nhe", "nhẹ": "nhe", "light": "nhe", "low": "nhe",
                 "vua": "vua", "vừa": "vua", "normal": "vua", "medium": "vua", "default": "vua",
                 "nghiem": "nghiem", "nghiêm": "nghiem", "strict": "nghiem", "chat": "nghiem", "chặt": "nghiem",
                 "high": "nghiem"}


def nudge_level(value):
    """Chuẩn hoá mức nhắc ("light" -> "nhe"...). Không nhận ra thì None."""
    return NUDGE_ALIASES.get(str(value).strip().lower().replace("_", " ").split(" ")[0]) if value is not None else None


class ConfigError(Exception):
    pass


# Việc theo giờ phải xảy ra TRƯỚC giờ tracker tự tắt (auto_stop_at). Dùng chung cho settings.json và /giobot.
STOP_AFTER_KEYS = ("daily_summary_at", "weekly_report_at", "review_prompt_at", "plan_prompt_after")


def run_window_conflict(cfg, start, stop):
    """Khung chạy start–stop (HH:MM đã chuẩn hoá) có hợp lệ không.
    Trả None nếu ổn; "auto_start_at" nếu start không trước stop; hoặc tên khoá giờ (trong STOP_AFTER_KEYS)
    rơi vào lúc tracker đã tắt."""
    if start >= stop:
        return "auto_start_at"
    for key in STOP_AFTER_KEYS:
        if cfg[key] >= stop:
            return key
    return None


def norm_hhmm(value):
    """"8:30" -> "08:30"; sai dạng (hoặc giờ > 24) -> None. Cùng luật với kiểm tra settings.json."""
    try:
        return _hhmm(value, "")
    except ConfigError:
        return None


def _hhmm(value, key):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value).strip())
    if not m or int(m.group(2)) > 59 or int(m.group(1)) > 24 or (int(m.group(1)) == 24 and m.group(2) != "00"):
        raise ConfigError(f'"{key}" phải có dạng HH:MM (ví dụ "08:00"), đang là "{value}".')
    return f"{int(m.group(1)):02d}:{m.group(2)}"


SECRET_QUOTES = " \t'\"`\u201c\u201d\u2018\u2019\u00ab\u00bb"  # nháy thẳng, nháy ngược, nháy cong, «»


def read_secrets(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            key = re.sub(r"^export\s+", "", key.strip(), flags=re.I).upper()  # "export X=..." / viết thường
            if sep and key in SECRET_KEYS:
                value = re.split(r"\s+#", value, maxsplit=1)[0]  # bỏ ghi chú cuối dòng: TOKEN=abc   # bot của tôi
                # Lỗi hay gặp: bọc giá trị trong dấu nháy ' " ''' `, ngoặc kép cong (Word, Notes trên Mac), dư dấu cách
                out[SECRET_KEYS[key]] = value.strip().strip(SECRET_QUOTES).strip()
    return out


def validate(cfg):
    """Chuẩn hoá và kiểm tra. Raise ConfigError với lời nhắn dễ hiểu."""
    for key in TIME_KEYS:
        cfg[key] = _hhmm(cfg[key], key)
    if cfg["afternoon_boost_at"]:
        cfg["afternoon_boost_at"] = _hhmm(cfg["afternoon_boost_at"], "afternoon_boost_at")
    for key in ("sample_seconds", "idle_threshold_seconds", "away_threshold_seconds", "focus_gap_seconds",
                "min_focus_block_minutes", "nudge_out_of_vdi_minutes", "away_alert_minutes",
                "break_reminder_minutes", "water_reminder_minutes", "report_refresh_minutes", "golden_nudge_minutes",
                "phone_pattern_count", "fullscreen_tip_minutes", "keep_samples_days",
                "keep_reports_days", "keep_db_backups", "ai_timeout_seconds", "ai_daily_call_budget", "gemini_free_calls_per_model",
                "ai_prompt_log_days"):
        if not isinstance(cfg[key], (int, float)) or isinstance(cfg[key], bool) or cfg[key] < 0:
            raise ConfigError(f'"{key}" phải là số ≥ 0, đang là {cfg[key]!r}.')
    for key in ("nudge_light_minutes", "nudge_strict_minutes"):
        if not isinstance(cfg[key], int) or isinstance(cfg[key], bool) or cfg[key] < 0:
            raise ConfigError(f'"{key}" phải là số nguyên ≥ 0 (phút), đang là {cfg[key]!r}.')
    level = nudge_level(cfg["nudge_level"]) if isinstance(cfg["nudge_level"], str) else None
    if level is None:
        raise ConfigError(f'"nudge_level" là một trong {list(NUDGE_LEVELS)} (hoặc light/normal/strict), '
                          f'đang là {cfg["nudge_level"]!r}.')
    cfg["nudge_level"] = level
    if not 1 <= cfg["sample_seconds"] <= 60:
        raise ConfigError('"sample_seconds" nên từ 1 đến 60.')
    if not isinstance(cfg["daily_focus_goal_hours"], (int, float)) or cfg["daily_focus_goal_hours"] <= 0:
        raise ConfigError('"daily_focus_goal_hours" phải là số > 0.')
    if cfg["keep_db_backups"] < 1 or cfg["keep_samples_days"] < 8:
        raise ConfigError('"keep_db_backups" ≥ 1 và "keep_samples_days" ≥ 8.')
    if cfg["work_start"] >= cfg["work_end"]:
        raise ConfigError('"work_start" phải trước "work_end".')
    if cfg["lunch_start"] > cfg["lunch_end"]:
        raise ConfigError('"lunch_start" phải trước "lunch_end".')
    bad = run_window_conflict(cfg, cfg["auto_start_at"], cfg["auto_stop_at"])
    if bad == "auto_start_at":
        raise ConfigError('"auto_start_at" phải trước "auto_stop_at".')
    if bad:  # tracker đã tắt thì việc này không bao giờ chạy
        raise ConfigError(f'"{bad}" ({cfg[bad]}) phải trước "auto_stop_at" ({cfg["auto_stop_at"]}), '
                          'nếu không tracker đã tắt trước giờ đó.')
    t = cfg["pace_target_vdi_hours"]
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not 0 < t <= 24:
        raise ConfigError(f'"pace_target_vdi_hours" phải là số giờ > 0, đang là {t!r}.')
    c = cfg["energy_capacity_hours"]
    if not isinstance(c, (int, float)) or isinstance(c, bool) or not 1 <= c <= 12:
        raise ConfigError(f'"energy_capacity_hours" phải là số giờ từ 1 đến 12 (ví dụ 4), đang là {c!r}.')
    r = cfg["pace_behind_ratio"]
    if not isinstance(r, (int, float)) or isinstance(r, bool) or not 0 < r < 1:
        raise ConfigError(f'"pace_behind_ratio" phải là số giữa 0 và 1 (ví dụ 0.4), đang là {r!r}.')
    cps = cfg["pace_checkpoints"]
    if not isinstance(cps, list):
        raise ConfigError('"pace_checkpoints" phải là danh sách giờ, ví dụ ["10:30", "14:00", "15:30"].')
    norm = []
    for cp in cps:
        cp = _hhmm(cp, "pace_checkpoints")
        if not cfg["work_start"] < cp < cfg["work_end"]:
            raise ConfigError(f'"pace_checkpoints": {cp} phải nằm trong giờ làm ({cfg["work_start"]}–{cfg["work_end"]}).')
        if cfg["lunch_start"] <= cp < cfg["lunch_end"]:
            raise ConfigError(f'"pace_checkpoints": {cp} rơi vào nghỉ trưa ({cfg["lunch_start"]}–{cfg["lunch_end"]}).')
        norm.append(cp)
    cfg["pace_checkpoints"] = sorted(set(norm))  # tự xếp theo giờ, bỏ trùng
    cfg["weekly_report_day"] = str(cfg["weekly_report_day"]).lower()[:3]
    if cfg["weekly_report_day"] not in WEEKDAYS:
        raise ConfigError(f'"weekly_report_day" phải là một trong {WEEKDAYS}.')
    for key in ("vdi_processes", "vdi_session_processes", "vdi_title_keywords", "extra_focus_processes", "extra_off_days",
                "encouragement_styles", "vdi_browser_title_keywords", "browser_processes"):
        if not isinstance(cfg[key], list) or not all(isinstance(x, str) for x in cfg[key]):
            raise ConfigError(f'"{key}" phải là danh sách chữ, ví dụ ["a", "b"].')
    cfg["vdi_processes"] = [p.lower() for p in cfg["vdi_processes"]]
    cfg["vdi_session_processes"] = [p.lower() for p in cfg["vdi_session_processes"]]
    cfg["vdi_title_keywords"] = [k.lower() for k in cfg["vdi_title_keywords"] if k.strip()]
    cfg["extra_focus_processes"] = [p.lower() for p in cfg["extra_focus_processes"]]
    cfg["vdi_browser_title_keywords"] = [k.lower().strip() for k in cfg["vdi_browser_title_keywords"] if k.strip()]
    cfg["browser_processes"] = [p.lower().strip() for p in cfg["browser_processes"] if p.strip()]
    cfg["encouragement_styles"] = [s for s in cfg["encouragement_styles"] if s in STYLES] or list(STYLES)
    for key in ("as400_enabled", "as400_photo_ai", "ai_review_enabled", "encouragement_enabled", "run_on_off_days", "store_window_titles", "holiday_fetch_enabled",
                "pace_check_enabled", "break_reminder_enabled", "water_reminder_enabled", "vdi_closed_alert",
                "energy_auto_enabled"):
        if not isinstance(cfg[key], bool):
            raise ConfigError(f'"{key}" phải là true hoặc false, đang là {cfg[key]!r}.')
    if not str(cfg["mom_holidays_url"]).startswith("https://"):
        raise ConfigError('"mom_holidays_url" phải là địa chỉ bắt đầu bằng https://')
    if not isinstance(cfg["work_context"], str):
        raise ConfigError('"work_context" phải là một đoạn chữ.')
    cfg["work_context"] = cfg["work_context"].strip()
    cfg["platform"] = str(cfg["platform"]).lower().strip()
    if cfg["platform"] in ("win", "win10", "win11", "windows10", "windows11"):
        cfg["platform"] = "windows"
    if cfg["platform"] in ("macos", "osx", "macbook", "darwin"):
        cfg["platform"] = "mac"
    if cfg["platform"] not in ("auto", "windows", "mac"):
        raise ConfigError('"platform" là "auto", "windows" hoặc "mac".')
    if str(cfg["ai_provider"]).lower() not in ("auto", "gemini", "claude", "off"):
        raise ConfigError('"ai_provider" là auto, gemini, claude hoặc off.')
    gh = cfg["golden_hours"]
    if gh != "auto":
        if not isinstance(gh, list):
            raise ConfigError('"golden_hours" là "auto", [] hoặc danh sách như ["09:00-11:00"].')
        ranges = []
        for item in gh:
            a, sep, b = str(item).partition("-")
            if not sep:
                raise ConfigError(f'"golden_hours": "{item}" phải có dạng "09:00-11:00".')
            a, b = _hhmm(a, "golden_hours"), _hhmm(b, "golden_hours")
            if a >= b:
                raise ConfigError(f'"golden_hours": "{item}" giờ bắt đầu phải trước giờ kết thúc.')
            ranges.append(f"{a}-{b}")
        cfg["golden_hours"] = ranges
    for key in SECRET_KEYS.values():
        cfg[key] = str(cfg.get(key) or "").strip()
    if cfg["telegram_bot_token"] and not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", cfg["telegram_bot_token"]):
        raise ConfigError("TELEGRAM_BOT_TOKEN trong config/secrets.env không đúng dạng (phải giống "
                          "123456789:AAH... do @BotFather cấp, không có dấu cách hay ghi chú).")
    if re.search(r"\s", cfg["gemini_api_key"]):
        raise ConfigError("GEMINI_API_KEY trong config/secrets.env có dấu cách ở giữa: chép lại nguyên key (giống "
                          "AIzaSy..., liền một mạch) từ trang Google AI Studio.")
    if cfg["telegram_chat_id"] and not re.fullmatch(r"-?\d+", cfg["telegram_chat_id"]):
        raise ConfigError("TELEGRAM_CHAT_ID trong config/secrets.env phải là một con số (bot trả khi bạn gõ /start).")
    return cfg


def load_config(settings_path=SETTINGS_PATH, secrets_path=SECRETS_PATH, env=None, make_dirs=True):
    env = os.environ if env is None else env
    cfg = dict(DEFAULTS)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8-sig") as f:
                user = json.load(f)
        except ValueError as e:
            raise ConfigError(f"{settings_path} sai cú pháp JSON: {e}")
        if not isinstance(user, dict):
            raise ConfigError(f"{settings_path} phải là một object JSON {{...}}.")
        unknown = [k for k in user if k not in DEFAULTS and not k.startswith("_")]
        cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        cfg["_unknown_keys"] = unknown
    cfg.update(read_secrets(secrets_path))
    for env_key, key in SECRET_KEYS.items():
        if not cfg.get(key) and env.get(env_key):
            cfg[key] = env[env_key]
    validate(cfg)
    # /giobot ghi lại giờ bật/tắt vào đúng file này, và chỉ cấu hình nạp từ đây mới được sửa lịch tự khởi động
    # của máy (Task Scheduler / launchd). Cấu hình dựng tay (test) không có 2 khoá này nên không đụng máy thật.
    cfg["_settings_path"] = settings_path
    cfg["_autostart_sync"] = True
    from .persona import load as load_persona  # import trễ: persona cũng import config
    cfg["persona"] = load_persona()
    for key in ("data_dir", "report_dir"):
        if not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(ROOT, cfg[key])
        if make_dirs:
            os.makedirs(cfg[key], exist_ok=True)
    return cfg
