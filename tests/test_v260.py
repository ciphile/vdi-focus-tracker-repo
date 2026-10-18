"""2.6.0: sửa theo báo cáo thật 16/10: ngày tốt/kém nhất khi hoà, "41 lần/ngày", câu nghiên cứu không xưng "Bạn",
prompt tuần không chê app ngoài VDI và không tự nghĩ ra issue, luật emoji, câu trích chỉ lấy trong danh sách đã kiểm,
tổng kết tuần 17:05 sau tổng kết ngày."""
import json
import os
import re
from unittest import mock

from focus import ai_client, ai_context, motivation, quotes, report, scoring
from focus.analysis import day_facts, week_facts
from focus.config import DEFAULTS
from focus.schedule import due_jobs
from focus.storage import db_path, open_db
from tests.helpers import TempCase as _TempCase, insert_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THU, FRI = "2026-10-15", "2026-10-16"


class TempCase(_TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)


class Calls:
    def __init__(self, text="AI: ổn"):
        self.calls, self.text = [], text

    def __call__(self, cfg, prompt, system="", image=None, purpose="", **kw):
        self.calls.append({"prompt": prompt, "system": system, "purpose": purpose})
        return self.text, "fake-model"


class BestWorstDayTest(TempCase):
    def test_tie_is_not_best_and_worst_same_day(self):
        insert_run(self.db, THU, "09:00", 10)  # cả hai ngày 0h tập trung sâu, điểm như nhau (như tuần 42 thật)
        insert_run(self.db, FRI, "09:00", 10)
        f = week_facts(self.db, self.cfg, FRI)
        self.assertTrue(f["days_tied"])
        self.assertEqual(f["best_day"], f["worst_day"])
        self.assertIn("bằng nhau", f["best_day"])
        self.assertIn("Ngày tốt / kém nhất", report.week_text(f))
        self.assertNotIn("kém nhất: Thứ", report.week_text(f))

    def test_ranked_by_total_score(self):
        insert_run(self.db, THU, "09:00", 10)
        insert_run(self.db, FRI, "09:00", 120)
        f = week_facts(self.db, self.cfg, FRI)
        self.assertFalse(f["days_tied"])
        self.assertIn("Thứ 6", f["best_day"])
        self.assertIn("Thứ 5", f["worst_day"])
        self.assertIn("điểm tổng", f["best_day"])

    def test_single_day(self):
        insert_run(self.db, FRI, "09:00", 60)
        f = week_facts(self.db, self.cfg, FRI)
        self.assertIn("chỉ có 1 ngày", f["best_day"])

    def test_explain_week_tie(self):
        days = [{"day": d, "weekday": w, "total_score": 10, "total_score_parts": {"focus": 5, "interruptions": 20}}
                for d, w in ((THU, "Thứ 5"), (FRI, "Thứ 6"))]
        ex = scoring.explain_week(days)
        self.assertEqual(ex["best_day"], ex["worst_day"])
        self.assertIn("bằng nhau", ex["best_day"])
        days[1]["total_score"] = 14
        ex = scoring.explain_week(days)
        self.assertIn("Thứ 6", ex["best_day"])
        self.assertIn("Thứ 5", ex["worst_day"])

    def test_week_html_tie_one_chip(self):
        insert_run(self.db, THU, "09:00", 10)
        insert_run(self.db, FRI, "09:00", 10)
        path, _ = report.write_week_report(self.db, self.cfg, FRI)
        with open(path, encoding="utf-8") as fh:
            page = fh.read()
        self.assertIn("Ngày tốt / kém nhất", page)
        self.assertNotIn("Tập trung nhiều nhất", page)


class SmallTextTest(TempCase):
    def test_minimize_count_integer(self):
        from focus.report_html import notes_section
        extra = {"distractions": {"days": 1, "avg_other": 600, "avg_minimize_count": 41.0, "top_hours": [],
                                  "noted": 0, "noted_hours": []}}
        out = notes_section(self.cfg, {}, extra)
        self.assertIn("41 lần/ngày", out)
        self.assertNotIn("41.0", out)
        extra["distractions"]["avg_minimize_count"] = 12.25
        self.assertIn("12.2 lần/ngày", notes_section(self.cfg, {}, extra))

    def test_science_advice_has_no_direct_address(self):
        self.assertNotRegex(scoring.FAMILY_WHY, r"\b[Bb]ạn\b")
        self.assertIn("gia đình", scoring.FAMILY_WHY)
        self.assertIn("xưng hô", ai_context.GLOSSARY["science_advice"])


class PromptRulesTest(TempCase):
    def week_prompt(self):
        insert_run(self.db, THU, "09:00", 60)
        insert_run(self.db, FRI, "09:00", 60)
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake), mock.patch.object(ai_client, "provider", lambda c: "gemini"):
            motivation.review_week(self.cfg, self.db, week_facts(self.db, self.cfg, FRI))
        return fake.calls[0]

    def test_outside_vdi_rule_in_every_prompt(self):
        sp = ai_context.system_prompt(self.cfg)
        self.assertIn("có thể là việc phục vụ công việc", sp)
        self.assertIn("nghiện", sp)

    def test_weekly_no_invented_issue_and_no_blame(self):
        p = re.sub(r"\s+", " ", self.week_prompt()["prompt"])
        self.assertIn("CHỈ lấy issue người dùng tự ghi", p)
        self.assertIn("tuần này chưa ghi issue nào", p)
        self.assertIn("không tự nghĩ ra issue", p)
        self.assertIn('không dùng từ "nghiện"', p)
        self.assertIn("bằng nhau", p)

    def test_emoji_rule_consistent(self):
        sp = ai_context.system_prompt(self.cfg)
        self.assertIn("mỗi mục đúng một emoji ở đầu mục", sp)
        self.assertNotIn("tối đa 1–2 emoji (", sp)
        self.assertIn("không gộp hai mục", motivation.DAILY_TASK)
        self.assertIn("không gộp hai mục", motivation.WEEKLY_TASK)


class QuoteMenuTest(TempCase):
    def test_lists_clean(self):
        for items in (quotes.BIBLE, quotes.QUOTES):
            texts = [t for t, _ in items]
            self.assertEqual(len(texts), len(set(texts)))
            for t, src in items:
                self.assertTrue(t.strip() and src.strip())
                self.assertNotIn("Ð", t, "dùng chữ Đ tiếng Việt, không dùng Ð (Eth)")
        for _, ref in quotes.BIBLE:
            self.assertRegex(ref, r"\d+:\d+")
        self.assertGreaterEqual(len(quotes.BIBLE), 20)
        self.assertIs(motivation.BIBLE, quotes.BIBLE)

    def test_daily_review_menu_bible_on(self):
        self.cfg["encouragement_styles"] = ["bible"]
        insert_run(self.db, FRI, "09:00", 60)
        fake = Calls()
        with mock.patch.object(ai_client, "generate", fake), mock.patch.object(ai_client, "provider", lambda c: "gemini"):
            motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, FRI))
        p = fake.calls[0]["prompt"]
        self.assertIn(quotes.MENU_HEAD, p)
        self.assertIn("(Thi-thiên 55:22)", p)
        self.assertIn("— Lão Tử", p)
        self.assertLess(p.index(quotes.MENU_HEAD), p.index("SỐ LIỆU (JSON):"), "JSON vẫn ở cuối prompt")
        json.loads(p.split("SỐ LIỆU (JSON):", 1)[1])
        self.assertIn("DANH SÁCH CÂU TRÍCH", fake.calls[0]["system"])

    def test_menu_bible_off_has_no_bible(self):
        self.cfg["encouragement_styles"] = ["motivation", "family"]
        for style in (None, "family", "motivation"):
            m = motivation.menu_for(self.cfg, style)
            self.assertNotIn("Kinh Thánh (bản", m)
            for _, ref in quotes.BIBLE:
                self.assertNotIn(ref, m)
        self.assertNotIn("Danh ngôn", motivation.menu_for(self.cfg, "bible"))

    def test_morning_and_encourage_get_menu(self):
        self.cfg["encouragement_styles"] = ["bible"]
        fake = Calls('"Tôi làm được mọi sự nhờ Đấng ban thêm sức cho tôi." (Phi-líp 4:13)')
        with mock.patch.object(ai_client, "generate", fake), mock.patch.object(ai_client, "provider", lambda c: "gemini"):
            motivation.morning_message(self.cfg, self.db, {"today": FRI})
            motivation.encouragement(self.cfg, self.db, "vừa quay lại VDI")
        for call in fake.calls:
            self.assertIn(quotes.MENU_HEAD, call["prompt"])
        # câu vừa gửi không có lại trong danh sách lần sau
        self.assertNotIn("(Phi-líp 4:13)", fake.calls[-1]["prompt"].split(quotes.MENU_HEAD, 1)[1])

    def test_fresh_keeps_all_when_everything_recent(self):
        recent = [t for t, _ in quotes.QUOTES]
        self.assertEqual(quotes.fresh(quotes.QUOTES, recent), list(quotes.QUOTES))


class WeeklyTimeTest(TempCase):
    def test_default_after_daily_summary(self):
        self.assertEqual(DEFAULTS["weekly_report_at"], "17:05")
        self.assertGreater(DEFAULTS["weekly_report_at"], DEFAULTS["daily_summary_at"])
        with open(os.path.join(ROOT, "config", "settings.example.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["weekly_report_at"], "17:05")

    def test_catch_up_runs_summary_before_weekly(self):
        jobs = due_jobs(self.cfg, "17:30", 4, active=False, off=False, note={}, has_bot=True)
        self.assertLess(jobs.index("summary"), jobs.index("weekly"))
        self.assertNotIn("weekly", due_jobs(self.cfg, "17:00", 4, active=False, off=False, note={}, has_bot=True))
