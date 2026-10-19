"""Điểm tổng, robot quà, dữ kiện khoa học, báo cáo HTML mới (2.3.0)."""
import re

from focus import analysis, messages, report, robots, scoring
from focus.storage import db_path, open_db, save_note
from tests.helpers import TempCase, insert_run

DAY = "2026-10-14"


def fake(**kw):
    a = {"has_data": True, "goal_h": 4, "deep": 2 * 3600, "vdi": 3 * 3600, "active": 4 * 3600, "other": 3600,
         "exits": 8, "short_idle_count": 4, "away": 0, "vdi_closed": []}
    a.update(kw)
    return a


class TotalScoreTest(TempCase):
    def test_formula_without_self_rated_energy(self):
        a = fake()
        sc = scoring.total_score(a, {"energy": 2, "energy_source": "auto"})  # bot tự tính: không vào điểm tổng
        focus = analysis.focus_score(a)                                     # 70 × 0.5 + 30 × 0.75 = 57.5 -> 58
        self.assertEqual(focus, 58)
        self.assertEqual(sc["parts"], {"focus": 58, "interruptions": 85})  # 12 lần / 4h = 3/h -> 100 × (1 − 3/20)
        self.assertEqual(sc["total"], round(0.65 * 58 + 0.35 * 85))
        self.assertFalse(sc["energy_self_rated"])
        self.assertEqual(sc["ten"], round(sc["total"] / 10, 1))

    def test_self_rated_energy_is_10_percent(self):
        sc = scoring.total_score(fake(), {"energy": 5})
        self.assertEqual(sc["parts"]["energy"], 100)
        self.assertEqual(sc["total"], round(0.6 * 58 + 0.3 * 85 + 0.1 * 100))

    def test_focus_score_formula_unchanged(self):
        self.assertEqual(analysis.focus_score(fake(deep=5 * 3600, vdi=4 * 3600, active=4 * 3600)), 100)

    def test_interruptions_floor_and_no_data(self):
        self.assertEqual(scoring.total_score(fake(exits=100, active=3600), {})["parts"]["interruptions"], 0)
        self.assertIsNone(scoring.total_score({"has_data": False}))

    def test_tiers(self):
        self.assertEqual([scoring.tier_of(x)["grade"] for x in (0, 29, 30, 49, 50, 69, 70, 84, 85, 100)],
                         ["SD", "SD", "HG", "HG", "RG", "RG", "MG", "MG", "PG", "PG"])

    def test_advice_only_below_threshold_and_from_verified_list(self):
        good = scoring.total_score(fake(deep=4 * 3600, exits=0, short_idle_count=0), {})
        self.assertGreaterEqual(good["total"], scoring.ADVICE_BELOW)
        self.assertEqual(scoring.advice(fake(), good), "")
        bad_a = fake(deep=0, vdi=600, exits=60, short_idle_count=10)
        tip = scoring.advice(bad_a, scoring.total_score(bad_a, {}))
        self.assertTrue(any(tip.startswith(v) for v in scoring.SCIENCE.values()))
        self.assertIn("gia đình", tip)

    def test_formula_lines_show_numbers(self):
        a = fake()
        lines = scoring.formula_lines(a, scoring.total_score(a, {}))
        self.assertIn("= 58", lines[0])
        self.assertIn("12 lần", lines[1])
        self.assertTrue(lines[-1].startswith("Điểm tổng = 65% × 58 + 35% × 85"))


class RobotTest(TempCase):
    def test_five_svgs_grow_in_detail_no_red(self):
        svgs = [robots.robot_svg(i) for i in range(5)]
        sizes = [len(s) for s in svgs]
        self.assertEqual(sizes[1:], sorted(sizes[1:]), "hạng càng cao càng nhiều chi tiết")
        for s in svgs:
            self.assertTrue(s.startswith("<svg") and s.endswith("</svg>"))
            for color in re.findall(r"#[0-9a-fA-F]{6}", s):
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                self.assertFalse(r > 180 and g < 100 and b < 100, f"màu đỏ {color}")


class ScienceMessagesTest(TempCase):
    def test_water_message_has_verified_study(self):
        for _ in range(20):
            line = messages.water({}).splitlines()[-1]
            self.assertTrue(line.startswith("🔬 "))
            self.assertIn(line[2:], [scoring.SCIENCE[k] for k in messages.WATER_SCIENCE])


class ReportTest(TempCase):
    def test_report_has_total_score_robot_formulas_and_distraction_stats(self):
        db = open_db(db_path(self.cfg))
        insert_run(db, DAY, "09:00", 60)
        insert_run(db, DAY, "10:00", 10, vdi="minimized", proc="chrome.exe")
        insert_run(db, DAY, "10:10", 30)
        insert_run(db, DAY, "17:30", 40)  # làm bù buổi tối
        save_note(db, DAY, {"distractions": "- bận trông em bé khóc (10:05)"})
        path, a = report.write_report(db, self.cfg, DAY)
        html = open(path, encoding="utf-8").read()
        for text in ("ĐIỂM TỔNG", "<svg", "Điểm tập trung = 70 × min(", "Ít bị cắt ngang = 100 × max(",
                     "Cách tính điểm và căn cứ khoa học", "González", "Năng lượng không ảnh hưởng điểm này",
                     "Làm ngoài giờ trong VDI (OT)", "VDI bị thu nhỏ", "1 lần", "Inactive / rời máy ≥ 10 phút",
                     "bận trông em bé khóc", "trung bình sao nhãng", "thường lúc 10:00–11:00", "Điểm tập trung",
                     "Làm ngoài giờ (OT) 14 ngày gần nhất", "17:30–18:10"):
            self.assertIn(text, html)
        text = report.summary_text(a, {})
        self.assertIn("  • Điểm tổng:", text)
        self.assertIn("  • Làm ngoài giờ (OT): 40m", text)
        self.assertNotIn("⭐", text)            # tin Telegram: không emoji


class ExplainTest(TempCase):
    def test_numbers_match_score(self):
        a = fake(deep=0.1 * 3600, vdi=2 * 3600, active=5 * 3600, other=3 * 3600, exits=48, short_idle_count=40)
        sc = scoring.total_score(a, {})
        ex = scoring.explain(a, sc)
        self.assertIn(f"{sc['total']}/100", ex["meaning"])
        self.assertIn("mức kém", ex["meaning"])
        self.assertIn(f"= {sc['total']}", ex["formula"])
        self.assertIn("65% × điểm tập trung", ex["formula"])
        self.assertIn(f"Điểm tập trung {sc['parts']['focus']}/100", ex["parts"][0])
        self.assertIn("88 lần", ex["parts"][1])
        self.assertIn("chưa tự chấm", ex["parts"][2])
        self.assertIn("thiếu giờ tập trung sâu", ex["biggest_loss"])
        self.assertTrue(any("tập trung sâu" in t for t in ex["how_to_raise"]))

    def test_self_rated_energy_part(self):
        sc = scoring.total_score(fake(), {"energy": 4})
        ex = scoring.explain(fake(), sc)
        self.assertIn("tự chấm 4/5", ex["parts"][2])
        self.assertIn("10% × năng lượng tự chấm 75", ex["formula"])

    def test_verdicts_follow_tiers(self):
        self.assertEqual([scoring.tier_of(x)["verdict"] for x in (10, 40, 60, 80, 90)],
                         ["kém", "chưa tốt", "trung bình", "tốt", "xuất sắc"])
        self.assertIn("dưới 30 kém", scoring.score_guide())

    def test_explain_week(self):
        days = [{"day": "2026-10-12", "weekday": "Thứ 2", "total_score": 40,
                 "total_score_parts": {"focus": 30, "interruptions": 60}},
                {"day": "2026-10-13", "weekday": "Thứ 3", "total_score": 80,
                 "total_score_parts": {"focus": 80, "interruptions": 70, "energy": 100}},
                {"day": "2026-10-11", "weekday": "CN"}]
        ex = scoring.explain_week(days)
        self.assertIn("60/100", ex["meaning"])
        self.assertEqual(ex["avg_parts"], {"điểm tập trung": 55, "ít bị cắt ngang": 65, "năng lượng tự chấm": 100})
        self.assertIn("Thứ 2 12/10 (40)", ex["worst_day"])
        self.assertIn("điểm tập trung", ex["biggest_loss"])
        self.assertIsNone(scoring.explain_week([]))
