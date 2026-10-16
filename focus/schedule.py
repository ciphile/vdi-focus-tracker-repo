"""Giờ giấc: khung chạy của tracker, giờ làm, nghỉ trưa, nghỉ phép nửa ngày, và các việc theo giờ trong ngày.

Tất cả là hàm thuần (không đọc đồng hồ, không đụng DB) để test được mọi tình huống.
Giờ dạng "HH:MM" đã được config chuẩn hoá 2 chữ số, nên so sánh chuỗi là đúng thứ tự thời gian.

Nghỉ phép nửa ngày (leave = "am" | "pm", ghi chú leave_part):
- Sáng: không theo dõi từ đầu ngày tới hết nghỉ trưa (lunch_end). Chào buổi sáng + hỏi kế hoạch dời tới lúc
  bạn bắt đầu làm buổi chiều (lần đầu dùng máy sau lunch_end). Tổng kết giữ giờ cũ.
- Chiều: không theo dõi từ lunch_start. Hỏi tổng kết + gửi tổng kết ngày (và tổng kết tuần nếu là ngày gửi
  tuần) dời lên trước lúc nghỉ: tổng kết lúc lunch_start, hỏi tổng kết sớm hơn chừng đó phút như ngày thường
  (mặc định 17:00 - 16:45 = 15 phút, tối đa 60). Khích lệ buổi chiều bỏ.
"""
from .config import WEEKDAYS

LEAVE_NAMES = {"am": "nghỉ phép buổi sáng", "pm": "nghỉ phép buổi chiều"}


def _min(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _hhmm(minutes):
    minutes = max(0, minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def in_run_window(cfg, hhmm):
    return cfg["auto_start_at"] <= hhmm < cfg["auto_stop_at"]


def is_lunch(cfg, hhmm):
    return cfg["lunch_start"] <= hhmm < cfg["lunch_end"]


def in_leave(cfg, hhmm, leave):
    """Đang trong phần nghỉ phép nửa ngày (không theo dõi, không cảnh báo)."""
    if leave == "am":
        return hhmm < cfg["lunch_end"]
    if leave == "pm":
        return hhmm >= cfg["lunch_start"]
    return False


def is_work_time(cfg, hhmm, off=None, leave=None):
    """Trong giờ làm, không phải nghỉ trưa, không phải ngày nghỉ / phần nghỉ phép: chỉ lúc này mới cảnh báo."""
    return (not off and not in_leave(cfg, hhmm, leave) and cfg["work_start"] <= hhmm < cfg["work_end"]
            and not is_lunch(cfg, hhmm))


def job_times(cfg, leave=None):
    """Giờ của các việc theo lịch trong ngày, đã dời theo nghỉ phép nửa ngày (xem đầu file)."""
    t = {"plan": cfg["plan_prompt_after"], "review": cfg["review_prompt_at"], "summary": cfg["daily_summary_at"],
         "weekly": cfg["weekly_report_at"], "boost": cfg["afternoon_boost_at"], "end": cfg["work_end"]}
    if leave == "am":
        t["plan"] = max(t["plan"], cfg["lunch_end"])
        if t["boost"]:
            t["boost"] = max(t["boost"], cfg["lunch_end"])
    elif leave == "pm":
        end = cfg["lunch_start"]
        lead = min(max(_min(cfg["daily_summary_at"]) - _min(cfg["review_prompt_at"]), 0), 60)
        t["summary"] = min(t["summary"], end)
        t["review"] = min(t["review"], _hhmm(_min(t["summary"]) - lead))
        t["weekly"] = min(t["weekly"], end)
        t["end"] = end
        if t["boost"] and t["boost"] >= end:
            t["boost"] = ""
    return t


OFFDAY_OT_QUIET_MINUTES = 30  # ngày nghỉ làm bù: ngưng làm trong VDI chừng này phút (sau giờ tan làm) = xong buổi


def offday_ot_due(cfg, hhmm, quiet_seconds):
    """Ngày nghỉ bật bot làm bù: tới lúc gửi tổng kết làm bù chưa? Từ giờ tan làm (work_end) trở đi VÀ đã ngưng làm
    trong VDI ít nhất OFFDAY_OT_QUIET_MINUTES phút (đang làm dở thì đợi làm xong mới báo)."""
    return hhmm >= cfg["work_end"] and quiet_seconds >= OFFDAY_OT_QUIET_MINUTES * 60


def due_jobs(cfg, hhmm, weekday, *, active, off, note, has_bot, leave=None):
    """Các việc theo giờ đã tới hạn. Mỗi việc chỉ chạy 1 lần/ngày (nơi gọi ghi sent_log).

    weekday: 0 = thứ Hai. note: ghi chú hôm nay. leave: "am" | "pm" | None (nghỉ phép nửa ngày).
    Trả list tên việc: morning, plan, review, summary, weekly, boost, pace_HHMM (cảnh báo tiến độ, xem pace.py).
    """
    if off or not has_bot:  # ngày nghỉ: không gì cả; mọi việc theo giờ đều đi qua bot Telegram
        return []
    t = job_times(cfg, leave)
    jobs = []
    work = is_work_time(cfg, hhmm, off, leave)
    # Lời chào + khích lệ đầu ngày: lần đầu bạn dùng máy trong giờ làm, sau plan_prompt_after.
    if active and work and hhmm >= t["plan"] and cfg.get("encouragement_enabled", True):
        jobs.append("morning")
    # Hỏi kế hoạch: lần đầu bạn dùng máy trong giờ làm, sau plan_prompt_after.
    if active and work and hhmm >= t["plan"] and not note.get("plan"):
        jobs.append("plan")
    # Hỏi tổng kết: lần đầu bạn dùng máy từ review_prompt_at tới hết giờ làm. Lỡ thì gõ /review. Đã tự gõ /review
    # xong trong ngày thì bot ghi sẵn sent_log "review" nên không hỏi lại. Không dựa vào ô năng lượng: /energy gõ
    # giữa ngày không được làm mất câu hỏi tổng kết.
    if active and t["review"] <= hhmm < t["end"] and not in_leave(cfg, hhmm, leave):
        jobs.append("review")
    if hhmm >= t["summary"]:
        jobs.append("summary")
    if (weekday > WEEKDAYS.index(cfg["weekly_report_day"])
            or (weekday == WEEKDAYS.index(cfg["weekly_report_day"]) and hhmm >= t["weekly"])):
        jobs.append("weekly")
    if (t["boost"] and cfg.get("encouragement_enabled", True) and active and work and hhmm >= t["boost"]):
        jobs.append("boost")
    # Cảnh báo tiến độ: mốc gần nhất đã qua (ngồi máy hay không), bỏ mốc trong phần nghỉ phép / trễ quá lâu.
    from .pace import due_checkpoint, job_name
    cp = due_checkpoint(cfg, hhmm, off, leave)
    if cp:
        jobs.append(job_name(cp))
    return jobs
