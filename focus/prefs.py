"""Tuỳ chọn đổi nhanh qua Telegram, lưu trong DB (bảng prefs), đè lên settings.json / persona.json.

- ai_review_enabled: /aireview on|off   bật/tắt AI tự đánh giá cuối ngày, cuối tuần
- giong:             /style <giọng>     đổi giọng văn của bot và của AI
- encouragement_enabled, encouragement_styles: /encourage on|off|quote|bible|both
- ask_mode:          /ask on|off        mọi tin nhắn thường được gửi cho AI trả lời
- tg_name:           tên Telegram của bạn (AI gọi tên này nếu persona.json chưa có "ten")
- nudge_level:       /nudge off|nhe|vua|nghiem   mức nhắc khi sao nhãng
- pace_check_enabled: /pace on|off      cảnh báo tiến độ ở các mốc trong ngày
- energy_auto_enabled: /autoenergy on|off   bot tự tính năng lượng lúc tổng kết khi bạn chưa chấm
- break_enabled, break_minutes: /break on|off|45   nhắc đứng dậy, vận động, tập mắt khi ngồi lâu
- water_enabled, water_minutes: /water on|off|45   nhắc uống nước
- auto_start_at, auto_stop_at: /giobot 08:30 18:00   giờ bot tự bật / tự tắt (thứ 2 – thứ 6). Cũng ghi vào
  settings.json + lịch tự bật của máy (xem actions._giobot). hours_orig: giờ trong settings.json TRƯỚC lần đổi đầu
  tiên qua Telegram (để /giobot mac_dinh trả lại đúng như cũ).

Muốn quay về giá trị trong file cấu hình: /style mac_dinh, /aireview mac_dinh, /nudge mac_dinh, /pace mac_dinh,
/break mac_dinh, /water mac_dinh, /giobot mac_dinh, /autoenergy mac_dinh.
"""
import json

from . import persona
from .config import NUDGE_LEVELS, STYLES, norm_hhmm, run_window_conflict
from .logs import get_logger
from .storage import get_pref, set_pref

log = get_logger()
HOURS = ("auto_start_at", "auto_stop_at")


# Nhắc sức khoẻ: kind -> (khoá bật/tắt, khoá số phút) trong cfg.
HEALTH = {"break": ("break_reminder_enabled", "break_reminder_minutes"),
          "water": ("water_reminder_enabled", "water_reminder_minutes")}


def apply(cfg, db):
    """Đọc prefs từ DB và ghi đè vào cfg (gọi lúc khởi động bot)."""
    cfg.setdefault("_file_ai_review_enabled", cfg.get("ai_review_enabled", True))
    cfg.setdefault("_file_tone", (cfg.get("persona") or persona.DEFAULT).get("giong"))
    v = get_pref(db, "ai_review_enabled")
    if v in ("0", "1"):
        cfg["ai_review_enabled"] = v == "1"
    cfg.setdefault("_file_encouragement_enabled", cfg.get("encouragement_enabled", True))
    cfg.setdefault("_file_encouragement_styles", list(cfg.get("encouragement_styles") or []))
    v = get_pref(db, "encouragement_enabled")
    if v in ("0", "1"):
        cfg["encouragement_enabled"] = v == "1"
    styles = [x for x in (get_pref(db, "encouragement_styles") or "").split(",") if x in STYLES]
    if styles:
        cfg["encouragement_styles"] = styles
    cfg["ask_mode"] = get_pref(db, "ask_mode") == "1"
    cfg["_tg_name"] = get_pref(db, "tg_name") or ""
    cfg.setdefault("_file_nudge_level", cfg.get("nudge_level", "vua"))
    cfg.setdefault("_file_pace_check_enabled", cfg.get("pace_check_enabled", True))
    v = get_pref(db, "nudge_level")
    if v in NUDGE_LEVELS:
        cfg["nudge_level"] = v
    v = get_pref(db, "pace_check_enabled")
    if v in ("0", "1"):
        cfg["pace_check_enabled"] = v == "1"
    cfg.setdefault("_file_energy_auto_enabled", cfg.get("energy_auto_enabled", True))
    v = get_pref(db, "energy_auto_enabled")
    if v in ("0", "1"):
        cfg["energy_auto_enabled"] = v == "1"
    for kind in HEALTH:
        en, mins = HEALTH[kind]
        cfg.setdefault("_file_" + en, cfg.get(en, True))
        cfg.setdefault("_file_" + mins, cfg.get(mins, 60))
        v = get_pref(db, kind + "_enabled")
        if v in ("0", "1"):
            cfg[en] = v == "1"
        v = get_pref(db, kind + "_minutes")
        if v and v.isdigit() and int(v) > 0:
            cfg[mins] = int(v)
    tone = get_pref(db, "giong")
    if tone in persona.TONES:
        cfg["persona"] = dict(cfg.get("persona") or persona.DEFAULT, giong=tone)
    _apply_hours(cfg, db)
    return cfg


def _apply_hours(cfg, db):
    """Giờ bật/tắt bot đổi qua /giobot. Giờ lưu không còn hợp lệ (vd. settings.json vừa dời giờ tổng kết ra sau giờ
    tắt) thì bỏ qua, dùng settings.json, ghi log."""
    for key in HOURS:
        cfg.setdefault("_file_" + key, cfg.get(key))
    start = norm_hhmm(get_pref(db, "auto_start_at") or cfg["auto_start_at"])
    stop = norm_hhmm(get_pref(db, "auto_stop_at") or cfg["auto_stop_at"])
    if (start, stop) == (cfg["auto_start_at"], cfg["auto_stop_at"]):
        return
    bad = None if start and stop else "format"
    bad = bad or run_window_conflict(cfg, start, stop)
    if bad:
        log.warning("Giờ bot đổi qua Telegram (%s–%s) không còn hợp lệ (%s), dùng settings.json %s–%s.",
                    start, stop, bad, cfg["auto_start_at"], cfg["auto_stop_at"])
        return
    log.info("Giờ bot (đổi qua Telegram): bật %s – tắt %s.", start, stop)
    cfg.update({"auto_start_at": start, "auto_stop_at": stop})


def hours_changed(db):
    """True nếu giờ bật/tắt đang theo /giobot (không phải settings.json)."""
    return any(get_pref(db, k) for k in HOURS)


def hours_orig(db):
    """Giờ trong settings.json trước lần đổi đầu tiên qua /giobot: {khoá: "HH:MM" hoặc None (không có dòng đó)}."""
    try:
        data = json.loads(get_pref(db, "hours_orig") or "null")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def set_bot_hours(cfg, db, start, stop, orig=None):
    """Lưu giờ bật/tắt (đã kiểm tra). orig: giờ trong settings.json lúc này, chỉ ghi lần đổi đầu tiên.
    Không đổi cfg (nơi gọi đổi cfg sau cùng, xem actions._giobot: tracker đọc cfg mỗi vòng)."""
    if orig is not None and hours_orig(db) is None:
        set_pref(db, "hours_orig", json.dumps(orig))
    set_pref(db, "auto_start_at", start)
    set_pref(db, "auto_stop_at", stop)


def clear_bot_hours(db):
    for key in HOURS + ("hours_orig",):
        set_pref(db, key, None)


def set_ai_review(cfg, db, on):
    set_pref(db, "ai_review_enabled", "1" if on else "0")
    cfg["ai_review_enabled"] = bool(on)


def set_tone(cfg, db, tone):
    set_pref(db, "giong", tone)
    cfg["persona"] = dict(cfg.get("persona") or persona.DEFAULT, giong=tone)


def set_encouragement(cfg, db, mode):
    """mode: on | off | quote | bible | both | default."""
    from .motivation import MODES
    if mode == "default":
        set_pref(db, "encouragement_enabled", None)
        set_pref(db, "encouragement_styles", None)
        cfg["encouragement_enabled"] = bool(cfg.get("_file_encouragement_enabled", True))
        cfg["encouragement_styles"] = list(cfg.get("_file_encouragement_styles") or ["motivation", "family"])
        return
    if mode in ("on", "off"):
        set_pref(db, "encouragement_enabled", "1" if mode == "on" else "0")
        cfg["encouragement_enabled"] = mode == "on"
        return
    set_pref(db, "encouragement_enabled", "1")
    set_pref(db, "encouragement_styles", ",".join(MODES[mode]))
    cfg["encouragement_enabled"] = True
    cfg["encouragement_styles"] = list(MODES[mode])


def set_ask_mode(cfg, db, on):
    set_pref(db, "ask_mode", "1" if on else "0")
    cfg["ask_mode"] = bool(on)


def set_nudge_level(cfg, db, level):
    """level: off | nhe | vua | nghiem | default (về settings.json). Có hiệu lực ngay (tracker dùng chung cfg)."""
    if level == "default":
        set_pref(db, "nudge_level", None)
        cfg["nudge_level"] = cfg.get("_file_nudge_level") or "vua"
        return
    set_pref(db, "nudge_level", level)
    cfg["nudge_level"] = level


def set_pace_check(cfg, db, state):
    """state: on | off | default."""
    if state == "default":
        set_pref(db, "pace_check_enabled", None)
        cfg["pace_check_enabled"] = bool(cfg.get("_file_pace_check_enabled", True))
        return
    set_pref(db, "pace_check_enabled", "1" if state == "on" else "0")
    cfg["pace_check_enabled"] = state == "on"


def set_energy_auto(cfg, db, state):
    """state: on | off | default."""
    if state == "default":
        set_pref(db, "energy_auto_enabled", None)
        cfg["energy_auto_enabled"] = bool(cfg.get("_file_energy_auto_enabled", True))
        return
    set_pref(db, "energy_auto_enabled", "1" if state == "on" else "0")
    cfg["energy_auto_enabled"] = state == "on"


def set_health(cfg, db, kind, value):
    """kind: break | water. value: "on" | "off" | "default" | số phút (> 0, tự bật luôn)."""
    en, mins = HEALTH[kind]
    if value == "default":
        set_pref(db, kind + "_enabled", None)
        set_pref(db, kind + "_minutes", None)
        cfg[en] = bool(cfg.get("_file_" + en, True))
        cfg[mins] = cfg.get("_file_" + mins, 60)
        return
    if isinstance(value, int):
        set_pref(db, kind + "_minutes", str(value))
        cfg[mins] = value
        value = "on"
    set_pref(db, kind + "_enabled", "1" if value == "on" else "0")
    cfg[en] = value == "on"
    if cfg[en] and not cfg[mins]:  # settings.json để 0 phút mà bật lên: dùng 60 phút
        set_pref(db, kind + "_minutes", "60")
        cfg[mins] = 60
