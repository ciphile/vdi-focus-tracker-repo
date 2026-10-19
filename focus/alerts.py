"""Cảnh báo tức thời, tính từ từng mẫu. Lớp thuần: không gửi gì, chỉ trả về danh sách sự kiện.

Sự kiện (kind, data):
- ("out_of_vdi", {minutes, nth, proc, vdi_state, golden, level, every, day_nudges, today_count, today_minutes})
      sao nhãng: dùng chuột/phím ngoài VDI (app khác ở trước, hoặc VDI thu nhỏ) quá N phút, theo mức nhắc
      cfg["nudge_level"] (đổi bằng /nudge, có hiệu lực ngay):
        off     không nhắc sao nhãng (cả "phone" và "not_fullscreen")
        nhe     1 lần/ngày: lần sao nhãng đầu tiên >= nudge_light_minutes; sau đó im cả ngày; "phone" tối đa 1 lần/ngày
        vua     mỗi lần sao nhãng >= nudge_out_of_vdi_minutes (giờ vàng: golden_nudge_minutes) nhắc đúng 1 lần
        nghiem  sau nudge_strict_minutes (giờ vàng: lấy ngưỡng nhỏ hơn), còn ở ngoài thì nhắc lại mỗi chừng đó phút
      Một "lần sao nhãng" (episode) kết thúc khi quay lại VDI, khoá máy / rời máy hẳn, tạm dừng, máy ngủ, hết giờ làm.
      today_count / today_minutes: số lần sao nhãng (>= 1 phút) và tổng phút sao nhãng hôm nay (tính cả lần đang diễn ra).
- ("away", {minutes, since, locked, in_vdi})   rời máy (không chạm phím/chuột, khoá máy) quá N phút
- ("back", {minutes})                          quay lại (chạm phím/chuột) sau khi đã bị cảnh báo rời máy
- ("break", {minutes, nth, water})             tập trung trong VDI liên tục N phút; chưa nghỉ thì nhắc lại
                                               (break_reminder_enabled). water=True: gộp luôn nhắc uống nước
- ("water", {minutes})                         nhắc uống nước mỗi water_reminder_minutes phút giờ làm; đang khoá máy /
                                               ngồi yên thì chờ tới lúc quay lại; sắp tới giờ nhắc nghỉ (<= 1 phút)
                                               thì chờ để gộp vào tin nhắc nghỉ
- ("phone", {count, window})                   nhiều lần ngồi yên 1–5 phút trước VDI: dấu hiệu cầm điện thoại/iPad
- ("not_fullscreen", {minutes})                làm trong VDI nhưng VDI không toàn màn hình một lúc lâu
- ("vdi_closed", {since, last_input, minutes, locked})
                                               cửa sổ VDI đã thấy hôm nay rồi biến mất >= VDI_CLOSED_GRACE giây
                                               (Citrix tự ngắt khi không dùng 10–20 phút, hoặc bị đóng). 1 lần mỗi
                                               lần mất; mất lúc nghỉ trưa thì báo khi vào giờ làm lại. cfg vdi_closed_alert

Chỉ cảnh báo trong giờ làm (trừ nghỉ trưa, ngày nghỉ). Ra khỏi giờ làm thì mọi đồng hồ về 0.
Quay lại sau một quãng ngồi yên (>= idle_threshold_seconds) = có chạm phím/chuột ở 2 mẫu liền nhau. Chạm lẻ rồi lại
ngồi yên (đi ngang bàn đụng chuột, chuột/bàn phím Bluetooth tự gửi tín hiệu) không phải quay lại: quãng ngồi yên / rời
máy vẫn tính tiếp từ lúc bắt đầu ("away", "back", "phone", "water").
"away", "back", "break", "water", "vdi_closed" (sức khoẻ, có mặt) không phụ thuộc mức nhắc.
"""
import datetime as dt
from collections import deque

from .logs import get_logger

log = get_logger()

PHONE_WINDOW_MINUTES = 30
PHONE_COOLDOWN_MINUTES = 60
EPISODE_MIN_SECONDS = 60     # ra ngoài VDI dưới 1 phút (liếc Zalo) không tính là một lần sao nhãng
MERGE_SECONDS = 60           # nhắc uống nước và nhắc nghỉ tới hạn cách nhau <= chừng này: gộp một tin
VDI_CLOSED_GRACE = 60        # cửa sổ VDI mất ít hơn chừng này (đang kết nối lại, đổi toàn màn hình) thì bỏ qua


class RealtimeAlerts:
    def __init__(self, cfg):
        self.cfg = cfg
        self.in_work = None       # để chỉ ghi log lúc vào / ra giờ làm, không ghi mỗi mẫu
        self.out_since = None
        # Cửa sổ VDI có / mất: theo dõi cả lúc nghỉ trưa, ngoài giờ (không xoá khi reset()), xoá khi sang ngày.
        self.vdi_day = None
        self.vdi_seen_at = None       # lần cuối thấy cửa sổ VDI hôm nay
        self.vdi_gone_since = None    # cửa sổ VDI mất từ lúc này
        self.vdi_closed_alerted = False
        self.last_vdi_input = None    # lần cuối chạm phím/chuột khi VDI ở trước
        self.date = None          # ngày của các bộ đếm trong ngày (không xoá khi reset())
        self._new_day(None)
        self.reset()

    def _new_day(self, date):
        self.date = date
        self.day_episodes = 0     # số lần sao nhãng >= 1 phút hôm nay (đã xong + đang diễn ra)
        self.day_lost = 0.0       # tổng giây sao nhãng của các lần đã xong
        self.day_nudges = 0       # số lần đã nhắc sao nhãng hôm nay
        self.light_done = False   # mức nhẹ: đã nhắc lần trong ngày
        self.phone_today = 0
        self.phone_alert_at = None    # chờ giữa 2 lần nhắc điện thoại: tính lại từ đầu mỗi ngày
        self.windowed_alerted = False  # gợi ý toàn màn hình: 1 lần MỖI NGÀY (tracker chạy qua đêm vẫn nhắc ngày mới)

    def day_counters(self):
        """Bộ đếm trong ngày để lưu vào DB: tắt tracker giữa ngày rồi bật lại vẫn đếm tiếp, không về 1.
        Lần sao nhãng đang diễn ra (đã đủ 1 phút) được cộng luôn vào tổng phút. None khi chưa vào ngày nào."""
        if self.date is None:
            return None
        ongoing = (self.out_last or 0) - self.out_since if self.out_since and self.out_counted else 0
        return {"date": self.date.isoformat(), "episodes": self.day_episodes, "lost": int(self.day_lost + ongoing),
                "nudges": self.day_nudges, "light_done": self.light_done, "phone": self.phone_today,
                "windowed": self.windowed_alerted}

    def restore_day(self, data, today):
        """Nạp lại bộ đếm đã lưu nếu cùng ngày today (datetime.date). Dữ liệu ngày khác / hỏng thì bỏ qua.
        Lần sao nhãng đang dở lúc tắt tracker coi như đã xong (số lần, số phút đã nằm trong bộ đếm)."""
        try:
            if not data or dt.date.fromisoformat(data["date"]) != today:
                return False
            self._new_day(today)
            self.day_episodes = max(0, int(data["episodes"]))
            self.day_lost = float(max(0, int(data["lost"])))
            self.day_nudges = max(0, int(data["nudges"]))
            self.light_done = bool(data["light_done"])
            self.phone_today = max(0, int(data.get("phone", 0)))
            self.windowed_alerted = bool(data.get("windowed", False))
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Bộ đếm sao nhãng đã lưu không đọc được, đếm lại từ đầu: %s", e)
            self._new_day(None)
            return False
        log.info("Nạp lại bộ đếm sao nhãng hôm nay: %d lần, %d phút, đã nhắc %d lần.",
                 self.day_episodes, self.day_lost // 60, self.day_nudges)
        return True

    def _end_episode(self, why):
        """Kết thúc lần sao nhãng đang diễn ra: cộng vào tổng trong ngày, xoá đồng hồ."""
        if self.out_since is not None:
            dur = max(0.0, (self.out_last or self.out_since) - self.out_since)
            if self.out_counted:
                self.day_lost += dur
            log.debug("Cảnh báo: hết lần sao nhãng (%s), %d giây, đã nhắc %d lần.", why, dur, self.nudges)
        self.out_since, self.out_last, self.out_counted, self.nudges, self.nudge_at = None, None, False, 0, None

    def reset(self, forget_vdi=False):
        """Gọi khi tạm dừng (/pause), khi máy vừa thức dậy, hoặc khi ra khỏi giờ làm.
        Bộ đếm trong ngày (số lần sao nhãng, mức nhẹ đã nhắc chưa) giữ nguyên tới khi sang ngày.
        forget_vdi=True (máy ngủ, /pause, nghỉ phép): VDI mất trong lúc đó là chuyện bình thường, không báo "VDI đã đóng".
        Nghỉ trưa / hết giờ thì không quên: VDI mất lúc trưa mà vào giờ làm vẫn chưa mở lại thì báo."""
        if forget_vdi:
            self.vdi_seen_at, self.vdi_gone_since, self.vdi_closed_alerted = None, None, False
        self._end_episode("reset")
        self.away_since = None
        self.away_alerted = False
        self.focus_since = None
        self.last_vdi = None
        self.breaks = 0
        self.since_reset = None   # lần cập nhật đầu tiên sau reset: không tính rời máy sớm hơn mốc này
        self.prev = None          # mẫu trước (để nhận ra lúc vừa quay lại sau một quãng ngồi yên)
        self.prev_ts = None
        self.resume = None        # lần chạm đầu sau quãng ngồi yên, chờ mẫu sau xác nhận: (lúc chạm, lúc bắt đầu
                                  # ngồi yên, VDI ở trước lúc ngồi yên)
        self.idle_start = None    # quãng ngồi yên vẫn tiếp diễn qua lần chạm lẻ: tính từ lúc này
        self.short_idles = deque()
        self.windowed_secs = 0.0  # giây đang gõ trong VDI mà VDI không toàn màn hình (phóng to VDI thì về 0)
        self.windowed_at = None   # mẫu "VDI vừa vừa đang dùng" trước đó (cộng khoảng giữa 2 mẫu liền nhau)
        self.water_since = None   # mốc tính nhắc uống nước (vào giờ làm / lần nhắc trước); trưa, /pause: tính lại

    def _track_vdi_window(self, s, now):
        date = dt.date.fromtimestamp(now)
        if date != self.vdi_day:  # sáng mới chưa mở VDI không phải "VDI đã đóng"
            self.vdi_day, self.vdi_seen_at, self.vdi_gone_since = date, None, None
            self.vdi_closed_alerted, self.last_vdi_input = False, None
        if s["vdi_state"] != "absent":
            if self.vdi_gone_since is not None:
                log.info("Cảnh báo: cửa sổ VDI có lại (mất %d giây).", now - self.vdi_gone_since)
            self.vdi_seen_at, self.vdi_gone_since, self.vdi_closed_alerted = now, None, False
            if s["vdi_state"] == "foreground" and not s["locked"] and s["idle"] < self.cfg["idle_threshold_seconds"]:
                self.last_vdi_input = now - s["idle"]
        elif self.vdi_seen_at is not None and self.vdi_gone_since is None:
            self.vdi_gone_since = self.vdi_seen_at  # mất trong khoảng giữa 2 mẫu: tính từ lần cuối còn thấy
            log.info("Cảnh báo: cửa sổ VDI biến mất (lần cuối thấy %s).",
                     dt.datetime.fromtimestamp(self.vdi_seen_at).strftime("%H:%M:%S"))

    def update(self, s, now, work_time, golden=False):
        """s: mẫu từ probe. now: epoch giây. work_time: schedule.is_work_time. golden: đang trong giờ vàng."""
        cfg = self.cfg
        events = []
        self._track_vdi_window(s, now)
        if not work_time:
            # Vào nghỉ trưa / hết giờ mà người vẫn chưa về: chỉ xoá đồng hồ, không báo "đã quay lại".
            if self.in_work:
                log.debug("Cảnh báo: ra khỏi giờ làm (trưa/hết giờ), xoá đồng hồ%s.",
                          ", đang vắng" if self.away_since else "")
            self.in_work = False
            self.reset()
            return events
        if not self.in_work:
            log.debug("Cảnh báo: vào giờ làm, bắt đầu theo dõi.")
            self.in_work = True
        if self.since_reset is None:
            self.since_reset = now

        date = dt.date.fromtimestamp(now)
        if date != self.date:
            if self.date is not None:
                log.debug("Cảnh báo: sang ngày %s, xoá bộ đếm sao nhãng trong ngày.", date)
            self._end_episode("sang ngày")
            self._new_day(date)
        level = cfg.get("nudge_level", "vua")

        active = not s["locked"] and s["idle"] < cfg["idle_threshold_seconds"]
        in_vdi = not s["locked"] and (s["vdi_state"] == "foreground" or s["fg_proc"] in cfg["extra_focus_processes"])

        returned = self._track_return(s, now, active)
        pending = self.resume is not None  # vừa chạm lần đầu sau quãng ngồi yên, chưa biết có phải quay lại không

        # 1. Sao nhãng (ngoài VDI: app khác ở trước, VDI thu nhỏ / nằm sau). Quay lại VDI mới xoá đồng hồ; ngồi yên
        #    một lúc ngoài VDI thì đồng hồ vẫn chạy, nhưng khoá máy / rời máy hẳn (>= away_threshold) là không ngồi
        #    máy: hết lần sao nhãng này.
        if in_vdi or (not active and (s["locked"] or s["idle"] >= cfg["away_threshold_seconds"])):
            if self.out_since is not None:
                self._end_episode("về VDI" if in_vdi else "khoá máy / rời máy")
        elif active:
            if self.out_since is None:
                self.out_since = now
            self.out_last = now
            if not self.out_counted and now - self.out_since >= EPISODE_MIN_SECONDS:
                self.out_counted = True
                self.day_episodes += 1
        limit = self._nudge_limit(level, golden) * 60
        # Lần nhắc kế tính từ lần nhắc trước (không đuổi theo số lần): ngồi yên xong quay lại chỉ nhắc 1 lần.
        due = (self.nudge_at if self.nudge_at is not None else self.out_since or 0) + limit
        allowed = (level == "nghiem" or (level == "vua" and not self.nudges)
                   or (level == "nhe" and not self.light_done and not self.nudges))
        if limit and allowed and active and self.out_since is not None and now >= due:
            self.nudges += 1
            self.day_nudges += 1
            self.nudge_at = now
            if level == "nhe":
                self.light_done = True
                log.info("Cảnh báo: mức nhẹ đã nhắc lần trong ngày, hôm nay không nhắc sao nhãng nữa.")
            lost = self.day_lost + (now - self.out_since if self.out_counted else 0)
            events.append(("out_of_vdi", {"minutes": int((now - self.out_since) // 60), "nth": self.nudges,
                                          "proc": s["fg_proc"], "vdi_state": s["vdi_state"], "golden": golden,
                                          "level": level, "every": limit // 60, "day_nudges": self.day_nudges,
                                          "today_count": max(self.day_episodes, 1),
                                          "today_minutes": int(lost // 60)}))

        # 2. Rời máy. Tính từ lần chạm phím/chuột cuối, không sớm hơn lúc vào giờ làm / máy thức dậy. Chạm lẻ không
        #    phải quay lại: đồng hồ rời máy chạy tiếp, chưa báo "back".
        if active and not pending:
            if self.away_alerted and self.away_since:
                events.append(("back", {"minutes": int((now - self.away_since) // 60)}))
            self.away_since, self.away_alerted = None, False
        elif not active and self.away_since is None:
            self.away_since = max(now - s["idle"], self.since_reset)
            log.debug("Cảnh báo: bắt đầu tính rời máy (%s).", "khoá máy" if s["locked"] else "ngồi yên")
        limit = cfg["away_alert_minutes"] * 60
        if (limit and self.away_since is not None and not self.away_alerted and not pending
                and now - self.away_since >= limit):
            self.away_alerted = True
            events.append(("away", {"minutes": int((now - self.away_since) // 60), "since": self.away_since,
                                    "locked": bool(s["locked"]), "in_vdi": s["vdi_state"] == "foreground"}))

        # 2b. Cửa sổ VDI biến mất (Citrix tự ngắt khi không dùng lâu, hoặc bị đóng): báo 1 lần mỗi lần mất.
        # Chỉ báo khi hôm nay đã thật sự làm trong VDI: mở VDI từ sớm rồi chưa đụng tới, Citrix tự ngắt lúc 8h
        # thì chưa phải "bỏ dở công việc" (log thật 16/10: mở VDI 07:45, báo đóng lúc 08:03 dù chưa làm).
        if (cfg.get("vdi_closed_alert", True) and self.vdi_gone_since is not None and not self.vdi_closed_alerted
                and self.last_vdi_input is not None and now - self.vdi_gone_since >= VDI_CLOSED_GRACE):
            self.vdi_closed_alerted = True
            ref = self.last_vdi_input or self.vdi_gone_since
            events.append(("vdi_closed", {"since": self.vdi_gone_since, "last_input": self.last_vdi_input,
                                          "minutes": int((now - ref) // 60), "locked": bool(s["locked"])}))

        # 3. Nhắc nghỉ sau khối tập trung dài + nhắc uống nước (sức khoẻ: không phụ thuộc mức nhắc sao nhãng).
        brk = cfg["break_reminder_minutes"] * 60 if cfg.get("break_reminder_enabled", True) else 0
        water = cfg.get("water_reminder_minutes", 0) * 60 if cfg.get("water_reminder_enabled", True) else 0
        if self.water_since is None:
            self.water_since = now
        water_due = bool(water) and active and not pending and now - self.water_since >= water  # chạm lẻ: chờ quay lại thật
        break_event = None
        if active and in_vdi:
            if self.last_vdi is None or now - self.last_vdi > cfg["focus_gap_seconds"]:
                self.focus_since, self.breaks = now, 0
            self.last_vdi = now
            if brk and now - self.focus_since >= brk * (self.breaks + 1):
                self.breaks += 1
                # Nước sắp tới hạn (<= 1 phút) thì gộp luôn vào tin nhắc nghỉ.
                merge = bool(water) and now + MERGE_SECONDS - self.water_since >= water
                break_event = ("break", {"minutes": int((now - self.focus_since) // 60), "nth": self.breaks,
                                         "water": merge})
                events.append(break_event)
                if merge:
                    self.water_since, water_due = now, False
                    log.debug("Cảnh báo: gộp nhắc uống nước vào nhắc nghỉ.")
        if water_due:
            soon_break = (brk and in_vdi and self.focus_since is not None
                          and now + MERGE_SECONDS - self.focus_since >= brk * (self.breaks + 1))
            if soon_break:
                log.debug("Cảnh báo: nhắc nghỉ sắp tới, chờ gộp nhắc uống nước.")
            else:
                events.append(("water", {"minutes": int((now - self.water_since) // 60)}))
                self.water_since = now

        # 4. Điện thoại/iPad: VDI vẫn ở trước nhưng ngồi yên 1–5 phút rồi mới làm tiếp, lặp nhiều lần. Quãng ngồi yên
        #    tính cả qua lần chạm lẻ (vắng 8 phút có 1 lần chạm ở giữa là vắng 8 phút, không phải 2 lần cầm điện thoại).
        if returned:
            touched, start, vdi_front = returned
            if vdi_front and cfg["idle_threshold_seconds"] <= touched - start < cfg["away_threshold_seconds"]:
                self.short_idles.append(now)
        while self.short_idles and now - self.short_idles[0] > PHONE_WINDOW_MINUTES * 60:
            self.short_idles.popleft()
        need = cfg["phone_pattern_count"] if level != "off" and not (level == "nhe" and self.phone_today) else 0
        if (need and len(self.short_idles) >= need
                and (self.phone_alert_at is None or now - self.phone_alert_at >= PHONE_COOLDOWN_MINUTES * 60)):
            self.phone_alert_at = now
            self.phone_today += 1
            events.append(("phone", {"count": len(self.short_idles), "window": PHONE_WINDOW_MINUTES}))
            self.short_idles.clear()

        # 5. VDI không toàn màn hình (làm song song với app khác dễ bị kéo đi). Nhắc 1 lần/ngày. Chỉ cộng lúc VDI ở
        #    trước và đang dùng: VDI nằm sau / thu nhỏ thì đồng hồ dừng (đã tính ở phần sao nhãng), phóng to thì về 0.
        if active and s["vdi_state"] == "foreground" and s.get("vdi_full") is False:
            if self.windowed_at is not None:  # máy ngủ / treo giữa 2 mẫu: không cộng cả quãng đó
                self.windowed_secs += min(now - self.windowed_at, 3 * cfg["sample_seconds"])
            self.windowed_at = now
        else:
            self.windowed_at = None
            if s["vdi_state"] == "foreground" and s.get("vdi_full"):
                self.windowed_secs = 0.0
        limit = cfg["fullscreen_tip_minutes"] * 60 if level != "off" else 0
        if limit and not self.windowed_alerted and self.windowed_secs >= limit:
            self.windowed_alerted = True
            events.append(("not_fullscreen", {"minutes": int(self.windowed_secs // 60)}))

        self.prev, self.prev_ts = s, now
        for kind, data in events:
            log.debug("Cảnh báo phát: %s %s", kind, data)
        return events

    def _track_return(self, s, now, active):
        """Nhận ra lúc quay lại sau một quãng ngồi yên. Lần chạm đầu chỉ là "chờ xác nhận" (self.resume); mẫu sau có
        chạm tiếp thì đúng là quay lại: trả (lúc chạm đầu, lúc bắt đầu ngồi yên, VDI ở trước lúc ngồi yên). Không chạm
        tiếp tới khi ngồi yên lại >= idle_threshold là chạm lẻ: quãng ngồi yên tiếp tục từ lúc bắt đầu cũ. Khoá máy thì
        bỏ hết (khoá máy là rời máy, tính riêng)."""
        p = self.prev
        if s["locked"]:
            self.resume = self.idle_start = None
        elif active and p is not None and not p["locked"] and p["idle"] >= self.cfg["idle_threshold_seconds"]:
            start = self.idle_start if self.idle_start is not None else self.prev_ts - p["idle"]
            self.resume = (now - s["idle"], start, p["vdi_state"] == "foreground")
            self.idle_start = None
        elif self.resume is not None:
            touched, start, vdi_front = self.resume
            if active and now - s["idle"] > touched + 1:
                self.resume = None
                return touched, start, vdi_front
            if not active:
                self.resume = None
                self.idle_start = start
                log.debug("Cảnh báo: chạm phím/chuột lẻ lúc %s rồi ngồi yên tiếp: vẫn tính là một quãng ngồi yên từ %s.",
                          dt.datetime.fromtimestamp(touched).strftime("%H:%M:%S"),
                          dt.datetime.fromtimestamp(start).strftime("%H:%M:%S"))
        return None

    def _nudge_limit(self, level, golden):
        """Ngưỡng (phút) nhắc sao nhãng theo mức. 0 = không nhắc."""
        cfg = self.cfg
        gold = cfg["golden_nudge_minutes"] if golden else 0
        if level == "nhe":
            return cfg["nudge_light_minutes"]
        if level == "vua":
            return gold or cfg["nudge_out_of_vdi_minutes"]
        if level == "nghiem":
            strict = cfg["nudge_strict_minutes"]
            return min(strict, gold) if strict and gold else strict
        return 0

    def today(self):
        """Bộ đếm sao nhãng hôm nay (cho /status, /nudge)."""
        lost = self.day_lost + ((self.out_last or 0) - self.out_since if self.out_since and self.out_counted else 0)
        return {"count": self.day_episodes, "minutes": int(lost // 60), "nudges": self.day_nudges,
                "light_done": self.light_done}
