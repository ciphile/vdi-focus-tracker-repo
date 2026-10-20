"""v2.10.4: câu nhắc đã dùng được lưu vào DB, tắt/bật lại tracker không gửi lại câu vừa dùng."""
import json
import os
import types

from focus import persona
from focus.nudge_lines import NUDGE
from focus.storage import get_pref, open_db
from focus.tracker import LINES_USED_KEY, Tracker
from tests.helpers import TempCase

P = dict(persona.DEFAULT, giong="hai_huoc", goi_nguoi_dung="bạn", bot_xung="mình")


def picks(n):
    return [persona.nudge_lead("out_of_vdi", "nghiem", P) for _ in range(n)]


class RestartNoRepeatTest(TempCase):
    def test_pool_has_many_lines(self):
        self.assertGreaterEqual(len(set(NUDGE["nghiem"]["hai_huoc"])), 10)

    def test_restart_continues_rotation(self):
        first = picks(10)
        raw = persona.export_used()
        persona._USED.clear()  # giống tắt/bật lại tracker
        self.assertTrue(persona.restore_used(raw))
        after = picks(10)
        self.assertEqual(len(set(first + after)), 20)

    def test_without_restore_can_repeat_is_old_behaviour_fixed(self):
        size = len(NUDGE["nghiem"]["hai_huoc"]) + len(persona.LEADS["out_of_vdi_nghiem"]["hai_huoc"])
        seen = []
        for _ in range(4):  # 4 lần tắt/bật, mỗi lần gửi vài câu
            seen += picks(size // 4)
            raw = persona.export_used()
            persona._USED.clear()
            persona.restore_used(raw)
        self.assertEqual(len(set(seen)), len(seen))

    def test_bad_data_is_ignored(self):
        for raw in (None, "", "{hỏng", "[1,2]", json.dumps({"a|b": [1, "x"]})):
            persona.restore_used(raw)
        self.assertEqual(len(set(picks(5))), 5)

    def test_saved_data_is_small(self):
        for kind in ("out_of_vdi", "minimized"):
            for level in ("nhe", "vua", "nghiem"):
                for tone in persona.TONES:
                    for _ in range(40):
                        persona.nudge_lead(kind, level, dict(P, giong=tone))
        raw = persona.export_used()
        self.assertLess(len(raw), 20000)
        self.assertNotIn("bạn", raw)  # chỉ lưu mã ngắn, không lưu câu

    def test_tracker_saves_only_when_new_line(self):
        db = open_db(os.path.join(self.cfg["data_dir"], "t.db"))
        tr = types.SimpleNamespace(db=db)
        persona.export_used()  # đánh dấu sạch
        Tracker._save_lines_used(tr)
        self.assertIsNone(get_pref(db, LINES_USED_KEY))
        line = picks(1)[0]
        Tracker._save_lines_used(tr)
        self.assertIsNotNone(get_pref(db, LINES_USED_KEY))
        self.assertFalse(persona.used_dirty())
        persona._USED.clear()
        Tracker._load_lines_used(tr)
        self.assertNotIn(line, picks(len(NUDGE["nghiem"]["hai_huoc"])))
        db.close()

    def test_pace_lines_differ_from_nudge_lines(self):
        pace = set(persona.LEADS["pace_behind_nghiem"]["hai_huoc"] + persona.LEADS["pace_behind"]["hai_huoc"])
        nudge = set(NUDGE["nghiem"]["hai_huoc"])
        self.assertFalse(pace & nudge)
        self.assertFalse([x for x in pace if "mài dao" in x])


class SaveIntervalTest(TempCase):
    def test_saved_about_every_5_minutes_not_every_sample(self):
        from focus import tracker
        self.assertEqual(tracker.LINES_SAVE_TICKS * 5, 300)  # 60 vòng × mẫu 5 giây = 5 phút
