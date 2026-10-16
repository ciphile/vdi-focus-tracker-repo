"""Việc còn tồn từ ngày làm việc trước (nhắc trong lời chào sáng)."""
import unittest

from focus import pending


class PendingTest(unittest.TestCase):
    def test_plan_minus_output_plus_issues(self):
        note = {"plan": "1. Gởi estimation uat release cho SH\n2. Uat check premium vóm\n3) Code acct switch",
                "output": "- gửi estimation UAT release cho SH xong (10:20)\n- code xong acct switch (16:00)",
                "issues": "- VDI chậm (09:00)\n- chờ anh Tuấn review (14:00)"}
        self.assertEqual(pending.pending_of(note), [("plan", "Uat check premium vóm"),
                                                    ("issue", "VDI chậm"), ("issue", "chờ anh Tuấn review")])

    def test_no_output_keeps_all_plan(self):
        self.assertEqual(pending.pending_of({"plan": "Sửa job CL01; viết spec"}),
                         [("plan", "Sửa job CL01"), ("plan", "viết spec")])

    def test_empty(self):
        self.assertEqual(pending.pending_of({}), [])
        self.assertEqual(pending.pending_text("2026-10-15", []), "")

    def test_text(self):
        t = pending.pending_text("2026-10-15", [("plan", "Tạo wu", "2026-10-15"), ("issue", "VDI chậm", "2026-10-15")])
        self.assertTrue(t.startswith("📌 Việc còn tồn từ thứ Năm 15/10"))
        self.assertIn("• Tạo wu", t)
        self.assertIn("• ⚠️ issue: VDI chậm", t)

    def test_max_items(self):
        note = {"plan": "\n".join(f"việc số {i} khác nhau hoàn toàn x{i}" for i in range(20))}
        self.assertEqual(len(pending.pending_of(note)), pending.MAX_ITEMS)
        self.assertEqual(len(pending.pending_of(note, limit=None)), 20)
