"""Cảnh báo tức thời: chạy từng mẫu 5 giây qua RealtimeAlerts."""
import tempfile
import unittest

from focus.alerts import RealtimeAlerts
from tests.helpers import make_cfg, sample


class AlertsTest(unittest.TestCase):
    def setUp(self):
        # Các test ngoài VDI dưới đây kiểm tra logic nhắc lặp (chống nhắc dồn): dùng mức "nghiem" với chu kỳ 10 phút
        # (nhắc sau 10 phút, còn ở ngoài thì 10 phút nhắc lại). Từng mức nhắc: tests/test_nudge_levels.py.
        self.cfg = make_cfg(tempfile.mkdtemp(), nudge_level="nghiem", nudge_strict_minutes=10)
        self.al = RealtimeAlerts(self.cfg)
        self.t = 1_000_000.0
        self.events = []

    def run_for(self, minutes, work=True, golden=False, **kw):
        idle_grow = kw.pop("idle_grow", False)
        idle0 = kw.pop("idle_start", 0)
        out = []
        for i in range(int(minutes * 12)):
            self.t += 5
            s = sample(**kw)
            if idle_grow:
                s["idle"] = idle0 + (i + 1) * 5
            ev = self.al.update(s, self.t, work, golden)
            out += [(round((self.t - self.t0) / 60, 2), k, d) for k, d in ev]
        self.events += out
        return out

    def kinds(self, evs=None):
        return [k for _, k, _ in (self.events if evs is None else evs)]

    def start(self):
        self.t0 = self.t

    # --- ngoài VDI ---------------------------------------------------
    def test_out_of_vdi_10_minutes_then_every_10(self):
        self.start()
        ev = self.run_for(31, vdi="minimized", proc="chrome.exe")
        outs = [(m, d["nth"]) for m, k, d in ev if k == "out_of_vdi"]
        self.assertEqual([n for _, n in outs], [1, 2, 3])
        self.assertAlmostEqual(outs[0][0], 10, delta=0.1)
        self.assertAlmostEqual(outs[1][0], 20, delta=0.1)
        self.assertEqual(ev[0][2]["vdi_state"], "minimized")

    def test_side_by_side_and_background_also_alert(self):
        self.start()
        self.assertIn("out_of_vdi", self.kinds(self.run_for(10.1, vdi="background", proc="zalo.exe")))

    def test_short_trips_do_not_alert(self):
        self.start()
        for _ in range(6):
            self.run_for(8, vdi="background")
            self.run_for(1)
        self.assertNotIn("out_of_vdi", self.kinds())

    def test_sitting_idle_outside_vdi_does_not_reset_timer(self):
        self.start()
        self.run_for(6, vdi="background")
        self.run_for(2, vdi="background", idle_grow=True)
        ev = self.run_for(3, vdi="background")
        self.assertIn("out_of_vdi", self.kinds(ev))

    def test_golden_hour_is_stricter(self):
        self.start()
        ev = self.run_for(5.1, golden=True, vdi="background")
        self.assertEqual(self.kinds(ev), ["out_of_vdi"])
        self.assertTrue(ev[0][2]["golden"])

    def test_no_alert_outside_work_time(self):
        self.start()
        self.run_for(60, work=False, vdi="minimized")
        self.run_for(60, work=False, vdi="foreground", idle_grow=True)
        self.assertEqual(self.events, [])

    def test_timer_restarts_after_lunch(self):
        self.start()
        self.run_for(8, vdi="background")
        self.run_for(75, work=False, vdi="background")  # nghỉ trưa
        ev = self.run_for(9, vdi="background")
        self.assertNotIn("out_of_vdi", self.kinds(ev))
        self.assertIn("out_of_vdi", self.kinds(self.run_for(1.1, vdi="background")))

    def test_locked_is_not_out_of_vdi(self):
        self.start()
        self.run_for(14, locked=True, idle_grow=True)
        self.assertNotIn("out_of_vdi", self.kinds())

    # --- rời máy -------------------------------------------------------
    def test_away_15_minutes_and_back(self):
        self.start()
        self.run_for(10)
        ev = self.run_for(20, idle_grow=True)
        aw = [(m, d) for m, k, d in ev if k == "away"]
        self.assertEqual(len(aw), 1)
        self.assertAlmostEqual(aw[0][0], 25, delta=0.1)
        self.assertTrue(aw[0][1]["in_vdi"])
        back = self.run_for(1)
        self.assertEqual(self.kinds(back)[:1], ["back"])
        self.assertGreaterEqual(back[0][2]["minutes"], 20)

    def test_lock_screen_away(self):
        self.start()
        self.run_for(5)
        ev = self.run_for(16, locked=True, idle_grow=True)
        self.assertEqual([d["locked"] for _, k, d in ev if k == "away"], [True])

    def test_away_counts_from_work_start_not_before(self):
        self.start()
        self.run_for(30, work=False, idle_grow=True)  # 07:30–08:00 chưa tới giờ làm
        ev = self.run_for(14, idle_grow=True, idle_start=1800)
        self.assertNotIn("away", self.kinds(ev))
        self.assertIn("away", self.kinds(self.run_for(1.1, idle_grow=True, idle_start=1800 + 14 * 60)))

    def test_short_toilet_trip_no_alert(self):
        self.start()
        self.run_for(10)
        self.run_for(12, idle_grow=True)
        self.run_for(5)
        self.assertNotIn("away", self.kinds())
        self.assertNotIn("back", self.kinds())

    def test_no_false_back_when_leaving_work_time(self):
        # Đang vắng mà tới giờ nghỉ trưa / hết giờ: không được báo "đã quay lại".
        self.start()
        self.run_for(16, idle_grow=True)
        ev = self.run_for(1, work=False, idle_grow=True, idle_start=16 * 60)
        self.assertNotIn("back", self.kinds(ev))
        ev = self.run_for(60, work=False, locked=True, idle_grow=True, idle_start=17 * 60)
        self.assertEqual(ev, [])

    def test_transitions_logged_once_not_per_sample(self):
        self.start()
        with self.assertLogs("focus", "DEBUG") as cm:
            self.run_for(16, idle_grow=True)
            self.run_for(30, work=False, idle_grow=True, idle_start=16 * 60)
        self.assertEqual(sum("ra khỏi giờ làm" in l for l in cm.output), 1)
        self.assertEqual(sum("Cảnh báo phát: away" in l for l in cm.output), 1)
        self.assertLess(len(cm.output), 10)

    def test_back_only_when_active_again(self):
        self.start()
        self.run_for(16, locked=True, idle_grow=True)
        ev = self.run_for(5, locked=True, idle_grow=True, idle_start=16 * 60)
        self.assertNotIn("back", self.kinds(ev))
        self.assertEqual(self.kinds(self.run_for(0.1))[:1], ["back"])

    def test_no_nudge_burst_after_lock(self):
        # Ngoài VDI 8 phút, khoá máy 60 phút, mở lại vẫn ngoài VDI: không được nhắc dồn 6 lần.
        self.start()
        self.run_for(8, vdi="background")
        self.run_for(60, locked=True, idle_grow=True)
        ev = self.run_for(9.9, vdi="background")
        self.assertNotIn("out_of_vdi", self.kinds(ev))
        ev = self.run_for(5, vdi="background")
        self.assertEqual([d["nth"] for _, k, d in ev if k == "out_of_vdi"], [1])

    def test_no_nudge_burst_after_short_idle(self):
        # Ngồi yên ngắn (< ngưỡng rời máy) ngoài VDI: đồng hồ vẫn chạy nhưng quay lại chỉ nhắc 1 lần.
        self.cfg["away_threshold_seconds"] = 3600
        self.start()
        self.run_for(9, vdi="background")
        self.run_for(30, vdi="background", idle_grow=True)
        ev = self.run_for(1, vdi="background")
        self.assertEqual(self.kinds(ev).count("out_of_vdi"), 1)
        ev = self.run_for(9, vdi="background")
        self.assertNotIn("out_of_vdi", self.kinds(ev))
        self.assertIn("out_of_vdi", self.kinds(self.run_for(1, vdi="background")))

    # --- nhắc nghỉ -----------------------------------------------------
    def test_break_at_60_then_120(self):
        self.start()
        ev = self.run_for(125)
        br = [(m, d["minutes"]) for m, k, d in ev if k == "break"]
        self.assertEqual([x[1] for x in br], [60, 120])

    def test_break_resets_after_real_break(self):
        self.start()
        self.run_for(50)
        self.run_for(5, vdi="background")  # nghỉ 5 phút (> 2 phút)
        ev = self.run_for(55)
        self.assertNotIn("break", self.kinds(ev))
        self.assertIn("break", self.kinds(self.run_for(6)))

    def test_short_switch_does_not_reset_break(self):
        self.start()
        self.run_for(40)
        self.run_for(1, vdi="background")
        ev = self.run_for(20)
        self.assertIn("break", self.kinds(ev))

    # --- điện thoại ----------------------------------------------------
    def test_phone_pattern(self):
        self.start()
        for _ in range(3):
            self.run_for(5)
            self.run_for(2, idle_grow=True)
        ev = self.run_for(0.2)  # lần chạm đầu + mẫu sau có chạm tiếp (xác nhận đã quay lại)
        self.assertEqual(self.kinds(ev), ["phone"])
        self.assertEqual(ev[0][2]["count"], 3)
        for _ in range(3):  # cooldown 60 phút
            self.run_for(5)
            self.run_for(2, idle_grow=True)
        self.run_for(0.1)
        self.assertEqual(self.kinds().count("phone"), 1)

    def test_two_short_idles_no_phone_alert(self):
        self.start()
        for _ in range(2):
            self.run_for(5)
            self.run_for(2, idle_grow=True)
        self.run_for(1)
        self.assertNotIn("phone", self.kinds())

    def test_reading_outside_vdi_not_phone(self):
        self.start()
        for _ in range(4):
            self.run_for(1, vdi="background")
            self.run_for(2, vdi="background", idle_grow=True)
        self.run_for(0.2)
        self.assertNotIn("phone", self.kinds())

    # --- chạm lẻ khi đang vắng (đi ngang bàn đụng chuột, chuột Bluetooth tự gửi tín hiệu) --------------
    def feed(self, idles, **kw):
        """Mỗi số trong idles là 1 mẫu 5 giây với idle đó."""
        out = []
        for idle in idles:
            self.t += 5
            out += [(round((self.t - self.t0) / 60, 2), k, d)
                    for k, d in self.al.update(sample(idle=idle, **kw), self.t, True, False)]
        self.events += out
        return out

    @staticmethod
    def grow(first, last):
        return range(first, last + 1, 5)

    def test_real_trace_single_touch_mid_absence_no_phone(self):
        # Log thật 15/10: 08:53 ngồi yên 115 giây trước VDI, liếc Telegram, đi pha cà phê 8 phút; 09:00:30 có đúng
        # 1 lần chạm, 09:04 mới quay lại thật, rồi thu nhỏ VDI cầm điện thoại. Bản cũ tính 3 lần ngồi yên ngắn
        # (115 + 287 + 214 giây) và báo 📱 lúc 09:04:09; thật ra chỉ có 1 lần ngồi yên ngắn và 1 lần vắng 8 phút.
        self.start()
        self.feed([1] * 36)
        self.feed(self.grow(5, 115))
        self.feed([1, 1], vdi="minimized", proc="telegram.exe")
        self.feed(self.grow(5, 285))
        self.feed(self.grow(2, 212))           # 1 lần chạm lúc 09:00:30 rồi ngồi yên tiếp
        self.feed([1] * 6)                     # 09:04:09 quay lại thật
        self.feed([1], vdi="minimized", proc="telegram.exe")
        self.feed(self.grow(5, 475), vdi="minimized", proc="telegram.exe")
        self.feed([1] * 12)
        self.assertEqual(self.kinds(), [])
        self.assertEqual(len(self.al.short_idles), 1)

    def test_single_touch_does_not_reset_away(self):
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 600))           # vắng 10 phút
        ev = self.feed(self.grow(3, 60))       # chạm lẻ: chưa phải quay lại, không báo "back"
        self.assertEqual(ev, [])
        ev = self.feed(self.grow(65, 400))
        aw = [(m, d) for m, k, d in ev if k == "away"]
        self.assertEqual(len(aw), 1, "vẫn tính rời máy từ lúc bắt đầu vắng, không đếm lại từ lần chạm lẻ")
        self.assertAlmostEqual(aw[0][0], 20, delta=0.1)
        self.assertGreaterEqual(aw[0][1]["minutes"], 15)
        ev = self.feed([1, 1])
        self.assertEqual(self.kinds(ev), ["back"])

    def test_touch_while_already_alerted_away_sends_no_back(self):
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 16 * 60))
        self.assertEqual(self.kinds(), ["away"])
        self.feed(self.grow(2, 90))
        self.assertNotIn("back", self.kinds())
        self.assertEqual(self.kinds(self.feed([1, 1])), ["back"])

    def test_real_return_counts_as_short_idle(self):
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 120))
        self.feed([1])
        self.assertEqual(len(self.al.short_idles), 0, "mới chạm 1 lần: chờ mẫu sau")
        self.feed([1])
        self.assertEqual(len(self.al.short_idles), 1)

    def test_second_touch_before_idle_again_is_return(self):
        # Chạm, đọc màn hình 40 giây rồi mới gõ tiếp (chưa kịp ngồi yên lại >= 60 giây): đúng là quay lại.
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 120))
        self.feed(self.grow(1, 41))
        self.feed([1])
        self.assertEqual(len(self.al.short_idles), 1)

    def test_touch_merges_two_short_idles_into_one(self):
        # 2 phút + chạm lẻ + 2 phút = 1 lần ngồi yên 4 phút (vẫn dưới 5 phút), không phải 2 lần.
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 120))
        self.feed(self.grow(2, 117))
        self.feed([1, 1])
        self.assertEqual(len(self.al.short_idles), 1)

    def test_touch_then_lock_is_not_short_idle(self):
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 120))
        self.feed([1])
        self.feed(self.grow(5, 60), locked=True)
        self.feed([1] * 6)
        self.assertEqual(len(self.al.short_idles), 0)

    def test_real_phone_pattern_with_touches_still_alerts(self):
        # Cầm điện thoại thật: mỗi lần ngồi yên 2 phút rồi làm tiếp. Vẫn báo dù có 1 lần chạm lẻ ở giữa.
        self.start()
        self.run_for(5)
        self.feed(self.grow(5, 60))
        self.feed(self.grow(2, 62))            # chạm lẻ giữa lần cầm điện thoại thứ nhất
        self.feed([1] * 12)
        for _ in range(2):
            self.feed(self.grow(5, 120))
            self.feed([1] * 12)
        self.assertEqual(self.kinds(), ["phone"])

    # --- toàn màn hình -------------------------------------------------
    def test_not_fullscreen_once(self):
        self.start()
        ev = self.run_for(40, full=False)
        self.assertEqual(self.kinds(ev).count("not_fullscreen"), 1)
        self.al.reset()
        self.run_for(40, full=False)
        self.assertEqual(self.kinds().count("not_fullscreen"), 1)

    def test_not_fullscreen_counts_only_vdi_in_front(self):
        # Log thật 15/10: VDI vừa vừa ở trước 20 giây rồi nằm sau / thu nhỏ 15 phút: không được báo "15 phút".
        self.start()
        self.run_for(0.4, full=False)
        self.run_for(16, vdi="background", proc="claude.exe")
        self.run_for(4, vdi="minimized", proc="claude.exe")
        self.assertNotIn("not_fullscreen", self.kinds())
        ev = self.run_for(15, full=False)  # cộng dồn đủ 15 phút làm trong VDI vừa vừa
        tips = [(m, d) for m, k, d in ev if k == "not_fullscreen"]
        self.assertEqual(len(tips), 1)
        self.assertEqual(tips[0][1]["minutes"], 15)

    def test_maximize_resets_windowed_time(self):
        self.start()
        self.run_for(10, full=False)
        self.run_for(1, full=True)
        self.run_for(10, full=False)
        self.assertNotIn("not_fullscreen", self.kinds())

    def test_fullscreen_no_tip(self):
        self.start()
        self.run_for(40, full=True)
        self.assertNotIn("not_fullscreen", self.kinds())

    def test_disable_with_zero(self):
        for key in ("nudge_out_of_vdi_minutes", "nudge_strict_minutes", "away_alert_minutes", "break_reminder_minutes",
                    "water_reminder_minutes",
                    "phone_pattern_count", "fullscreen_tip_minutes"):
            self.cfg[key] = 0
        self.cfg["golden_nudge_minutes"] = 0
        self.start()
        self.run_for(70, vdi="background")
        self.run_for(70, full=False)
        self.run_for(30, idle_grow=True)
        self.assertNotIn("out_of_vdi", self.kinds())
        self.assertEqual([k for k in self.kinds() if k != "back"], [])
