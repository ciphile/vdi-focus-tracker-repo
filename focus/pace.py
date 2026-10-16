"""Cảnh báo tiến độ: giờ làm THẬT trong VDI hôm nay so với nhịp cần để đạt mục tiêu trước giờ về.

- Giờ làm thật = analysis "vdi": VDI ở trước (hoặc app trong extra_focus_processes) và có dùng phím/chuột.
- Mục tiêu: pace_target_vdi_hours (mặc định 6h) trước work_end. Nghỉ phép nửa ngày: mục tiêu một nửa.
- Thời gian làm có được = giờ làm trừ nghỉ trưa (và trừ phần nghỉ phép). Mặc định 08:00–17:00 trừ 11:15–12:30 = 7,75h.
- Mức cần lúc hhmm = mục tiêu x (thời gian làm đã qua / tổng thời gian làm). Ví dụ 14:00: 6 x 4,75 / 7,75 ≈ 3,7h.
- Chậm khi thực tế < (1 - pace_behind_ratio) x mức cần (mặc định 0,6 x 3,7 ≈ 2,2h): nhắc ngay.
- Mốc kiểm tra pace_checkpoints (mặc định 10:30, 14:00, 15:30): mỗi mốc tối đa 1 lần/ngày (sent_log pace_1030...),
  chạy ở lần lấy mẫu đầu tiên từ mốc đó trong giờ làm (có ngồi máy hay không), trễ quá LATE_MINUTES thì bỏ.
  Mốc nằm trong phần nghỉ phép thì bỏ. Đúng nhịp ở mốc khen (đầu tiên từ PRAISE_AT) thì khen 1 câu, mốc khác im.

Hàm thuần (trừ today_status đọc DB) để test được mọi tình huống.
"""
from .schedule import _min, in_leave, is_work_time

LATE_MINUTES = 60
PRAISE_AT = "14:00"


def work_minutes(cfg, upto, leave=None):
    """Số phút làm việc từ work_start tới `upto` (HH:MM), trừ nghỉ trưa và phần nghỉ phép nửa ngày."""
    segs = [(cfg["work_start"], cfg["lunch_start"]), (cfg["lunch_end"], cfg["work_end"])]
    if cfg["lunch_start"] < cfg["work_start"] or cfg["lunch_end"] > cfg["work_end"]:
        segs = [(cfg["work_start"], cfg["work_end"])]  # trưa nằm ngoài giờ làm: không trừ
    if leave == "am":
        segs = [(max(a, cfg["lunch_end"]), b) for a, b in segs]
    elif leave == "pm":
        segs = [(a, min(b, cfg["lunch_start"])) for a, b in segs]
    total = 0
    for a, b in segs:
        b = min(b, upto)
        if b > a:
            total += _min(b) - _min(a)
    return total


def status(cfg, vdi_seconds, hhmm, leave=None):
    """Tiến độ lúc hhmm. Trả dict: at, actual_h, expected_h, target_h, behind (bool), behind_h, left_h,
    remaining_min, need_per_hour (phút VDI cần mỗi giờ còn lại), end, leave."""
    target = cfg["pace_target_vdi_hours"] / (2 if leave in ("am", "pm") else 1)
    total = work_minutes(cfg, cfg["work_end"], leave) or 1
    elapsed = work_minutes(cfg, hhmm, leave)
    remaining = total - elapsed
    expected = target * elapsed / total
    actual = (vdi_seconds or 0) / 3600
    left = max(target - actual, 0.0)
    return {"at": hhmm, "actual_h": actual, "expected_h": expected, "target_h": target,
            "behind": expected > 0 and actual < (1 - cfg["pace_behind_ratio"]) * expected,
            "behind_h": max(expected - actual, 0.0), "left_h": left, "remaining_min": remaining,
            "need_per_hour": left * 60 / (remaining / 60) if remaining > 0 else 0.0,
            "end": cfg["work_end"], "leave": leave}


def due_checkpoint(cfg, hhmm, off=None, leave=None):
    """Mốc kiểm tra tới hạn lúc hhmm (mốc gần nhất đã qua, trễ không quá LATE_MINUTES), hoặc None."""
    if off or not cfg.get("pace_check_enabled", True) or not is_work_time(cfg, hhmm, off, leave):
        return None
    passed = [cp for cp in cfg["pace_checkpoints"] if cp <= hhmm and not in_leave(cfg, cp, leave)]
    if not passed or _min(hhmm) - _min(passed[-1]) > LATE_MINUTES + _lunch_inside(cfg, passed[-1], hhmm):
        return None
    return passed[-1]


def _lunch_inside(cfg, a, b):
    """Số phút nghỉ trưa nằm giữa a và b (mốc trước trưa mà lần đầu ngồi máy là sau trưa vẫn chưa tính là trễ)."""
    lo, hi = max(a, cfg["lunch_start"]), min(b, cfg["lunch_end"])
    return max(_min(hi) - _min(lo), 0) if hi > lo else 0


def praise_checkpoint(cfg):
    """Mốc duy nhất được khen khi đúng nhịp: mốc đầu tiên từ PRAISE_AT (mặc định chính 14:00)."""
    return next((cp for cp in cfg["pace_checkpoints"] if cp >= PRAISE_AT), None)


def job_name(cp):
    return "pace_" + cp.replace(":", "")


def today_status(db, cfg, day, hhmm):
    """Tiến độ hôm nay đọc từ DB (mẫu đã ghi; tracker ghi DB mỗi phút nên trễ tối đa ~1 phút)."""
    from .analysis import analyze  # import trễ: analysis nặng, pace dùng cả ở config/test
    a = analyze(db, cfg, day)
    leave = a.get("leave")
    if hhmm < cfg["work_start"] or (leave and in_leave(cfg, hhmm, leave) and hhmm < cfg["lunch_end"]):
        return None
    return status(cfg, a.get("vdi", 0) if a.get("has_data") else 0, min(hhmm, cfg["work_end"]), leave)
