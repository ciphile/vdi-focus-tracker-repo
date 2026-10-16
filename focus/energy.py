"""Tự tính năng lượng cuối ngày khi bạn không tự chấm (/energy, hay câu cuối của tổng kết 16:45).

Năng lượng là sức còn lại cuối ngày, cùng thang 1–5 như khi bạn tự chấm (1 = kiệt sức, 5 = còn rất sung). Tập trung
càng sâu, càng lâu thì càng cạn; sao nhãng, ngồi ngoài VDI không tốn sức tập trung nên còn dư. Công thức:

    tải (giờ)  = tập trung sâu + 0,5 × làm vụn trong VDI + 0,5 × phần quá 90 phút của mỗi khối làm liền
    năng lượng = 5 − 4 × min(tải / sức tập trung tối đa, 1), làm tròn, trong khoảng 1–5
    sức tập trung tối đa = energy_capacity_hours (mặc định 4 giờ/ngày)

Cơ sở:
- 4 giờ: nghiên cứu về luyện tập có chủ đích (Ericsson và cộng sự, 1993) thấy người giỏi nhất cũng chỉ giữ được
  khoảng 4 giờ tập trung cao độ mỗi ngày; làm tới mức đó là cạn sức.
- Quá 90 phút: làm liên tục không nghỉ thì sự chú ý giảm dần (vigilance decrement, nhịp ultradian khoảng 90 phút),
  phần làm liền quá 90 phút tốn thêm sức.
- Làm vụn trong VDI (đoạn ngắn hơn min_focus_block_minutes, chuyển qua lại) vẫn tốn sức nhưng ít hơn tập trung sâu:
  tính nửa. Hệ số 0,5 là giả định của app.
Đây là ước tính từ số liệu, không đo được cảm giác thật: bạn tự chấm thì số của bạn luôn được dùng.
"""

LONG_BLOCK_MINUTES = 90
SHALLOW_WEIGHT = 0.5
LONG_WEIGHT = 0.5
LABELS = {1: "kiệt sức", 2: "còn ít", 3: "vừa phải", 4: "còn khá", 5: "còn rất sung"}


def estimate(a, capacity_h=4):
    """a: kết quả analysis.analyze(). Trả dict các phần của công thức, hoặc None nếu ngày đó không có số liệu."""
    if not a.get("has_data"):
        return None
    deep_h = a["deep"] / 3600
    shallow_h = max(a["vdi"] + a.get("ot", 0) - a["deep"], 0) / 3600  # tập trung sâu có cả phần làm ngoài giờ
    long_h = sum(max(b["focus"] / 3600 - LONG_BLOCK_MINUTES / 60, 0) for b in a["blocks"])
    load_h = deep_h + SHALLOW_WEIGHT * shallow_h + LONG_WEIGHT * long_h
    ratio = min(load_h / capacity_h, 1)
    exact = 5 - 4 * ratio
    return {"energy": max(1, min(5, int(exact + 0.5))), "exact": round(exact, 1), "ratio": round(ratio, 2),
            "load_h": load_h, "deep_h": deep_h, "shallow_h": shallow_h, "long_h": long_h, "capacity_h": capacity_h}


def dur(hours):
    m = int(round(hours * 60))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def _num(x):
    return f"{x:g}".replace(".", ",")


def label(level):
    return LABELS.get(int(level), "")


def message(est, when="Hôm nay"):
    """Tin báo năng lượng bot tự tính, kèm cách tính để bạn kiểm tra. when: "Hôm nay" hoặc "Ngày 14/10" (gửi bù)."""
    parts = [f"tập trung sâu {dur(est['deep_h'])}"]
    if est["shallow_h"] >= 1 / 60:
        parts.append(f"làm vụn trong VDI {dur(est['shallow_h'])} × 0,5")
    if est["long_h"] >= 1 / 60:
        parts.append(f"làm liền quá {LONG_BLOCK_MINUTES} phút {dur(est['long_h'])} × 0,5")
    return "\n".join([
        f"🔋 {when} bạn chưa chấm năng lượng nên mình tự tính: {est['energy']}/5 ({label(est['energy'])}).",
        f"Cách tính: {' + '.join(parts)} = tải {dur(est['load_h'])}, so với sức tập trung tối đa "
        f"{_num(est['capacity_h'])}h/ngày → 5 − 4 × {_num(est['ratio'])} = {_num(est['exact'])}.",
        "Tập trung càng sâu, càng lâu thì năng lượng càng cạn; sao nhãng thì còn dư.",
        "Thấy chưa đúng thì gõ /energy 1–5 để sửa, số bạn tự chấm luôn được ưu tiên.",
    ])
