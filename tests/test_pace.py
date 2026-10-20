"""Cảnh báo tiến độ (/pace): công thức ở từng mốc, mốc tới hạn, nghỉ phép nửa ngày, khen 1 lần, bật/tắt."""
import tempfile
import threading
import unittest
from unittest import mock

from focus import errors, intent, messages, pace, persona
from focus.config import ConfigError, DEFAULTS, validate
from focus.schedule import due_jobs
from focus.storage import db_path, get_pref, open_db
from focus.telegram_bot import TelegramBot
from tests import test_tracker as T
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, make_cfg, msg


def first(xs):
    return xs[0]


class MathTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())

    def test_available_work_time(self):
        self.assertEqual(pace.work_minutes(self.cfg, "17:00"), 465)  # 9h - 1h15 trưa = 7h45
        self.assertEqual(pace.work_minutes(self.cfg, "12:00"), 195)  # trong giờ trưa: dừng ở 11:15
        self.assertEqual(pace.work_minutes(self.cfg, "07:00"), 0)
        self.assertEqual(pace.work_minutes(self.cfg, "17:00", "am"), 270)
        self.assertEqual(pace.work_minutes(self.cfg, "17:00", "pm"), 195)

    def test_expected_at_each_checkpoint(self):
        want = {"10:30": 6 * 150 / 465, "14:00": 6 * 285 / 465, "15:30": 6 * 375 / 465}
        for cp, exp in want.items():
            with self.subTest(cp=cp):
                info = pace.status(self.cfg, 0, cp)
                self.assertAlmostEqual(info["expected_h"], exp, places=6)
                self.assertTrue(info["behind"])
        self.assertAlmostEqual(want["14:00"], 3.677, places=3)

    def test_behind_threshold(self):
        # 14:00 cần ~3,68h; chậm khi < 0,6 x 3,68 ≈ 2,21h
        self.assertTrue(pace.status(self.cfg, 2 * 3600, "14:00")["behind"])
        self.assertFalse(pace.status(self.cfg, 2.25 * 3600, "14:00")["behind"])
        self.assertTrue(pace.status(self.cfg, 1.1 * 3600, "10:30")["behind"])   # cần 1,94 -> ngưỡng 1,16
        self.assertFalse(pace.status(self.cfg, 1.2 * 3600, "10:30")["behind"])
        self.assertTrue(pace.status(self.cfg, 2.8 * 3600, "15:30")["behind"])   # cần 4,84 -> ngưỡng 2,90

    def test_needed_minutes_per_remaining_hour(self):
        info = pace.status(self.cfg, 3 * 3600, "14:00")
        self.assertEqual(info["remaining_min"], 180)
        self.assertAlmostEqual(info["need_per_hour"], 60)
        info = pace.status(self.cfg, 4.5 * 3600, "14:00")
        self.assertAlmostEqual(info["need_per_hour"], 30)
        self.assertIn("30 phút", messages.pace_need_line(info))
        info = pace.status(self.cfg, 2 * 3600, "14:00")  # cần 4h trong 3h còn lại: không kịp nữa
        self.assertGreater(info["need_per_hour"], 60)
        self.assertIn("chỉ được khoảng 5h00", messages.pace_need_line(info))
        self.assertIn("Đã đủ mục tiêu", messages.pace_need_line(pace.status(self.cfg, 7 * 3600, "15:30")))

    def test_half_day_leave(self):
        info = pace.status(self.cfg, 0.5 * 3600, "14:00", "am")  # 12:30–17:00 = 4,5h, mục tiêu 3h
        self.assertEqual(info["target_h"], 3)
        self.assertAlmostEqual(info["expected_h"], 3 * 90 / 270)
        self.assertTrue(info["behind"])
        self.assertFalse(pace.status(self.cfg, 0.7 * 3600, "14:00", "am")["behind"])
        info = pace.status(self.cfg, 0, "10:30", "pm")  # 08:00–11:15, mục tiêu 3h
        self.assertAlmostEqual(info["expected_h"], 3 * 150 / 195)

    def test_due_checkpoint(self):
        c = self.cfg
        cases = {"10:29": None, "10:30": "10:30", "11:10": "10:30", "11:30": None, "12:30": "10:30",
                 "12:50": None, "13:59": None, "14:00": "14:00", "15:00": "14:00", "15:01": None, "15:30": "15:30",
                 "16:30": "15:30", "16:31": None, "17:00": None}
        for hhmm, want in cases.items():
            with self.subTest(hhmm=hhmm):
                self.assertEqual(pace.due_checkpoint(c, hhmm), want)
        self.assertIsNone(pace.due_checkpoint(c, "14:00", off="lễ"))
        self.assertIsNone(pace.due_checkpoint(c, "10:30", leave="am"))
        self.assertEqual(pace.due_checkpoint(c, "14:00", leave="am"), "14:00")
        self.assertEqual(pace.due_checkpoint(c, "10:30", leave="pm"), "10:30")
        self.assertIsNone(pace.due_checkpoint(c, "14:00", leave="pm"))
        c["pace_check_enabled"] = False
        self.assertIsNone(pace.due_checkpoint(c, "14:00"))

    def test_due_jobs_even_when_idle(self):
        kw = dict(off=None, note={"plan": "x"}, has_bot=True)
        self.assertIn("pace_1400", due_jobs(self.cfg, "14:00", 2, active=False, **kw))
        self.assertNotIn("pace_1400", due_jobs(self.cfg, "13:59", 2, active=True, **kw))
        self.assertEqual(due_jobs(self.cfg, "14:00", 2, active=True, off="lễ", note={}, has_bot=True), [])
        self.assertEqual(errors.job_name("pace_1400"), "cảnh báo tiến độ 14:00")
        self.assertEqual(errors.job_name("pace_0945"), "cảnh báo tiến độ 09:45")

    def test_praise_checkpoint(self):
        self.assertEqual(pace.praise_checkpoint(self.cfg), "14:00")
        self.cfg["pace_checkpoints"] = ["10:00", "14:30"]
        self.assertEqual(pace.praise_checkpoint(self.cfg), "14:30")


class WordingTest(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())
        self.info = pace.status(self.cfg, 2 * 3600, "14:00")

    def test_behind_per_tone_and_level(self):
        texts = set()
        with mock.patch.object(persona.random, "choice", first):
            for tone in persona.TONES:
                p = dict(persona.DEFAULT, giong=tone)
                for level in ("vua", "nghiem"):
                    t = messages.pace_behind(self.info, p, level)
                    self.assertIn("mới làm thật trong VDI 2h00", t)
                    self.assertIn("Chậm 1h41", t)
                    self.assertIn("Còn 3h00 giờ làm", t)
                    texts.add(t.splitlines()[0])
                    if level == "nghiem":   # câu chốt gắt: một trong các câu pace_hard của giọng đó
                        hard = [x.format(u="bạn", U="Bạn", me="mình", Me="Mình", boss="")
                                for x in persona.LEADS["pace_hard"][tone]]
                        self.assertIn(t.splitlines()[-1], hard)
        self.assertEqual(len(texts), 8, "mỗi giọng x mức có câu mở đầu riêng")
        boss = messages.pace_behind(self.info, dict(persona.DEFAULT, giong="sep_kho_tinh"), "nghiem")
        self.assertIn(boss.splitlines()[-1], persona.LEADS["pace_hard"]["sep_kho_tinh"])

    def test_praise_per_tone(self):
        info = pace.status(self.cfg, 4 * 3600, "14:00")
        leads = {messages.pace_praise(info, dict(persona.DEFAULT, giong=t)).splitlines()[0] for t in persona.TONES}
        self.assertEqual(len(leads), 4)
        self.assertIn("✅ 14:00", messages.pace_praise(info))


# ------------------------------------------------------------ cả ngày qua Tracker.run()

BEHIND_DAY = [
    ("07:00:00", "locked"),
    ("08:00:00", "vdi"),       # 1,5h buổi sáng: 10:30 vẫn đủ ngưỡng (cần 1,94 -> ngưỡng 1,16)
    ("09:30:00", "locked"),
    ("12:30:00", "vdi"),       # +0,5h -> 14:00 có 2h (ngưỡng 2,21): chậm
    ("13:00:00", "locked"),
]

ON_PACE_DAY = [
    ("07:00:00", "locked"),
    ("08:00:00", "vdi"),
    ("11:15:00", "locked"),
    ("12:30:00", "vdi"),
]


class TrackerPaceTest(T._Base):
    def run_day(self, script, stop="16:00", leave=None, **cfg):
        self.cfg.update(auto_stop_at=stop, **cfg)
        if leave:
            db = open_db(db_path(self.cfg))
            from focus.storage import save_note
            save_note(db, T.FRIDAY, {"leave_part": leave})
            db.close()
        tr, fc, probe, bot, nt = T.make_tracker(self.cfg, T.FRIDAY, "07:00:00", script)
        tr.run()
        return bot, nt, [t for t, _ in bot.sent if "📉" in t or "✅" in t]

    def test_behind_warns_at_14_and_15_30(self):
        bot, nt, sent = self.run_day(BEHIND_DAY)
        self.assertEqual([lb for _, lb in T.labels(nt, T.FRIDAY, {"pace_1030", "pace_1400", "pace_1530"})],
                         ["pace_1030", "pace_1400", "pace_1530"])
        self.assertEqual(len(sent), 2, sent)
        self.assertIn("📉 14:00: mới làm thật trong VDI 2h00", sent[0])
        self.assertIn("📉 15:30", sent[1])
        self.assertEqual(self.audit_text().count("| PACE |"), 3)
        self.assertIn("'verdict': 'ok'", self.audit_text())

    def test_strict_level_is_harsher(self):
        bot, nt, sent = self.run_day(BEHIND_DAY, stop="14:10", nudge_level="nghiem")
        hard = [x.format(u="bạn", U="Bạn", me="mình", Me="Mình", boss="")
                for t in persona.LEADS["pace_hard"].values() for x in t]
        self.assertIn(sent[0].splitlines()[-1], hard)

    def test_nudge_off_does_not_disable_pace(self):
        bot, nt, sent = self.run_day(BEHIND_DAY, stop="14:10", nudge_level="off")
        self.assertEqual(len(sent), 1)

    def test_on_pace_praise_once_only_at_14(self):
        bot, nt, sent = self.run_day(ON_PACE_DAY)
        self.assertEqual(len(sent), 1, sent)
        self.assertTrue(sent[0].startswith(sent[0].splitlines()[0]))
        self.assertIn("✅ 14:00", sent[0])

    def test_restart_does_not_repeat_checkpoint(self):
        self.run_day(BEHIND_DAY, stop="14:10")
        bot, nt, sent = self.run_day(BEHIND_DAY, stop="14:20")
        self.assertEqual(sent, [], "mỗi mốc tối đa 1 lần/ngày (sent_log)")

    def test_disabled(self):
        bot, nt, sent = self.run_day(BEHIND_DAY, pace_check_enabled=False)
        self.assertEqual(sent, [])
        self.assertFalse(T.labels(nt, T.FRIDAY, {"pace_1030", "pace_1400", "pace_1530"}))

    def test_morning_leave_skips_1030_and_halves_target(self):
        script = [("07:00:00", "locked"), ("12:30:00", "vdi"), ("13:00:00", "locked")]  # 0,5h buổi chiều
        bot, nt, sent = self.run_day(script, leave="am")
        got = [lb for _, lb in T.labels(nt, T.FRIDAY, {"pace_1030", "pace_1400", "pace_1530"})]
        self.assertEqual(got, ["pace_1400", "pace_1530"])
        self.assertIn("kịp 3h trước 17:00", sent[0])

    def test_afternoon_leave_only_1030(self):
        bot, nt, sent = self.run_day(BEHIND_DAY, leave="pm")
        got = [lb for _, lb in T.labels(nt, T.FRIDAY, {"pace_1030", "pace_1400", "pace_1530"})]
        self.assertEqual(got, ["pace_1030"])


# ------------------------------------------------------------ lệnh /pace

class PaceCommandTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def test_toggle_persist_default(self):
        self.assertIn("ĐANG TẮT", self.say("/pace off")[0])
        self.assertFalse(self.cfg["pace_check_enabled"])
        self.assertEqual(get_pref(self.bot.db, "pace_check_enabled"), "0")
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.state, api=self.api)
        self.assertFalse(cfg2["pace_check_enabled"], "khởi động lại vẫn tắt")
        self.assertIn("ĐANG BẬT", self.say("/tiendo bật")[0])
        self.say("/pace mac_dinh")
        self.assertTrue(self.cfg["pace_check_enabled"])
        self.assertIsNone(get_pref(self.bot.db, "pace_check_enabled"))
        self.assertTrue(any("PACE_CHECK" in l for l in self.audit_lines()))

    def test_view_no_confirm(self):
        info = pace.status(self.cfg, 2 * 3600, "14:00")
        with mock.patch.object(pace, "today_status", return_value=info):
            out = self.say("/pace")[0]
            self.assertIn("Tiến độ lúc 14:00", out)
            self.assertIn("chậm 1h41", out)
            self.assertIn("Cảnh báo tiến độ tự động: ĐANG BẬT (mốc 10:30, 14:00, 15:30)", out)
            for text in ("tiến độ hôm nay sao rồi", "tiến độ hôm nay thế nào?"):
                out = self.say(text)
                self.assertFalse(self.bot.pending, text)
                self.assertIn("canh_bao_tien_do", out[0], text)
                self.assertIn("Tiến độ lúc 14:00", out[1], text)

    def test_natural_language_toggle_confirms(self):
        self.say("tắt cảnh báo tiến độ")
        self.assertTrue(self.bot.pending)
        self.assertTrue(self.cfg["pace_check_enabled"])
        pid = list(self.bot.pending)[0]
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        self.assertFalse(self.cfg["pace_check_enabled"])
        self.assertEqual(intent.by_rules("bật cảnh báo tiến độ")[1], {"state": "on"})

    def test_view_before_work(self):
        self.assertIn("Chưa tới giờ làm", messages.pace_view(None, True, ["10:30"]))


class ConfigTest(unittest.TestCase):
    def cfg(self, **kw):
        c = dict(DEFAULTS)
        c.update(kw)
        return validate(c)

    def test_defaults_and_normalize(self):
        c = self.cfg(pace_checkpoints=["15:30", "9:45", "14:00", "14:00"])
        self.assertEqual(c["pace_checkpoints"], ["09:45", "14:00", "15:30"])
        self.assertTrue(DEFAULTS["pace_check_enabled"])
        self.assertEqual((DEFAULTS["pace_target_vdi_hours"], DEFAULTS["pace_behind_ratio"]), (6, 0.4))

    def test_bad_values(self):
        for bad in ({"pace_checkpoints": "14:00"}, {"pace_checkpoints": ["7:30"]}, {"pace_checkpoints": ["17:00"]},
                    {"pace_checkpoints": ["11:30"]}, {"pace_checkpoints": ["25:00"]},
                    {"pace_target_vdi_hours": 0}, {"pace_target_vdi_hours": "6"}, {"pace_behind_ratio": 1},
                    {"pace_behind_ratio": 0}, {"pace_check_enabled": "yes"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    self.cfg(**bad)


if __name__ == "__main__":
    unittest.main()
