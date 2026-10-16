"""Tạo một tuần dữ liệu giả + báo cáo mẫu (data/demo/, không đụng dữ liệu thật)."""
import datetime as dt
import os
import random
import time

from . import scoring
from .analysis import analyze, fmt_dur, week_facts
from .report import write_report, write_week_report
from .storage import db_path, open_db, save_note


def make_demo(cfg):
    random.seed(7)
    demo_dir = os.path.join(cfg["data_dir"], "demo")
    cfg = dict(cfg, data_dir=demo_dir, report_dir=os.path.join(demo_dir, "reports"))
    os.makedirs(cfg["report_dir"], exist_ok=True)
    path = db_path(cfg)
    if os.path.exists(path):
        os.remove(path)
    db = open_db(path)
    today = dt.date.today()
    # (giờ bắt đầu, phút, trạng thái): vdi / other / min (VDI thu nhỏ) / idle / away / lock
    plan = [(8.75, 25, "vdi"), (9.17, 6, "other"), (9.27, 55, "vdi"), (10.2, 4, "idle"),
            (10.27, 12, "min"), (10.47, 15, "away"), (10.72, 70, "vdi"), (11.9, 8, "other"),
            (12.03, 60, "lock"), (13.03, 20, "other"), (13.37, 45, "vdi"), (14.12, 3, "idle"),
            (14.17, 35, "vdi"), (14.75, 30, "min"), (15.25, 50, "vdi"), (16.08, 10, "away"),
            (16.25, 40, "vdi"), (16.92, 12, "other"), (17.12, 25, "vdi")]
    for back in range(6, -1, -1):
        day = today - dt.timedelta(days=back)
        if back and day.weekday() >= 5:
            continue
        base = dt.datetime.combine(day, dt.time()).timestamp()
        jitter = random.uniform(0.6, 1.15) if back else 1.0
        prev, idle_start = None, None
        for start_h, minutes, st in plan:
            t, end = base + start_h * 3600, base + start_h * 3600 + minutes * 60 * (jitter if st == "vdi" else 1)
            prev = prev or t
            while t < end:
                t += cfg["sample_seconds"]
                if st in ("idle", "away"):
                    idle_start = idle_start or t
                    idle = t - idle_start
                else:
                    idle_start, idle = None, random.uniform(0, 8)
                vdi_state = {"vdi": "foreground", "min": "minimized", "other": "background"}.get(st, "foreground")
                proc = {"vdi": "cdviewer.exe", "min": random.choice(["chrome.exe", "zalo.exe"]),
                        "other": random.choice(["chrome.exe", "teams.exe", "outlook.exe"])}.get(st, "cdviewer.exe")
                if random.random() < 0.004 and st == "vdi":  # cú chuyển nhanh sang app khác
                    vdi_state, proc = "background", "teams.exe"
                full = (1 if day.day % 2 else int(start_h < 12)) if vdi_state == "foreground" else None
                db.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?)",
                           (t, t - prev, idle, int(st == "lock"), vdi_state, proc, None, full))
                prev = t
    day = today.isoformat()
    save_note(db, day, {
        "plan": "1. Fix bug đối soát hợp đồng\n2. Review PR của team\n3. Viết spec API thanh toán",
        "output": "Fix xong bug đối soát (đã deploy UAT). Review 2 PR. Spec API được 60%.",
        "issues": "VDI chậm lúc 10h, phải chờ restart. Thiếu quyền truy cập DB UAT.",
        "distractions": "Chat Zalo nhóm, 2 cuộc họp ngắn không có agenda",
        "energy": 4, "tomorrow": "Hoàn thiện spec API thanh toán"})
    _sample_reviews(db, cfg, day)
    db.commit()
    rpath, a = write_report(db, cfg, day)
    wpath, _ = write_week_report(db, cfg, day)
    print(f"Báo cáo mẫu: {rpath}")
    print(f"Báo cáo tuần mẫu: {wpath}")
    print(f"Tập trung sâu {fmt_dur(a['deep'])}, VDI {fmt_dur(a['vdi'])}, ngoài VDI {fmt_dur(a['other'])}, "
          f"thu nhỏ {fmt_dur(a['minimized'])}, inactive {fmt_dur(a['idle'])}, rời máy {fmt_dur(a['away'])}")
    return rpath


def _sample_reviews(db, cfg, day):
    """Lời AI MẪU (soạn sẵn, ghi rõ là mẫu) để báo cáo mẫu có đủ mục «Lời khuyên của AI». Báo cáo thật do AI viết."""
    a = analyze(db, cfg, day)
    sc = scoring.total_score(a, {"energy": 4})
    t = sc["tier"]
    daily = (
        "(Lời AI MẪU để xem bố cục. Báo cáo thật: AI viết theo số liệu của bạn lúc tổng kết cuối ngày.)\n\n"
        f"1. Điểm tổng hôm nay: {sc['total']}/100 ({str(sc['ten']).replace('.', ',')}/10), mức {t['verdict']}, "
        f"quà robot {t['grade']} {t['name']}. Điểm tổng gộp 60% điểm tập trung, 30% mức ít bị cắt ngang và 10% "
        "năng lượng bạn tự chấm. Phần kéo điểm xuống nhiều nhất là thời gian dùng máy ngoài VDI; dồn bớt chừng đó "
        "vào VDI là điểm tăng thêm vài điểm.\n"
        "2. Việc pending cho ngày mai: hoàn thiện spec API thanh toán (đang 60%), xin quyền truy cập DB UAT.\n"
        "3. Mất tập trung vì đâu: chủ yếu VDI bị thu nhỏ để xem Zalo / Chrome và 2 cuộc họp ngắn không có agenda.\n"
        "4. Cần khắc phục: VDI chậm lúc 10h, thử mở ticket với IT kèm giờ bị chậm; quyền DB UAT: gửi yêu cầu sớm "
        "trong sáng mai để không chặn việc test.\n"
        "5. Ngày mai cải thiện: đặt điện thoại ngoài tầm tay trong khung 09:00–10:00, giờ vàng của bạn.\n"
        "6. \u201cKhông có gió thuận cho người không biết mình đi đâu.\u201d (Seneca, Thư 71) Bạn đã biết rõ việc đầu tiên "
        "sáng mai, cứ thế mà đi.\n"
        "7. Chúc bạn buổi tối ấm áp bên gia đình.")
    week = week_facts(db, cfg, day)["week"]
    weekly = (
        "(Lời AI MẪU để xem bố cục. Báo cáo thật: AI viết theo số liệu cả tuần lúc tổng kết tuần.)\n\n"
        "1. Điểm tổng trung bình tuần ở mức tốt: phần tập trung sâu vững, phần kéo điểm xuống là thời gian ngoài "
        "VDI vào đầu giờ chiều.\n"
        "2. Ngày tốt nhất có khối tập trung dài liền mạch buổi sáng; ngày kém nhất bị cắt ngang nhiều sau 13:00.\n"
        "3. Việc xong: bug đối soát, review PR. Còn pending sang tuần sau: spec API thanh toán.\n"
        "4. Issue lặp lại: VDI chậm buổi sáng (2 ngày), nên báo IT một lần kèm giờ cụ thể.\n"
        "5. Mục tiêu tuần sau: giữ khung 09:00–10:00 không họp, gom tin nhắn Zalo vào 2 lần nghỉ.\n"
        "6. \u201cHọc mà không nghĩ thì mờ, nghĩ mà không học thì nguy.\u201d (Khổng Tử, Luận Ngữ) Chúc bạn cuối tuần "
        "nghỉ ngơi trọn vẹn bên gia đình.")
    now = time.time()
    db.execute("INSERT OR REPLACE INTO ai_cache (key, created, text) VALUES (?,?,?)", (f"review:{day}:mau", now, daily))
    db.execute("INSERT OR REPLACE INTO ai_cache (key, created, text) VALUES (?,?,?)", (f"week:{week}:mau", now, weekly))
