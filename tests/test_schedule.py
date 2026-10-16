import unittest
import tempfile

from focus.schedule import due_jobs, in_run_window, is_lunch, is_work_time
from tests.helpers import make_cfg


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())

    def test_work_time_boundaries(self):
        c = self.cfg
        cases = {"07:59": False, "08:00": True, "11:14": True, "11:15": False, "12:29": False,
                 "12:30": True, "16:59": True, "17:00": False, "20:00": False}
        for hhmm, want in cases.items():
            with self.subTest(hhmm=hhmm):
                self.assertEqual(is_work_time(c, hhmm), want)
        self.assertFalse(is_work_time(c, "09:00", off="cuối tuần"))
        self.assertTrue(is_lunch(c, "12:00"))

    def test_run_window(self):
        self.assertFalse(in_run_window(self.cfg, "06:59"))
        self.assertTrue(in_run_window(self.cfg, "07:00"))
        self.assertTrue(in_run_window(self.cfg, "23:58"))
        self.assertFalse(in_run_window(self.cfg, "23:59"))

    def jobs(self, hhmm, weekday=2, active=True, off=None, note=None, has_bot=True):
        return due_jobs(self.cfg, hhmm, weekday, active=active, off=off, note=note or {}, has_bot=has_bot)

    def test_plan_only_in_work_time_when_missing(self):
        self.assertIn("plan", self.jobs("08:00"))
        self.assertNotIn("plan", self.jobs("07:30"))
        self.assertNotIn("plan", self.jobs("08:30", note={"plan": "x"}))
        self.assertNotIn("plan", self.jobs("08:30", active=False))
        self.assertNotIn("plan", self.jobs("11:30"), "nghỉ trưa")
        self.assertNotIn("plan", self.jobs("18:00"), "ngoài giờ làm")

    def test_review_window(self):
        self.assertIn("review", self.jobs("16:45"))
        self.assertNotIn("review", self.jobs("16:44"))
        self.assertNotIn("review", self.jobs("17:00"))
        self.assertIn("review", self.jobs("16:50", note={"energy": 3}), "/energy giữa ngày không làm mất câu hỏi")

    def test_summary_weekly_boost(self):
        self.assertIn("summary", self.jobs("17:00", active=False))
        self.assertNotIn("summary", self.jobs("16:59"))
        self.assertIn("weekly", self.jobs("16:50", weekday=4))
        self.assertNotIn("weekly", self.jobs("16:49", weekday=4))
        self.assertNotIn("weekly", self.jobs("16:50", weekday=3))
        self.assertIn("boost", self.jobs("14:30"))
        self.assertNotIn("boost", self.jobs("17:30"))
        self.assertEqual(self.jobs("14:30", has_bot=False), [])

    def test_nothing_on_off_day(self):
        self.assertEqual(self.jobs("17:30", off="Christmas Day"), [])
