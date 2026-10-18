"""Điểm tổng của ngày (0–100, kèm thang 1–10), hạng robot quà tặng, và các dữ kiện khoa học dùng trong lời khuyên.

ĐIỂM TỔNG = trung bình có trọng số của các thành phần đo được:

  Thành phần                Điểm 0–100                                         Trọng số
  ------------------------  -------------------------------------------------  -------------------------------
  Điểm tập trung (giữ       70 × min(tập trung sâu / mục tiêu, 1)              60%  (65% khi chưa tự chấm
  nguyên công thức cũ)      + 30 × (giờ VDI / giờ có thao tác)                       năng lượng)
  Ít bị cắt ngang           100 × max(0, 1 − số lần bị cắt ngang mỗi giờ / 20)  30%  (35% khi chưa tự chấm)
  Năng lượng tự chấm        (năng lượng − 1) / 4 × 100                          10%  (chỉ khi BẠN tự chấm /energy)

  Số lần bị cắt ngang = số lần rời VDI sang app khác / thu nhỏ VDI (exits) + số lần ngồi yên ngắn rồi làm tiếp
  (thường là cầm điện thoại), chia cho số giờ có thao tác trong giờ làm.

Căn cứ (đã đối chiếu bản gốc, xem SCIENCE):
- Ngưỡng 20 lần/giờ: González & Mark (CHI 2004) quan sát nhân viên IT thật, trung bình cứ khoảng 3 phút lại chuyển
  sang việc khác (= 20 lần/giờ). Ngày bị cắt ngang dày như mức "bình thường" đó được 0 điểm phần này.
- Bị cắt ngang làm tăng căng thẳng, bực bội, áp lực thời gian (Mark, Gudith & Klocke, CHI 2008, 48 người); chuyển
  việc để lại "dư âm chú ý" làm giảm hiệu quả việc kế tiếp (Leroy, OBHDP 2009).
- Năng lượng / sức sống cuối ngày là thước đo phục hồi được dùng trong các nghiên cứu nghỉ ngắn (Albulescu và cộng sự,
  PLOS ONE 2022, gộp 22 nghiên cứu). Năng lượng do bot TỰ ƯỚC TÍNH (energy.py) là quy tắc của app, không phải số đo
  khoa học, nên KHÔNG đưa vào điểm tổng.
Trọng số 60/30/10 là lựa chọn thiết kế của app (chưa có nghiên cứu nào công bố một công thức gộp đã kiểm chứng cho
đúng bộ số liệu này); từng thành phần và ngưỡng thì có căn cứ thực nghiệm như trên. Năng lượng KHÔNG ảnh hưởng điểm
tập trung, chỉ góp vào điểm tổng.
"""
from .analysis import focus_score

SWITCHES_PER_HOUR_ZERO = 20      # González & Mark 2004: chuyển việc trung bình ~3 phút/lần
WEIGHTS_WITH_ENERGY = {"focus": 0.60, "interruptions": 0.30, "energy": 0.10}
WEIGHTS_NO_ENERGY = {"focus": 0.65, "interruptions": 0.35}
ADVICE_BELOW = 50                # điểm tổng dưới mức này: kèm một lời khuyên có căn cứ khoa học

# Hạng robot quà tặng (robot tự vẽ, không dùng hình Gundam có bản quyền). Tên hạng mượn cách gọi phổ biến của mô hình
# lắp ráp Nhật: SD (nhỏ, đơn giản) -> HG -> RG -> MG -> PG (lớn, chi tiết nhất).
TIERS = [
    (0, "SD", "Mini", "robot tí hon méo mó, sơn chưa khô"),
    (30, "HG", "Scout", "robot trinh sát cơ bản"),
    (50, "RG", "Guardian", "robot hộ vệ có khiên"),
    (70, "MG", "Vanguard", "robot tiên phong giáp nhiều lớp, có cánh đẩy"),
    (85, "PG", "Celestial", "robot thiên giới hoàn chỉnh, cánh sáng, vũ khí đầy đủ"),
]


VERDICTS = ["kém", "chưa tốt", "trung bình", "tốt", "xuất sắc"]  # mức chữ, cùng thứ tự với TIERS
PART_NAMES = {"focus": "điểm tập trung", "interruptions": "ít bị cắt ngang", "energy": "năng lượng tự chấm"}


def tier_of(total):
    best = TIERS[0]
    for t in TIERS:
        if total >= t[0]:
            best = t
    level = TIERS.index(best)
    return {"min": best[0], "grade": best[1], "name": best[2], "desc": best[3], "level": level,
            "verdict": VERDICTS[level]}


def scale_text():
    bounds = [t[0] for t in TIERS] + [None]
    out = []
    for i, (t, v) in enumerate(zip(TIERS, VERDICTS)):
        lo, hi = t[0], bounds[i + 1]
        rng = f"dưới {hi}" if lo == 0 else (f"từ {lo}" if hi is None else f"{lo}–{hi - 1}")
        out.append(f"{rng} {v} (robot {t[1]})")
    return ", ".join(out)


def interruptions(a):
    """(số lần bị cắt ngang, số giờ có thao tác trong giờ làm, số lần mỗi giờ)."""
    n = a.get("exits", 0) + a.get("short_idle_count", 0)
    hours = a.get("active", 0) / 3600
    return n, hours, (n / hours if hours > 0 else 0.0)


def total_score(a, note=None):
    """Điểm tổng của ngày. note: ghi chú ngày (để biết năng lượng tự chấm). Không có số liệu -> None."""
    if not a.get("has_data"):
        return None
    note = note or {}
    focus = focus_score(a)
    n, hours, per_h = interruptions(a)
    inter = round(100 * max(0.0, 1 - per_h / SWITCHES_PER_HOUR_ZERO)) if hours > 0 else 100
    parts = {"focus": focus, "interruptions": inter}
    energy = note.get("energy")
    self_rated = energy not in (None, "") and note.get("energy_source") != "auto"
    if self_rated:
        parts["energy"] = round((int(energy) - 1) / 4 * 100)
        weights = WEIGHTS_WITH_ENERGY
    else:
        weights = WEIGHTS_NO_ENERGY
    total = round(sum(parts[k] * w for k, w in weights.items()))
    return {"total": total, "ten": round(total / 10, 1), "parts": parts, "weights": weights,
            "interruptions": n, "active_hours": round(hours, 2), "per_hour": round(per_h, 1),
            "tier": tier_of(total), "energy_self_rated": self_rated}


def formula_lines(a, sc):
    """Các dòng giải thích công thức kèm số của ngày (cho báo cáo HTML)."""
    goal = a["goal_h"] * 3600 or 1
    ratio = a["vdi"] / a["active"] if a.get("active") else 0
    lines = [
        f"Điểm tập trung = 70 × min(tập trung sâu / mục tiêu, 1) + 30 × (giờ VDI / giờ có thao tác) = 70 × "
        f"min({a['deep'] / 3600:.2f}h / {a['goal_h']:g}h, 1) + 30 × {ratio:.2f} = {sc['parts']['focus']}",
        f"Ít bị cắt ngang = 100 × max(0, 1 − lần cắt ngang mỗi giờ / {SWITCHES_PER_HOUR_ZERO}) = 100 × max(0, 1 − "
        f"{sc['interruptions']} lần / {sc['active_hours']:.2f}h / {SWITCHES_PER_HOUR_ZERO}) = {sc['parts']['interruptions']}",
    ]
    if "energy" in sc["parts"]:
        lines.append(f"Năng lượng = (năng lượng tự chấm − 1) / 4 × 100 = {sc['parts']['energy']}")
    w = sc["weights"]
    lines.append("Điểm tổng = " + " + ".join(f"{int(w[k] * 100)}% × {sc['parts'][k]}" for k in w)
                 + f" = {sc['total']}/100 ({sc['ten']:.1f}/10)")
    return lines


def losses(sc):
    """Mỗi thành phần làm điểm tổng mất bao nhiêu điểm so với 100 (trọng số × (100 − điểm thành phần))."""
    return {k: round(w * (100 - sc["parts"][k]), 1) for k, w in sc["weights"].items()}


def _n(x, nd=1):
    return f"{x:.{nd}f}".rstrip("0").rstrip(".").replace(".", ",") if nd else str(round(x))


def explain(a, sc):
    """Giải thích điểm tổng bằng số của chính ngày đó, để AI nói lại cho người dùng (người dùng không biết điểm tổng
    là gì). Mọi con số đã tính sẵn ở đây, AI không phải tự tính."""
    w, p = sc["weights"], sc["parts"]
    goal_h = a["goal_h"] or 1
    deep_h = a.get("deep", 0) / 3600
    ratio = a["vdi"] / a["active"] if a.get("active") else 0
    deep_pts, ratio_pts = 70 * min(deep_h / goal_h, 1), 30 * ratio
    pct = lambda k: int(round(w[k] * 100))
    parts = [
        f"Điểm tập trung {p['focus']}/100 (trọng số {pct('focus')}%, góp {_n(w['focus'] * p['focus'])} điểm tổng): "
        f"phần giờ tập trung sâu = 70 × min({_n(deep_h, 2)}h / mục tiêu {_n(goal_h)}h, 1) = {_n(deep_pts)}/70; "
        f"phần ở trong VDI = 30 × (giờ trong VDI {_n(a['vdi'] / 3600, 2)}h / giờ có dùng phím chuột "
        f"{_n(a.get('active', 0) / 3600, 2)}h = {ratio:.0%}) = {_n(ratio_pts)}/30",
        f"Ít bị cắt ngang {p['interruptions']}/100 (trọng số {pct('interruptions')}%, góp "
        f"{_n(w['interruptions'] * p['interruptions'])} điểm tổng): bị cắt ngang {sc['interruptions']} lần "
        f"(rời VDI / thu nhỏ VDI {a.get('exits', 0)} lần + ngồi yên 1–5 phút rồi làm tiếp {a.get('short_idle_count', 0)} "
        f"lần) trong {_n(sc['active_hours'], 2)} giờ làm = {_n(sc['per_hour'])} lần/giờ; 0 lần/giờ = 100 điểm, từ "
        f"{SWITCHES_PER_HOUR_ZERO} lần/giờ trở lên = 0 điểm",
    ]
    if "energy" in p:
        parts.append(f"Năng lượng tự chấm {p['energy']}/100 (trọng số {pct('energy')}%, góp "
                     f"{_n(w['energy'] * p['energy'])} điểm tổng): người dùng tự chấm "
                     f"{round(p['energy'] / 25) + 1}/5")
    else:
        parts.append("Năng lượng: người dùng chưa tự chấm nên không tính; trọng số dồn sang 65% điểm tập trung + "
                     "35% ít bị cắt ngang")
    lost = losses(sc)
    worst = max(lost, key=lost.get)
    if worst == "focus":
        why = ("thiếu giờ tập trung sâu" if 70 - deep_pts >= 30 - ratio_pts else
               "nhiều thời gian dùng máy ở ngoài VDI")
    elif worst == "interruptions":
        why = "bị cắt ngang nhiều (rời VDI, thu nhỏ VDI, cầm điện thoại)"
    else:
        why = "năng lượng tự chấm thấp"
    raise_tips = []
    if deep_h < goal_h:
        gain = round(w["focus"] * 70 * min((goal_h - deep_h) / goal_h, 1))
        raise_tips.append(f"thêm {_n(goal_h - deep_h)}h tập trung sâu (khối làm liền trong VDI từ 20 phút) cho đủ "
                          f"mục tiêu: điểm tổng tăng khoảng {gain}")
    if ratio < 0.95 and a.get("active"):
        gain = round(w["focus"] * 30 * (1 - ratio))
        raise_tips.append(f"dồn {_n(a.get('other', 0) / 60, 0)} phút đang dùng ngoài VDI vào VDI: tăng tối đa "
                          f"khoảng {gain}")
    if sc["per_hour"] > 0:
        per = w["interruptions"] * 100 / SWITCHES_PER_HOUR_ZERO
        raise_tips.append(f"mỗi giờ bớt được 1 lần bị cắt ngang thì điểm tổng tăng khoảng {_n(per)} (đang "
                          f"{_n(sc['per_hour'])} lần/giờ)")
    return {
        "meaning": f"{sc['total']}/100 ({_n(sc['ten'])}/10) = mức {sc['tier']['verdict']}, robot "
                   f"{sc['tier']['grade']} {sc['tier']['name']}. Thang: {scale_text()}",
        "formula": " + ".join(f"{pct(k)}% × {PART_NAMES[k]} {p[k]}" for k in w) + f" = {sc['total']}",
        "parts": parts,
        "biggest_loss": f"{PART_NAMES[worst]} làm mất nhiều điểm nhất ({_n(lost[worst])} điểm tổng), chủ yếu do {why}",
        "how_to_raise": raise_tips or ["giữ nhịp như hôm nay"],
    }


def explain_week(days):
    """Giải thích điểm tổng trung bình của tuần từ các ngày (mỗi phần tử là day_facts có total_score)."""
    rows = [d for d in days if d.get("total_score") is not None and d.get("total_score_parts")]
    if not rows:
        return None
    avg = round(sum(d["total_score"] for d in rows) / len(rows))
    keys = ["focus", "interruptions"] + (["energy"] if any("energy" in d["total_score_parts"] for d in rows) else [])
    avg_parts = {}
    for k in keys:
        vals = [d["total_score_parts"][k] for d in rows if k in d["total_score_parts"]]
        avg_parts[PART_NAMES[k]] = round(sum(vals) / len(vals))
    lost = {}
    for d in rows:
        has_e = "energy" in d["total_score_parts"]
        weights = WEIGHTS_WITH_ENERGY if has_e else WEIGHTS_NO_ENERGY
        for k, wk in weights.items():
            lost[k] = lost.get(k, 0) + wk * (100 - d["total_score_parts"][k]) / len(rows)
    worst = max(lost, key=lost.get)
    best_d = max(rows, key=lambda d: d["total_score"])
    worst_d = min(rows, key=lambda d: d["total_score"])
    label = lambda d: f"{d.get('weekday', '')} {d['day'][8:]}/{d['day'][5:7]}".strip()
    if best_d["total_score"] == worst_d["total_score"]:  # hoà / chỉ 1 ngày: không gọi một ngày vừa cao vừa thấp nhất
        best_txt = worst_txt = (f"chỉ có 1 ngày: {label(best_d)} ({best_d['total_score']})" if len(rows) == 1 else
                                f"các ngày bằng nhau ({best_d['total_score']})")
    else:
        best_txt = f"{label(best_d)} ({best_d['total_score']})"
        worst_txt = f"{label(worst_d)} ({worst_d['total_score']})"
    return {
        "meaning": f"Điểm tổng trung bình tuần {avg}/100 = mức {tier_of(avg)['verdict']}. Thang: {scale_text()}",
        "avg_parts": avg_parts,
        "by_day": [f"{label(d)}: {d['total_score']} ({', '.join(f'{PART_NAMES[k]} {v}' for k, v in d['total_score_parts'].items())})"
                   for d in rows],
        "best_day": best_txt,
        "worst_day": worst_txt,
        "biggest_loss": f"{PART_NAMES[worst]} làm mất nhiều điểm nhất, trung bình {_n(lost[worst])} điểm tổng mỗi ngày",
    }


SCORE_GUIDE = """ĐIỂM TỔNG LÀ GÌ (người dùng KHÔNG biết điểm tổng là gì, bạn phải giải thích lại bằng lời dễ hiểu):
- Điểm tổng 0–100 (thang 10 = chia 10) là con số chính cho biết ngày làm việc tập trung tốt tới đâu. Mức: {scale}.
- Điểm tổng gộp 3 thành phần, mỗi phần 0–100:
  a) Điểm tập trung (60%) = 70 × min(giờ tập trung sâu / mục tiêu, 1) + 30 × (giờ trong VDI / giờ có dùng phím chuột
     trong giờ làm). Tập trung sâu = khối làm liền trong VDI đủ dài (mặc định từ 20 phút).
  b) Ít bị cắt ngang (30%) = 100 × max(0, 1 − số lần bị cắt ngang mỗi giờ / {zero}). Bị cắt ngang = rời VDI sang app
     khác hoặc thu nhỏ VDI, hoặc ngồi yên 1–5 phút rồi làm tiếp (thường là cầm điện thoại). Mốc {zero} lần/giờ lấy từ
     nghiên cứu González và Mark (CHI 2004): nhân viên văn phòng trung bình khoảng 3 phút lại chuyển việc.
  c) Năng lượng tự chấm (10%) = (năng lượng 1–5 − 1) / 4 × 100, chỉ khi người dùng TỰ chấm. Không tự chấm thì điểm
     tổng = 65% điểm tập trung + 35% ít bị cắt ngang. Năng lượng app tự ước tính KHÔNG tính vào điểm tổng.
- Rời máy, ngồi yên lâu không trừ điểm trực tiếp (chỉ làm ít giờ tập trung đi). Làm ngoài giờ (OT) trong VDI được cộng
  vào giờ tập trung sâu, không tính bị cắt ngang.
- Trọng số 60/30/10 là lựa chọn của app, không phải chuẩn khoa học: không nói điểm tổng là "chuẩn khoa học".
- Trường "total_score_explained" đã tính sẵn bằng số thật: meaning (điểm nghĩa là mức gì), formula, parts (từng thành
  phần và nó đến từ số liệu gốc nào), biggest_loss (phần kéo điểm xuống nhiều nhất), how_to_raise (làm gì để tăng
  điểm, tăng khoảng bao nhiêu). Dùng ĐÚNG các con số đó, không tự tính lại, không bịa số khác."""


def score_guide():
    return SCORE_GUIDE.format(scale=scale_text(), zero=SWITCHES_PER_HOUR_ZERO)


# Dữ kiện khoa học đã đối chiếu với bản tóm tắt / bài gốc (tháng 10/2026). Chỉ dùng các câu này, không để AI tự bịa.
SCIENCE = {
    "interrupt_stress": "Nghiên cứu của Gloria Mark và cộng sự (ĐH California Irvine, hội nghị CHI 2008, 48 người): "
                        "khi bị cắt ngang, người ta làm nhanh hơn để bù nhưng căng thẳng, bực bội và áp lực thời "
                        "gian đều tăng rõ.",
    "switch_3min": "González và Mark (CHI 2004) quan sát nhân viên IT thật suốt nhiều ngày: trung bình chỉ khoảng 3 "
                   "phút là chuyển sang việc khác, mỗi mảng việc chỉ được làm liền khoảng 11 phút.",
    "attention_residue": "Sophie Leroy (2009) gọi là \"dư âm chú ý\": chuyển việc khi việc trước còn dở thì đầu óc vẫn "
                         "vướng việc cũ và làm việc mới kém hơn. Chốt một điểm dừng rõ ràng trước khi chuyển việc.",
    "email_batch": "Kushlev và Dunn (2015, 124 người): khi chỉ xem email 3 lần mỗi ngày thay vì xem liên tục, mọi "
                   "người thấy bớt căng thẳng rõ rệt.",
    "micro_breaks": "Tổng hợp 22 nghiên cứu (Albulescu và cộng sự, PLOS ONE 2022): nghỉ ngắn 10 phút trở xuống giúp "
                    "tăng sức sống và giảm mệt mỏi.",
    "water_kidney": "Nghiên cứu ngẫu nhiên 5 năm của Borghi và cộng sự (Journal of Urology 1996, 199 người từng bị "
                    "sỏi thận): nhóm uống nhiều nước tái phát sỏi 12%, nhóm không đổi thói quen tái phát 27%.",
    "water_brain": "Ganio và cộng sự (British Journal of Nutrition 2011, 26 nam thanh niên): chỉ mất nước nhẹ khoảng "
                   "1,6% cân nặng đã làm tăng lỗi khi canh chừng, chậm trí nhớ làm việc, căng thẳng và mệt mỏi hơn.",
    "sitting_mortality": "Phân tích gộp trên Lancet (Ekelund và cộng sự 2016, hơn 1 triệu người, 16 nghiên cứu): ngồi "
                         "trên 8 tiếng/ngày mà ít vận động thì nguy cơ tử vong sớm cao hơn; vận động vừa 60–75 phút "
                         "mỗi ngày xoá được phần nguy cơ tăng thêm đó.",
    "sitting_glucose": "Dunstan và cộng sự (Diabetes Care 2012, 19 người 45–65 tuổi thừa cân): cứ 20 phút đứng dậy đi "
                       "bộ nhẹ 2 phút thì đường huyết sau ăn giảm khoảng một phần tư, insulin giảm khoảng 23% so với "
                       "ngồi liền.",
}

# Viết trung tính, không xưng hô: AI nói lại bằng cách xưng hô trong persona (báo cáo HTML thì in nguyên câu này).
FAMILY_WHY = ("Lý do đáng giữ: mỗi khối tập trung trọn vẹn là xong việc sớm hơn, tối về có thêm thời gian thật sự "
              "cho gia đình.")


def advice_key(a, sc):
    """Chọn dữ kiện khoa học hợp với điểm yếu nhất của ngày (None nếu điểm tổng đạt)."""
    if not sc or sc["total"] >= ADVICE_BELOW:
        return None
    if sc["parts"]["interruptions"] < 50:
        return "interrupt_stress" if a.get("exits", 0) >= a.get("short_idle_count", 0) else "switch_3min"
    if a.get("vdi_closed") or a.get("away", 0) > a.get("vdi", 0):
        return "micro_breaks"
    return "attention_residue"


def advice(a, sc):
    """Một câu lời khuyên có căn cứ khoa học khi điểm tổng thấp, kèm lý do vì gia đình. "" nếu điểm ổn."""
    key = advice_key(a, sc)
    return f"{SCIENCE[key]} {FAMILY_WHY}" if key else ""
