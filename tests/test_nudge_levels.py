"""Mức nhắc khi sao nhãng (/nudge): off | nhe | vua | nghiem. Đếm số lần nhắc qua một ngày giả lập,
câu nhắc theo mức + giọng, lệnh /nudge, nhắn tự nhiên, lưu prefs, cấu hình."""
import threading
import unittest
from unittest import mock

from focus import intent, messages, motivation, persona
from focus.actions import nudge_lookup
from focus.alerts import RealtimeAlerts
from focus.config import ConfigError, DEFAULTS, validate
from focus.storage import db_path, get_pref, open_db
from focus.telegram_bot import TelegramBot
from focus.tracker import Tracker
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, make_cfg, msg, sample, ts

DAY = "2026-10-14"

# Một ngày giả lập (giờ bắt đầu, phút, loại). Loại: vdi | chrome (app khác ở trước) | min (VDI thu nhỏ) | lock.
# golden=True: đoạn đó nằm trong giờ vàng.
SCRIPT = [
    ("08:00", 30, "vdi"),
    ("08:30", 20, "chrome"),   # A: 20 phút ngoài VDI
    ("08:50", 20, "vdi"),
    ("09:10", 18, "min"),      # B: 18 phút VDI thu nhỏ mà vẫn bấm chuột
    ("09:28", 10, "vdi"),
    ("09:38", 8, "chrome"),    # C: 8 phút (ngắn)
    ("09:46", 10, "vdi"),
    ("09:56", 7, "chrome"),    # D: 7 phút, rồi khoá máy 30 phút giữa chừng
    ("10:03", 30, "lock"),
    ("10:33", 10, "chrome"),   # E: mở máy vẫn ngoài VDI 10 phút: không được nhắc dồn
    ("10:43", 10, "vdi"),
    ("10:53", 6, "chrome", True),  # F: 6 phút trong giờ vàng
    ("10:59", 5, "vdi"),
]


def run_script(cfg, script=SCRIPT, day=DAY):
    al = RealtimeAlerts(cfg)
    events = []
    for item in script:
        start, minutes, kind = item[:3]
        golden = len(item) > 3 and item[3]
        t0 = ts(day, start)
        for i in range(1, int(minutes * 12) + 1):
            t = t0 + i * 5
            if kind == "vdi":
                s = sample()
            elif kind == "chrome":
                s = sample(vdi="background", proc="chrome.exe")
            elif kind == "min":
                s = sample(vdi="minimized", proc="cdviewer.exe")
            else:
                s = sample(vdi="background", proc="lockapp.exe", locked=True, idle=i * 5)
            for k, d in al.update(s, t, True, golden):
                events.append((t, k, d))
    return al, events


def hm(t):
    import datetime as dt
    return dt.datetime.fromtimestamp(t).strftime("%H:%M:%S")


class LevelCountTest(unittest.TestCase):
    def cfg(self, level, **kw):
        import tempfile
        return make_cfg(tempfile.mkdtemp(), nudge_level=level, **kw)

    def outs(self, level, **kw):
        al, ev = run_script(self.cfg(level, **kw))
        return al, [(hm(t), d) for t, k, d in ev if k == "out_of_vdi"]

    def test_off_never_nudges(self):
        al, outs = self.outs("off")
        self.assertEqual(outs, [])
        self.assertEqual(al.today()["count"], 6, "vẫn đếm số lần sao nhãng cho /status")

    def test_light_once_per_day(self):
        al, outs = self.outs("nhe")
        self.assertEqual([t for t, _ in outs], ["08:45:05"])  # A, đủ 15 phút; B, F... bỏ qua
        self.assertEqual(outs[0][1]["level"], "nhe")

    def test_light_needs_15_minutes(self):
        al, outs = self.outs("nhe", nudge_light_minutes=25)
        self.assertEqual(outs, [], "không lần nào kéo dài 25 phút")

    def test_medium_once_per_episode_incl_minimized_and_golden(self):
        al, outs = self.outs("vua")
        self.assertEqual([t for t, _ in outs], ["08:45:05", "09:25:05", "10:58:05"])
        self.assertEqual([d["nth"] for _, d in outs], [1, 1, 1], "không nhắc lặp trong cùng một lần")
        self.assertEqual(outs[1][1]["vdi_state"], "minimized", "VDI thu nhỏ cũng là sao nhãng")
        self.assertTrue(outs[2][1]["golden"])
        self.assertEqual([d["day_nudges"] for _, d in outs], [1, 2, 3])

    def test_medium_threshold_override_still_works(self):
        al, outs = self.outs("vua", nudge_out_of_vdi_minutes=8, golden_nudge_minutes=0)
        self.assertEqual(len(outs), 3)  # A, B, C (8 phút); D 7', E 10' sau khoá máy -> E

    def test_strict_repeats_every_5_with_running_totals(self):
        al, outs = self.outs("nghiem")
        times = [t for t, _ in outs]
        self.assertEqual(times, ["08:35:05", "08:40:05", "08:45:05",          # A
                                 "09:15:05", "09:20:05", "09:25:05",          # B (thu nhỏ)
                                 "09:43:05",                                  # C
                                 "10:01:05",                                  # D
                                 "10:38:05",                                  # E: sau khoá máy tính lại từ đầu
                                 "10:58:05"])                                 # F
        self.assertEqual([d["nth"] for _, d in outs[:3]], [1, 2, 3])
        self.assertEqual([d["today_count"] for _, d in outs], [1, 1, 1, 2, 2, 2, 3, 4, 5, 6])
        self.assertEqual(outs[2][1]["today_minutes"], 15)
        self.assertEqual(outs[3][1]["today_minutes"], 19 + 5, "A (19'55\") + B đang chạy 5'")
        self.assertTrue(all(d["every"] == 5 for _, d in outs))

    def test_lock_in_middle_no_burst(self):
        """Khoá máy 30 phút giữa lần sao nhãng: mở lại không nhắc ngay, không nhắc dồn ở mọi mức."""
        for level in ("nhe", "vua", "nghiem"):
            with self.subTest(level=level):
                al, ev = run_script(self.cfg(level))
                after = [t for t, k, d in ev if k == "out_of_vdi" and ts(DAY, "10:33") <= t < ts(DAY, "10:43")]
                self.assertLessEqual(len(after), 1)
                for t in after:
                    self.assertGreaterEqual(t - ts(DAY, "10:33"), 5 * 60)

    def test_off_disables_phone_and_fullscreen_but_not_health(self):
        cfg = self.cfg("off", fullscreen_tip_minutes=5, break_reminder_minutes=30)
        al = RealtimeAlerts(cfg)
        t, kinds = ts(DAY, "08:00"), []
        for i in range(12 * 40):  # 40 phút VDI không toàn màn hình
            t += 5
            kinds += [k for k, _ in al.update(sample(full=False), t, True)]
        for _ in range(4):  # ngồi yên 90 giây trước VDI rồi làm tiếp: dấu hiệu điện thoại
            for j in range(18):
                t += 5
                kinds += [k for k, _ in al.update(sample(idle=(j + 1) * 5), t, True)]
            t += 5
            kinds += [k for k, _ in al.update(sample(), t, True)]
        self.assertNotIn("not_fullscreen", kinds)
        self.assertNotIn("phone", kinds)
        self.assertIn("break", kinds, "nhắc nghỉ (sức khoẻ) vẫn chạy khi tắt nhắc sao nhãng")

    def phone_day(self, level):
        al = RealtimeAlerts(self.cfg(level))
        t, kinds = ts(DAY, "08:00"), []
        for _ in range(30):  # cứ ~6,5 phút lại ngồi yên 90 giây trước VDI, suốt hơn 3 giờ
            for j in range(18):
                t += 5
                kinds += [k for k, _ in al.update(sample(idle=(j + 1) * 5), t, True)]
            for _ in range(12 * 5):
                t += 5
                kinds += [k for k, _ in al.update(sample(), t, True)]
        return kinds.count("phone")

    def test_light_phone_tip_once_per_day(self):
        self.assertEqual(self.phone_day("nhe"), 1)
        self.assertGreaterEqual(self.phone_day("vua"), 3, "mức vừa: mỗi 60 phút tối đa 1 lần")

    def test_counters_reset_on_new_day_not_on_lunch(self):
        cfg = self.cfg("nhe")
        al, _ = run_script(cfg)
        self.assertTrue(al.light_done)
        al.update(sample(), ts(DAY, "12:00"), False)  # nghỉ trưa: reset() không xoá bộ đếm ngày
        self.assertTrue(al.light_done)
        al.update(sample(vdi="background"), ts("2026-10-15", "08:00"), True)
        self.assertFalse(al.light_done)
        self.assertEqual(al.today()["count"], 0)

    def test_level_change_applies_immediately(self):
        cfg = self.cfg("off")
        al = RealtimeAlerts(cfg)
        t = ts(DAY, "08:00")
        for _ in range(12 * 3):
            t += 5
            self.assertEqual(al.update(sample(vdi="background"), t, True), [])
        cfg["nudge_level"] = "nghiem"
        got = []
        for _ in range(12 * 3):
            t += 5
            got += [k for k, _ in al.update(sample(vdi="background"), t, True)]
        self.assertEqual(got, ["out_of_vdi"], "đã ra ngoài 5 phút -> nhắc ngay khi đổi sang nghiêm")


class WordingTest(unittest.TestCase):
    DATA = {"minutes": 15, "nth": 1, "proc": "chrome.exe", "vdi_state": "background", "golden": False,
            "every": 5, "today_count": 3, "today_minutes": 42, "day_nudges": 1}

    def text(self, level, tone, vdi_state="background", nth=1):
        p = dict(persona.DEFAULT, giong=tone, goi_nguoi_dung="bro", ten_sep="anh Tuấn")
        with mock.patch.object(persona.random, "choice", lambda xs: xs[0]):
            return messages.out_of_vdi(dict(self.DATA, level=level, vdi_state=vdi_state, nth=nth), "fix job", p)

    def test_distinct_lead_per_level_tone_and_case(self):
        leads = set()
        for level in ("nhe", "vua", "nghiem"):
            for tone in persona.TONES:
                for state in ("background", "minimized"):
                    t = self.text(level, tone, state)
                    self.assertIn("phút làm việc ngoài VDI", t)
                    self.assertNotIn("{", t)
                    leads.add(t.splitlines()[0])
        self.assertEqual(len(leads), 3 * 4 * 2, "mỗi mức x giọng x (thu nhỏ / app khác) có câu mở đầu riêng")

    def test_level_specific_lines(self):
        self.assertIn("chỉ nhắc một lần", self.text("nhe", "than_mat"))
        self.assertIn("lần sao nhãng thứ 3", self.text("nghiem", "vui_tuoi"))
        self.assertIn("42 phút", self.text("nghiem", "vui_tuoi"))
        self.assertIn("5 phút nữa", self.text("nghiem", "hai_huoc"))
        self.assertNotIn("lần sao nhãng thứ", self.text("vua", "than_mat"))
        self.assertIn("VDI đang thu nhỏ", self.text("vua", "than_mat", "minimized"))

    def test_strict_boss_tone_is_cold(self):
        t = self.text("nghiem", "sep_kho_tinh", nth=2)
        self.assertIn("tôi nhắc tiếp", t)
        self.assertIn("anh Tuấn", t)
        self.assertNotIn("😄", t)
        self.assertIn("tôi chỉ nhắc một lần", messages.out_of_vdi(dict(self.DATA, level="nhe"), None,
                                                                    dict(persona.DEFAULT, giong="sep_kho_tinh")))

    def test_old_data_without_level_still_works(self):
        d = {k: self.DATA[k] for k in ("minutes", "nth", "proc", "vdi_state", "golden")}
        self.assertIn("15 phút làm việc ngoài VDI", messages.out_of_vdi(d))


class FakeBot:
    def __init__(self, cfg):
        self.cfg, self.sent, self._db = cfg, [], None

    @property
    def db(self):
        if self._db is None:
            self._db = open_db(db_path(self.cfg))
        return self._db

    def send(self, text, raw=False):
        self.sent.append((text, raw))


class TrackerSendTest(TempCase):
    def setUp(self):
        super().setUp()
        self.bot = FakeBot(self.cfg)
        self.addCleanup(lambda: self.bot._db and self.bot._db.close())
        self.tr = Tracker(self.cfg, None, self.bot, notifier=None, run_housekeeping=False)
        self.tr.db, self.tr.day = self.bot.db, DAY

    def send(self, level, **d):
        data = dict(WordingTest.DATA, level=level, **d)
        self.bot.sent.clear()
        with mock.patch.object(motivation, "encouragement", return_value="Cố lên!"):
            self.tr._send_out_of_vdi(data, None)
        return self.bot.sent

    def test_encouragement_only_medium_and_strict(self):
        self.assertEqual(len(self.send("nhe", nth=1, day_nudges=2)), 1, "mức nhẹ: không kèm động viên")
        self.assertEqual(len(self.send("vua", nth=1, day_nudges=1)), 1, "lần nhắc đầu tiên trong ngày: không")
        self.assertEqual(self.send("vua", nth=1, day_nudges=2)[1], ("Cố lên!", True))
        self.assertEqual(len(self.send("nghiem", nth=1)), 1)
        self.assertEqual(len(self.send("nghiem", nth=2)), 2, "nghiêm: lần nhắc lại đầu tiên")
        self.assertEqual(len(self.send("nghiem", nth=3)), 1, "không gọi AI mỗi 5 phút")
        self.cfg["encouragement_enabled"] = False
        self.assertEqual(len(self.send("vua", nth=1, day_nudges=5)), 1, "/encourage off")

    def test_light_once_per_day_survives_restart(self):
        data = dict(WordingTest.DATA, level="nhe")
        self.tr.notifier = None
        self.tr.dispatch("out_of_vdi", data, {})
        tr2 = Tracker(self.cfg, None, self.bot, notifier=None, run_housekeeping=False)
        tr2.db, tr2.day = self.bot.db, DAY
        tr2.dispatch("out_of_vdi", data, {})
        self.assertEqual(sum("phút làm việc ngoài VDI" in t for t, _ in self.bot.sent), 1)


class NudgeCommandTest(TempCase):
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

    def ok(self):
        pid = list(self.bot.pending)[0]
        self.api.clear()
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        return self.api.sent()

    def test_view_lists_four_options(self):
        out = self.say("/nudge")[0]
        self.assertIn("Đang dùng mức nhắc khi sao nhãng: vừa", out)
        for k in ("/nudge off", "/nudge nhe", "/nudge vua", "/nudge nghiem", "/nudge mac_dinh"):
            self.assertIn(k, out)
        self.assertFalse(self.bot.pending)

    def test_view_shows_today_counters(self):
        al = RealtimeAlerts(self.cfg)
        self.state["alerts"] = al
        t = ts(DAY, "08:00")
        for _ in range(12 * 3):
            t += 5
            al.update(sample(vdi="background"), t, True)
        self.assertIn("Hôm nay: 1 lần sao nhãng", self.say("/nudge")[0])

    def test_set_persist_restore_default(self):
        self.say("/nudge nghiem")
        self.assertEqual(self.cfg["nudge_level"], "nghiem")
        self.assertEqual(get_pref(self.bot.db, "nudge_level"), "nghiem")
        self.assertTrue(any("NUDGE_LEVEL" in l for l in self.audit_lines()))
        cfg2 = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42")
        TelegramBot(cfg2, self.state, api=self.api)
        self.assertEqual(cfg2["nudge_level"], "nghiem", "khởi động lại vẫn giữ mức")
        self.say("/nhac light")
        self.assertEqual(self.cfg["nudge_level"], "nhe")
        self.say("/nudge strict")
        self.assertEqual(self.cfg["nudge_level"], "nghiem")
        self.say("/nudge tat")
        self.assertEqual(self.cfg["nudge_level"], "off")
        self.say("/nudge bật")
        self.assertEqual(self.cfg["nudge_level"], "vua", "bật lại = mức trong settings.json")
        self.say("/nudge chat")
        self.say("/nudge mac_dinh")
        self.assertEqual(self.cfg["nudge_level"], "vua")
        self.assertIsNone(get_pref(self.bot.db, "nudge_level"))
        self.assertIn("Mức nhắc là", self.say("/nudge xyz")[0])

    def test_natural_language_confirm(self):
        cases = {"nhắc nghiêm khắc hơn nhé": "nghiem", "tắt nhắc nhở sao nhãng": "off",
                 "chỉ nhắc 1 lần mỗi ngày thôi": "nhe", "nhắc nhẹ thôi": "nhe", "nhắc vừa phải thôi": "vua"}
        for text, level in cases.items():
            with self.subTest(text=text):
                self.bot.pending.clear()
                self.cfg["nudge_level"] = "off" if level == "vua" else "vua"
                out = self.say(text)
                self.assertTrue(self.bot.pending, out)
                self.assertNotEqual(self.cfg["nudge_level"], level, "chưa bấm OK thì chưa đổi")
                self.ok()
                self.assertEqual(self.cfg["nudge_level"], level)

    def test_rules_and_lookup(self):
        self.assertEqual(intent.by_rules("tắt nhắc nhở sao nhãng")[0].name, "doi_muc_nhac")
        self.assertEqual(intent.by_rules("Zalo nhóm làm mình sao nhãng")[0].name, "ghi_phan_tam")
        self.assertEqual(intent.by_rules("mức nhắc hiện tại là gì?")[0].name, "doi_muc_nhac")
        self.assertEqual(nudge_lookup("tắt nhắc nhở nhé"), "off", "\"nhé\" không phải \"nhẹ\"")
        self.assertEqual(nudge_lookup("nhe"), "nhe")
        self.assertIsNone(nudge_lookup("mức nhắc hiện tại thế nào nhé"))

    def test_status_and_help(self):
        self.say("/nudge nhe")
        status = self.say("/status")[0]
        self.assertIn("Nhắc sao nhãng: nhẹ (1 lần/ngày) (/nudge)", status)
        self.assertIn("Cảnh báo tiến độ: bật", status)
        help_text = "\n".join(self.say("/help"))
        for word in ("/nudge /nhac", "/pace /tiendo", "nhắc nghiêm khắc hơn", "mức nhẹ"):
            self.assertIn(word, help_text)


class ConfigTest(unittest.TestCase):
    def cfg(self, **kw):
        c = dict(DEFAULTS)
        c.update(kw)
        return validate(c)

    def test_defaults(self):
        c = self.cfg()
        self.assertEqual((c["nudge_level"], c["nudge_out_of_vdi_minutes"], c["nudge_light_minutes"],
                          c["nudge_strict_minutes"]), ("vua", 15, 15, 5))

    def test_aliases(self):
        for raw, want in (("off", "off"), ("tat", "off"), ("light", "nhe"), ("nhẹ", "nhe"), ("normal", "vua"),
                          ("medium", "vua"), ("STRICT", "nghiem"), ("chat", "nghiem"), ("nghiêm", "nghiem")):
            self.assertEqual(self.cfg(nudge_level=raw)["nudge_level"], want, raw)

    def test_bad_values(self):
        for bad in ({"nudge_level": "xyz"}, {"nudge_level": 3}, {"nudge_light_minutes": -1},
                    {"nudge_strict_minutes": 2.5}, {"nudge_strict_minutes": True}):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    self.cfg(**bad)


if __name__ == "__main__":
    unittest.main()
