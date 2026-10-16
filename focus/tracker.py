"""Vòng lấy mẫu chính: mỗi 5 giây đọc trạng thái máy, ghi DB theo lô, tính cảnh báo, gửi việc theo giờ.

Nhẹ máy:
- Mỗi vòng chỉ vài lời gọi Win32 + vài phép so sánh (~1 ms). Ghi đĩa 1 lần/phút.
- Mọi việc cần mạng (Telegram, AI) chạy ở hàng đợi nền: vòng lấy mẫu không bao giờ chờ mạng.
- Tiến trình chạy ở mức ưu tiên thấp + chế độ tiết kiệm (EcoQoS) của Windows.
- Ngoài khung giờ chạy hoặc ngày nghỉ (cuối tuần, lễ, nghỉ bù, /off, /leave cả ngày): tự thoát, không chạy nền
  (Task Scheduler bật lại hôm sau). Bật sớm hơn auto_start_at (đăng nhập / máy thức dậy lúc 07:30): thoát im lặng,
  không mở bot Telegram (on_start chưa gọi); trigger theo lịch bật lại đúng auto_start_at.
- Giờ bật/tắt đọc từ cfg MỖI vòng (/giobot đổi là có hiệu lực): giờ tắt mới đã qua -> chốt số liệu, thoát (không gửi
  gì thêm); giờ bật mới muộn hơn bây giờ -> hôm nay vẫn chạy tiếp (đã bật rồi), giờ mới áp dụng từ hôm sau. Lễ / nghỉ phép: báo 1 câu qua Telegram (1 lần/ngày). Sang ngày mới khi vẫn
  trong khung giờ (máy ngủ qua đêm rồi thức dậy): chốt số liệu ngày cũ rồi theo dõi tiếp ngày mới, trừ khi ngày
  mới là ngày nghỉ (thoát). Báo /off cho hôm nay lúc đang chạy: dừng ngay vòng kế tiếp rồi thoát.
- Nghỉ phép nửa ngày (/leave sang|chieu): trong phần nghỉ không lấy mẫu, không cảnh báo; việc theo giờ dời
  theo schedule.job_times.
- Hẹn giờ ngủ / phát hiện máy ngủ bằng đồng hồ đơn điệu (time.monotonic, không bị chỉnh giờ làm lệch);
  giờ thật (time.time) chỉ dùng làm mốc thời gian của mẫu.
"""
import datetime as dt
import logging
import os
import sys
import threading
import time

from . import holidays, housekeeping, messages, motivation, pace, persona
from .alerts import RealtimeAlerts
from .analysis import DAY_NAMES, daily_stats, day_goal_hours, golden_hours, in_golden, off_day, off_detail
from .logs import audit, get_logger
from .notifier import Notifier
from .probe import log_limited
from .schedule import due_jobs, in_leave, in_run_window, is_work_time, offday_ot_due
from .storage import SampleWriter, db_path, get_note, mark_sent, open_db

log = get_logger()

SLEEP_GAP_SECONDS = 120     # 2 mẫu cách nhau lâu hơn mức này = máy vừa ngủ dậy
PERF_EVERY_SECONDS = 600
MAX_CONSECUTIVE_ERRORS = 720  # ~1 giờ đọc lỗi liên tục thì dừng hẳn (log + audit CRASH)
LOCK_WAIT_SECONDS = 120       # bản mới chờ bản cũ thoát (vd. Task Scheduler bật lại đúng lúc bản cũ đang tắt)
MAX_PENDING_ROWS = 2000       # DB bận/đầy: giữ tối đa chừng này mẫu chưa ghi trong RAM (~2,8 giờ)


# ------------------------------------------------------------ tài nguyên hệ thống

class PerfMeter:
    """Đo tracker tốn bao nhiêu: % CPU (của 1 nhân), RAM, thời gian xử lý mỗi vòng."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.reset()

    def reset(self):
        self.t0, self.c0 = self.clock(), time.process_time()
        self.loops, self.loop_total, self.loop_max = 0, 0.0, 0.0

    def tick(self, seconds):
        self.loops += 1
        self.loop_total += seconds
        self.loop_max = max(self.loop_max, seconds)

    def report(self):
        wall = max(self.clock() - self.t0, 1e-6)
        cpu = time.process_time() - self.c0
        text = (f"CPU {cpu / wall * 100:.2f}% (1 nhân) · RAM {memory_mb():.0f} MB · "
                f"mỗi vòng {self.loop_total / max(self.loops, 1) * 1000:.1f} ms (tối đa {self.loop_max * 1000:.0f} ms) "
                f"· {self.loops} vòng trong {wall / 60:.0f} phút")
        self.reset()
        return text


def memory_mb():
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                                   "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                                   "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                                   "PagefileUsage", "PeakPagefileUsage")]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(pmc)
            k32 = ctypes.WinDLL("kernel32")
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            return pmc.WorkingSetSize / 1e6
        if sys.platform == "darwin":
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6  # macOS: byte, là đỉnh RSS
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    except Exception as e:
        log_limited("memory_mb", "Không đọc được RAM của tracker: %s: %s", type(e).__name__, e, level=logging.DEBUG)
        return 0.0


def lower_priority():
    """Ưu tiên thấp + EcoQoS (Windows 10 1709+): Windows xếp tracker vào nhân tiết kiệm điện."""
    try:
        if sys.platform != "win32":
            os.nice(5)
            return
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.SetPriorityClass(k32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS

        class THROTTLE(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]
        st = THROTTLE(1, 0x1, 0x1)  # PROCESS_POWER_THROTTLING_EXECUTION_SPEED: bật
        k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.SetProcessInformation(k32.GetCurrentProcess(), 4, ctypes.byref(st), ctypes.sizeof(st))
        log.debug("Đã hạ ưu tiên tiến trình (BELOW_NORMAL + EcoQoS).")
    except Exception as e:
        log.debug("Không hạ được ưu tiên tiến trình: %s: %s", type(e).__name__, e)


class InstanceLock:
    """Không cho 2 tracker chạy cùng lúc. Windows: named mutex; nơi khác: giữ một cổng nội bộ.
    Bản đến sau chờ tối đa `wait` giây (bản cũ có thể đang tắt dở), hết giờ mà chưa được thì thoát."""

    def __init__(self, name="FocusTracker", port=47392):
        self.name, self.port, self.handle, self.sock = name, port, None, None

    def acquire(self, wait=LOCK_WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic):
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = wintypes.HANDLE
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            k32.WaitForSingleObject.restype = wintypes.DWORD
            k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = k32.CreateMutexW(None, False, f"Local\\{self.name}")
            if not self.handle:
                log.error("Không tạo được mutex chống chạy trùng (lỗi %s).", ctypes.get_last_error())
                return False
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                log.info("Có tracker khác đang chạy: chờ tối đa %d giây cho nó thoát.", wait)
            r = k32.WaitForSingleObject(self.handle, int(wait * 1000))
            if r in (0, 0x80):  # WAIT_OBJECT_0, WAIT_ABANDONED (bản cũ chết không kịp nhả): coi như đã giữ được
                if r == 0x80:
                    log.warning("Bản tracker trước thoát bất thường (mutex bị bỏ rơi), bản này tiếp quản.")
                return True
            log.info("Chờ mutex hết giờ / lỗi (mã %s, lỗi %s).", r, ctypes.get_last_error())
            k32.CloseHandle(self.handle)
            self.handle = None
            return False
        import socket
        deadline = clock() + wait
        waited = False
        while True:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.sock.bind(("127.0.0.1", self.port))
                return True
            except OSError as e:
                self.sock.close()
                self.sock = None
                if not waited:
                    waited = True
                    log.info("Có tracker khác đang chạy (cổng %s: %s): chờ tối đa %d giây.", self.port, e, wait)
            left = deadline - clock()
            if left <= 0:
                return False
            sleep(min(2.0, left))

    def release(self):
        if self.sock:
            self.sock.close()
            self.sock = None


# ------------------------------------------------------------ tracker

class Tracker:
    def __init__(self, cfg, probe=None, bot=None, clock=time.time, sleep=time.sleep, now=dt.datetime.now,
                 notifier=None, run_housekeeping=True, mono=None, on_start=None, manual=False):
        self.cfg = cfg
        # manual: bạn tự bật (start_tracker, lam_bu_ngoai_gio), không phải lịch tự bật. Khi đó ngày nghỉ (cuối tuần,
        # lễ, /off) vẫn chạy để ghi giờ làm bù trong VDI (không nhắc gì, không tính sao nhãng), và bật sớm hơn giờ tự
        # bật cũng được (vẫn tự tắt lúc auto_stop_at).
        self.manual = manual
        self.last_vdi_work = None  # lần cuối đang làm trong VDI (clock); ngày nghỉ làm bù dùng để biết xong buổi chưa
        self.on_start = on_start  # gọi 1 lần khi chắc chắn chạy (trong khung giờ, không phải ngày nghỉ): mở bot
        self.probe = probe
        self.bot = bot
        self.clock, self.sleep, self.now = clock, sleep, now
        # Đồng hồ đơn điệu cho hẹn giờ / khoảng cách giữa 2 mẫu. Test truyền đồng hồ giả: dùng luôn đồng hồ đó.
        self.mono = mono or (time.monotonic if clock is time.time else clock)
        self.notifier = notifier
        self.run_housekeeping = run_housekeeping
        # recheck: bot vừa đổi ngày nghỉ / nghỉ phép -> vòng kế tiếp đọc lại ghi chú ngay, không chờ hết phút.
        self.state = {"paused": threading.Event(), "recheck": threading.Event(), "last": None, "perf": "",
                      "platform": "", "probe_warnings": []}
        self.alerts = RealtimeAlerts(cfg)
        self.state["alerts"] = self.alerts  # /status, /nudge đọc bộ đếm sao nhãng hôm nay
        self.perf = PerfMeter(self.mono)

    @property
    def persona(self):
        """Đọc mỗi lần dùng: đổi giọng bằng /style có hiệu lực ngay, không cần khởi động lại."""
        return self.cfg.get("persona") or persona.DEFAULT

    # ---------------------------------------------------------- gửi (luôn qua hàng đợi nền)

    def submit(self, label, fn, *args):
        log.info("Việc nền: %s", label)
        if self.notifier:
            self.notifier.submit(label, fn, *args)
        else:
            fn(*args)
    def _send(self, text):
        self.bot.send(text)

    def _send_out_of_vdi(self, data, plan):
        self.bot.send(messages.out_of_vdi(data, plan, self.persona))
        # Thêm một câu động viên (AI nếu có): mức vừa từ lần nhắc thứ 2 trong ngày; mức nghiêm ở lần nhắc lại đầu
        # tiên của mỗi lần sao nhãng (không gọi AI mỗi 5 phút). Mức nhẹ: không. /encourage off: không.
        level = data.get("level", "vua")
        again = ((level == "vua" and data.get("day_nudges", data["nth"]) > 1)
                 or (level == "nghiem" and data["nth"] == 2))
        if again and motivation.auto_on(self.cfg):
            self.bot.send(motivation.encouragement(
                self.cfg, self.bot.db, f"người dùng đã ra khỏi VDI {data['minutes']} phút, cần quay lại tập trung"),
                raw=True)

    def _send_break(self, data):
        self.bot.send(motivation.break_message(self.bot.db, data["minutes"], self.persona, data.get("water", False)))

    def _send_offday_ot(self, day):
        """Tổng kết làm bù ngày nghỉ. Telegram lỗi (False) thì gỡ dấu đã gửi để lần sau thử lại."""
        if self.bot.send_offday_ot(day) is False:
            from .storage import unmark_sent
            unmark_sent(self.db, day, "offday_ot")

    def _send_pace(self, day, cp, hhmm):
        """Mốc kiểm tra tiến độ: chậm thì nhắc ngay; đúng nhịp ở mốc khen thì khen 1 câu (1 lần/ngày); còn lại im."""
        info = pace.today_status(self.bot.db, self.cfg, day, hhmm)
        if info is None:
            log.info("Tiến độ %s: chưa tính được (ngoài giờ làm / đang nghỉ phép), bỏ qua.", cp)
            return
        verdict = "behind" if info["behind"] else "ok"
        log.info("Tiến độ mốc %s (lúc %s): VDI %.2fh / cần %.2fh (mục tiêu %gh) -> %s", cp, hhmm, info["actual_h"],
                 info["expected_h"], info["target_h"], verdict)
        audit("PACE", {"cp": cp, "at": hhmm, "actual_h": round(info["actual_h"], 2),
                       "expected_h": round(info["expected_h"], 2), "verdict": verdict})
        if info["behind"]:
            self.bot.send(messages.pace_behind(info, self.persona, self.cfg.get("nudge_level", "vua")))
        elif cp == pace.praise_checkpoint(self.cfg) and mark_sent(self.bot.db, day, "pace_praise"):
            self.bot.send(messages.pace_praise(info, self.persona))

    def dispatch(self, kind, data, note):
        """Một cảnh báo tức thời -> ghi audit + gửi Telegram (nếu có bot)."""
        audit("ALERT_" + kind.upper(), {k: v for k, v in data.items() if k != "since"})
        if kind == "not_fullscreen" and not mark_sent(self.db, self.day, "not_fullscreen"):
            return
        # Mức nhẹ: 1 lần/ngày kể cả khi tracker khởi động lại giữa ngày.
        if kind == "out_of_vdi" and data.get("level") == "nhe" and not mark_sent(self.db, self.day, "nudge_light"):
            log.info("Mức nhắc nhẹ: hôm nay đã nhắc sao nhãng rồi, không gửi nữa.")
            return
        if not self.bot:
            return
        if kind == "out_of_vdi":
            self.submit(kind, self._send_out_of_vdi, data, note.get("plan"))
        elif kind == "break":
            self.submit(kind, self._send_break, data)
        else:
            self.submit(kind, self._send, getattr(messages, kind)(data, self.persona))

    def run_jobs(self, hhmm, active, off, note, leave=None, paused=False):
        """paused=True (/pause): không lấy mẫu nên không biết có ngồi máy không. Tổng kết ngày/tuần vẫn gửi đúng giờ,
        hỏi tổng kết vẫn hỏi (qua Telegram, trả lời trên điện thoại được); cảnh báo tiến độ thì bỏ (chưa đánh dấu
        đã gửi: /resume kịp trong LATE_MINUTES thì vẫn kiểm)."""
        weekday = self.now().weekday()
        jobs = due_jobs(self.cfg, hhmm, weekday, active=active, off=off, note=note, has_bot=bool(self.bot),
                        leave=leave)
        if paused:
            jobs = [j for j in jobs if not j.startswith("pace_")]
            if "review" not in jobs and "review" in due_jobs(self.cfg, hhmm, weekday, active=True, off=off, note=note,
                                                             has_bot=bool(self.bot), leave=leave):
                jobs.append("review")
        if (off and self.manual and self.bot and self.last_vdi_work is not None
                and offday_ot_due(self.cfg, hhmm, self.clock() - self.last_vdi_work)):
            if mark_sent(self.db, self.day, "offday_ot"):
                audit("JOB_OFFDAY_OT", self.day)
                self.submit("offday_ot", self._send_offday_ot, self.day)
        for job in jobs:
            key = self.week_id if job == "weekly" else self.day
            if not self.bot or not mark_sent(self.db, key, job):
                continue
            audit("JOB_" + job.upper(), self.day)
            if job.startswith("pace_"):
                self.submit(job, self._send_pace, self.day, f"{job[5:7]}:{job[7:]}", hhmm)
                continue
            fn = {"morning": lambda: self.bot.send_morning(self.day),
                  "plan": lambda: self.bot.start_convo("plan"),
                  "review": lambda: self.bot.start_convo("review"),
                  "summary": lambda: self.bot.send_daily_summary(self.day),
                  "weekly": lambda: self.bot.send_weekly(self.day),
                  "boost": lambda: self.bot.send_boost(self.day)}[job]
            self.submit(job, fn)
        if self.bot and self.bot.has_review_retry():  # đánh giá AI lỗi lúc trước: thử gửi lại
            self.submit("ai_review_retry", self.bot.retry_ai_reviews, self.day)
        if self.bot and holidays.next_year_missing(self.cfg) and mark_sent(self.db, self.day[:4] + "-12", "holiday_warn"):
            self.submit("holiday_warn", self._send,
                        "Đã giữa tháng 12 mà mình chưa có lịch lễ Singapore năm sau (chưa tải được từ trang MOM). "
                        "Mình sẽ tự thử lại mỗi ngày. Bạn cũng có thể thêm ngày lễ vào \"extra_off_days\" trong "
                        "config/settings.json, hoặc nhắn /off <ngày> cho từng ngày.")

    # ---------------------------------------------------------- ngày nghỉ / nghỉ phép

    def _next_work_day(self, day):
        d = dt.date.fromisoformat(day)
        for i in range(1, 15):
            n = d + dt.timedelta(days=i)
            try:
                if not off_day(self.db, self.cfg, n.isoformat()):
                    return n
            except Exception as e:
                log.debug("Không xét được ngày %s: %s", n, e)
                return None
        return None

    def off_notice_text(self, kind, reason, day):
        n = self._next_work_day(day)
        if n is None:
            when = "ngày làm việc tới mình tự bật lại"
        elif n == dt.date.fromisoformat(day) + dt.timedelta(days=1):
            when = "mai bật lại"
        else:
            when = f"bật lại {DAY_NAMES[n.weekday()]} {n:%d/%m}"
        if kind == "holiday":
            return f"🌴 Hôm nay là ngày lễ {reason}, mình tắt, {when}."
        if kind == "observed":
            return f"🌴 Hôm nay là ngày {reason} (lễ rơi Chủ nhật), mình tắt, {when}."
        if kind == "config":
            return f"🌴 Hôm nay là ngày nghỉ bạn khai trong config, mình tắt, {when}."
        return (f"🌴 Hôm nay bạn nghỉ ({reason}), mình tắt, {when}. "
                "Nếu vẫn đi làm: nhắn /on rồi mở lại tracker "
                f"({'start_tracker.command' if sys.platform == 'darwin' else 'start_tracker.vbs'}).")

    def _off_notice(self, kind, reason, day):
        """Ngày nghỉ: báo 1 câu (1 lần/ngày). Cuối tuần thì im lặng. Gửi ngay (tracker sắp thoát)."""
        log.info("Ngày %s nghỉ (%s: %s): không theo dõi.", day, kind, reason)
        if kind == "weekend" or not self.bot:
            return
        try:
            if not mark_sent(self.db, day, "off_notice"):
                log.debug("Đã báo ngày nghỉ %s rồi, không báo lại.", day)
                return
            text = self.off_notice_text(kind, reason, day)
            audit("OFF_NOTICE", f"{day} {kind} {reason}")
            self.bot.send(text)
        except Exception as e:  # mất mạng / DB bận: chỉ ghi log, vẫn thoát bình thường
            log.warning("Không báo được ngày nghỉ %s: %s", day, e)

    def _leave_notice(self, leave):
        """Bắt đầu phần nghỉ phép nửa ngày (lần đầu trong ngày): báo 1 câu."""
        if not self.bot or not mark_sent(self.db, self.day, "leave_notice"):
            return
        cfg = self.cfg
        half = day_goal_hours(cfg, leave)
        if leave == "am":
            text = (f"☀️ Sáng nay bạn nghỉ phép: mình chưa theo dõi, từ {cfg['lunch_end']} mới bắt đầu "
                    f"(chào + hỏi kế hoạch lúc đó). Mục tiêu hôm nay còn {half:g}h.")
        else:
            text = (f"🌴 Chiều nay bạn nghỉ phép: mình dừng theo dõi từ {cfg['lunch_start']}, gửi tổng kết ngày "
                    f"luôn. Mục tiêu hôm nay {half:g}h. Nghỉ vui nhé!")
        self.submit("leave_notice", self._send, text)

    # ---------------------------------------------------------- vòng chính

    def _run_off_day(self):
        """Ngày nghỉ vẫn chạy (ghi giờ làm bù trong VDI): settings run_on_off_days, hoặc bạn tự bật tracker."""
        return bool(self.cfg["run_on_off_days"] or self.manual)

    def _set_day(self, now_dt):
        self.day = now_dt.date().isoformat()
        iso = now_dt.date().isocalendar()
        self.week_id = f"{iso[0]}-W{iso[1]:02d}"

    def _finish_day(self, writer):
        """Chốt số liệu của self.day: ghi nốt mẫu trong RAM + tính daily_stats."""
        try:
            writer.flush()
        except Exception as e:
            log.error("Không ghi được %d mẫu cuối ngày %s: %s", len(writer.buf), self.day, e, exc_info=True)
        try:
            daily_stats(self.db, self.cfg, self.day, refresh=True)
        except Exception as e:
            log.error("Lỗi khi chốt số liệu ngày %s: %s", self.day, e, exc_info=True)

    def _write(self, writer, ts, dur, s):
        """Ghi mẫu. DB bận quá lâu / ổ đầy: giữ mẫu trong RAM (có giới hạn) và vẫn tiếp tục lấy mẫu."""
        try:
            writer.add(ts, dur, s)
        except Exception as e:
            extra = len(writer.buf) - MAX_PENDING_ROWS
            if extra > 0:
                del writer.buf[:extra]
            log_limited("write-" + type(e).__name__, "Không ghi được mẫu vào DB (%s: %s), giữ %d mẫu trong RAM%s",
                        type(e).__name__, e, len(writer.buf), f", bỏ {extra} mẫu cũ nhất" if extra > 0 else "",
                        exc_info=True)

    def _probe_info(self):
        name = getattr(self.probe, "platform_name", "")
        method = getattr(self.probe, "method", "")
        if name or method:
            self.state["platform"] = f"{name}: {method}"
        warnings = getattr(self.probe, "warnings", None)
        if isinstance(warnings, list):
            self.state["probe_warnings"] = warnings  # cùng một list: cảnh báo phát hiện sau cũng hiện ở /status
        log.info("Đọc trạng thái máy: %s · cảnh báo: %s", self.state["platform"] or type(self.probe).__name__,
                 "; ".join(self.state["probe_warnings"]) or "không")

    def run(self):
        cfg = self.cfg
        now_dt = self.now()
        self._set_day(now_dt)
        hhmm = now_dt.strftime("%H:%M")
        if not in_run_window(cfg, hhmm) and not (self.manual and hhmm < cfg["auto_stop_at"]):
            early = hhmm < cfg["auto_start_at"]
            log.info("Ngoài khung giờ chạy (%s–%s, bây giờ %s): thoát%s.", cfg["auto_start_at"], cfg["auto_stop_at"],
                     hhmm, ", lịch tự bật sẽ bật lại lúc " + cfg["auto_start_at"] if early else "")
            audit("OUTSIDE_WINDOW", f"{hhmm} {cfg['auto_start_at']}-{cfg['auto_stop_at']}")
            return "outside_window"
        self.db = open_db(db_path(cfg))
        # Năm nay chưa có lịch lễ nào trên máy: tải MOM ngay (tối đa 1 lần/ngày) để không chạy nhầm ngày lễ.
        holidays.ensure_today_known(cfg, now_dt.date())
        kind, off = off_detail(self.db, cfg, self.day)
        if off and self.manual and not cfg["run_on_off_days"]:
            log.info("Hôm nay nghỉ (%s) nhưng bạn tự bật: chỉ ghi giờ làm bù trong VDI, không nhắc gì.", off)
            audit("OFF_DAY_MANUAL", f"{self.day} {kind} {off}")
        if off and not self._run_off_day():
            log.info("Hôm nay nghỉ (%s), không chạy.", off)
            audit("OFF_DAY", f"{self.day} {kind} {off}")
            self._off_notice(kind, off, self.day)
            return "off_day"
        if self.probe is None:
            from .probe import make_probe
            self.probe = make_probe(cfg)
        self._probe_info()
        if self.notifier is None and self.bot is not None:
            self.notifier = Notifier(on_error=getattr(self.bot, "notify_job_error", None))
        if self.bot is not None:
            self.bot.state = self.state
        if self.on_start is not None:
            try:
                self.on_start()
            except Exception as e:  # bot không mở được thì vẫn theo dõi
                log.error("Lỗi khi mở bot: %s", e, exc_info=True)
        if off and self.manual and self.bot is not None:
            try:
                if mark_sent(self.db, self.day, "ot_manual_notice"):
                    self.bot.send(f"🌙 Hôm nay nghỉ ({off}) mà bạn tự bật bot: mình chỉ ghi giờ làm bù trong VDI (có gõ "
                                  "phím / rê chuột), không nhắc gì, không tính sao nhãng. Sáng ngày làm việc tới mình "
                                  f"báo lại tổng giờ làm bù. Tracker tự tắt lúc {cfg['auto_stop_at']}.")
            except Exception as e:  # mất mạng / DB bận: vẫn theo dõi
                log.warning("Không báo được chế độ làm bù: %s", e)
        if self.run_housekeeping:
            self.submit("housekeeping", housekeeping.run, cfg)
            # Lịch lễ: năm nay chưa có bản MOM / tháng 12 chưa có năm sau -> tải ở nền (không chặn, không raise).
            self.submit("holidays", holidays.background_check, cfg, now_dt.date())
        catch_up = getattr(self.bot, "catch_up", None) if self.bot is not None else None
        if catch_up and not off:  # tổng kết ngày/tuần bị lỡ (máy tắt đúng giờ gửi): gửi bù một lần
            self.submit("catchup", catch_up, self.day)
        golden = golden_hours(self.db, cfg, self.day)
        if golden:
            log.info("Giờ vàng: %s", golden)
        writer = SampleWriter(self.db, cfg["store_window_titles"])
        step = cfg["sample_seconds"]
        last_report = last_perf = prev = self.mono()
        prev_wall = self.clock()
        next_tick = prev + step
        minute = None
        note = {}
        leave = None
        errors = ticks = 0
        last_vdi = last_locked = None
        paused = leave_paused = early_logged = False
        recheck = self.state["recheck"]
        log.info("Đang theo dõi ngày %s mỗi %ss. Dữ liệu: %s", self.day, step, db_path(cfg))
        try:
            while True:
                self.sleep(max(0.0, next_tick - self.mono()))
                mono = self.mono()
                now = self.clock()
                next_tick = max(next_tick + step, mono + step * 0.5)  # giữ nhịp đều, không dồn vòng
                t_loop = time.perf_counter()
                # macOS: đồng hồ đơn điệu đứng yên khi máy ngủ, nên lấy thêm giờ thật (chỉ khi nó tiến xa hơn).
                gap = mono - prev
                wall_gap = now - prev_wall
                if wall_gap > gap + SLEEP_GAP_SECONDS:
                    gap = wall_gap
                prev, prev_wall = mono, now
                now_dt = self.now()
                hhmm = now_dt.strftime("%H:%M")
                if gap > SLEEP_GAP_SECONDS:
                    log.info("Máy vừa thức dậy (ngủ khoảng %d phút).", gap // 60)
                    audit("WAKE", f"{int(gap // 60)}m")
                    self.alerts.reset(forget_vdi=True)
                if not in_run_window(cfg, hhmm):
                    if hhmm < cfg["auto_start_at"] and now_dt.date().isoformat() == self.day:
                        # /giobot vừa dời giờ bật muộn hơn bây giờ: đã bật rồi thì chạy tiếp hôm nay.
                        if not early_logged:
                            early_logged = True
                            log.info("Giờ bật mới %s muộn hơn bây giờ (%s): hôm nay vẫn chạy tiếp.",
                                     cfg["auto_start_at"], hhmm)
                    else:
                        log.info("Hết khung giờ chạy (%s, tắt lúc %s), tracker chốt số liệu rồi tự tắt.", hhmm,
                                 cfg["auto_stop_at"])
                        audit("AUTO_STOP", f"{hhmm} stop={cfg['auto_stop_at']}")
                        return "window_end"
                today = now_dt.date().isoformat()
                if today != self.day:  # qua đêm (máy ngủ rồi thức) mà vẫn trong khung giờ: sang ngày mới, chạy tiếp
                    log.info("Sang ngày mới %s: chốt số liệu ngày %s rồi theo dõi tiếp.", today, self.day)
                    audit("NEW_DAY", f"{self.day} -> {today}")
                    self._finish_day(writer)
                    kind, off = off_detail(self.db, cfg, today)
                    if off and not self._run_off_day():
                        log.info("Ngày mới %s là ngày nghỉ (%s), tracker tự tắt.", today, off)
                        audit("AUTO_STOP", f"off_day {today}")
                        self._off_notice(kind, off, today)
                        return "off_day"
                    self._set_day(now_dt)
                    self.alerts.reset()
                    if self.state["paused"].is_set():  # /pause hôm qua (gập máy qua đêm) không kéo sang ngày mới
                        self.state["paused"].clear()
                        log.info("Ngày mới: bỏ tạm dừng (/pause) của hôm trước, theo dõi lại.")
                        audit("RESUME", "ngày mới")
                    paused = leave_paused = False
                    golden = golden_hours(self.db, cfg, self.day)
                    minute, note, leave = None, {}, None
                    gap = min(gap, step)  # không kéo quãng ngủ qua đêm sang ngày mới
                    if self.run_housekeeping:  # dọn dẹp + lịch lễ của ngày mới (housekeeping tự giữ 1 lần/ngày)
                        self.submit("housekeeping", housekeeping.run, cfg)
                        self.submit("holidays", holidays.background_check, cfg, now_dt.date())
                    if catch_up and not off:
                        self.submit("catchup", catch_up, self.day)
                if hhmm != minute or recheck.is_set():  # mỗi phút (hoặc bot vừa đổi ngày nghỉ): đọc lại ghi chú
                    recheck.clear()
                    minute = hhmm
                    try:
                        note = get_note(self.db, self.day)
                        kind, off = off_detail(self.db, cfg, self.day)
                        leave = note.get("leave_part") if note.get("leave_part") in ("am", "pm") else None
                    except Exception as e:  # DB bận: giữ trạng thái cũ, phút sau đọc lại
                        log_limited("note-" + type(e).__name__, "Không đọc được ghi chú hôm nay: %s", e)
                    if off and not self._run_off_day():  # /off hôm nay, hoặc lịch lễ mới: dừng ngay
                        log.info("Hôm nay %s thành ngày nghỉ (%s): dừng theo dõi, tracker tự tắt.", self.day, off)
                        audit("AUTO_STOP", f"off_day {self.day}")
                        self._off_notice(kind, off, self.day)
                        return "off_day"
                if leave and not cfg["run_on_off_days"] and in_leave(cfg, hhmm, leave):
                    if not leave_paused:
                        leave_paused = True
                        log.info("Đang nghỉ phép %s: không lấy mẫu, không cảnh báo.", leave)
                        audit("LEAVE_PAUSE", f"{self.day} {leave}")
                        self._leave_notice(leave)
                    self.alerts.reset(forget_vdi=True)
                    ticks += 1
                    if ticks % 6 == 0:  # tổng kết (nghỉ chiều: gửi lúc bắt đầu nghỉ) vẫn chạy theo giờ
                        try:
                            self.run_jobs(hhmm, False, off, note, leave)
                        except Exception as e:
                            log.error("Lỗi xử lý lịch: %s", e, exc_info=True)
                    continue  # phần nghỉ phép: không ghi mẫu (báo cáo coi như không có mặt)
                if leave_paused:
                    leave_paused = False
                    log.info("Hết phần nghỉ phép: theo dõi lại.")
                    audit("LEAVE_RESUME", self.day)
                    gap = min(gap, step)
                if self.state["paused"].is_set():
                    if not paused:
                        paused = True
                        log.info("Tạm dừng theo dõi (/pause).")
                    self.alerts.reset(forget_vdi=True)
                    ticks += 1
                    if ticks % 6 == 0:  # tạm dừng không chặn tổng kết ngày / tuần / hỏi tổng kết
                        try:
                            self.run_jobs(hhmm, False, off, note, leave, paused=True)
                        except Exception as e:
                            log.error("Lỗi xử lý lịch: %s", e, exc_info=True)
                    continue  # khoảng tạm dừng hiện là "rời máy" trong báo cáo
                if paused:
                    paused = False
                    log.info("Tiếp tục theo dõi.")
                    gap = min(gap, step)
                try:
                    s = self.probe.sample()
                except Exception as e:  # một lần đọc lỗi không được làm chết tracker
                    errors += 1
                    log_limited("probe-" + type(e).__name__, "Đọc trạng thái máy lỗi (%d lần liên tiếp): %s: %s",
                                errors, type(e).__name__, e, exc_info=True)
                    if errors >= MAX_CONSECUTIVE_ERRORS:
                        log.error("Đọc trạng thái máy lỗi %d lần liên tiếp, dừng hẳn.", errors)
                        raise
                    continue
                if errors:
                    log.info("Đọc trạng thái máy bình thường lại sau %d lần lỗi.", errors)
                errors = 0
                self._write(writer, now, gap, s)
                self.state["last"] = s
                if (s["vdi_state"] in ("foreground", "windowed") and not s["locked"]
                        and s["idle"] < cfg["idle_threshold_seconds"]):
                    self.last_vdi_work = now  # lần cuối đang làm trong VDI (để biết buổi làm bù đã xong chưa)
                if s["locked"] != last_locked:
                    if last_locked is not None:
                        log.info("Máy %s.", "khoá" if s["locked"] else "mở khoá")
                    last_locked = s["locked"]
                if s["vdi_state"] != last_vdi:
                    log.info("VDI: %s → %s (app trước mặt: %s)", last_vdi or "bắt đầu", s["vdi_state"],
                             s.get("fg_proc") or "?")
                    last_vdi = s["vdi_state"]
                ticks += 1
                try:
                    work = is_work_time(cfg, hhmm, off, leave)
                    for kind, data in self.alerts.update(s, now, work, golden=in_golden(golden, hhmm)):
                        self.dispatch(kind, data, note)
                    if ticks % 6 == 0:  # việc theo giờ: kiểm tra mỗi 30 giây là đủ
                        active = not s["locked"] and s["idle"] < cfg["idle_threshold_seconds"]
                        self.run_jobs(hhmm, active, off, note, leave)
                    refresh = cfg["report_refresh_minutes"] * 60
                    if refresh and mono - last_report >= refresh:
                        last_report = mono
                        writer.flush()
                        from .report import write_report
                        write_report(self.db, cfg, self.day)
                except Exception as e:  # lỗi nhắc nhở/báo cáo không được làm dừng việc ghi mẫu
                    log.error("Lỗi xử lý cảnh báo/lịch: %s", e, exc_info=True)
                self.perf.tick(time.perf_counter() - t_loop)
                if mono - last_perf >= PERF_EVERY_SECONDS:
                    last_perf = mono
                    self.state["perf"] = self.perf.report()
                    log.debug("PERF %s", self.state["perf"])
        finally:
            self._finish_day(writer)
            if self.notifier:
                self.notifier.drain(30)
            if self.bot:
                self.bot.stop()
