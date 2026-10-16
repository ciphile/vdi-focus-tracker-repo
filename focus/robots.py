"""Robot quà tặng theo điểm tổng (scoring.TIERS): SVG tự vẽ kiểu "đồ chơi nhựa 3D" (đổ bóng bằng gradient, vệt bóng
nhựa), tông sáng theo bảng màu báo cáo (report_html.py). Hạng càng cao robot càng to, càng nhiều chi tiết.
Không chép thiết kế có bản quyền (Gundam của Bandai / Sunrise): không ăng-ten chữ V, không mặt nạ + hai mắt kiểu Gundam,
không phối trắng-xanh-đỏ-vàng, không dùng màu đỏ. Mặt robot là kính visor một dải; đỉnh đầu là vây đơn / vương miện.

  level 0 SD Mini      tí hon, nhựa xám sơn lót, ăng-ten lò xo, một mắt to một mắt nhỏ
  level 1 HG Scout     trắng + xanh lam, ăng-ten bi, visor xanh
  level 2 RG Guardian  trắng + xanh lá, vây đầu, giáp vai, khiên lục giác ngôi sao vàng
  level 3 MG Vanguard  trắng + xanh lam + viền vàng, vương miện 3 mũi, ba lô phản lực, kiếm năng lượng
  level 4 PG Celestial trắng + vàng + xanh lá, vầng hào quang, cánh sáng, lõi ngực phát sáng, kiếm, lấp lánh
"""
INK = "#3E322D"

# (sáng, đậm) cho gradient nhựa
SHELL = ("#FFFFFF", "#E6DCD2")
PRIMER = ("#E4DDD6", "#B5AAA1")
BLUE = ("#8CC3D3", "#4A8A9E")
TEAL = ("#86C7AC", "#3D8A6F")
GOLD = ("#F6D98A", "#D39E25")
ORANGE = ("#F3B38A", "#DD814B")
DARK = ("#5A4D46", "#2C2420")


class Pen:
    """Gom <defs> gradient theo màu, id có tiền tố riêng để nhiều robot trên một trang không đụng nhau."""

    def __init__(self, uid):
        self.uid, self.defs, self.ids = uid, [], {}

    def grad(self, pair, angle="tl"):
        key = (pair, angle)
        if key not in self.ids:
            gid = f"{self.uid}g{len(self.ids)}"
            x1, y1, x2, y2 = {"tl": (0, 0, 1, 1), "v": (0, 0, 0, 1), "h": (0, 0, 1, 0)}[angle]
            self.defs.append(f"<linearGradient id='{gid}' x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}'>"
                             f"<stop offset='0' stop-color='{pair[0]}'/><stop offset='1' stop-color='{pair[1]}'/>"
                             "</linearGradient>")
            self.ids[key] = gid
        return f"url(#{self.ids[key]})"

    def glow(self, color):
        key = ("glow", color)
        if key not in self.ids:
            gid = f"{self.uid}r{len(self.ids)}"
            self.defs.append(f"<radialGradient id='{gid}'><stop offset='0' stop-color='#FFFFFF'/>"
                             f"<stop offset='.45' stop-color='{color}'/><stop offset='1' stop-color='{color}' "
                             "stop-opacity='0'/></radialGradient>")
            self.ids[key] = gid
        return f"url(#{self.ids[key]})"

    # hình cơ bản, viền nâu đậm như báo cáo
    def rect(self, x, y, w, h, pair, rx=6, angle="tl", sw=2.2):
        return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' fill='{self.grad(pair, angle)}' "
                f"stroke='{INK}' stroke-width='{sw}'/>")

    def circle(self, cx, cy, r, pair, sw=2.2):
        return f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{self.grad(pair)}' stroke='{INK}' stroke-width='{sw}'/>"

    def path(self, d, pair, angle="tl", sw=2.2):
        return (f"<path d='{d}' fill='{self.grad(pair, angle)}' stroke='{INK}' stroke-width='{sw}' "
                "stroke-linejoin='round'/>")


def shine(x, y, w, h, op=.75):
    """Vệt bóng nhựa (đốm sáng) cho cảm giác 3D."""
    return f"<ellipse cx='{x}' cy='{y}' rx='{w}' ry='{h}' fill='#FFFFFF' opacity='{op}'/>"


def _visor(p, color, odd=False):
    out = [p.rect(78, 66, 44, 22, DARK, 11)]
    if odd:  # SD: một mắt to một mắt nhỏ
        out += [f"<circle cx='91' cy='77' r='7' fill='{p.glow(color)}'/>", f"<circle cx='110' cy='78' r='4' "
                f"fill='{p.glow(color)}'/>"]
    else:
        out += [f"<rect x='84' y='72' width='32' height='10' rx='5' fill='{color}'/>",
                f"<rect x='86' y='73.5' width='14' height='3' rx='1.5' fill='#FFFFFF' opacity='.85'/>"]
    return "".join(out)


def _figure(p, body, accent, visor, level):
    """Thân robot chibi: đầu to, thân gọn, tay chân tròn trịa."""
    trim = GOLD if level >= 3 else accent
    out = [
        # chân + bàn chân
        p.rect(80, 150, 16, 34, body, 7), p.rect(104, 150, 16, 34, body, 7),
        p.rect(72, 180, 28, 16, accent, 8), p.rect(100, 180, 28, 16, accent, 8),
        shine(80, 184, 5, 2.5, .6), shine(108, 184, 5, 2.5, .6),
        # hông
        p.rect(78, 140, 44, 16, DARK, 6),
        # tay
        p.rect(52, 112, 16, 38, body, 8), p.rect(132, 112, 16, 38, body, 8),
        p.circle(60, 154, 8, accent), p.circle(140, 154, 8, accent),
        # thân
        p.rect(70, 100, 60, 46, body, 14),
        shine(84, 108, 9, 4),
        p.path("M86 118 h28 l-4 16 h-20 Z", accent, "v"),
        # vai
        p.circle(60, 110, 13, trim), shine(56, 105, 5, 3), p.circle(140, 110, 13, trim), shine(136, 105, 5, 3),
        # lõi ngực
        f"<circle cx='100' cy='126' r='7' fill='{p.glow('#7FD6C0' if level >= 2 else '#9CD2E2')}' stroke='{INK}' "
        "stroke-width='1.8'/>",
        # đầu
        p.circle(62, 72, 9, accent), p.circle(138, 72, 9, accent),
        p.rect(66, 44, 68, 58, body, 24),
        shine(84, 54, 12, 5),
        _visor(p, visor, odd=level == 0),
        f"<path d='M90 94 q10 5 20 0' fill='none' stroke='{INK}' stroke-width='2' stroke-linecap='round'/>",
    ]
    return out


def _crest(p, level):
    if level == 0:  # ăng-ten lò xo cong
        return ("<path d='M100 46 q-6 -6 0 -10 q6 -4 0 -10 q-6 -4 0 -10' fill='none' stroke='#8C8178' "
                "stroke-width='3' stroke-linecap='round'/>" + p.circle(100, 14, 6, ORANGE))
    if level == 1:
        return f"<rect x='98' y='24' width='4' height='22' rx='2' fill='{INK}'/>" + p.circle(100, 22, 7, GOLD)
    if level == 2:  # vây đơn
        return p.path("M92 46 Q100 6 108 46 Z", TEAL, "h") + shine(98, 30, 1.6, 7, .7)
    if level == 3:  # vương miện 3 mũi
        return p.path("M80 48 L84 26 L92 38 L100 16 L108 38 L116 26 L120 48 Z", GOLD, "v") + shine(100, 28, 2, 5, .8)
    return (p.path("M78 48 L82 22 L91 36 L100 8 L109 36 L118 22 L122 48 Z", GOLD, "v")
            + f"<circle cx='100' cy='34' r='5' fill='{p.glow('#7FD6C0')}' stroke='{INK}' stroke-width='1.6'/>")


def _shield(p):
    return (p.path("M30 112 L48 104 L60 112 L60 140 L45 154 L30 140 Z", TEAL)
            + p.path("M45 116 l3 7 7 .5 -5.5 4.5 2 7 -6.5 -4 -6.5 4 2 -7 -5.5 -4.5 7 -.5 Z", GOLD)
            + shine(38, 116, 4, 2.5, .7))


def _sword(p, color):
    return (f"<rect x='150' y='{30}' width='9' height='92' rx='4.5' fill='{p.glow(color)}' opacity='.95'/>"
            f"<rect x='152.5' y='34' width='4' height='84' rx='2' fill='#FFFFFF' opacity='.9'/>"
            + p.rect(146, 120, 17, 8, GOLD, 3) + p.rect(150, 126, 9, 22, DARK, 3))


def _backpack(p):
    return (p.rect(60, 96, 18, 40, BLUE, 7) + p.rect(122, 96, 18, 40, BLUE, 7)
            + p.path("M62 136 h14 l-3 10 h-8 Z", DARK) + p.path("M124 136 h14 l-3 10 h-8 Z", DARK)
            + "<ellipse cx='69' cy='152' rx='5' ry='8' fill='#F6D98A' opacity='.7'/>"
              "<ellipse cx='131' cy='152' rx='5' ry='8' fill='#F6D98A' opacity='.7'/>")


def _wings(p):
    out = []
    for s in (-1, 1):
        for i, op in enumerate((.9, .75, .6)):
            x0 = 100 + s * 26
            out.append(f"<path d='M{x0} 108 L{100 + s * (78 + i * 10)} {30 + i * 26} L{100 + s * (58 + i * 8)} "
                       f"{112 + i * 8} Z' fill='{p.grad((GOLD[0], TEAL[0]), 'v')}' stroke='{INK}' stroke-width='1.8' "
                       f"stroke-linejoin='round' opacity='{op}'/>")
    return "".join(out)


def _sparkles():
    pts = [(28, 40, 7), (172, 58, 6), (36, 170, 5), (166, 176, 6), (150, 20, 4)]
    return "".join(f"<path d='M{x} {y - r} L{x + r * .3} {y - r * .3} L{x + r} {y} L{x + r * .3} {y + r * .3} "
                   f"L{x} {y + r} L{x - r * .3} {y + r * .3} L{x - r} {y} L{x - r * .3} {y - r * .3} Z' "
                   f"fill='#F6D98A' stroke='{INK}' stroke-width='1.2'/>" for x, y, r in pts)


STYLE = {  # thân, màu phụ, màu visor
    0: (PRIMER, PRIMER, "#9CD2E2"),
    1: (SHELL, BLUE, "#7FD6F0"),
    2: (SHELL, TEAL, "#8FE3C6"),
    3: (SHELL, BLUE, "#7FD6F0"),
    4: (SHELL, TEAL, "#B8F0DA"),
}


def robot_svg(level, size=180, uid=None):
    """SVG robot hạng level (0–4), khung 200×230. Id gradient có tiền tố theo hạng + cỡ (uid), nên nhiều robot trên
    cùng một trang không đụng nhau; hai hình cùng hạng, cùng cỡ có định nghĩa gradient giống hệt nên trùng id vô hại."""
    level = max(0, min(4, int(level)))
    p = Pen(uid or f"r{level}s{size}")
    body, accent, visor = STYLE[level]
    layers = [f"<ellipse cx='100' cy='206' rx='{46 + level * 4}' ry='8' fill='{INK}' opacity='.18'/>"]
    if level == 4:
        layers.append(f"<circle cx='100' cy='100' r='86' fill='{p.glow('#F6D98A')}' opacity='.55'/>"
                      f"<circle cx='100' cy='27' r='21' fill='none' stroke='{GOLD[1]}' stroke-width='4' "
                      "opacity='.85'/>")
        layers.append(_wings(p))
    if level >= 3:
        layers.append(_backpack(p))
    layers += _figure(p, body, accent, visor, level)
    layers.append(_crest(p, level))
    if level >= 2:
        layers.append(_shield(p))
    if level >= 3:
        layers.append(_sword(p, "#7FD6C0" if level == 4 else "#9CD2E2"))
    if level == 4:
        layers.append(_sparkles())
    scale = [0.7, 0.8, 0.88, 0.95, 1.0][level]
    tilt = " rotate(-5 100 206)" if level == 0 else ""
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 230' width='{size}' height='{size * 1.15:.0f}' "
            f"role='img' aria-label='robot hạng {level}'><defs>{''.join(p.defs)}</defs>"
            f"<g transform='translate(100 212) scale({scale}) translate(-100 -212){tilt}'>{''.join(layers)}</g></svg>")
