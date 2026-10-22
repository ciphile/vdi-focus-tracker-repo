"""Giao diện HTML của báo cáo ngày và báo cáo tuần (file reports/focus-*.html, gửi qua Telegram).

Phong cách Pop Art cổ điển, bảng màu cố định (chọn ngày 16/10/2026):
  nền #F1DFD5 · chữ #1A1A1A · viền và bóng đổ #3E322D
  tập trung sâu #3D8A6F · thao tác trong VDI #4A8A9E · app ngoài VDI #DD814B · VDI bị thu nhỏ #DFAB36
  inactive phím/chuột #9E938B · rời máy #C35850 · làm ngoài giờ (OT) = sọc xanh VDI
Chỉ dùng HTML + CSS + SVG viết tay: không tải gì từ mạng, mở được khi không có Internet, nhẹ để gửi qua Telegram.
Không gọi AI ở đây: lời khuyên AI (nếu có) được truyền vào sẵn.
"""
import datetime as dt
import math

from . import energy, robots, scoring
from .review_text import drop_wish_heading, sections
from .analysis import day_bounds, fmt_dur, fmt_t, focus_score, hour_end, ot_ranges
from .report import avg_dur, breakdown_parts, esc, insights, late_ot_texts, leave_line, real_work_line

WEEKDAY_FULL = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]
WEEKDAY_SHORT = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

# Loại khoảng thời gian trên dòng thời gian -> (nhãn, chữ đậm hay sáng khi nằm trên nền màu đó)
KINDS = {
    "deep": "Tập trung sâu",
    "vdi": "Thao tác trong VDI",
    "ot": "Làm ngoài giờ trong VDI (OT)",
    "other": "App ngoài VDI",
    "min": "VDI bị thu nhỏ",
    "idle": "Inactive phím/chuột",
    "away": "Rời máy / khoá màn hình",
}
LIGHT_TEXT = {"deep", "vdi", "away"}  # nền đậm: chữ màu kem; các nền còn lại: chữ đen
LEVEL_COLOR = ["idle", "other", "min", "vdi", "deep"]  # màu nhãn mức điểm theo hạng robot (kém -> xuất sắc)

CSS = """
:root{--bg:#F1DFD5;--ink:#1A1A1A;--line:#3E322D;--paper:#FBF3EC;--mut:#5E514A;
--deep:#3D8A6F;--vdi:#4A8A9E;--other:#DD814B;--min:#DFAB36;--idle:#9E938B;--away:#C35850;
--ot:repeating-linear-gradient(135deg,#4A8A9E 0 5px,#FBF3EC 5px 8px);
--b:3px solid var(--line);--sh:5px 5px 0 var(--line)}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",-apple-system,system-ui,"Helvetica Neue",
sans-serif;-webkit-text-size-adjust:100%}
main{max-width:1060px;margin:0 auto;padding:26px 16px 56px;overflow-wrap:anywhere;position:relative;overflow-x:hidden}
.num{font-family:Bahnschrift,"DIN Alternate","DIN Condensed","Arial Narrow",sans-serif;font-weight:700;
font-stretch:condensed;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
h1,h2,h3,.disp{font-family:"Segoe UI Black","Segoe UI",-apple-system,system-ui,sans-serif;font-weight:900;
letter-spacing:-.02em;line-height:1.08}
h1{font-size:clamp(30px,6.4vw,54px);margin:10px 0 6px}
h2{font-size:21px;margin:36px 0 14px;display:flex;align-items:center;gap:10px}
h2::before{content:"";flex:0 0 auto;width:13px;height:13px;background:var(--min);border:2px solid var(--line);
transform:rotate(45deg)}
h3{font-size:16px;margin:0 0 6px}
.mut{color:var(--mut)}small{font-size:12px}
.card{background:var(--paper);border:var(--b);border-radius:14px;box-shadow:var(--sh);padding:18px;min-width:0}
.top{position:relative;padding:8px 0 4px}
.top>*{position:relative;z-index:1}
.top .burst{position:absolute;z-index:0;top:-26px;right:-22px;width:140px;height:140px}
.top .burst svg{width:100%;height:100%}.top .burst.small{width:90px;height:90px;top:-14px;right:-12px}
.top .burst .bn{font:900 30px 'Segoe UI Black','Segoe UI',system-ui,sans-serif;fill:#FBF3EC;stroke:#3E322D;stroke-width:1.2px;paint-order:stroke}
.top .burst .bl{font:800 9px 'Segoe UI',system-ui,sans-serif;fill:#FBF3EC;letter-spacing:.5px}
.top .dots{position:absolute;z-index:0;left:-22px;top:-8px;width:220px;height:150px;opacity:.32;
background-image:radial-gradient(var(--line) 1.4px,transparent 1.7px);background-size:8px 8px;
-webkit-mask-image:radial-gradient(closest-side,#000,transparent);mask-image:radial-gradient(closest-side,#000,transparent)}
.kicker{display:inline-block;background:var(--ink);color:var(--paper);font-weight:800;font-size:12px;letter-spacing:.14em;
padding:5px 11px;transform:rotate(-1.5deg);box-shadow:3px 3px 0 var(--away)}
.sub{font-size:17px}.sub b{font-weight:700}
.banner{margin-top:16px;padding:12px 16px;border:var(--b);border-radius:12px;box-shadow:var(--sh);font-weight:600}
.banner.sum{background:var(--paper)}.banner.sum .mut{display:block;margin-top:4px;font-size:13px;font-weight:400}
.banner.leave{background:var(--min)}.banner.off{background:var(--ot);}
.banner.off span{background:var(--paper);padding:2px 8px;border-radius:6px;box-decoration-break:clone;
-webkit-box-decoration-break:clone;line-height:1.9}
/* điểm tổng */
.score{margin-top:22px;display:grid;grid-template-columns:200px minmax(0,1fr) minmax(0,1.25fr);gap:20px;align-items:center;
position:relative}
.robot{position:relative;display:flex;justify-content:center;align-items:flex-end;height:220px}
.robot .halo{position:absolute;left:50%;top:50%;width:190px;height:190px;margin:-95px 0 0 -95px;border-radius:50%;
background:var(--min);border:var(--b);overflow:hidden}
.robot .halo::after{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(62,50,45,.35) 1.6px,
transparent 1.9px);background-size:9px 9px}
.robot svg{position:relative}
.slabel{font-weight:800;font-size:13px;letter-spacing:.12em}
.big{font-size:104px;line-height:.86;margin:6px 0 8px}.big span{font-size:30px;color:var(--mut)}
.verdict{display:inline-block;padding:4px 12px;border:var(--b);border-radius:999px;font-weight:800;letter-spacing:.06em;
box-shadow:3px 3px 0 var(--line)}
.gift{margin-top:12px}
.parts{display:grid;gap:10px}
.part{display:grid;grid-template-columns:minmax(110px,1.1fr) minmax(80px,2fr) 38px 52px;gap:10px;align-items:center}
.part .w{color:var(--mut);font-size:13px}.part .pv{font-size:22px;text-align:right}
.part .pc{font-size:13px;color:var(--mut);text-align:right}
.track{position:relative;height:18px;border:2px solid var(--line);border-radius:999px;background:#fff;overflow:hidden}
.track i{position:absolute;left:0;top:0;bottom:0;border-right:2px solid var(--line)}
.track em{position:absolute;top:-2px;bottom:-2px;border-left:2px dashed var(--line)}
.why{margin-top:6px;padding-top:10px;border-top:2px dashed var(--line);font-size:14px}
.why ul{margin:4px 0 0;padding-left:20px}
.ladder{grid-column:1/-1;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.rung{border:2px solid var(--line);border-radius:12px;padding:6px 4px 8px;text-align:center;background:#fff;font-size:12px;
line-height:1.25}
.rung svg{display:block;margin:0 auto}.rung b{display:block;font-size:14px}
.rung.locked{filter:grayscale(1);opacity:.4;border-style:dashed}
.rung.now{background:var(--min);box-shadow:3px 3px 0 var(--line);transform:translateY(-3px)}
.rung.now b::after{content:" ★"}
.tip{grid-column:1/-1;margin:0;padding:12px 14px;border:2px solid var(--line);border-radius:10px;background:#fff}
.sticker{position:absolute;top:-24px;right:-12px;width:78px;height:78px;z-index:2}
.score>.parts{margin-top:46px}
.sticker text{font:900 15px "Segoe UI Black","Segoe UI",system-ui,sans-serif}
/* ô số liệu màu */
.stats{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin-top:22px}
.stats.s3{grid-template-columns:repeat(3,minmax(0,1fr))}
.stat{background:var(--c);color:var(--ink);border:var(--b);border-radius:14px;box-shadow:var(--sh);padding:14px;
min-height:136px;display:flex;flex-direction:column;justify-content:flex-end}
.stat.lt{color:var(--paper)}
.stat .v{font-size:clamp(24px,2.9vw,36px);line-height:1;white-space:nowrap}.stat .k{font-weight:700;margin-top:6px;line-height:1.2}
.stat .s{font-size:13px;opacity:.9;margin-top:2px;line-height:1.3}
.stats.more{grid-template-columns:repeat(var(--cols),minmax(0,1fr));margin-top:16px}
.stat.plain{min-height:118px;padding-top:0;overflow:hidden}
.stat.plain .bar{height:12px;margin:0 -14px auto;border-bottom:2px solid var(--line)}.stat.plain .v{margin-top:14px}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.chip{background:var(--paper);border:2px solid var(--line);border-radius:999px;padding:5px 14px 5px 6px;
display:flex;align-items:center;gap:8px;font-size:14px;box-shadow:2px 2px 0 var(--line)}
.chip .num{background:var(--ink);color:var(--paper);border-radius:999px;padding:1px 10px;font-size:15px}
/* dòng thời gian */
.tl{position:relative;height:48px;border:var(--b);border-radius:10px;background:#fff;overflow:hidden}
.tl.sm{height:28px;border-width:2px;border-radius:8px}
.tl i{position:absolute;top:0;bottom:0}
.tl .lunch{position:absolute;top:0;bottom:0;background:repeating-linear-gradient(45deg,transparent 0 6px,
rgba(62,50,45,.13) 6px 8px)}
.ticks{position:relative;height:26px;font-size:12px;font-weight:700;margin-top:2px}
.ticks span{position:absolute;transform:translateX(-50%);white-space:nowrap;padding-top:8px}
.ticks span::before{content:"";position:absolute;left:50%;top:0;width:3px;height:7px;margin-left:-1.5px;
background:var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:13px;margin-top:10px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:16px;height:16px;border:2px solid var(--line);border-radius:4px}
.sw.blank{background:#fff}.sw.lunchsw{background:#fff repeating-linear-gradient(45deg,transparent 0 3px,rgba(62,50,45,.35) 3px 5px)}
.dayrow{display:grid;grid-template-columns:86px minmax(0,1fr);gap:10px;align-items:center;margin-bottom:8px}
/* bảng */
.grid2{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:22px;align-items:start}
.scroll{overflow-x:auto;border-radius:12px}
table{width:100%;border-collapse:separate;border-spacing:0;border:var(--b);border-radius:12px;overflow:hidden;
background:var(--paper);font-size:14px;box-shadow:var(--sh)}
th,td{padding:7px 10px;text-align:left;border-right:2px solid var(--line);border-bottom:2px solid var(--line);
white-space:nowrap}
th:last-child,td:last-child{border-right:0}tr:last-child td{border-bottom:0}
th{font-weight:800;font-size:13px}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.apps .row{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(50px,1fr) 60px;gap:10px;align-items:center;
padding:4px 0}
.apps .row .track{height:14px}
/* biểu đồ theo giờ */
.hours{display:flex;align-items:flex-end;gap:6px;height:160px;border-bottom:3px solid var(--line);padding:0 2px}
.hours .col{flex:1;display:flex;flex-direction:column-reverse;height:100%;min-width:0}
.hours .col i{display:block;border:2px solid var(--line);border-bottom-width:0;margin-top:-2px}
.hours .col i:first-child{border-bottom-width:0}
.hlab{display:flex;gap:6px;font-size:12px;font-weight:700;padding:4px 2px 0}.hlab span{flex:1;text-align:center;min-width:0}
/* 7 ngày */
.days .drow{display:grid;grid-template-columns:78px minmax(60px,1fr) 64px 44px;gap:10px;align-items:center;
padding:5px 0;border-bottom:1px dashed rgba(62,50,45,.35)}
.days .drow:last-child{border-bottom:0}
.days .when{font-size:12px;color:var(--mut);grid-column:2/-1;margin-top:-4px}
.badge{display:inline-block;min-width:40px;text-align:center;border:2px solid var(--line);border-radius:8px;
padding:0 6px;font-weight:800}
/* nhận xét */
.say{position:relative;margin-top:4px}
.say ul{margin:0;padding-left:20px}.say li{margin:3px 0}
.bubble{position:relative;margin-top:22px;background:#fff}
.bubble::after{content:"";position:absolute;left:36px;bottom:-17px;width:26px;height:26px;background:#fff;
border-right:3px solid var(--line);border-bottom:3px solid var(--line);transform:skewY(35deg) rotate(10deg)}
.ai{white-space:normal;line-height:1.6}
.aisec{margin:0 0 16px}.aisec:last-child{margin-bottom:0}.aisec p{margin:6px 0 0}
.aih{display:inline-block;margin:0;padding:1px 10px;background:var(--min);border:2px solid var(--line);border-radius:6px;box-shadow:2px 2px 0 var(--line);font-size:14px;font-weight:800;letter-spacing:.2px}
/* giấy ghi chú */
.notes{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:22px 18px;margin-top:8px}
.note{position:relative;background:#FFF9F2;border:var(--b);border-radius:4px 4px 22px 4px;box-shadow:var(--sh);
padding:22px 14px 14px;transform:rotate(var(--r,0deg));font-size:14px}
.note::before{content:"";position:absolute;top:-13px;left:50%;width:72px;height:22px;margin-left:-36px;
background:rgba(223,171,54,.8);border:2px solid var(--line);transform:rotate(-3deg)}
.note .body{margin-top:4px}
.plist{margin:0;padding-left:18px}.plist li{margin:2px 0}
.dots5{display:flex;gap:6px;margin:8px 0 4px}
.dots5 i{width:22px;height:22px;border-radius:50%;border:2px solid var(--line);background:#fff}
.dots5 i.on{background:var(--away)}
/* biểu đồ tuần */
.wbars{display:flex;align-items:flex-end;gap:14px;height:190px;border-bottom:3px solid var(--line);position:relative;
padding:0 6px}
.wbars .wb{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;min-width:0;text-align:center}
.wbars .wb i{display:block;background:var(--deep);border:2px solid var(--line);border-bottom:0;border-radius:6px 6px 0 0}
.wbars .wb i.ot{background:var(--ot);border-radius:0}
.wbars .goal{position:absolute;left:0;right:0;border-top:3px dashed var(--away)}
.wbars .goal span{position:absolute;right:0;top:-24px;font-size:12px;font-weight:700;color:var(--away);
background:var(--paper);padding:0 4px}
/* OT 14 ngày */
.ot .orow{display:grid;grid-template-columns:150px minmax(60px,1fr) 70px;gap:12px;align-items:center;padding:6px 0;
border-bottom:1px dashed rgba(62,50,45,.35)}
.ot .orow:last-child{border-bottom:0}.ot .rg{grid-column:2/-1;font-size:12px;color:var(--mut);margin-top:-6px}
.ot .head{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:8px}
.wlab{display:flex;gap:14px;padding:4px 6px 0;font-size:12px;font-weight:700}.wlab span{flex:1;text-align:center}
.collect{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:12px}
.collect .rung{padding:8px 6px 10px}
details.card{margin-top:22px}details summary{cursor:pointer;font-weight:800}details ul{margin:10px 0 0;padding-left:20px}
details li{margin:4px 0}
footer{margin-top:34px;display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:12px;
color:var(--mut)}
@media (max-width:820px){.score{grid-template-columns:1fr}.grid2{grid-template-columns:1fr}
.stats,.stats.more{grid-template-columns:repeat(3,minmax(0,1fr))}
.robot{height:200px}.ladder{gap:6px}.big{font-size:88px}}
@media (max-width:560px){.ticks span:nth-child(even){display:none}.stat .v{font-size:30px}
.stats,.stats.s3,.stats.more{grid-template-columns:repeat(2,minmax(0,1fr))}.ot .orow{grid-template-columns:1fr 64px}
.ot .orow .track{display:none}.ot .rg{grid-column:1/-1}
.part{grid-template-columns:1fr 38px 52px}.part .track{grid-column:1/-1;grid-row:2}
.top .burst{width:80px;height:80px;top:-20px;right:-10px}.top .burst.small{width:56px;height:56px}.rung svg{width:34px;height:40px}.rung{font-size:11px}
.dayrow{grid-template-columns:1fr}.dayrow>b{margin-bottom:-4px}}
@media print{body{background:#fff}.card,.stat,.note,table{box-shadow:none}}
"""


# ----------------------------------------------------------------------------------------------- mảnh ghép chung

def burst(fill, n=14, size=170, inner=0.62, label="", content=""):
    """Hình nổ kiểu truyện tranh (SVG), có thể kèm chữ (label) hoặc SVG tự soạn đặt giữa (content)."""
    c, pts = 50, []
    for i in range(n * 2):
        r = 48 if i % 2 == 0 else 48 * inner
        ang = math.pi * i / n - math.pi / 2
        pts.append(f"{c + r * math.cos(ang):.1f},{c + r * math.sin(ang):.1f}")
    txt = (f"<text x='50' y='55' text-anchor='middle' fill='#1A1A1A'>{esc(label)}</text>" if label else "")
    return (f"<svg viewBox='0 0 100 100' width='{size}' height='{size}' aria-hidden='true'>"
            f"<polygon points='{' '.join(pts)}' fill='{fill}' stroke='#3E322D' stroke-width='2.5' "
            f"stroke-linejoin='round'/>{txt}{content}</svg>")


def page(title, body):
    return (f"<!doctype html><html lang='vi'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f"<style>{CSS}</style></head><body><main>{body}"
            f"<footer><span>{burst('#C35850', 10, 26)}</span><span>Tạo lúc {dt.datetime.now():%H:%M %d/%m/%Y}"
            f"</span></footer></main></body></html>")


def header(kicker, title, sub, score=None):
    """Đầu báo cáo. score: điểm tổng (ngày) / điểm tổng trung bình (tuần), in giữa hình nổ đỏ góc phải: mức chữ
    (kém, chưa tốt, trung bình, tốt, xuất sắc), số điểm, "/100". Không có điểm (chưa có số liệu, ngày nghỉ làm bù):
    hình nổ nhỏ, không chữ."""
    if score is None:
        star = f"<div class='burst small'>{burst('#C35850')}</div>"
    else:
        word = scoring.tier_of(score)["verdict"].upper()
        fit = " textLength='50' lengthAdjust='spacingAndGlyphs'" if len(word) > 8 else ""  # TRUNG BÌNH, CHƯA TỐT
        num = (f"<text x='50' y='35' text-anchor='middle' class='bl'{fit}>{esc(word)}</text>"
               f"<text x='50' y='62' text-anchor='middle' class='bn'>{int(score)}</text>"
               "<text x='50' y='75' text-anchor='middle' class='bl'>/100</text>")
        star = f"<div class='burst'>{burst('#C35850', content=num)}</div>"
    return (f"<header class='top'><div class='dots'></div>{star}"
            f"<div class='kicker'>{esc(kicker)}</div><h1>{esc(title)}</h1><div class='sub'>{sub}</div></header>")


def stat(kind, value, label, sub=""):
    bg = "var(--ot)" if kind == "ot" else f"var(--{kind})"
    return (f"<div class='stat{' lt' if kind in LIGHT_TEXT else ''}' style='--c:{bg}'>"
            f"<div class='v num'>{value}</div><div class='k'>{label}</div>"
            + (f"<div class='s'>{sub}</div>" if sub else "") + "</div>")


def plain_stat(accent, value, label, sub=""):
    """Thẻ lớn nền kem (chỉ số phụ: điểm tập trung, OT, khối dài nhất...), dải màu trên đầu cho dễ phân biệt."""
    bg = "var(--ot)" if accent == "ot" else f"var(--{accent})"
    return (f"<div class='stat plain' style='--c:var(--paper)'><div class='bar' style='background:{bg}'></div>"
            f"<div class='v num'>{value}</div><div class='k'>{label}</div>"
            + (f"<div class='s'>{sub}</div>" if sub else "") + "</div>")


def stat_row(cards):
    """Hàng thẻ lớn phụ: 4 thẻ trở xuống một hàng, nhiều hơn thì chia đều 2 hàng."""
    cols = len(cards) if len(cards) <= 4 else (len(cards) + 1) // 2
    return f"<div class='stats more' style='--cols:{cols}'>" + "".join(cards) + "</div>"


def chip(value, label):
    return f"<div class='chip'><span class='num'>{value}</span>{label}</div>"


def swatch(kind):
    bg = "var(--ot)" if kind == "ot" else f"var(--{kind})"
    return f"<i class='sw' style='background:{bg}'></i>"


def legend(kinds, cfg, blank=False, lunch=False):
    """Chú thích màu. blank: thêm ô trắng (không ghi); lunch: thêm ô sọc mờ (nghỉ trưa, không tính)."""
    names = dict(KINDS, deep=f"Tập trung sâu (khối ≥ {cfg['min_focus_block_minutes']}m)")
    items = [f"<span>{swatch(k)}{names[k]}</span>" for k in kinds]
    if lunch:
        items.append(f"<span><i class='sw lunchsw'></i>Nghỉ trưa {cfg['lunch_start']}–{cfg['lunch_end']} (không tính)"
                     "</span>")
    if blank:
        items.append("<span><i class='sw blank'></i>Trắng: không ghi (trước khi bắt đầu / sau khi ngừng dùng máy, "
                     "hoặc ngoài giờ làm mà không làm trong VDI)</span>")
    return "<div class='legend'>" + "".join(items) + "</div>"


def verdict_chip(tier, extra=""):
    k = LEVEL_COLOR[tier["level"]]
    color = "var(--paper)" if k in LIGHT_TEXT else "var(--ink)"
    return (f"<span class='verdict' style='background:var(--{k});color:{color}'>{esc(tier['verdict'].upper())}"
            f"{extra}</span>")


def track(pct, kind, goal_pct=None):
    bg = "var(--ot)" if kind == "ot" else f"var(--{kind})"
    pct = max(0.0, min(100.0, pct))
    return (f"<div class='track'><i style='width:{pct:.1f}%;background:{bg}'></i>"
            + (f"<em style='left:{min(goal_pct, 100):.1f}%'></em>" if goal_pct is not None else "") + "</div>")


def ladder(level, size=46):
    out = []
    for i, (lo, grade, name, _) in enumerate(scoring.TIERS):
        hi = scoring.TIERS[i + 1][0] if i + 1 < len(scoring.TIERS) else None
        rng = f"&lt;{hi}" if lo == 0 else (f"≥{lo}" if hi is None else f"{lo}–{hi - 1}")
        cls = "now" if i == level else ("locked" if i > level else "got")
        out.append(f"<div class='rung {cls}'>{robots.robot_svg(i, size)}<b>{grade}</b>{esc(name)}<br>"
                   f"<small>{rng} · {scoring.VERDICTS[i]}</small></div>")
    return "<div class='ladder'>" + "".join(out) + "</div>"


def note_box(title, body, rot=0.0, raw=False):
    content = body if raw else (esc(body) if body not in (None, "") else "")
    return (f"<div class='note' style='--r:{rot}deg'><h3>{title}</h3>"
            f"<div class='body'>{content or '<i class=mut>chưa nhập</i>'}</div></div>")


def pending_box(items, rot=0.0):
    """Ghi chú "Việc tồn sang ngày mai" (cộng dồn, có ngày bắt đầu tồn). Không có việc tồn: ghi rõ là không có."""
    from .pending import MAX_ITEMS, since_label
    if not items:
        return note_box("📌 Việc tồn sang ngày mai", "<i class=mut>không còn việc tồn (theo những gì đã ghi)</i>", rot,
                        raw=True)
    rows = "".join(f"<li>{'⚠️ issue: ' if k == 'issue' else ''}{esc(t)} <small class='mut'>· tồn từ {since_label(s)}"
                   "</small></li>" for k, t, s in items[:MAX_ITEMS])
    more = f"<li class='mut'>… và {len(items) - MAX_ITEMS} việc nữa</li>" if len(items) > MAX_ITEMS else ""
    return note_box("📌 Việc tồn sang ngày mai", f"<ul class='plist'>{rows}{more}</ul>"
                    "<small class='mut'>Kế hoạch / issue chưa thấy ghi xong trong output, cộng dồn qua các ngày.</small>",
                    rot, raw=True)


def energy_dots(value):
    try:
        v = max(0, min(5, int(value)))
    except (TypeError, ValueError):
        return ""
    return "<div class='dots5'>" + "".join(f"<i class='{'on' if i < v else ''}'></i>" for i in range(5)) + "</div>"


def science_details(a=None, cfg=None):
    est = energy.estimate(a, (cfg or {}).get("energy_capacity_hours") or 4) if a else None
    return ("<details class='card'><summary>Cách tính điểm và căn cứ khoa học</summary><ul>"
            "<li><b>Điểm tập trung</b>: 70 điểm cho giờ tập trung sâu so với mục tiêu, 30 điểm cho tỉ lệ thời gian "
            "trong VDI. Năng lượng không ảnh hưởng điểm này.</li>"
            f"<li><b>Ít bị cắt ngang</b>: mỗi lần rời VDI / thu nhỏ VDI hoặc ngồi yên ngắn rồi làm tiếp là một lần bị "
            f"cắt ngang. {scoring.SWITCHES_PER_HOUR_ZERO} lần/giờ (cứ 3 phút một lần) là mức González &amp; Mark (2004) "
            "đo được ở nhân viên IT văn phòng: tới mức đó phần này 0 điểm. Bị cắt ngang làm tăng căng thẳng (Mark "
            "và cộng sự 2008) và để lại \"dư âm chú ý\" (Leroy 2009).</li>"
            "<li><b>Năng lượng</b> (1–5) là sức còn lại cuối ngày. Bạn tự chấm (/energy) thì được tính 10% điểm tổng; "
            "bot tự ước tính thì KHÔNG tính vào điểm tổng (đó là quy tắc của app, không phải số đo). Công thức ước "
            "tính: tải = tập trung sâu + 0,5 × làm vụn trong VDI + 0,5 × phần quá 90 phút của mỗi khối; năng lượng = "
            "5 − 4 × min(tải / 4 giờ, 1)"
            + (f". Hôm nay: tải {est['load_h']:.1f}h → năng lượng ước tính {est['exact']:g}." if est else ".")
            + " Năng lượng giúp AI khuyên ngày mai nên dồn việc khó hay nghỉ bớt.</li>"
            "<li><b>Trọng số</b> 60% / 30% / 10% (chưa tự chấm năng lượng: 65% / 35%) là lựa chọn của app: chưa có "
            "nghiên cứu nào công bố một công thức gộp đã kiểm chứng cho đúng bộ số liệu này. Từng thành phần và "
            "ngưỡng thì có căn cứ thực nghiệm như trên.</li>"
            "<li><b>Robot quà</b>: SD dưới 30 · HG 30–49 · RG 50–69 · MG 70–84 · PG từ 85. Robot do app tự vẽ theo kiểu "
            "mô hình lắp ráp, không dùng hình Gundam / Bandai thật (có bản quyền).</li>"
            "<li><b>Ngoài giờ (OT)</b> (trước giờ làm, sau giờ làm, ngày nghỉ bật bot làm bù): chỉ cộng giờ làm "
            "trong VDI có gõ phím/chuột, không tính ngoài VDI, thu nhỏ, inactive, rời máy. Giờ nghỉ trưa không tính "
            "gì cả (không sao nhãng, không OT).</li></ul></details>")


# ----------------------------------------------------------------------------------------------- dòng thời gian

def _at(day, hhmm):
    d0, _ = day_bounds(day)
    h, m = map(int, hhmm.split(":"))
    return d0 + h * 3600 + m * 60


def segments(a):
    """Các khoảng (bắt đầu, kết thúc, loại) để tô: VDI nằm trong khối tập trung -> deep; VDI thu nhỏ tô đè lên."""
    blocks = sorted((b["start"], b["end"]) for b in a.get("blocks") or [])
    out = []
    for s, e, k in a.get("timeline") or []:
        if k != "vdi":
            out.append((s, e, k))
            continue
        cur = s
        for bs, be in blocks:
            if be <= cur or bs >= e:
                continue
            if bs > cur:
                out.append((cur, bs, "vdi"))
            out.append((max(cur, bs), min(e, be), "deep"))
            cur = min(e, be)
        if cur < e:
            out.append((cur, e, "vdi"))
    out += [(s, e, "min") for s, e in a.get("minimized_spans") or []]
    return out


def time_range(cfg, a_list):
    """Khung giờ chung cho dòng thời gian: ít nhất giờ làm chính thức, nới ra theo dữ liệu (tròn giờ)."""
    t0 = t1 = None
    for a in a_list:
        s = min(_at(a["day"], cfg["work_start"]), a["first"] // 3600 * 3600)
        e = max(_at(a["day"], cfg["work_end"]), hour_end(a["last"] - 1))
        d0, _ = day_bounds(a["day"])
        t0 = s - d0 if t0 is None else min(t0, s - d0)
        t1 = e - d0 if t1 is None else max(t1, e - d0)
    return t0, t1


def timeline_bar(cfg, a, off0, off1, small=False):
    """Thanh dòng thời gian của 1 ngày, từ off0 tới off1 giây tính từ 0 giờ."""
    d0, _ = day_bounds(a["day"])
    t0, t1 = d0 + off0, d0 + off1
    span = max(t1 - t0, 1)
    pos = lambda s, e: f"left:{(s - t0) / span * 100:.3f}%;width:{max((e - s) / span * 100, 0.12):.3f}%"
    out = []
    if not a.get("off"):
        ls, le = _at(a["day"], cfg["lunch_start"]), _at(a["day"], cfg["lunch_end"])
        if le > t0 and ls < t1:
            out.append(f"<div class='lunch' style='{pos(max(ls, t0), min(le, t1))}' title='Nghỉ trưa "
                       f"{cfg['lunch_start']}–{cfg['lunch_end']}: không tính'></div>")
    for s, e, k in segments(a):
        bg = "var(--ot)" if k == "ot" else f"var(--{k})"
        out.append(f"<i title='{fmt_t(s)}–{fmt_t(e)} · {KINDS[k]} · {fmt_dur(e - s)}' "
                   f"style='{pos(s, e)};background:{bg}'></i>")
    return f"<div class='tl{' sm' if small else ''}'>{''.join(out)}</div>"


def ticks(day, off0, off1):
    d0, _ = day_bounds(day)
    span = max(off1 - off0, 1)
    return "<div class='ticks'>" + "".join(
        f"<span style='left:{(t - off0) / span * 100:.2f}%'>{fmt_t(d0 + t)}</span>"
        for t in range(int(off0), int(off1) + 1, 3600)) + "</div>"


# ----------------------------------------------------------------------------------------------- báo cáo ngày

def score_section(cfg, a, note, sc):
    tier, ex = sc["tier"], scoring.explain(a, sc)
    nxt = next((t for t in scoring.TIERS if t[0] > sc["total"]), None)
    w, p = sc["weights"], sc["parts"]
    colors = {"focus": "deep", "interruptions": "vdi", "energy": "min"}
    vn = lambda x: f"{x:.1f}".replace(".", ",")
    rows = "".join(
        f"<div class='part'><div><b>{scoring.PART_NAMES[k][0].upper() + scoring.PART_NAMES[k][1:]}</b> "
        f"<span class='w'>× {int(round(w[k] * 100))}%</span></div>{track(p[k], colors[k])}"
        f"<div class='pv num'>{p[k]}</div><div class='pc' title='góp vào điểm tổng'>+{vn(w[k] * p[k])}</div></div>"
        for k in w)
    if "energy" not in p:
        rows += ("<div class='part'><div><b>Năng lượng tự chấm</b> <span class='w'>× 0%</span></div>"
                 "<div class='mut' style='font-size:13px'>chưa tự chấm (/energy 1–5) nên không tính</div>"
                 "<div></div><div></div></div>")
    tip = scoring.advice(a, sc)
    return (
        "<section class='card score'>"
        f"<div class='sticker'>{burst('#DFAB36', 12, 78, 0.7, tier['grade'])}</div>"
        f"<div class='robot'><div class='halo'></div>{robots.robot_svg(tier['level'], 170)}</div>"
        "<div><div class='slabel'>ĐIỂM TỔNG HÔM NAY</div>"
        f"<div class='big num'>{sc['total']}<span>/100</span></div>"
        f"{verdict_chip(tier, ' · ' + vn(sc['ten']) + '/10')}"
        f"<div class='gift'>Quà hôm nay: robot <b>{tier['grade']} {esc(tier['name'])}</b> ({esc(tier['desc'])})."
        + (f" Thêm <b>{nxt[0] - sc['total']}</b> điểm để lên {nxt[1]} {esc(nxt[2])}." if nxt else " Hạng cao nhất!")
        + "</div></div>"
        f"<div class='parts'>{rows}<div class='why'>📉 <b>Kéo điểm xuống nhiều nhất:</b> {esc(ex['biggest_loss'])}."
        "<br><b>Muốn lên điểm:</b><ul>" + "".join(f"<li>{esc(x)}</li>" for x in ex["how_to_raise"]) + "</ul></div></div>"
        + ladder(tier["level"])
        + (f"<p class='tip'>🔬 {esc(tip)}</p>" if tip else "")
        + "<details style='grid-column:1/-1'><summary>Công thức với số của hôm nay</summary><ul>"
        + "".join(f"<li>{esc(x)}</li>" for x in scoring.formula_lines(a, sc)) + "</ul></details>"
        "</section>")


def render_day(cfg, a, note, week, extra=None):
    extra = extra or {}
    day = a["day"]
    d = dt.date.fromisoformat(day)
    title = f"{WEEKDAY_FULL[d.weekday()]} {d:%d.%m.%Y}"
    if not a["has_data"]:
        sub = "Chưa có dữ liệu cho ngày này."
        body = header("TỔNG KẾT TẬP TRUNG", title, sub)
        if a.get("leave"):
            body += f"<div class='banner leave'>🌴 {esc(leave_line(a))}</div>"
        return page(f"Tập trung {day}", body + notes_section(cfg, note, extra))
    sub = (f"⏱ Làm việc từ <b>{fmt_t(a['first'])}</b> đến <b>{fmt_t(a['last'])}</b> ({fmt_dur(a['span'])})"
           f" · mục tiêu tập trung sâu {a['goal_h']:g}h")
    off = a.get("off")
    sc = None if off else scoring.total_score(a, note)
    p = [header("TỔNG KẾT TẬP TRUNG", title, sub, sc["total"] if sc else None)]
    if a.get("leave"):
        p.append(f"<div class='banner leave'>🌴 {esc(leave_line(a))}</div>")
    mb = cfg["min_focus_block_minutes"]
    goal = a["goal_h"] * 3600
    if off:
        p.append(f"<div class='banner off'><span>🌙 Hôm nay nghỉ ({esc(off)}), bạn bật bot làm bù. Bot chỉ ghi giờ làm "
                 "trong VDI có gõ phím/chuột: không tính sao nhãng, không cảnh báo, không chấm điểm.</span></div>")
        p.append("<div class='stats s3'>"
                 + plain_stat("ot", fmt_dur(a.get("ot", 0)), "Làm bù trong VDI")
                 + stat("deep", fmt_dur(a["deep"]), f"Tập trung sâu (khối ≥ {mb}m)", f"{len(a['blocks'])} khối")
                 + stat("vdi", fmt_dur(a["longest"]), "Khối dài nhất") + "</div>")
    else:
        p.append(score_section(cfg, a, note, sc))
        pct = a["deep"] / goal * 100 if goal else 0
        p.append("<div class='stats'>"
                 + stat("deep", fmt_dur(a["deep"]), f"Tập trung sâu (khối ≥ {mb}m)",
                        f"{len(a['blocks'])} khối · {pct:.0f}% mục tiêu"
                        + (f" · có {fmt_dur(a['deep_ot'])} ngoài giờ" if a.get("deep_ot") else ""))
                 + stat("vdi", fmt_dur(a["vdi"]), "Thao tác trong VDI", "trong giờ làm"
                        + (f" · {fmt_dur(a['windowed'])} chưa toàn màn hình" if a.get("windowed", 0) >= 60 else ""))
                 + stat("other", fmt_dur(a["other"]), "Ngoài VDI",
                        f"{a['exits']} lần rời VDI · TB mỗi lần {avg_dur(a['other'], a['exits'])}")
                 + stat("min", fmt_dur(a["minimized"]), "VDI bị thu nhỏ",
                        f"{a.get('minimize_count', 0)} lần · TB mỗi lần "
                        f"{avg_dur(a['minimized'], a.get('minimize_count', 0))}")
                 + stat("idle", fmt_dur(a["idle"]), "Inactive phím/chuột",
                        f"{a['short_idle_count']} lần · TB mỗi lần {avg_dur(a['idle'], a['short_idle_count'])}")
                 + stat("away", fmt_dur(a["away"]), "Rời máy",
                        f"{a['away_count']} lần · TB mỗi lần {avg_dur(a['away'], a['away_count'])}")
                 + "</div>")
        bd = breakdown_parts(a)
        if bd:  # cộng các ô giờ ở trên cho thấy đủ giờ làm
            p.append(f"<div class='banner sum'>🧮 Cộng giờ làm: <span class='num'>{esc(bd[0])}</span>"
                     f"<span class='mut'>{esc(bd[1])}</span></div>")
        # Thực làm trong VDI = trong giờ + OT của CHÍNH ngày này; OT ngày trước làm sau giờ báo cáo chỉ nhắc lại.
        p.append(f"<div class='banner sum'>{esc(real_work_line(a))}<span class='mut'>OT tính cho đúng ngày làm "
                 "(qua 00:00 là ngày mới), không cộng sang ngày khác</span></div>")
        for line in late_ot_texts(extra.get("late_ot") or []):
            p.append(f"<div class='banner sum'>{esc(line)}<span class='mut'>làm sau khi báo cáo hôm đó đã gửi, "
                     "nên nhắc lại ở đây; đã cộng vào đúng ngày đó, không cộng vào hôm nay</span></div>")
        streak = extra.get("streak", 0)
        closed = a.get("vdi_closed") or []
        cards = [plain_stat("deep", f"{focus_score(a)}<small>/100</small>", "Điểm tập trung",
                            "70 điểm tập trung sâu + 30 điểm tỉ lệ trong VDI")]
        if a.get("ot", 0) >= 60:  # OT = 0 thì không hiện thẻ OT (các thẻ khác = 0 vẫn hiện)
            cards.append(plain_stat("ot", fmt_dur(a["ot"]), "Làm ngoài giờ trong VDI (OT)",
                                    ", ".join(f"{fmt_t(x)}–{fmt_t(y)}" for x, y in ot_ranges(a))))
        cards += [plain_stat("deep", fmt_dur(a["longest"]), "Khối tập trung dài nhất"),
                  plain_stat("vdi", f"{sc['per_hour']:g}".replace(".", ","), "Lần bị cắt ngang mỗi giờ",
                             f"tổng {sc['interruptions']} lần (rời VDI + inactive 1–5 phút)"),
                  plain_stat("idle", f"{a.get('inactive_10m_count', 0)} lần", "Inactive / rời máy ≥ 10 phút"),
                  plain_stat("min", f"{streak} ngày", "Chuỗi ngày đạt mục tiêu" + (" 🔥" if streak >= 3 else "")),
                  plain_stat("away", f"{len(closed)} lần", "VDI bị đóng / tự ngắt",
                             ", ".join(f"{fmt_t(x)}–{fmt_t(y)}" for x, y in closed))]
        p.append(stat_row(cards))

    # Dòng thời gian
    o0, o1 = time_range(cfg, [a])
    kinds = ["deep", "vdi", "ot"] if off else ["deep", "vdi", "ot", "other", "min", "idle", "away"]
    p.append("<h2>Dòng thời gian</h2><div class='card'>" + timeline_bar(cfg, a, o0, o1) + ticks(day, o0, o1)
             + legend(kinds, cfg, blank=True, lunch=not off)
             + "<div class='mut' style='font-size:12px;margin-top:6px'>Rê chuột (hoặc chạm) lên thanh để xem giờ.</div>"
             + "</div>")

    # Khối tập trung + app ngoài VDI
    heads = [("Từ", "deep"), ("Đến", "vdi"), ("Độ dài", "other"), ("Thực sự trong VDI", "min"), ("Ngoài giờ", "idle"),
             ("Ngắt quãng", "away")]
    th = "".join(f"<th style='background:var(--{k});color:{'var(--paper)' if k in LIGHT_TEXT else 'var(--ink)'}'>{t}</th>"
                 for t, k in heads)
    if a["blocks"]:
        blocks = ("<div class='scroll'><table><tr>" + th + "</tr>" + "".join(
            f"<tr><td>{fmt_t(b['start'])}</td><td>{fmt_t(b['end'])}</td><td class='n'>{fmt_dur(b['end'] - b['start'])}</td>"
            f"<td class='n'>{fmt_dur(b['focus'])}</td><td class='n'>{fmt_dur(b['ot']) if b.get('ot') else '–'}</td>"
            f"<td class='n'>{b['breaks']}</td></tr>" for b in a["blocks"]) + "</table></div>")
    else:
        blocks = f"<div class='card mut'>Chưa có khối nào đủ {mb} phút.</div>"
    if a["apps"] and not off:
        mx = a["apps"][0][1] or 1
        apps = ("<div class='card apps'>" + "".join(
            f"<div class='row'><span>{esc(proc)}</span>{track(s / mx * 100, 'other')}<span class='num' "
            f"style='text-align:right'>{fmt_dur(s)}</span></div>" for proc, s in a["apps"]) + "</div>")
    else:
        apps = "<div class='card mut'>Không dùng app nào ngoài VDI.</div>" if not off else ""
    p.append("<div class='grid2'><div><h2>Các khối tập trung</h2>" + blocks + "</div>"
             + (f"<div><h2>App ngoài VDI</h2>{apps}</div>" if apps else "") + "</div>")

    # Theo giờ + 7 ngày
    hours = range(dt.datetime.fromtimestamp(day_bounds(day)[0] + o0).hour,
                  dt.datetime.fromtimestamp(day_bounds(day)[0] + o1 - 1).hour + 1)
    cols, labs = [], []
    for h in hours:
        v = a["hourly"].get(h, {"vdi": 0, "other": 0, "ot": 0})
        parts = [("vdi", v["vdi"]), ("ot", v.get("ot", 0)), ("other", v["other"])]
        cols.append(f"<div class='col' title='{h:02d}h: VDI {fmt_dur(v['vdi'])}, ngoài giờ {fmt_dur(v.get('ot', 0))}, "
                    f"ngoài VDI {fmt_dur(v['other'])}'>" + "".join(
                        f"<i style='height:{sec / 36:.1f}%;background:{'var(--ot)' if k == 'ot' else f'var(--{k})'}'></i>"
                        for k, sec in parts if sec >= 30) + "</div>")
        labs.append(f"<span>{h}</span>")
    hourly = ("<div class='card'><div class='hours'>" + "".join(cols) + "</div><div class='hlab'>" + "".join(labs)
              + "</div>" + legend(["vdi", "ot", "other"], cfg) + "</div>")
    p.append("<div class='grid2'><div><h2>Theo giờ (phút hoạt động)</h2>" + hourly + "</div>"
             "<div><h2>7 ngày gần nhất</h2>" + week_list(week, a["goal_h"]) + "</div></div>")

    if extra.get("ot_history") is not None:
        p.append(ot_section(extra["ot_history"]))

    # Nhận xét + AI
    if not off:
        p.append("<h2>Nhận xét</h2><div class='card say'><div class='sticker'>" + burst("#4A8A9E", 9, 60, 0.6)
                 + "</div><ul>" + "".join(f"<li>{esc(x)}</li>" for x in insights(a)) + "</ul></div>")
    p.append("<h2>Lời khuyên của AI</h2>" + ai_box(extra.get("review"), "AI viết lời khuyên lúc tổng kết cuối ngày "
                                                 f"({cfg['daily_summary_at']}); báo cáo tạo sau đó sẽ có."))

    p.append("<h2>Ghi chú trong ngày</h2>" + notes_section(cfg, note, extra))
    if not off:
        p.append(science_details(a, cfg))
    return page(f"Tập trung {day}", "".join(p))


def ai_box(text, when):
    """Khung lời AI; chưa có thì vẫn hiện khung, nói rõ vì sao chưa có (không bịa lời khuyên)."""
    if text:
        parts = []
        for head, lines in sections(drop_wish_heading(text)):
            body = "<br>".join(esc(x) for x in lines)
            parts.append("<div class='aisec'>" + (f"<h3 class='aih'>{esc(head)}</h3>" if head else "")
                         + (f"<p>{body}</p>" if body else "") + "</div>")
        return f"<div class='card bubble'><div class='ai'>{''.join(parts)}</div></div>"
    return (f"<div class='card mut'>Chưa có lời AI cho báo cáo này. {esc(when)} Cần bật /aireview và có API key "
            "Gemini (README mục 2.3).</div>")


def ot_section(hist):
    """Làm ngoài giờ (OT) của 14 ngày gần nhất: chỉ các ngày có OT, kèm giờ và các khoảng giờ."""
    head = f"<h2>Làm ngoài giờ (OT) {hist['span']} ngày gần nhất</h2>"
    if not hist["days"]:
        return head + (f"<div class='card mut'>{hist['span']} ngày qua không có ngày nào làm ngoài giờ trong VDI.</div>")
    mx = max(r["ot"] for r in hist["days"]) or 1
    rows = []
    for r in hist["days"]:
        d = dt.date.fromisoformat(r["day"])
        ranges = ", ".join(f"{fmt_t(s)}–{fmt_t(e)}" for s, e in r["ranges"] if fmt_t(s) != fmt_t(e))
        rows.append(f"<div class='orow'><b>{WEEKDAY_SHORT[d.weekday()]} {d:%d/%m}"
                    + (f" <small class='mut'>({esc(r['off'])})</small>" if r["off"] else "") + "</b>"
                    f"{track(r['ot'] / mx * 100, 'ot')}<span class='num' style='text-align:right'>{fmt_dur(r['ot'])}"
                    "</span>" + (f"<span class='rg'>{ranges}</span>" if ranges else "") + "</div>")
    return (head + "<div class='card ot'><div class='head'>"
            + chip(fmt_dur(hist["total"]), f"tổng OT trong {hist['count']} ngày")
            + "<span class='mut' style='font-size:13px'>OT = gõ phím / rê chuột trong VDI ngoài giờ làm chính thức "
              "(trước giờ làm, sau giờ làm, thứ Bảy / Chủ nhật / ngày lễ có bật bot); giờ nghỉ trưa không tính.</span>"
            + "</div>" + "".join(rows) + "</div>")


def week_list(week, goal_h):
    if not week:
        return "<div class='card mut'>Chưa có số liệu.</div>"
    mx = max([w["deep"] for w in week] + [goal_h * 3600, 1])
    rows = []
    for w in week:
        d = dt.date.fromisoformat(w["day"])
        if w.get("off"):
            badge = "<span class='badge' style='background:var(--ot)'>🌙</span>"
        else:
            lvl = scoring.tier_of(w.get("total", 0))["level"]
            k = LEVEL_COLOR[lvl]
            badge = (f"<span class='badge num' style='background:var(--{k});color:"
                     f"{'var(--paper)' if k in LIGHT_TEXT else 'var(--ink)'}'>{w.get('total', '–')}</span>")
        rows.append(f"<div class='drow'><b>{WEEKDAY_SHORT[d.weekday()]} {d:%d/%m}</b>"
                    f"{track(w['deep'] / mx * 100, 'deep', goal_h * 3600 / mx * 100)}"
                    f"<span class='num' style='text-align:right'>{fmt_dur(w['deep'])}</span>{badge}"
                    f"<span class='when'>{fmt_t(w['first'])}–{fmt_t(w['last'])}"
                    + (f" · nghỉ ({esc(w['off'])}), làm bù {fmt_dur(w.get('ot', 0))}" if w.get("off") else "")
                    + "</span></div>")
    return ("<div class='card days'>" + "".join(rows) + "<div class='mut' style='font-size:12px;margin-top:6px'>Thanh "
            "xanh = tập trung sâu, vạch đứt = mục tiêu, ô số = điểm tổng.</div></div>")


def notes_section(cfg, note, extra):
    ds = extra.get("distractions")
    dist = esc(note.get("distractions") or "")
    if ds:
        dist += ("<br><br>" if dist else "") + "<small class='mut'>" + esc(
            f"{ds['days']} ngày làm việc gần nhất: trung bình sao nhãng {fmt_dur(ds['avg_other'])}/ngày (ngoài VDI + "
            f"thu nhỏ VDI, trong giờ làm), thu nhỏ VDI {round(ds['avg_minimize_count'], 1):g} lần/ngày"
            + (f"; hay sao nhãng nhất lúc {', '.join(ds['top_hours'])}" if ds["top_hours"] else "")
            + (f". Bạn đã tự ghi {ds['noted']} lần" + (f", thường lúc {', '.join(ds['noted_hours'])}"
                                                      if ds["noted_hours"] else "")
               if ds["noted"] else ". Chưa tự ghi lần nào: nhắn bot kiểu «nãy giờ bận trông em bé khóc» là bot ghi")
            + ".") + "</small>"
    en = note.get("energy")
    en_html = ""
    if en not in (None, ""):
        en_html = (energy_dots(en) + f"<b>{esc(en)}/5</b> "
                   + ("(bot tự tính) · sửa: /energy 1–5" if note.get("energy_source") == "auto" else "(bạn tự chấm)"))
    as400 = f"{note.get('as400_start')} – {note.get('as400_end') or '?'}" if note.get("as400_start") else ""
    rots = [-1.2, 0.8, -0.6, 1.1, -0.9, 0.5, -1.0]
    return ("<div class='notes'>"
            + note_box("Kế hoạch đầu ngày", note.get("plan"), rots[0])
            + note_box("Output hôm nay", note.get("output"), rots[1])
            + note_box("Issue / blocker", note.get("issues"), rots[2])
            + note_box("Bị phân tâm bởi", dist, rots[3], raw=True)
            + note_box("Năng lượng (1–5)", en_html, rots[4], raw=True)
            + note_box("Việc đầu tiên ngày mai", note.get("tomorrow"), rots[5])
            + pending_box(extra.get("pending"), rots[0])
            + note_box("Giờ vào / ra AS400", as400, rots[6])
            + "</div>")


# ----------------------------------------------------------------------------------------------- báo cáo tuần

SUM_KEYS = ("deep", "vdi", "other", "minimized", "idle", "away", "ot", "exits", "minimize_count", "short_idle_count",
            "away_count", "inactive_10m_count")


def render_week(cfg, wk):
    """wk: dữ liệu tuần từ report.week_report_data()."""
    facts, days = wk["facts"], wk["days"]
    work = [x for x in days if not x["off"] and x["rec"]]
    offs = [x for x in days if x["off"] and x["rec"] and x["rec"].get("ot")]
    f0, f1 = dt.date.fromisoformat(facts["from"]), dt.date.fromisoformat(facts["to"])
    title = f"Tuần {int(facts['week'][-2:])} · {f0:%d/%m} → {f1:%d/%m/%Y}"
    sub = (f"📅 {len(work)} ngày làm việc có số liệu" + (f" + {len(offs)} ngày nghỉ làm bù" if offs else "")
           + f" · mục tiêu tập trung sâu {facts['goal_hours_per_day']:g}h/ngày")
    wavg = round(sum(x["rec"].get("total", 0) for x in work) / len(work)) if work else None
    p = [header("TỔNG KẾT TUẦN", title, sub, wavg)]
    if not work and not offs:
        p.append("<div class='card' style='margin-top:20px'>Tuần này chưa có số liệu.</div>")
        return page(f"Tập trung tuần {facts['week']}", "".join(p))
    tot = {k: sum((x["rec"].get(k) or 0) for x in work) for k in SUM_KEYS}
    n = len(work) or 1

    # Điểm tổng tuần + bộ sưu tập robot
    if work:
        avg = round(sum(x["rec"].get("total", 0) for x in work) / n)
        tier = scoring.tier_of(avg)
        ew = wk.get("explain") or {}
        rows = ""
        colors = {"điểm tập trung": "deep", "ít bị cắt ngang": "vdi", "năng lượng tự chấm": "min"}
        for name, val in (ew.get("avg_parts") or {}).items():
            rows += (f"<div class='part'><div><b>{name[0].upper() + name[1:]}</b> <span class='w'>TB</span></div>"
                     f"{track(val, colors.get(name, 'vdi'))}<div class='pv num'>{val}</div><div></div></div>")
        why = ""
        if ew:
            why = (f"<div class='why'>📉 <b>Kéo điểm xuống nhiều nhất:</b> {esc(ew['biggest_loss'])}.<br>"
                   + (f"🏆 Ngày điểm cao / thấp nhất: <b>{esc(ew['best_day'])}</b></div>"
                      if ew["best_day"] == ew["worst_day"] else
                      f"🏆 Ngày điểm cao nhất: <b>{esc(ew['best_day'])}</b> · thấp nhất: <b>{esc(ew['worst_day'])}</b></div>"))
        p.append("<section class='card score'>"
                 f"<div class='sticker'>{burst('#DFAB36', 12, 78, 0.7, tier['grade'])}</div>"
                 f"<div class='robot'><div class='halo'></div>{robots.robot_svg(tier['level'], 170)}</div>"
                 "<div><div class='slabel'>ĐIỂM TỔNG TRUNG BÌNH TUẦN</div>"
                 f"<div class='big num'>{avg}<span>/100</span></div>{verdict_chip(tier)}"
                 f"<div class='gift'>Robot của tuần: <b>{tier['grade']} {esc(tier['name'])}</b> ({esc(tier['desc'])}).</div>"
                 "</div>"
                 f"<div class='parts'>{rows or '<div class=mut>Chưa đủ số liệu thô để tách thành phần điểm.</div>'}{why}"
                 "</div></section>")
    p.append("<h2>Bộ sưu tập robot tuần này</h2><div class='collect'>")
    for x in days:
        d = dt.date.fromisoformat(x["day"])
        lab = f"<b>{WEEKDAY_SHORT[d.weekday()]} {d:%d/%m}</b>"
        if x["off"]:
            if x["rec"] and x["rec"].get("ot"):
                p.append(f"<div class='rung' style='background:var(--ot)'><span style='background:var(--paper);"
                         f"padding:2px 6px;border-radius:6px;display:inline-block'>{lab}🌙 làm bù "
                         f"{fmt_dur(x['rec']['ot'])}<br><small>{esc(x['off'])}</small></span></div>")
            continue
        if not x["rec"]:
            p.append(f"<div class='rung locked'>{lab}<small>chưa có số liệu</small></div>")
            continue
        t = scoring.tier_of(x["rec"].get("total", 0))
        p.append(f"<div class='rung now' style='transform:none'>{robots.robot_svg(t['level'], 58)}{lab}"
                 f"<span class='num' style='font-size:20px'>{x['rec'].get('total', 0)}</span> · {t['grade']} "
                 f"{esc(t['name'])}<br><small>{t['verdict']}</small></div>")
    p.append("</div>")

    # Ô số liệu tổng tuần
    avg_s = lambda k: f"TB {fmt_dur(tot[k] / n)}/ngày"
    p.append("<div class='stats'>"
             + stat("deep", fmt_dur(tot["deep"]), "Tập trung sâu cả tuần",
                    f"{avg_s('deep')} · đạt mục tiêu {facts.get('days_reached_goal', 0)}/{len(work)} ngày")
             + stat("vdi", fmt_dur(tot["vdi"]), "Thao tác trong VDI", avg_s("vdi"))
             + stat("other", fmt_dur(tot["other"]), "Ngoài VDI",
                    f"{tot['exits']} lần rời · TB mỗi lần {avg_dur(tot['other'], tot['exits'])} · {avg_s('other')}")
             + stat("min", fmt_dur(tot["minimized"]), "VDI bị thu nhỏ",
                    f"{tot['minimize_count']} lần · TB mỗi lần {avg_dur(tot['minimized'], tot['minimize_count'])} · "
                    + avg_s("minimized"))
             + stat("idle", fmt_dur(tot["idle"]), "Inactive phím/chuột",
                    f"{tot['short_idle_count']} lần · TB mỗi lần {avg_dur(tot['idle'], tot['short_idle_count'])}")
             + stat("away", fmt_dur(tot["away"]), "Rời máy",
                    f"{tot['away_count']} lần · TB mỗi lần {avg_dur(tot['away'], tot['away_count'])}")
             + "</div>")
    cards = [plain_stat("deep", f"{facts.get('avg_score', 0)}<small>/100</small>", "Điểm tập trung TB"),
             plain_stat("vdi", f"{facts.get('days_reached_goal', 0)}/{len(work)}", "Ngày đạt mục tiêu")]
    ot_all = sum((x["rec"].get("ot") or 0) for x in days if x["rec"])  # cả ngày làm việc lẫn làm bù ngày nghỉ
    if ot_all >= 60:  # OT = 0 thì không hiện thẻ OT
        cards.append(plain_stat("ot", fmt_dur(ot_all), "Làm ngoài giờ + làm bù trong VDI (OT)"))
    cards += [plain_stat("deep", fmt_dur(max([x["rec"].get("longest", 0) for x in work] or [0])),
                         "Khối tập trung dài nhất"),
              plain_stat("idle", f"{tot['inactive_10m_count']} lần", "Inactive / rời máy ≥ 10 phút"),
              plain_stat("min", f"{facts.get('streak_days', 0)} ngày",
                         "Chuỗi hiện tại" + (" 🔥" if facts.get("streak_days", 0) >= 3 else ""))]
    p.append(stat_row(cards))
    chips = []
    if facts.get("golden_hours"):
        chips.append(chip("⏰", "Giờ vàng: " + ", ".join(facts["golden_hours"])))
    if facts.get("best_day") and facts.get("days_tied"):
        chips.append(chip("=", f"Ngày tốt / kém nhất: {facts['best_day']}"))
    elif facts.get("best_day"):
        chips.append(chip("▲", f"Ngày tốt nhất: {facts['best_day']}"))
        chips.append(chip("▼", f"Kém nhất: {facts['worst_day']}"))
    if chips:
        p.append("<div class='chips'>" + "".join(chips) + "</div>")

    # Dòng thời gian từng ngày
    with_tl = [x for x in days if x["a"] and x["a"].get("has_data")]
    if with_tl:
        o0, o1 = time_range(cfg, [x["a"] for x in with_tl])
        rows = "".join(
            f"<div class='dayrow'><b>{WEEKDAY_SHORT[dt.date.fromisoformat(x['day']).weekday()]} "
            f"{dt.date.fromisoformat(x['day']):%d/%m}</b>{timeline_bar(cfg, x['a'], o0, o1, small=True)}</div>"
            for x in with_tl)
        p.append("<h2>Dòng thời gian từng ngày</h2><div class='card'>" + rows
                 + f"<div class='dayrow'><span></span>{ticks(with_tl[0]['day'], o0, o1)}</div>"
                 + legend(["deep", "vdi", "ot", "other", "min", "idle", "away"], cfg, blank=True, lunch=True) + "</div>")

    # Biểu đồ tập trung sâu theo ngày + app ngoài VDI
    goal_s = facts["goal_hours_per_day"] * 3600
    shown = [x for x in days if x["rec"]]
    mx = max([x["rec"]["deep"] for x in shown] + [goal_s * 1.15, 1])
    bars = "".join(
        f"<div class='wb' title='{x['day']}: tập trung sâu {fmt_dur(x['rec']['deep'])}'>"
        f"<span class='num' style='font-size:13px'>{fmt_dur(x['rec']['deep'])}</span>"
        f"<i class='{'ot' if x['off'] else ''}' style='height:{x['rec']['deep'] / mx * 100:.1f}%'></i></div>"
        for x in shown)
    labs = "".join(f"<span>{WEEKDAY_SHORT[dt.date.fromisoformat(x['day']).weekday()]}</span>" for x in shown)
    chart = (f"<div class='card'><div class='wbars'>{bars}<div class='goal' style='bottom:{goal_s / mx * 100:.1f}%'>"
             f"<span>mục tiêu {facts['goal_hours_per_day']:g}h</span></div></div><div class='wlab'>{labs}</div></div>")
    apps = wk.get("apps") or []
    if apps:
        amx = apps[0][1] or 1
        app_html = ("<div class='card apps'>" + "".join(
            f"<div class='row'><span>{esc(proc)}</span>{track(s / amx * 100, 'other')}<span class='num' "
            f"style='text-align:right'>{fmt_dur(s)}</span></div>" for proc, s in apps) + "</div>")
    else:
        app_html = "<div class='card mut'>Không dùng app nào ngoài VDI.</div>"
    p.append("<div class='grid2'><div><h2>Tập trung sâu từng ngày</h2>" + chart + "</div>"
             "<div><h2>App ngoài VDI cả tuần</h2>" + app_html + "</div></div>")

    # Bảng đủ thông số từng ngày
    cols = [("Ngày", "deep"), ("Giờ làm", "vdi"), ("Tập trung sâu", "deep"), ("Trong VDI", "vdi"), ("Ngoài giờ", "vdi"),
            ("Ngoài VDI", "other"), ("Thu nhỏ", "min"), ("Inactive", "idle"), ("Rời máy", "away"),
            ("≥10 phút", "idle"), ("Điểm TT", "deep"), ("Điểm tổng", "min")]
    th = "".join(f"<th style='background:var(--{k});color:{'var(--paper)' if k in LIGHT_TEXT else 'var(--ink)'}'>{t}</th>"
                 for t, k in cols)
    trs = []
    for x in shown:
        r, d = x["rec"], dt.date.fromisoformat(x["day"])
        g = lambda k: r.get(k) or 0
        if x["off"]:
            trs.append(f"<tr><td>{WEEKDAY_SHORT[d.weekday()]} {d:%d/%m}</td><td>{fmt_t(r['first'])}–{fmt_t(r['last'])}"
                       f"</td><td class='n'>{fmt_dur(g('deep'))}</td><td class='n'>–</td><td class='n'>"
                       f"{fmt_dur(g('ot'))}</td><td colspan='7' class='mut'>🌙 nghỉ ({esc(x['off'])}), bật bot làm bù: "
                       "chỉ tính giờ làm trong VDI</td></tr>")
            continue
        trs.append(f"<tr><td>{WEEKDAY_SHORT[d.weekday()]} {d:%d/%m}</td><td>{fmt_t(r['first'])}–{fmt_t(r['last'])}</td>"
                   f"<td class='n'>{fmt_dur(g('deep'))}</td><td class='n'>{fmt_dur(g('vdi'))}</td>"
                   f"<td class='n'>{fmt_dur(g('ot')) if g('ot') else '–'}</td>"
                   f"<td class='n'>{fmt_dur(g('other'))} · {g('exits')} lần</td>"
                   f"<td class='n'>{fmt_dur(g('minimized'))} · {g('minimize_count')} lần</td>"
                   f"<td class='n'>{fmt_dur(g('idle'))} · {g('short_idle_count')} lần</td>"
                   f"<td class='n'>{fmt_dur(g('away'))} · {g('away_count')} lần</td>"
                   f"<td class='n'>{g('inactive_10m_count')}</td><td class='n'>{g('score')}</td>"
                   f"<td class='n'><b>{g('total')}</b></td></tr>")
    p.append("<h2>Từng ngày, đủ thông số</h2><div class='scroll'><table><tr>" + th + "</tr>" + "".join(trs)
             + "</table></div>")

    if wk.get("ot_history") is not None:
        p.append(ot_section(wk["ot_history"]))
    p.append("<h2>Đánh giá tuần của AI</h2>" + ai_box(wk.get("review"), "AI viết đánh giá tuần lúc tổng kết tuần "
                                                    f"({cfg['weekly_report_at']} thứ Sáu) hoặc khi gõ /week."))

    # Ghi chú cả tuần
    def per_day(field):
        lines = []
        for x in days:
            v = (x["note"].get(field) or "").strip()
            if v:
                d = dt.date.fromisoformat(x["day"])
                lines.append(f"<b>{WEEKDAY_SHORT[d.weekday()]} {d:%d/%m}</b>: {esc(v)}")
        return "<br>".join(lines)
    energy_lines = []
    for x in days:
        en = x["note"].get("energy")
        if en not in (None, ""):
            d = dt.date.fromisoformat(x["day"])
            energy_lines.append(f"<b>{WEEKDAY_SHORT[d.weekday()]}</b> {energy_dots(en)}"
                                + ("<small class='mut'>bot tự tính</small>" if x["note"].get("energy_source") == "auto"
                                   else ""))
    as400 = "<br>".join(
        f"<b>{WEEKDAY_SHORT[dt.date.fromisoformat(x['day']).weekday()]}</b> {esc(x['note']['as400_start'])} – "
        f"{esc(x['note'].get('as400_end') or '?')}" for x in days if x["note"].get("as400_start"))
    p.append("<h2>Ghi chú cả tuần</h2><div class='notes'>"
             + note_box("Output trong tuần", per_day("output"), -1.0, raw=True)
             + note_box("Issue / blocker", per_day("issues"), 0.9, raw=True)
             + note_box("Bị phân tâm bởi", per_day("distractions"), -0.6, raw=True)
             + note_box("Năng lượng từng ngày", "".join(energy_lines), 1.0, raw=True)
             + note_box("Giờ vào / ra AS400", as400, -0.8, raw=True)
             + "</div>")
    p.append(science_details())
    return page(f"Tập trung tuần {facts['week']}", "".join(p))
