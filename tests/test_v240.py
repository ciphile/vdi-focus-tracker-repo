"""2.4.0: báo cáo HTML Pop Art (ngày + tuần), OT 14 ngày, tổng kết làm bù ngày nghỉ, giờ trưa không tính, nhắc uống
nước mặc định tắt, tắt Kinh Thánh thì mọi lời khích lệ dùng châm ngôn danh nhân."""
import json
import os
import re
import threading
from unittest import mock

from focus import ai_client, ai_context, motivation, report, report_html
from focus.analysis import analyze, daily_stats, ot_ranges
from focus.config import DEFAULTS
from focus.schedule import offday_ot_due
from focus.storage import db_path, open_db, save_note
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, ts
from tests.test_tracker import SATURDAY, FakeBot, _Base, make_tracker

MON, TUE, FRI = "2026-10-12", "2026-10-13", "2026-10-16"
SAT, SUN = "2026-10-17", "2026-10-18"
PALETTE = ("#F1DFD5", "#1A1A1A", "#3E322D", "#3D8A6F", "#4A8A9E", "#DD814B", "#DFAB36", "#9E938B", "#C35850")


class LunchAndOtTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))

    def test_lunch_vdi_work_is_not_counted_at_all(self):
        insert_run(self.db, TUE, "10:15", 120)  # 10:15–12:15: phần 11:15–12:15 là giờ trưa
        a = analyze(self.db, self.cfg, TUE)
        self.assertAlmostEqual(a["vdi"], 60 * 60, delta=10)
        self.assertEqual(a["ot"], 0, "giờ trưa không phải OT")
        self.assertAlmostEqual(a["deep"], 60 * 60, delta=10)

    def test_weekend_lunch_hours_count_as_make_up(self):
        insert_run(self.db, SAT, "11:00", 60)
        self.assertAlmostEqual(analyze(self.db, self.cfg, SAT)["ot"], 60 * 60, delta=10)

    def test_ot_ranges_merge_and_persist(self):
        insert_run(self.db, TUE, "17:00", 30)
        insert_run(self.db, TUE, "17:35", 20)  # cách 5 phút: gộp
        insert_run(self.db, TUE, "20:00", 15)
        a = analyze(self.db, self.cfg, TUE)
        rng = [(f"{(s - ts(TUE, '00:00')) / 3600:.2f}", f"{(e - ts(TUE, '00:00')) / 3600:.2f}") for s, e in ot_ranges(a)]
        self.assertEqual(len(rng), 2, rng)
        rec = daily_stats(self.db, self.cfg, TUE, refresh=True)
        self.assertEqual(len(rec["ot_ranges"]), 2)

    def test_ot_history_lists_only_days_with_ot_in_14_days(self):
        insert_run(self.db, "2026-10-01", "18:00", 60)  # quá 14 ngày tính tới 16/10: không có
        insert_run(self.db, MON, "09:00", 60)           # không OT: không ghi
        insert_run(self.db, TUE, "17:30", 45)
        insert_run(self.db, "2026-10-11", "09:00", 30)  # Chủ nhật làm bù
        h = report.ot_history(self.db, self.cfg, FRI)
        self.assertEqual([r["day"] for r in h["days"]], ["2026-10-11", TUE])
        self.assertAlmostEqual(h["total"], 75 * 60, delta=20)
        self.assertEqual(h["days"][0]["off"], "cuối tuần")
        text = report.ot_history_text(h)
        self.assertIn("OT 14 ngày gần nhất: tổng 1h 15m trong 2 ngày", text)
        self.assertIn("T3 13/10: 45m (17:30–18:15)", text)
        self.assertIn("CN 11/10 (cuối tuần): 30m", text)
        self.assertEqual(report.ot_history_text(report.ot_history(self.db, self.cfg, "2026-11-30")), "")

    def test_offday_ot_due(self):
        self.assertFalse(offday_ot_due(self.cfg, "16:59", 3600), "trước giờ tan làm")
        self.assertFalse(offday_ot_due(self.cfg, "17:30", 20 * 60), "vừa làm xong 20 phút: đợi")
        self.assertTrue(offday_ot_due(self.cfg, "17:30", 30 * 60))


class HtmlReportTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        for day in (MON, TUE, FRI):
            insert_run(self.db, day, "08:30", 120)
            insert_run(self.db, day, "10:30", 15, vdi="minimized", proc="zalo.exe")
            insert_run(self.db, day, "10:45", 20, vdi="background", proc="chrome.exe")
            insert_run(self.db, day, "12:30", 150)
            insert_run(self.db, day, "15:00", 12, idle_grow=True)
            insert_run(self.db, day, "15:12", 60)
        insert_run(self.db, TUE, "17:30", 40)   # OT tối thứ Ba
        insert_run(self.db, SAT, "09:00", 50)   # làm bù thứ Bảy (báo cáo tuần 12–18 không có, tuần sau có)
        save_note(self.db, FRI, {"plan": "1. Fix job", "output": "Fix xong job", "issues": "VDI chậm",
                                 "distractions": "Chat Zalo", "energy": 4, "tomorrow": "Spec API",
                                 "as400_start": "08:40", "as400_end": "17:10"})

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_daily_has_palette_score_robot_every_metric_and_ot(self):
        path, a = report.write_report(self.db, self.cfg, FRI)
        html = self.read(path)
        for c in PALETTE:
            self.assertIn(c, html, c)
        for text in ("ĐIỂM TỔNG HÔM NAY", "<svg", "robot hạng", "Kéo điểm xuống nhiều nhất", "Muốn lên điểm",
                     "Tập trung sâu", "Thao tác trong VDI", "Ngoài VDI", "lần rời VDI", "VDI bị thu nhỏ",
                     "Inactive phím/chuột", "Rời máy", "Điểm tập trung", "Làm ngoài giờ trong VDI (OT)",
                     "Khối tập trung dài nhất", "Lần bị cắt ngang mỗi giờ", "Inactive / rời máy ≥ 10 phút",
                     "Chuỗi ngày đạt mục tiêu", "Dòng thời gian", "Các khối tập trung", "App ngoài VDI", "chrome.exe",
                     "Theo giờ", "7 ngày gần nhất", "Nhận xét", "Kế hoạch đầu ngày", "Output hôm nay",
                     "Issue / blocker", "Bị phân tâm bởi", "Năng lượng (1–5)", "Việc đầu tiên ngày mai",
                     "Giờ vào / ra AS400", "08:40 – 17:10", "Cách tính điểm và căn cứ khoa học",
                     "Công thức với số của hôm nay", "Làm ngoài giờ (OT) 14 ngày gần nhất", "T3 13/10",
                     "17:30–18:10"):
            self.assertIn(text, html, text)
        self.assertNotRegex(html, r"(src|href)=['\"]https?://", "không tải gì từ mạng")

    def test_off_day_report_has_no_score(self):
        path, _ = report.write_report(self.db, self.cfg, SAT)
        html = self.read(path)
        self.assertIn("bạn bật bot làm bù", html)
        self.assertNotIn("ĐIỂM TỔNG HÔM NAY", html)

    def test_weekly_report_has_everything(self):
        motivation._store(self.db, "week:2026-W42:abc", "AI tuần: giữ giờ vàng")
        path, facts = report.write_week_report(self.db, self.cfg, FRI)
        self.assertTrue(path.endswith("focus-week-2026-W42.html"))
        html = self.read(path)
        for c in PALETTE:
            self.assertIn(c, html, c)
        for text in ("ĐIỂM TỔNG TRUNG BÌNH TUẦN", "Bộ sưu tập robot tuần này", "T2 12/10", "T3 13/10", "T6 16/10",
                     "Tập trung sâu cả tuần", "Thao tác trong VDI", "Ngoài VDI", "VDI bị thu nhỏ", "Inactive phím/chuột",
                     "Rời máy", "Ngày đạt mục tiêu", "Điểm tập trung TB", "Dòng thời gian từng ngày",
                     "Tập trung sâu từng ngày", "App ngoài VDI cả tuần", "Từng ngày, đủ thông số", "Điểm tổng",
                     "Làm ngoài giờ (OT) 14 ngày gần nhất", "AI tuần: giữ giờ vàng", "Output trong tuần",
                     "Fix xong job", "Năng lượng từng ngày", "Kéo điểm xuống nhiều nhất"):
            self.assertIn(text, html, text)
        self.assertEqual(facts["work_days"], 3)

    def test_week_report_shows_weekend_make_up_day(self):
        path, _ = report.write_week_report(self.db, self.cfg, SUN)
        html = self.read(path)
        self.assertIn("làm bù", html)
        self.assertIn("T7 17/10", html)


class BotOtTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42")
        self.api = FakeTelegramAPI()
        self.bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=self.api)

    def test_send_offday_ot_text_and_file(self):
        insert_run(self.bot.db, SAT, "09:00", 50)
        insert_run(self.bot.db, SAT, "14:00", 30)
        self.assertTrue(self.bot.send_offday_ot(SAT))
        text = self.api.sent()[0]
        self.assertIn("Tổng kết làm bù Thứ bảy 17/10 (cuối tuần): 1h 20m trong VDI (09:00–09:50, 14:00–14:30)", text)
        self.assertIn("OT 14 ngày gần nhất", text)
        self.assertTrue(any(m == "sendDocument" for m, p, f in self.api.calls))

    def test_send_offday_ot_nothing_to_send(self):
        self.assertIsNone(self.bot.send_offday_ot(SAT))
        self.assertEqual(self.api.sent(), [])

    def test_weekly_sends_html_file(self):
        insert_run(self.bot.db, FRI, "09:00", 60)
        self.bot.send_weekly(FRI)
        docs = [p for m, p, f in self.api.calls if m == "sendDocument"]
        self.assertTrue(any("Báo cáo tuần 2026-W42" in p.get("caption", "") for p in docs), docs)

    def test_daily_summary_lists_ot_14_days(self):
        insert_run(self.bot.db, TUE, "09:00", 60)
        insert_run(self.bot.db, TUE, "18:00", 30)
        self.bot.send_daily_summary(TUE)
        self.assertTrue(any("OT 14 ngày gần nhất: tổng 30m trong 1 ngày" in t for t in self.api.sent()))


class OtBot(FakeBot):
    def send_offday_ot(self, day):
        self.calls.append(("offday_ot", day))
        return True


class TrackerOffDayOtTest(_Base):
    def test_saturday_manual_sends_make_up_summary_after_work_ends(self):
        script = [("16:00:00", "vdi"), ("17:10:00", "locked")]
        tr, fc, probe, bot, nt = make_tracker(self.cfg, SATURDAY, "16:00:00", script, manual=True)
        tr.bot = OtBot(self.cfg)
        self.assertEqual(tr.run(), "window_end")
        calls = [c for c in tr.bot.calls if c[0] == "offday_ot"]
        self.assertEqual(calls, [("offday_ot", SATURDAY)], "gửi đúng 1 lần, sau khi ngưng làm 30 phút")

    def test_saturday_still_working_waits(self):
        self.cfg["auto_stop_at"] = "17:20"
        script = [("16:00:00", "vdi")]
        tr, fc, probe, bot, nt = make_tracker(self.cfg, SATURDAY, "16:00:00", script, manual=True)
        tr.bot = OtBot(self.cfg)
        tr.run()
        self.assertEqual([c for c in tr.bot.calls if c[0] == "offday_ot"], [], "đang làm: chưa báo")


class DefaultsTest(TempCase):
    def test_water_off_by_default_and_in_example(self):
        self.assertFalse(DEFAULTS["water_reminder_enabled"])
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "config", "settings.example.json"), encoding="utf-8") as f:
            self.assertFalse(json.load(f)["water_reminder_enabled"])


class BibleOffTest(TempCase):
    def test_system_prompt_follows_bible_toggle(self):
        self.cfg["encouragement_styles"] = ["motivation", "family"]
        sp = ai_context.system_prompt(self.cfg)
        self.assertIn("TẮT Kinh Thánh: TUYỆT ĐỐI không dùng câu Kinh Thánh", sp)
        self.assertIn("danh nhân, nhà hiền triết thời xưa", sp)
        self.assertNotIn("Truyền Thống 1926", sp)
        self.cfg["encouragement_styles"] = ["bible"]
        self.assertIn("BẬT Kinh Thánh", ai_context.system_prompt(self.cfg))

    def test_every_encouragement_without_bible_when_off(self):
        self.cfg["encouragement_styles"] = ["motivation", "family"]
        db = open_db(db_path(self.cfg))
        prompts = []
        fake = lambda cfg, prompt, system="", **kw: (prompts.append((prompt, system)) or ("\"Câu\" — Khổng Tử", {}))
        with mock.patch.object(ai_client, "generate", fake), mock.patch.object(ai_client, "provider", lambda c: "gemini"):
            for style in ("motivation", "family"):
                motivation.encouragement(self.cfg, db, "đang chậm", style)
            motivation.morning_message(self.cfg, db, {"today": FRI}, style="family")
        for prompt, system in prompts:
            self.assertNotIn("câu Kinh Thánh nếu hợp", prompt)
            self.assertIn("KHÔNG dùng Kinh Thánh", prompt)
            self.assertIn("TẮT Kinh Thánh", ai_context.ensure_context(self.cfg, system))

    def test_local_fallback_never_bible_when_off(self):
        bible = {q[0] for q in motivation.BIBLE}
        for _ in range(60):
            for style in ("motivation", "family"):
                text = motivation._local(style, [])
                self.assertFalse(any(b in text for b in bible), text)
                self.assertNotRegex(text, r"\d+:\d+\)")

    def test_family_prompt_may_use_bible_only_when_on(self):
        self.cfg["encouragement_styles"] = ["motivation", "bible", "family"]
        self.assertIn("Kinh Thánh nếu hợp", motivation.style_prompt(self.cfg, "family"))
        self.cfg["encouragement_styles"] = ["motivation", "family"]
        self.assertIn("KHÔNG dùng Kinh Thánh", motivation.style_prompt(self.cfg, "family"))


class HtmlHelpersTest(TempCase):
    def test_segments_mark_deep_and_minimized(self):
        a = {"timeline": [[0, 100, "vdi"], [100, 160, "other"], [160, 400, "vdi"]],
             "blocks": [{"start": 160, "end": 400}], "minimized_spans": [[110, 150]]}
        kinds = [k for _, _, k in report_html.segments(a)]
        self.assertEqual(kinds, ["vdi", "other", "deep", "min"])

    def test_burst_is_svg(self):
        self.assertTrue(re.match(r"<svg[^>]*><polygon", report_html.burst("#C35850")))
