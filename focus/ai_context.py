"""Ngữ cảnh đầy đủ gửi kèm MỖI lần gọi AI.

AI không nhớ gì giữa các lần gọi, nên mỗi prompt phải tự mô tả: app này là gì, người dùng làm
công việc gì (work_context trong settings.json), giờ làm, luật tính tập trung, ý nghĩa từng chỉ số,
cách xưng hô và giọng văn (persona.json hoặc lệnh /style).

Sửa nội dung gửi AI thì sửa ở đây, các module khác chỉ gọi system_prompt() / glossary().
"""
from . import persona as _persona

APP = """BỐI CẢNH (bạn không có trí nhớ giữa các lần gọi, mọi thông tin cần thiết đều nằm dưới đây):
- Bạn là trợ lý của "Focus Tracker", một app nhỏ chạy trên máy tính của người dùng ({os_name}), nói chuyện với người dùng qua bot Telegram.
- Người dùng làm việc bên trong máy ảo VDI (Citrix Desktop Viewer). App chỉ đo từ bên ngoài: cửa sổ nào đang ở trước, chuột/bàn phím có dùng không, máy có khoá không. App KHÔNG đọc nội dung màn hình, email hay code.
- Luật tính tập trung: chỉ thời gian cửa sổ VDI ở trước VÀ có thao tác chuột/phím mới tính là làm việc. VDI bị thu nhỏ (minimize), nằm sau app khác, hoặc dùng app ngoài VDI đều tính là KHÔNG tập trung. "Tập trung sâu" là các khối làm liên tục trong VDI từ {min_block} phút trở lên.
- Sao nhãng, ngồi yên, rời máy CHỈ đo trong giờ làm chính thức (không tính giờ nghỉ trưa). Ngoài giờ (trước / sau giờ làm, thứ Bảy, Chủ nhật, ngày lễ có bật bot) app chỉ cộng thêm thời gian làm trong VDI (làm ngoài giờ / OT, ví dụ làm bù buổi tối), không ghi sao nhãng."""

WORK = """- Công việc của người dùng: {work_context}
- Giờ làm {work_start}–{work_end}, nghỉ trưa {lunch_start}–{lunch_end}. Mục tiêu tập trung sâu: {goal} giờ/ngày."""

STYLE = """CÁCH NÓI:
- Viết tiếng Việt, gửi qua Telegram: văn bản thường, không tiêu đề markdown, không bảng, tối đa 1–2 emoji (giọng sếp khó tính thì không emoji).
- Cụ thể, dựa trên số liệu được cung cấp, không bịa số, không lên lớp chung chung.
- Không bịa câu trích dẫn hay nguồn; câu trích dẫn giữ nguyên văn, ghi đúng nguồn.
- {quote_rule}
- {persona}"""

QUOTE_BIBLE = ("Câu trích khích lệ: người dùng BẬT Kinh Thánh, dùng câu Kinh Thánh Tin Lành bản Truyền Thống 1926, "
               "trích nguyên văn, ghi sách chương câu; chọn câu nâng đỡ, không chọn câu răn đe.")
QUOTE_SAGES = ("Người dùng TẮT Kinh Thánh: TUYỆT ĐỐI không dùng câu Kinh Thánh hay nội dung tôn giáo trong mọi tin "
               "nhắn (chào buổi sáng, khích lệ, nhắc nhở, cảnh báo, đánh giá), trừ khi chính người dùng xin câu Kinh "
               "Thánh (lệnh /bible). Câu trích dẫn chỉ dùng châm ngôn, câu nói có thật của người thành đạt hoặc danh "
               "nhân, nhà hiền triết thời xưa (ví dụ Khổng Tử, Mạnh Tử, Lão Tử, Seneca, Marcus Aurelius), ghi đúng "
               "tác giả; không chắc tác giả thì chọn câu khác.")


def bible_on(cfg):
    """Kinh Thánh có đang bật trong lời khích lệ không (/kinhthanh, /encourage)."""
    return "bible" in (cfg.get("encouragement_styles") or [])

GLOSSARY = {
    "report_date": "ngày đang được đánh giá (chỉ đánh giá ngày này)",
    "today": "số liệu và ghi chú CHỈ của ngày đang đánh giá",
    "previous_days_context": "báo cáo tóm tắt các ngày TRƯỚC, mỗi mục có date; chỉ để so sánh, không phải số liệu hôm nay",
    "date": "ngày của mục chứa nó",
    "day / weekday": "ngày của khối số liệu chứa nó",
    "goal_hours": "mục tiêu giờ tập trung sâu mỗi ngày",
    "work_from_to": "giờ dùng máy đầu tiên – cuối cùng",
    "deep_hours": "giờ tập trung sâu (khối làm liên tục trong VDI đủ dài)",
    "vdi_hours": "tổng giờ VDI ở trước và có thao tác",
    "outside_vdi_minutes": "phút dùng chuột/phím ở app ngoài VDI (Chrome, Teams, Zalo...)",
    "vdi_minimized_minutes": "phút VDI bị thu nhỏ (taskbar / Dock), bị ẩn hoặc nằm sau app khác trong lúc vẫn dùng máy",
    "idle_minutes": "phút ngồi yên không chạm phím/chuột (dưới ngưỡng rời máy)",
    "away_minutes": "phút rời máy hoặc khoá máy",
    "vdi_closed": "các khoảng giờ cửa sổ VDI bị đóng trong giờ làm (Citrix tự ngắt khi người dùng không đụng VDI "
                  "10–20 phút, hoặc tự đóng): người dùng đã rời VDI quá lâu, khoảng này không tính giờ làm",
    "out_of_vdi_exits": "số lần rời VDI sang app khác",
    "short_idle_count_1_5min": "số lần ngồi yên 1–5 phút trước VDI rồi làm tiếp; cao thường là do cầm điện thoại",
    "vdi_not_fullscreen_minutes": "phút VDI không toàn màn hình (dễ liếc sang app khác)",
    "score": "điểm tập trung 0–100 = 70 × min(tập trung sâu / mục tiêu, 1) + 30 × (giờ VDI / giờ có thao tác)",
    "total_score / total_score_10": "ĐIỂM TỔNG 0–100 (và thang 1–10), chỉ số quan trọng nhất của ngày: 60% điểm tập "
                                    "trung + 30% điểm ít bị cắt ngang + 10% năng lượng tự chấm (chưa tự chấm thì 65/35)",
    "total_score_parts": "điểm thành phần 0–100: focus (điểm tập trung), interruptions (ít bị cắt ngang: 100 khi "
                         "không bị cắt ngang, 0 khi bị cắt ngang từ 20 lần/giờ trở lên), energy (năng lượng tự chấm)",
    "interruptions_per_hour": "số lần bị cắt ngang mỗi giờ làm (rời VDI / thu nhỏ VDI + ngồi yên ngắn rồi làm tiếp)",
    "total_score_explained": "giải thích điểm tổng đã tính sẵn bằng số thật: meaning (nghĩa là mức gì), formula, parts "
                             "(từng thành phần + số liệu gốc), biggest_loss (phần kéo điểm xuống nhiều nhất), "
                             "how_to_raise / avg_parts / by_day (cách tăng điểm, điểm thành phần trung bình, từng ngày)",
    "gift_robot": "robot quà tặng theo điểm tổng: SD (thấp nhất, robot tí hon) -> HG -> RG -> MG -> PG (cao nhất)",
    "science_advice": "dữ kiện khoa học app đã kiểm chứng, chỉ có khi điểm tổng dưới 50: dùng nguyên ý, không thêm nghiên cứu khác",
    "vdi_minimize_count": "số lần thu nhỏ VDI trong giờ làm",
    "inactive_over_10min_count": "số lần ngồi yên / rời máy từ 10 phút trở lên trong giờ làm",
    "away_count": "số lần rời máy (ngồi yên quá ngưỡng hoặc khoá máy)",
    "overtime_vdi_minutes / overtime_deep_minutes": "phút làm trong VDI ngoài giờ (trước / sau giờ làm: làm bù / OT; giờ trưa không tính) và "
                                                    "phần trong đó thuộc khối tập trung sâu; đã cộng vào deep_hours",
    "streak_days": "số ngày làm việc liên tiếp đạt mục tiêu",
    "focus_blocks": "các khối tập trung sâu trong ngày",
    "golden_hour": "giờ tập trung tốt nhất trong ngày",
    "top_apps_outside_vdi": "app ngoài VDI dùng nhiều nhất",
    "avg_deep_hours_7d": "trung bình giờ tập trung sâu 7 ngày làm việc trước",
    "recent_days": "giờ tập trung sâu và điểm của từng ngày làm việc TRƯỚC (có date; để so sánh xu hướng)",
    "plan": "kế hoạch người dùng tự ghi đầu ngày",
    "output": "việc người dùng ghi là đã xong",
    "issues": "issue / blocker người dùng ghi trong ngày",
    "recent_issues": "issue của các ngày TRƯỚC, kèm date (để thấy issue lặp lại)",
    "distractions": "điều làm mất tập trung người dùng tự ghi",
    "energy": "mức năng lượng tự chấm 1–5",
    "tomorrow": "việc đầu tiên sáng mai người dùng đã ghi",
    "pending_carry": "việc tồn chuyển sang ngày làm việc kế: kế hoạch và issue của ngày này và các ngày trước chưa thấy ghi xong trong output, cộng dồn, ghi ngày bắt đầu tồn",
    "promised_yesterday": "việc người dùng ghi ngày written_on, hẹn làm đầu tiên ở ngày đang đánh giá",
    "as400": "giờ vào/ra AS400 hôm nay",
    "per_day / best_day / worst_day / golden_hours": "số liệu từng ngày trong tuần, ngày tốt nhất/kém nhất, giờ vàng của tuần",
    "deep_hours_total / deep_hours_avg / avg_score / days_reached_goal / work_days": "tổng / trung bình giờ tập trung sâu của tuần, điểm trung bình, số ngày đạt mục tiêu, số ngày làm việc",
    "off_day_overtime": "ngày nghỉ (cuối tuần, lễ) người dùng tự bật bot làm bù trong VDI: chỉ có giờ làm, không "
                        "tính sao nhãng, không chấm điểm; đã cộng vào overtime_hours",
    "avg_total_score / overtime_hours": "điểm tổng trung bình của tuần, tổng giờ làm trong VDI ngoài giờ (OT)",
    "ai_daily_review": "lời đánh giá AI đã gửi người dùng cuối ngày đó (để xem lời khuyên có được làm theo không)",
    "days_off": "ngày nghỉ trong tuần và lý do",
    "previous_week": "số liệu tổng của tuần trước để so sánh",
}


def os_name(cfg):
    plat = str(cfg.get("platform") or "auto").lower()
    if plat == "auto":
        import sys
        plat = "mac" if sys.platform == "darwin" else "windows" if sys.platform.startswith("win") else plat
    return {"mac": "MacBook / macOS", "windows": "laptop Windows"}.get(plat, "laptop")


def persona_of(cfg):
    return cfg.get("persona") or _persona.DEFAULT


def system_prompt(cfg, extra=""):
    """System prompt đầy đủ ngữ cảnh. extra: dặn thêm riêng cho từng loại việc."""
    parts = [APP.format(min_block=cfg["min_focus_block_minutes"], os_name=os_name(cfg)),
             WORK.format(work_context=(cfg.get("work_context") or "chưa ghi").strip()[:1500],
                         work_start=cfg["work_start"], work_end=cfg["work_end"],
                         lunch_start=cfg["lunch_start"], lunch_end=cfg["lunch_end"],
                         goal=cfg["daily_focus_goal_hours"]),
             STYLE.format(persona=_persona.ai_instructions(persona_of(cfg)),
                          quote_rule=QUOTE_BIBLE if bible_on(cfg) else QUOTE_SAGES)]
    p = persona_of(cfg)
    if not p.get("ten") and cfg.get("_tg_name"):
        parts[-1] += f" Người dùng tên {cfg['_tg_name']} (tên Telegram); gọi đúng tên khi phù hợp."
    if extra:
        parts.append(extra.strip())
    return "\n\n".join(parts)


def glossary(facts):
    """Giải thích các chỉ số có mặt trong facts (chỉ những khoá dùng tới, cho prompt gọn)."""
    keys = set(facts)
    lines = []
    for k, meaning in GLOSSARY.items():
        names = [n.strip() for n in k.split("/")]
        if any(n in keys for n in names):
            lines.append(f"- {k}: {meaning}")
    return "Ý nghĩa các trường số liệu:\n" + "\n".join(lines)


CONTEXT_MARK = "BỐI CẢNH (bạn không có trí nhớ giữa các lần gọi"


def ensure_context(cfg, system):
    """Mọi lần gọi AI đều phải có BỐI CẢNH đầy đủ: system chưa có thì thêm system_prompt(cfg) lên đầu.
    ai_client.generate gọi hàm này, nên dù nơi gọi quên truyền system thì AI vẫn nhận đủ ngữ cảnh."""
    if CONTEXT_MARK in (system or ""):
        return system
    return system_prompt(cfg, system or "")


def fingerprint(cfg):
    """Mã của TOÀN BỘ ngữ cảnh gửi AI (giọng, tên, xưng hô, sếp, công việc, giờ làm, mục tiêu...): đổi bất kỳ
    thông số nào thì không dùng lại đánh giá đã lưu trong cache."""
    import hashlib
    return hashlib.sha256(system_prompt(cfg).encode("utf-8")).hexdigest()[:16]
