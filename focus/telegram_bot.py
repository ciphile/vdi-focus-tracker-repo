"""Bot Telegram: kênh giao tiếp DUY NHẤT với app.

Một tin nhắn đi theo thứ tự:
1. Lệnh (/tmrtask ...)       -> action tương ứng trong actions.py, chạy luôn (bạn đã gõ rõ ràng).
2. Đang hỏi dở (/review)     -> tin nhắn là câu trả lời.
3. Đang chờ "Sửa lại"        -> hiểu lại tin nhắn mới.
4. Tin nhắn tự nhiên         -> intent.understand (AI, dự phòng bằng từ khoá).
   Action ghi dữ liệu -> hỏi lại "Mình hiểu bạn muốn ...", có nút ✅ OK / ✏️ Sửa lại / ❌ Huỷ.
   Action chỉ xem -> chạy luôn. Không hiểu -> báo lại.

Chỉ dùng thư viện chuẩn (urllib). Bot chỉ trả lời đúng một chat_id (TELEGRAM_CHAT_ID).
"""
import datetime as dt
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid

from . import ai_client, energy, errors, holidays, intent, motivation, net, pace, pending, persona, prefs
from .actions import (BY_COMMAND, BY_NAME, NUDGE_NAMES, bot_commands, confirm_card, describe, example, help_text, hours_line,
                      ask_toggle, parse_command_args, parse_times, understood_line, validate)
from . import __version__
from .analysis import (analyze, daily_stats, day_facts, fmt_dur, fmt_t, focus_score, golden_hours, off_day, ot_ranges,
                       streak, week_facts)
from .logs import audit, get_logger
from .messages import golden_tip
from .report import ot_history, ot_history_text, summary_text, week_text, write_report, write_week_report
from .schedule import LEAVE_NAMES, in_leave
from .storage import append_note, db_path, get_note, last_tomorrow, mark_sent, open_db, save_note, unmark_sent

log = get_logger()

PLAN_QUESTIONS = [("plan", "3 việc quan trọng nhất hôm nay là gì? Ghi rõ output cụ thể.")]
REVIEW_QUESTIONS = [
    ("output", "Hôm nay bạn đã xong những gì?"),
    ("issues", "Có issue / blocker gì không?"),
    ("distractions", "Điều gì làm bạn mất tập trung nhất?"),
    ("as400", "Giờ vào/ra AS400 hôm nay? Gõ kiểu 08:10 17:35, hoặc gửi ảnh spooled file."),
    ("tomorrow", "Việc đầu tiên sẽ làm sáng mai? (sáng mai mở máy là bắt tay luôn)"),
    ("energy", "Năng lượng hôm nay từ 1 đến 5?"),
]
SKIP_WORDS = {"/skip", "bỏ qua", "bo qua", "skip", "-"}
CONVO_TTL_SECONDS = 3 * 3600       # /plan, /review bạn tự gõ
AUTO_CONVO_TTL_SECONDS = 20 * 60   # bot tự hỏi theo lịch: lâu không trả lời thì thôi, không "bắt" tin nhắn sau đó
STALE_MESSAGE_SECONDS = 3600        # tin nhắn gửi lúc app tắt, tới khi mở máy mới đọc
STALE_SKIP = {"tam_dung", "tiep_tuc"}  # tin cũ kiểu này bỏ qua (tạm dừng cả ngày vì tin tối qua là sai)
ENERGY_RE = re.compile(r"(?<!\d)([1-5])(?!\d)")
PENDING_TTL_SECONDS = 30 * 60
MAX_PHOTO_BYTES = 10 * 1024 * 1024
CONFIRM_KEYBOARD = lambda pid: {"inline_keyboard": [[
    {"text": "✅ OK", "callback_data": f"ok:{pid}"},
    {"text": "✏️ Sửa lại", "callback_data": f"edit:{pid}"},
    {"text": "❌ Huỷ", "callback_data": f"no:{pid}"}]]}


RETRY_REVIEW_SECONDS = 15 * 60

ALERT_NAMES = {"out_of_vdi": "ngoài VDI", "away": "rời máy", "back": "quay lại", "break": "nghỉ giải lao",
               "phone": "điện thoại", "not_fullscreen": "VDI không toàn màn hình",
               "water": "uống nước", "vdi_closed": "VDI đã đóng"}


def _split(text, size):
    """Cắt tin dài theo dòng (Telegram giới hạn 4096 ký tự/tin)."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > size:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:size])
            line = line[size:]
        if cur and len(cur) + 1 + len(line) > size:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def _redacted(exc, token):
    """Trả lại đúng loại lỗi nhưng lời nhắn đã che token (để log không bao giờ lộ token)."""
    if token and token in str(exc):
        if isinstance(exc, urllib.error.URLError):
            reason = str(exc.reason).replace(token, "***")
            return urllib.error.URLError(reason)
        return type(exc)(str(exc).replace(token, "***")) if isinstance(exc, (ValueError, OSError)) \
            else RuntimeError(str(exc).replace(token, "***"))
    return exc


WEEKDAY_VN = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]


def _day_label(day, today):
    """"qua" nếu là hôm qua, còn lại "thứ Sáu 10/10" để không gọi lời hẹn 3 ngày trước là "hôm qua"."""
    d, t = dt.date.fromisoformat(day), dt.date.fromisoformat(today)
    return "qua" if (t - d).days == 1 else f"{WEEKDAY_VN[d.weekday()]} {d:%d/%m}"


class TelegramAPI:
    """Gọi Bot API qua urllib. Tách riêng để test thay bằng bản giả."""

    def __init__(self, token):
        self.token = token

    def call(self, method, params=None, files=None, timeout=40):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        if files:
            boundary = uuid.uuid4().hex
            body = b""
            for k, v in (params or {}).items():
                body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
            for k, path in files.items():
                with open(path, "rb") as f:
                    data = f.read()
                body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                         f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: text/html\r\n\r\n").encode()
                body += data + b"\r\n"
            body += f"--{boundary}--\r\n".encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        else:
            req = urllib.request.Request(url, data=json.dumps(params or {}).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with net.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError:
            raise  # lời nhắn không chứa URL
        except Exception as e:  # URLError/InvalidURL có thể chứa URL (có token): che token trước khi log
            raise _redacted(e, self.token)

    def download(self, file_path, limit=MAX_PHOTO_BYTES):
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        try:
            with net.urlopen(url, timeout=60) as r:
                data = r.read(limit + 1)
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            raise _redacted(e, self.token)
        if len(data) > limit:
            raise ai_client.AIError(f"ảnh quá lớn (tối đa {limit // 1_000_000} MB), gửi ảnh chụp nhỏ hơn", permanent=True)
        return data


class TelegramBot:
    def __init__(self, cfg, state, api=None):
        self.cfg = cfg
        self.state = state  # dùng chung với tracker: paused (Event), last (mẫu gần nhất), perf
        self.api = api or TelegramAPI(cfg["telegram_bot_token"])
        self.chat_id = str(cfg.get("telegram_chat_id") or "")
        self.offset = 0
        self.convo = None        # (kind, [câu hỏi còn lại], lúc bắt đầu, thời hạn giây)
        self.pending = {}        # id -> (action, args, lúc tạo, câu gốc, ngày ghi)
        self.awaiting_edit = False
        self._local = threading.local()
        self._lock = threading.RLock()  # tracker (hàng đợi nền) và vòng nhận tin cùng đụng convo
        self.stopped = threading.Event()
        self._job_errors = {}
        self._retry_running = 0  # lúc bắt đầu lượt gửi lại đang chạy (0 = không có)
        prefs.apply(cfg, self.db)  # /aireview, /style đã đổi trước đó

    # ------------------------------------------------------------ gửi

    def persona_text(self, text):
        return persona.apply(text, self.cfg.get("persona") or persona.DEFAULT)

    def send(self, text, chat_id=None, markup=None, raw=False):
        """Gửi tin (tự cắt nếu dài). raw=True: không đổi xưng hô (câu AI viết, câu trích dẫn).
        Trả message_id của đoạn cuối, hoặc None nếu lỗi."""
        chat_id = chat_id or self.chat_id
        if not chat_id or not text:
            return None
        text = self.persona_text(text) if not raw else persona.strip_keep(text)
        log.debug("Gửi Telegram (%s ký tự): %s", len(text), text[:120].replace("\n", " ⏎ "))
        chunks = _split(text, 4000)
        msg_id = None
        for n, chunk in enumerate(chunks):
            params = {"chat_id": chat_id, "text": chunk}
            if markup and n == len(chunks) - 1:
                params["reply_markup"] = markup
            for attempt in (1, 2):
                try:
                    res = self.api.call("sendMessage", params)
                    msg_id = (res.get("result") or {}).get("message_id")
                    break
                except Exception as e:
                    if attempt == 2:
                        # Không gửi được thì không thể báo qua Telegram: ghi rõ vào log + audit.log để xem lại.
                        log.warning("Telegram gửi lỗi: %s", errors.explain(e))
                        audit("TELEGRAM_SEND_FAIL", errors.explain(e))
                        return None
                    time.sleep(3)
        return msg_id

    def send_file(self, path, caption=""):
        try:
            self.api.call("sendDocument", {"chat_id": self.chat_id, "caption": caption},
                          files={"document": path}, timeout=60)
        except Exception as e:
            log.warning("Telegram gửi file lỗi: %s", e)
            self.send(f"Không gửi được file báo cáo: {errors.explain(e)}. Thử lại /report sau nhé.")

    def _quiet(self, method, params):
        try:
            self.api.call(method, params)
        except Exception as e:
            log.debug("%s lỗi: %s", method, e)

    # ------------------------------------------------------------ tiện ích

    @property
    def db(self):
        # Mỗi thread cần connection SQLite riêng.
        if not hasattr(self._local, "db"):
            self._local.db = open_db(db_path(self.cfg))
        return self._local.db

    def today(self):
        """Ngày của tin nhắn đang xử lý (tin gửi lúc app tắt thuộc về ngày gửi), mặc định hôm nay."""
        return getattr(self._local, "day", None) or dt.date.today().isoformat()

    def stats_line(self):
        a = analyze(self.db, self.cfg, self.today())
        now = dt.datetime.now().strftime("%H:%M")
        if not a["has_data"]:
            return f"chưa có dữ liệu hôm nay, bây giờ là {now}"
        return (f"đã tập trung sâu {fmt_dur(a['deep'])} / mục tiêu {a['goal_h']:g}h, "
                f"ngoài VDI {fmt_dur(a['other'])}, bây giờ là {now}")

    def encourage(self, situation, style=None):
        return motivation.encouragement(self.cfg, self.db, situation, style)

    def status_text(self):
        """/status: tình trạng lúc này, hôm nay, cài đặt, AI, hệ thống."""
        cfg, day = self.cfg, self.today()
        lines = ["📍 LÚC NÀY"]
        s = self.state.get("last")
        if self.state["paused"].is_set():
            lines.append("Đang tạm dừng theo dõi (/resume để theo dõi lại).")
        elif not s:
            lines.append("Tracker chưa có mẫu nào (tracker chưa chạy hoặc vừa khởi động).")
        else:
            where = {"foreground": "đang trong VDI", "minimized": "VDI đang thu nhỏ",
                     "background": "VDI nằm sau app khác", "absent": "không thấy cửa sổ VDI"}.get(s["vdi_state"], "?")
            if s["locked"]:
                where = "máy đang khoá"
            lines.append(f"{where}, app đang dùng: {s['fg_proc'] or '?'}, không chạm phím/chuột {int(s['idle'])}s.")
        off = off_day(self.db, cfg, day)
        if off:
            lines.append(f"Hôm nay là ngày nghỉ ({off}), không nhắc.")
        leave = get_note(self.db, day).get("leave_part")
        if not off and leave in LEAVE_NAMES:
            now = dt.datetime.now().strftime("%H:%M")
            lines.append(f"🌴 Hôm nay {LEAVE_NAMES[leave]}"
                         + (" — đang trong phần nghỉ, không theo dõi." if in_leave(cfg, now, leave) else ".")
                         + " Huỷ: /on")

        lines += ["", "📊 HÔM NAY"]
        a = analyze(self.db, cfg, day)
        if a["has_data"]:
            lines.append(f"Tập trung sâu {fmt_dur(a['deep'])} / mục tiêu {a['goal_h']:g}h · trong VDI {fmt_dur(a['vdi'])} · "
                         f"ngoài VDI {fmt_dur(a['other'])} · VDI thu nhỏ {fmt_dur(a['minimized'])} · "
                         f"rời máy {fmt_dur(a['away'])}")
            lines.append(f"Điểm {focus_score(a)}/100 · rời VDI {a['exits']} lần · chuỗi đạt mục tiêu "
                         f"{streak(self.db, cfg, day)} ngày")
        else:
            lines.append("Chưa có số liệu hôm nay.")
        try:
            info = None if off else pace.today_status(self.db, cfg, day, dt.datetime.now().strftime("%H:%M"))
            if info:
                lines.append(f"Tiến độ: làm thật trong VDI {fmt_dur(info['actual_h'] * 3600)} / cần khoảng "
                             f"{fmt_dur(info['expected_h'] * 3600)} lúc này "
                             + ("(chậm ⚠️)" if info["behind"] else "(đúng nhịp ✅)") + " · chi tiết: /pace")
        except Exception as e:
            log.debug("Không tính được tiến độ cho /status: %s", e)
        al = self.state.get("alerts")
        if al is not None:
            t = al.today()
            lines.append(f"Sao nhãng hôm nay: {t['count']} lần (≥ 1 phút), {t['minutes']} phút")
        alerts = self._alerts_today(day)
        if alerts:
            lines.append("Đã nhắc: " + ", ".join(f"{ALERT_NAMES.get(k, k)} {v}" for k, v in alerts.items()))
        note = get_note(self.db, day)
        count = lambda f: len([x for x in (note.get(f) or "").splitlines() if x.strip()])
        lines.append(f"Ghi chú: kế hoạch {'✓' if note.get('plan') else '✗'} · output {count('output')} · "
                     f"issue {count('issues')} · việc sáng mai {'✓' if note.get('tomorrow') else '✗'}")

        p = cfg.get("persona") or persona.DEFAULT
        styles = ", ".join(cfg.get("encouragement_styles") or [])
        lines += ["", "⚙️ CÀI ĐẶT", hours_line(cfg),
                  f"Giờ làm {cfg['work_start']}–{cfg['work_end']}, trưa {cfg['lunch_start']}–{cfg['lunch_end']} · "
                  f"rời máy {cfg['away_alert_minutes']}' · nhắc nghỉ (/break): "
                  + (f"{cfg['break_reminder_minutes']}'" if cfg.get("break_reminder_enabled", True)
                     and cfg["break_reminder_minutes"] else "tắt")
                  + " · uống nước (/water): " + (f"{cfg['water_reminder_minutes']}'" if cfg.get(
                      "water_reminder_enabled", True) and cfg.get("water_reminder_minutes") else "tắt"),
                  f"Nhắc sao nhãng: {NUDGE_NAMES[cfg.get('nudge_level', 'vua')]} (/nudge) · Cảnh báo tiến độ: "
                  + (f"bật, mốc {', '.join(cfg['pace_checkpoints'])}, mục tiêu {cfg['pace_target_vdi_hours']:g}h VDI"
                     if cfg.get("pace_check_enabled", True) else "tắt") + " (/pace)",
                  f"AI đánh giá ngày/tuần: {'bật' if cfg.get('ai_review_enabled', True) else 'tắt'} (/aireview) · "
                  f"Khích lệ tự động: {'bật' if cfg.get('encouragement_enabled', True) else 'tắt'} [{styles}] (/encourage)",
                  f"Giọng: {p['giong']} (/style) · Hỏi AI: {'bật' if self.ask_mode() else 'tắt'} (/ask) · "
                  f"Gọi bạn là \u201c{p['goi_nguoi_dung']}\u201d"]

        try:
            year = int(day[:4])
            hol = f"Lịch lễ {year}: {holidays.source_label(cfg, year)}"
            nxt = holidays.next_holiday(cfg, day)
            if nxt:
                hol += f" · lễ tới: {nxt[1]} {nxt[0]:%d/%m}"
            lines.append(hol)
        except Exception as e:
            log.debug("Không đọc được lịch lễ cho /status: %s", e)

        lines += ["", "🤖 AI", ai_client.status_text(cfg)]

        lines += ["", "🖥️ HỆ THỐNG"]
        if self.state.get("platform"):
            lines.append(f"Máy: {self.state['platform']}")
        for w in list(self.state.get("probe_warnings") or [])[:5]:
            lines.append(f"⚠️ {w}")
        if self.state.get("perf"):
            lines.append(self.state["perf"])
        try:
            from . import housekeeping
            use = housekeeping.data_usage(cfg)
            lines.append(f"Dung lượng app: {housekeeping.fmt_size(use['total_bytes'])} "
                         f"(DB {housekeeping.fmt_size(use['db_bytes'])}, backup {housekeeping.fmt_size(use['backups_bytes'])}, "
                         f"log {housekeeping.fmt_size(use['logs_bytes'])}) · tự dọn mỗi ngày · phiên bản {__version__}")
        except Exception as e:
            log.debug("Không đo được dung lượng: %s", e)
            lines.append(f"Phiên bản {__version__}")
        return "\n".join(lines)

    def _alerts_today(self, day):
        """Đếm cảnh báo hôm nay từ audit.log (đọc phần cuối file, nhẹ)."""
        out = {}
        path = os.path.join(self.cfg["data_dir"], "audit.log")
        try:
            with open(path, "rb") as f:
                f.seek(max(0, os.path.getsize(path) - 400_000))
                tail = f.read().decode("utf-8", "replace")
        except OSError:
            return out
        for line in tail.splitlines():
            if line.startswith(day) and "| ALERT_" in line:
                kind = line.split("| ALERT_", 1)[1].split(" ", 1)[0].lower()
                out[kind] = out.get(kind, 0) + 1
        return out

    # ------------------------------------------------------------ gửi theo lịch (gọi từ hàng đợi nền)

    def send_daily_summary(self, day, title=""):
        """Trả False nếu chưa gửi được (đã gỡ dấu sent_log để thử lại)."""
        path, a = write_report(self.db, self.cfg, day)
        if not a["has_data"]:
            return True
        self.auto_energy(day, a)
        note = get_note(self.db, day)
        text = summary_text(a, note, streak(self.db, self.cfg, day))
        ot_text = ot_history_text(ot_history(self.db, self.cfg, day))
        if ot_text:
            text += "\n\n" + ot_text
        if not note.get("tomorrow"):
            text += "\n\nChưa ghi việc đầu tiên sáng mai. Gõ: /tmrtask nội dung"
        if title:
            text = title + "\n" + text
        if self.send(text) is None:  # Telegram lỗi: gỡ dấu đã gửi để lần sau gửi lại, không mất tổng kết
            unmark_sent(self.db, day, "summary")
            log.warning("Tổng kết %s chưa gửi được, sẽ thử lại.", day)
            return False
        if not self.send_ai_review("day", day):  # AI tắt / lỗi: báo cáo vẫn kết thúc bằng lời chúc
            self.send(motivation.local_wish(day))
        path, _ = write_report(self.db, self.cfg, day)  # lần 2 để chèn lời khuyên AI vào HTML
        self.send_file(path, f"Báo cáo {day}")
        audit("DAILY_SUMMARY_SENT", day)
        return True

    def auto_energy(self, day, a):
        """Lúc tổng kết ngày: chưa chấm năng lượng thì tự tính từ số liệu tập trung, lưu (energy_source = auto) rồi
        báo bạn kèm cách tính. Trả True nếu đã tự tính."""
        if not self.cfg.get("energy_auto_enabled", True) or get_note(self.db, day).get("energy") not in (None, ""):
            return False
        est = energy.estimate(a, self.cfg.get("energy_capacity_hours", 4))
        if not est:
            return False
        save_note(self.db, day, {"energy": est["energy"], "energy_source": "auto"})
        audit("ENERGY_AUTO", f"{day} {est['energy']}/5 tải {est['load_h']:.2f}h")
        when = "Hôm nay" if day == self.today() else f"Ngày {dt.date.fromisoformat(day):%d/%m}"
        self.send(energy.message(est, when))
        return True

    def send_weekly(self, day, title=""):
        facts = week_facts(self.db, self.cfg, day)
        tip = golden_tip(golden_hours(self.db, self.cfg, day))
        ot_text = ot_history_text(ot_history(self.db, self.cfg, day))
        if self.send((title + "\n" if title else "") + week_text(facts) + (f"\n\n{ot_text}" if ot_text else "")
                     + (f"\n\n{tip}" if tip else "")) is None:
            unmark_sent(self.db, facts["week"], "weekly")
            log.warning("Tổng kết tuần %s chưa gửi được, sẽ thử lại.", facts["week"])
            return False
        if not (facts.get("work_days") and self.send_ai_review("week", day)):
            self.send(motivation.local_wish(day))  # giữa tuần (/week thứ Ba) thì chúc buổi tối, thứ Sáu chúc cuối tuần
        try:  # file HTML báo cáo tuần (đã chèn đánh giá AI tuần nếu có)
            path, _ = write_week_report(self.db, self.cfg, day)
            self.send_file(path, f"Báo cáo tuần {facts['week']}")
        except Exception as e:  # lỗi tạo file không được chặn tổng kết tuần
            log.warning("Không tạo được báo cáo tuần HTML: %s", e, exc_info=True)
        audit("WEEKLY_SENT", facts["week"])
        return True

    def catch_up(self, today):
        """Gọi lúc tracker khởi động: gửi bù tổng kết ngày làm việc trước / tổng kết tuần trước nếu hôm đó máy
        tắt sớm hoặc là ngày nghỉ nên chưa gửi."""
        base = dt.date.fromisoformat(today)
        for i in range(1, 8):  # ngày làm việc gần nhất trước hôm nay có số liệu
            ds = (base - dt.timedelta(days=i)).isoformat()
            if off_day(self.db, self.cfg, ds):
                continue
            if analyze(self.db, self.cfg, ds)["has_data"]:
                if mark_sent(self.db, ds, "summary"):
                    log.info("Gửi bù tổng kết ngày %s", ds)
                    audit("CATCH_UP", f"summary {ds}")
                    self.send_daily_summary(ds, title=f"📌 Gửi bù tổng kết ngày {ds} (hôm đó máy tắt trước giờ tổng kết):")
                break
        last_week_day = (base - dt.timedelta(days=base.weekday() + 1)).isoformat()  # Chủ nhật tuần trước
        facts = week_facts(self.db, self.cfg, last_week_day)
        if facts.get("work_days") and mark_sent(self.db, facts["week"], "weekly"):
            log.info("Gửi bù tổng kết tuần %s", facts["week"])
            audit("CATCH_UP", f"weekly {facts['week']}")
            self.send_weekly(last_week_day, title=f"📌 Gửi bù tổng kết tuần {facts['week']}:")

    def morning_info(self, day):
        """Thông tin tích cực cho lời chào buổi sáng (không đưa điểm yếu cho AI)."""
        d = dt.date.fromisoformat(day)
        info = {"today": day, "weekday": ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy",
                                           "Chủ nhật"][d.weekday()]}
        first = last_tomorrow(self.db, day)
        if first:
            info["first_task"] = first
        for i in range(1, 8):  # ngày làm việc gần nhất có số liệu
            prev = (d - dt.timedelta(days=i)).isoformat()
            if off_day(self.db, self.cfg, prev):
                continue
            a = analyze(self.db, self.cfg, prev)
            if a["has_data"]:
                good = a["deep"] >= a["goal_h"] * 3600
                info["yesterday"] = (f"{prev}: tập trung sâu {fmt_dur(a['deep'])}"
                                     + (", đạt mục tiêu" if good else "")
                                     + (f", có làm thêm ngoài giờ {fmt_dur(a['ot'])} trong VDI" if a.get("ot") else ""))
                break
        prev_day, items = pending.previous_pending(self.db, self.cfg, day, off_day)
        if items:
            info["pending_from_previous_workday"] = {
                "date": prev_day, "items": [pending.item_label(it) for it in items[:pending.MAX_ITEMS]]}
        s = streak(self.db, self.cfg, day)
        if s:
            info["streak_days"] = s
        if d.weekday() == 4:
            info["note"] = "hôm nay thứ Sáu, ngày cuối tuần làm việc"
        leave = get_note(self.db, day).get("leave_part")
        if leave in LEAVE_NAMES:
            info["leave"] = (f"hôm nay {LEAVE_NAMES[leave]}, mục tiêu tập trung còn một nửa"
                             + (", bắt đầu làm từ buổi chiều" if leave == "am" else ", chỉ làm buổi sáng"))
        nxt = holidays.next_holiday(self.cfg, (d + dt.timedelta(days=1)).isoformat(), within_days=7)
        if nxt:
            info["upcoming_holiday"] = f"{nxt[1]} ({nxt[0]:%d/%m})"
        return info

    def overtime_line(self, day):
        """Làm bù ngoài giờ trong VDI từ ngày làm việc trước tới hôm qua (cả cuối tuần / ngày lễ nếu bạn tự bật bot):
        báo đã tính lại số liệu. Không có -> ""."""
        from .scoring import total_score
        d = dt.date.fromisoformat(day)
        lines = []
        for i in range(1, 8):
            prev = (d - dt.timedelta(days=i)).isoformat()
            off = off_day(self.db, self.cfg, prev)
            a = analyze(self.db, self.cfg, prev)
            label = f"{pending.WEEKDAYS[dt.date.fromisoformat(prev).weekday()].capitalize()} {prev[8:]}/{prev[5:7]}"
            if a["has_data"] and a.get("ot", 0) >= 60:
                daily_stats(self.db, self.cfg, prev, refresh=True)  # chốt lại số liệu ngày đó (có phần làm ngoài giờ)
                when = ", ".join(f"{fmt_t(s)}–{fmt_t(e)}" for s, e in ot_ranges(a))
                when = f" ({when})" if when else ""
                if off:
                    lines.append(f"🌙 {label} ({off}) bạn bật bot làm bù {fmt_dur(a['ot'])} trong VDI{when}, tập trung "
                                 f"sâu {fmt_dur(a['deep'])}. Bot đã ghi nhận giờ làm, không tính sao nhãng.")
                else:
                    sc = total_score(a, get_note(self.db, prev))
                    lines.append(f"🌙 {label} bạn làm thêm ngoài giờ (OT) {fmt_dur(a['ot'])} trong VDI{when}. Bot đã "
                                 f"cộng vào số liệu ngày đó: tập trung sâu {fmt_dur(a['deep'])}, điểm tập trung "
                                 f"{focus_score(a)}, điểm tổng {sc['total']}/100. Ngoài giờ bot chỉ cộng giờ làm, không "
                                 "tính sao nhãng.")
            if not off and a["has_data"]:
                break  # tới ngày làm việc trước là đủ
        if lines:
            hist = ot_history(self.db, self.cfg, (d - dt.timedelta(days=1)).isoformat())
            lines.insert(0, f"⏱ Tổng OT {hist['span']} ngày qua: {fmt_dur(hist['total'])} trong {hist['count']} ngày "
                            "(chi tiết trong báo cáo HTML).")
        return "\n".join(reversed(lines))

    def send_offday_ot(self, day):
        """Cuối buổi làm bù ngày nghỉ (thứ Bảy, Chủ nhật, lễ có bật bot): báo tổng giờ OT + file báo cáo HTML."""
        a = analyze(self.db, self.cfg, day)
        if not a["has_data"] or a.get("ot", 0) < 60:
            return None  # không có gì để báo (không phải lỗi)
        daily_stats(self.db, self.cfg, day, refresh=True)
        d = dt.date.fromisoformat(day)
        label = f"{pending.WEEKDAYS[d.weekday()].capitalize()} {d:%d/%m}"
        when = ", ".join(f"{fmt_t(s)}–{fmt_t(e)}" for s, e in ot_ranges(a))
        text = (f"🌙 Tổng kết làm bù {label} ({a.get('off') or 'ngày nghỉ'}): {fmt_dur(a['ot'])} trong VDI"
                + (f" ({when})" if when else "") + f", tập trung sâu {fmt_dur(a['deep'])}.\n"
                "Ngày nghỉ bot chỉ ghi giờ gõ phím / rê chuột trong VDI, không tính sao nhãng, không chấm điểm. "
                "Làm tiếp sau tin này thì sáng ngày làm việc tới bot báo phần còn lại.")
        ot_text = ot_history_text(ot_history(self.db, self.cfg, day))
        if self.send(text + ("\n\n" + ot_text if ot_text else "")) is None:
            return False
        path, _ = write_report(self.db, self.cfg, day)
        self.send_file(path, f"Báo cáo làm bù {day}")
        audit("OFFDAY_OT_SENT", f"{day} {round(a['ot'] / 60)}m")
        return True

    def send_morning(self, day):
        """Tự gửi lúc bắt đầu ngày làm việc: chào + câu khích lệ / Kinh Thánh (AI có đủ ngữ cảnh)."""
        if not motivation.auto_on(self.cfg):
            return
        info = self.morning_info(day)
        text = motivation.morning_message(self.cfg, self.db, info)
        leave = get_note(self.db, day).get("leave_part")
        if leave in LEAVE_NAMES:  # câu cố định (AI có thể quên nhắc)
            a = analyze(self.db, self.cfg, day)
            text += f"\n\n🌴 Hôm nay {LEAVE_NAMES[leave]}: mục tiêu tập trung sâu còn {a['goal_h']:g}h."
        if info.get("upcoming_holiday"):
            text += f"\n📅 Sắp nghỉ lễ: {info['upcoming_holiday']}."
        ot_line = self.overtime_line(day)
        if ot_line:
            text += "\n\n" + ot_line
        block = pending.pending_text(*pending.previous_pending(self.db, self.cfg, day, off_day))
        if block:  # danh sách cố định do app ghép (AI có thể quên hoặc chép sai)
            text += "\n\n" + block
        self.send(text, raw=True)
        audit("MORNING_SENT", day)

    # ------------------------------------------------------------ AI đánh giá (chỉ AI viết, lỗi thì gửi lại sau)

    def send_ai_review(self, kind, day, retry=False):
        """Gửi đánh giá AI ngày/tuần. AI lỗi -> báo một lần, ghi hẹn gửi lại (retry_ai_reviews). Trả True nếu đã gửi."""
        if kind == "day":
            text, error = motivation.review_day(self.cfg, self.db, day_facts(self.db, self.cfg, day))
            head = f"🤖 AI đánh giá ngày {day}:\n\n" if retry else "🤖 AI đánh giá cuối ngày:\n\n"
        else:
            facts = week_facts(self.db, self.cfg, day)
            text, error = motivation.review_week(self.cfg, self.db, facts)
            head = f"🤖 AI tổng kết tuần {facts['week']}:\n\n"
        if text:
            self.send(head + text, raw=True)
            self._set_retry(kind, day, None)
            return True
        if error is None:  # đã tắt /aireview: không gửi lại nữa
            self._set_retry(kind, day, None)
            return False
        permanent = getattr(error, "permanent", False)  # thiếu/sai key: thử lại cũng vô ích
        log.warning("AI đánh giá %s %s chưa được: %s (permanent=%s)", kind, day, error, permanent)
        if not retry:
            msg = f"AI chưa đánh giá được {'hôm nay' if kind == 'day' else 'tuần này'} ({error})."
            if not permanent:
                msg += " Mình sẽ tự gửi khi AI dùng lại được."
            self.send(msg)
        self._set_retry(kind, day, None if permanent else time.time() + RETRY_REVIEW_SECONDS)
        return False

    def _retries(self):
        try:
            data = json.loads(prefs.get_pref(self.db, "ai_review_retry") or "{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _set_retry(self, kind, day, next_try):
        data = self._retries()
        key = f"{kind}:{day}"
        if next_try is None:
            if key not in data:
                return
            data.pop(key)
        else:
            data[key] = next_try
        prefs.set_pref(self.db, "ai_review_retry", json.dumps(data) if data else None)

    def retry_ai_reviews(self, today):
        """Gọi định kỳ từ tracker: gửi lại đánh giá AI đã lỗi (mỗi 15 phút, chỉ trong 2 ngày gần nhất)."""
        oldest = (dt.date.fromisoformat(today) - dt.timedelta(days=2)).isoformat()
        try:
            for key, next_try in sorted(self._retries().items()):
                kind, _, day = key.partition(":")
                if kind not in ("day", "week") or (kind == "day" and day < oldest) or (
                        kind == "week" and day < (dt.date.fromisoformat(today) - dt.timedelta(days=9)).isoformat()):
                    self._set_retry(kind, day, None)
                    continue
                if time.time() >= next_try:
                    log.info("Thử gửi lại đánh giá AI %s %s", kind, day)
                    self.send_ai_review(kind, day, retry=True)
        finally:
            self._retry_running = 0

    def has_review_retry(self):
        """True chỉ khi có đánh giá tới hạn gửi lại VÀ chưa có lượt gửi lại nào đang chạy (tracker hỏi mỗi 30 giây)."""
        if self._retry_running and time.time() - self._retry_running < 600:  # quá 10 phút coi như lượt cũ đã mất
            return False
        due = [t for t in self._retries().values() if isinstance(t, (int, float)) and time.time() >= t]
        if due:
            self._retry_running = time.time()  # retry_ai_reviews tự gỡ cờ khi xong
        return bool(due)

    def notify_job_error(self, label, exc):
        """Việc chạy nền (tổng kết, cảnh báo...) lỗi: báo người dùng câu dễ hiểu, tối đa 1 lần/giờ mỗi việc."""
        now = time.time()
        last = self._job_errors.get(label, 0)
        if now - last < 3600:
            return
        self._job_errors[label] = now
        try:
            self.send(f"⚠️ Không làm được «{errors.job_name(label)}»: {errors.explain(exc)}.")
        except Exception:  # gửi cũng lỗi (mất mạng): chỉ còn log
            pass

    def send_boost(self, day):
        if not motivation.auto_on(self.cfg):
            return
        a = analyze(self.db, self.cfg, day)
        behind = a["has_data"] and a["deep"] < a["goal_h"] * 3600 * 0.4
        mood = "buổi chiều, đang chậm so với mục tiêu, dễ tuột mood" if behind else "buổi chiều, đang giữ nhịp tốt"
        self.send(self.encourage(f"{mood}; {self.stats_line()}"), raw=True)

    # ------------------------------------------------------------ hỏi từng câu (/plan, /review)

    def start_convo(self, kind, manual=False):
        """manual=True: bạn tự gõ /plan, /review (chờ trả lời 3 giờ). Bot tự hỏi theo lịch: chờ 20 phút."""
        with self._lock:
            questions = list(PLAN_QUESTIONS if kind == "plan" else REVIEW_QUESTIONS)
            if not self.cfg.get("as400_enabled", True):
                questions = [q for q in questions if q[0] != "as400"]
            self.convo = (kind, questions, time.time(), CONVO_TTL_SECONDS if manual else AUTO_CONVO_TTL_SECONDS)
            self.awaiting_edit = False  # bấm "Sửa lại" từ trước rồi bỏ đó: không nuốt câu trả lời của lượt hỏi mới
        log.info("Bắt đầu hỏi %s (%s)", kind, "bạn gõ lệnh" if manual else "tự động theo lịch")
        if kind == "review":
            intro = summary_text(analyze(self.db, self.cfg, self.today()), {}) + "\n\n"
        else:
            intro = ""
            prev = last_tomorrow(self.db, self.today(), with_day=True)
            if prev:
                intro += f"Hôm {_day_label(prev[0], self.today())} bạn hẹn sáng nay làm trước: {persona.keep(prev[1])}\n"
            tip = golden_tip(golden_hours(self.db, self.cfg, self.today()))
            if tip:
                intro += tip + "\n"
        self.send(intro + self.ask_text(questions[0]) + "\n(gõ \"bỏ qua\" để bỏ qua câu này, /cancel để dừng)")

    def ask_text(self, question):
        field, text = question
        note = get_note(self.db, self.today())
        if field == "energy" and note.get("energy_source") == "auto" and note.get("energy") not in (None, ""):
            return (f"Bot đã tự tính năng lượng hôm nay: {note['energy']}/5. {text}\n"
                    "(gõ số của bạn để thay, hoặc \"bỏ qua\" để giữ số bot tính)")
        if field == "plan" and note.get("plan"):
            return (f"Kế hoạch đã lưu hôm nay:\n{persona.keep(note['plan'])}\n\n{text}\n"
                    "(trả lời để thay bằng kế hoạch mới, /cancel để giữ nguyên kế hoạch trên)")
        if field in ("output", "issues") and note.get(field):
            return f"Đã ghi trong ngày:\n{persona.keep(note[field])}\n\n{text} (phần thêm, nếu có)"
        if field == "as400" and note.get("as400_start"):
            return (f"Giờ AS400 đã ghi: {note['as400_start']}–{note.get('as400_end') or '?'}. "
                    "Gõ giờ mới nếu muốn sửa, hoặc \"bỏ qua\".")
        if field == "tomorrow" and note.get("tomorrow"):
            return (f"Việc đầu tiên sáng mai đã ghi: {persona.keep(note['tomorrow'])}. Gõ việc khác nếu muốn đổi, "
                    "hoặc \"bỏ qua\".")
        return text

    def convo_active(self):
        with self._lock:
            if self.convo and time.time() - self.convo[2] > self.convo[3]:
                log.info("Hết hạn chờ trả lời %s, tin nhắn mới được hiểu bình thường", self.convo[0])
                self.convo = None  # hỏi đã lâu không trả lời: thôi, để tin nhắn mới được hiểu bình thường
            return self.convo is not None

    def convo_is_auto(self):
        with self._lock:
            return bool(self.convo) and self.convo[3] == AUTO_CONVO_TTL_SECONDS

    def continue_convo(self, text):
        with self._lock:
            kind, questions = self.convo[:2]
            field, _ = questions[0]
        value = text.strip()
        if value.lower() not in SKIP_WORDS:
            if field == "as400":
                times = parse_times(value)
                if not times:
                    self.send("Mình chưa thấy giờ nào. Gõ kiểu 08:10 17:35, gửi ảnh, hoặc \"bỏ qua\".")
                    return
                save_note(self.db, self.today(), {"as400_start": times[0],
                                                  "as400_end": times[1] if len(times) > 1 else None})
            elif field == "energy":
                m = ENERGY_RE.search(value)
                if not m:
                    self.send("Gõ một số từ 1 đến 5 nhé (hoặc \"bỏ qua\").")
                    return
                save_note(self.db, self.today(), {"energy": int(m.group(1))})
            elif field in ("output", "issues"):  # giữ các dòng đã ghi nhanh trong ngày
                append_note(self.db, self.today(), field, value)
            else:
                save_note(self.db, self.today(), {field: value})
        with self._lock:
            if self.convo and self.convo[1]:
                self.convo[1].pop(0)
        self.next_question()

    def next_question(self):
        with self._lock:
            if not self.convo:
                return
            kind, questions = self.convo[:2]
            if questions:
                q = questions[0]
            else:
                q, self.convo = None, None
        if q:
            self.send(self.ask_text(q))
            return
        if kind == "plan":
            self.send("Đã lưu kế hoạch. Bắt đầu với việc số 1 trong 25 phút đầu tiên nhé.")
            audit("PLAN_SAVED", self.today())
        else:
            audit("REVIEW_SAVED", self.today())
            mark_sent(self.db, self.today(), "review")  # /review tự gõ xong: lịch 16:45 không hỏi lại
            if mark_sent(self.db, self.today(), "summary"):
                self.send_daily_summary(self.today())
            else:
                write_report(self.db, self.cfg, self.today())
                self.send("Đã lưu tổng kết. Gõ /report để xem báo cáo.")

    # ------------------------------------------------------------ xác nhận trước khi ghi

    def ask_confirm(self, action, args, original, source=None, warning=None):
        with self._lock:
            now = time.time()
            for k in [k for k, v in self.pending.items() if now - v[2] > PENDING_TTL_SECONDS]:
                del self.pending[k]
            pid = uuid.uuid4().hex[:10]
            self.pending[pid] = (action, args, now, original, self.today())
        log.info("Hỏi xác nhận %s %s", action.name, json.dumps(args, ensure_ascii=False)[:200])
        if warning:
            log.info("Cảnh báo trên thẻ xác nhận %s: %s", action.name, warning)
        self.send(confirm_card(action, args, original, source, warning, today=self.today()), markup=CONFIRM_KEYBOARD(pid))

    def cancel_pending(self):
        with self._lock:
            had = bool(self.pending) or self.awaiting_edit or self.convo is not None
            self.pending.clear()
            self.awaiting_edit = False
            self.convo = None
        return had

    def handle_callback(self, cq):
        chat_id = str(((cq.get("message") or {}).get("chat") or {}).get("id", ""))
        self._quiet("answerCallbackQuery", {"callback_query_id": cq.get("id")})
        if not self.chat_id or chat_id != self.chat_id:
            audit("REJECT_STRANGER", f"callback chat_id={chat_id}")
            return
        verb, _, pid = (cq.get("data") or "").partition(":")
        msg = cq.get("message") or {}
        self._quiet("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg.get("message_id"),
                                               "reply_markup": {"inline_keyboard": []}})
        with self._lock:
            item = self.pending.pop(pid, None)
        if not item or time.time() - item[2] > PENDING_TTL_SECONDS:
            self.send("Yêu cầu này đã hết hạn hoặc đã xử lý. Nhắn lại nhé.")
            return
        action, args, _, original, day = item
        log.info("Bấm %s cho %s", verb, action.name)
        if verb == "ok":
            audit("CONFIRMED", f"{action.name} {json.dumps(args, ensure_ascii=False)[:200]}")
            self._local.day = day if day != dt.date.today().isoformat() else None  # ghi vào đúng ngày của tin gốc
            try:
                self.run_action(action, args)
            finally:
                self._local.day = None
            if action.name == "ghi_gio_as400" and self._convo_at("as400"):  # đang hỏi tổng kết: sang câu sau
                with self._lock:
                    self.convo[1].pop(0)
                self.next_question()
        elif verb == "edit":
            with self._lock:
                self.awaiting_edit = time.time()  # hết hạn như thẻ xác nhận
            self.send(f"Bạn gõ lại giúp mình (ví dụ: {example(action)}, hoặc nhắn tự nhiên).")
        else:
            self.send("Đã huỷ, không ghi gì.")
            if action.name == "ghi_gio_as400" and self._convo_at("as400"):
                self.send(self.ask_text(self.convo[1][0]))

    def _convo_at(self, field):
        with self._lock:
            return bool(self.convo and self.convo[1] and self.convo[1][0][0] == field)

    # ------------------------------------------------------------ chạy action

    def run_action(self, action, args):
        stale = getattr(self._local, "stale", None)
        if stale and action.name in STALE_SKIP:
            log.info("Bỏ qua %s cũ (gửi lúc %s)", action.name, stale)
            self.send(f"Bỏ qua lệnh «{action.title}» bạn gửi lúc {stale} (khi đó app chưa chạy). "
                      f"Cần thì gửi lại {action.command} nhé.")
            return
        log.info("Action %s %s", action.name, json.dumps(args, ensure_ascii=False)[:300])
        action.run(self, args)
        if stale and action.writes:
            self.send(f"(Tin nhắn gửi lúc {stale} khi app chưa chạy, nên mình ghi vào ngày {self.today()}.)")

    def handle_command(self, cmd, arg):
        action = BY_COMMAND.get(cmd)
        if not action:
            self.send("Không có lệnh này.\n\n" + help_text(self.cfg))
            return
        args, error = validate(action, parse_command_args(action, arg, today=self.today()))
        error = error or self._precheck(action, args)
        if error:
            log.info("Lệnh %s sai tham số: %s", cmd, error)
            self.send(f"{error}\nVí dụ: {example(action)}")
            return
        self.run_action(action, args)

    def _precheck(self, action, args):
        """Kiểm tra cần cấu hình thật (vd. /giobot: giờ tắt phải sau giờ tổng kết) trước khi hỏi OK / chạy."""
        if not action.check:
            return None
        error = action.check(args, self.cfg)
        if error:
            log.info("%s bị từ chối: %s", action.name, error)
        return error

    def handle_text(self, text):
        action, args, source, error = intent.understand(self.cfg, text, today=self.today())
        if action is None:
            self.send("Mình chưa hiểu tin nhắn này (AI không dùng được lúc này và không khớp từ khoá nào). "
                      "Bạn dùng lệnh giúp mình nhé.\n\n" + help_text(self.cfg))
            return
        log.info("Hiểu tin nhắn bằng %s: %s %s", source, action.name, json.dumps(args, ensure_ascii=False)[:200])
        audit("PARSED", f"{source}: {action.name} {json.dumps(args, ensure_ascii=False)[:200]}")
        error = error or self._precheck(action, args)
        if error:
            self.send(f"Mình hiểu bạn muốn: {action.title} ({action.name}). Nhưng {error[0].lower() + error[1:]}\n"
                      f"Bạn gõ lại kèm đủ thông tin, hoặc dùng lệnh {action.command}.")
            return
        if action.needs_confirm(args) or (action.name == "hoi_ai" and ask_toggle(args.get("text"))):
            self.ask_confirm(action, args, text, source, intent.cross_check(text, action, args, source, self.today()))
        else:
            if action.name not in ("hoi_ai", "tro_chuyen"):  # chỉ xem: chạy luôn, nhưng vẫn cho thấy bot hiểu thành gì
                self.send(understood_line(action, args))
            self.run_action(action, args)

    # ------------------------------------------------------------ nhận tin

    def handle_photo(self, msg):
        """Ảnh (hoặc file ảnh gửi dạng tài liệu) giờ AS400 -> AI đọc giờ -> hỏi OK trước khi ghi."""
        if not self.cfg.get("as400_photo_ai") or not ai_client.provider(self.cfg):
            self.send("Mình chưa đọc ảnh được (chưa bật AI đọc ảnh). Gõ giờ giúp mình: /as400 08:10 17:35")
            return
        self.send("Đang đọc giờ trong ảnh...")
        try:
            if msg.get("photo"):
                file_id = max(msg["photo"], key=lambda p: p.get("file_size", 0))["file_id"]
            else:
                file_id = msg["document"]["file_id"]
            info = self.api.call("getFile", {"file_id": file_id})
            image = self.api.download(info["result"]["file_path"])
            start, end, note = motivation.read_as400_times(self.cfg, image, self.today())
        except ai_client.AIError as e:
            log.info("Đọc ảnh AS400 không được: %s", e)
            self.send(f"Chưa đọc được ảnh: {e}\nGõ giờ giúp mình: /as400 08:10 17:35")
            return
        except Exception as e:
            log.warning("Tải ảnh lỗi: %s", e, exc_info=True)
            self.send(f"Không tải được ảnh: {errors.explain(e)}.\nGõ giờ giúp mình: /as400 08:10 17:35")
            return
        if not start:
            self.send(f"Không thấy giờ của hôm nay trong ảnh. {note}\nGõ giờ giúp mình: /as400 08:10 17:35")
            return
        action = BY_NAME["ghi_gio_as400"]
        args, error = validate(action, {"start": start, "end": end} if end else {"start": start})
        if error:  # AI đọc ra giờ vô lý (ra trước vào...)
            self.send(f"Giờ đọc từ ảnh chưa hợp lý: {error}\nGõ giờ giúp mình: /as400 08:10 17:35")
            return
        # Đang hỏi tổng kết thì chỉ sang câu sau khi bạn bấm OK (handle_callback).
        self.ask_confirm(action, args, "ảnh AS400" + (f" ({note})" if note else ""))

    @staticmethod
    def _is_image_doc(msg):
        doc = msg.get("document") or {}
        return str(doc.get("mime_type") or "").startswith("image/")

    def handle(self, msg):
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        text = unicodedata.normalize("NFC", (msg.get("text") or msg.get("caption") or "")).strip()  # bộ gõ "tổ hợp"
        if not self.chat_id:
            self.send(f"Chat ID của bạn là {chat_id}. Điền TELEGRAM_CHAT_ID={chat_id} vào config/secrets.env "
                      "rồi chạy lại tracker.", chat_id)
            return
        if chat_id != self.chat_id:
            audit("REJECT_STRANGER", f"chat_id={chat_id}")
            return
        name = ((msg.get("from") or {}).get("first_name") or "").strip()[:40]
        if name and name != self.cfg.get("_tg_name"):  # tên Telegram, để AI gọi đúng tên nếu persona chưa ghi
            prefs.set_pref(self.db, "tg_name", name)
            self.cfg["_tg_name"] = name
        sent = msg.get("date")
        if isinstance(sent, (int, float)) and time.time() - sent > STALE_MESSAGE_SECONDS:
            when = dt.datetime.fromtimestamp(sent)
            self._local.day = when.date().isoformat()  # ghi chú thuộc về ngày bạn gửi, không phải ngày đọc
            self._local.stale = when.strftime("%H:%M %d/%m")
            log.info("Tin nhắn cũ gửi lúc %s (app chưa chạy khi đó)", self._local.stale)
        try:
            self._handle(msg, text)
        finally:
            self._local.day = self._local.stale = None

    def _handle(self, msg, text):
        if msg.get("photo") or self._is_image_doc(msg):
            log.info("Telegram: ảnh")
            self.handle_photo(msg)
            return
        if not text:
            log.info("Telegram: tin không có chữ (sticker, file...), bỏ qua")
            if msg.get("document") or msg.get("voice") or msg.get("video"):
                self.send("Mình chỉ đọc được chữ và ảnh (giờ AS400). Bạn gõ chữ giúp mình nhé.")
            return
        cmd, arg = (re.split(r"\s+", text, maxsplit=1) + [""])[:2]  # "/issue⏎VDI chậm" cũng là lệnh
        cmd = cmd.split("@")[0].lower()
        is_cmd = cmd.startswith("/")
        log.info("Telegram nhận: %s", text[:200].replace("\n", " ⏎ "))
        if is_cmd and cmd != "/skip":
            with self._lock:
                self.awaiting_edit = False
                if cmd != "/cancel":
                    self.convo = None if cmd in ("/plan", "/review") else self.convo
            self.handle_command(cmd, arg.strip())
            return
        with self._lock:
            editing, self.awaiting_edit = self.awaiting_edit, False
        if editing and time.time() - editing > PENDING_TTL_SECONDS:
            log.info("Chờ sửa lại đã quá hạn, hiểu tin nhắn bình thường")
            editing = False
        if editing:  # vừa bấm "Sửa lại": tin này là bản sửa, kể cả khi đang hỏi dở
            self.handle_text(text)
        elif self.convo_active() and not (self.convo_is_auto() and intent.looks_like_question(text)):
            # đang hỏi kế hoạch / tổng kết: câu trả lời vào đúng chỗ kể cả khi bật /ask; chỉ câu HỎI mới gửi AI
            self.continue_convo(text)
        elif self.ask_mode():
            self.answer_question(text)
        else:
            self.handle_text(text)

    # ------------------------------------------------------------ hỏi AI (/ask)

    def ask_mode(self):
        return bool(self.cfg.get("ask_mode"))

    def answer_question(self, question):
        """Gửi câu hỏi cho AI (mỗi câu độc lập, AI nhận đủ ngữ cảnh), trả lời qua Telegram."""
        if not ai_client.provider(self.cfg):
            self.send("Chưa có API key AI nên mình chưa trả lời được. Xem README mục 2.3 để thêm key (GEMINI_API_KEY trong config/secrets.env).")
            return
        try:
            self.api.call("sendChatAction", {"chat_id": self.chat_id, "action": "typing"}, timeout=10)
        except Exception:  # chỉ là hiệu ứng "đang gõ", lỗi cũng không sao
            pass
        now = dt.datetime.now().astimezone()
        live = {"luc_nay": now.strftime("%Y-%m-%d %H:%M (%Z, UTC%z)"),
                "thu": ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"][now.weekday()],
                "so_lieu_tap_trung_hom_nay": self.stats_line()}
        text, ok = motivation.ask_ai(self.cfg, question, live)
        audit("ASK_AI", f"{len(question.split())} từ, {'ok' if ok else 'lỗi'}")
        footer = "\n\n(Đang ở chế độ hỏi AI: /ask off để tắt)" if self.ask_mode() and ok else ""
        self.send(text + footer, raw=True)

    # ------------------------------------------------------------ vòng nhận tin

    def poll_once(self):
        res = self.api.call("getUpdates", {"offset": self.offset, "timeout": 50,
                                           "allowed_updates": ["message", "callback_query"]}, timeout=60)
        for upd in res.get("result", []):
            self.offset = upd["update_id"] + 1
            try:
                if upd.get("callback_query"):
                    self.handle_callback(upd["callback_query"])
                elif upd.get("message"):
                    self.handle(upd["message"])
            except Exception as e:
                log.error("Lỗi xử lý tin nhắn: %s", e, exc_info=True)
                audit("BOT_ERROR", f"{type(e).__name__}: {e}")
                self.send(f"⚠️ Mình chưa làm được việc vừa rồi: {errors.explain(e)}.\n"
                          "Bạn thử lại, hoặc dùng lệnh (/help xem danh sách).")

    def run(self):
        log.info("Bot Telegram đang chạy.")
        self._quiet("setMyCommands", {"commands": bot_commands()})
        wait = 5
        while not self.stopped.is_set():
            try:
                self.poll_once()
                wait = 5
            except urllib.error.HTTPError as e:
                if e.code in (401, 404):
                    log.error("Token bot Telegram sai (HTTP %s). Bot dừng; tracker vẫn chạy.", e.code)
                    audit("TELEGRAM_BAD_TOKEN", e.code)
                    return
                log.warning("Telegram HTTP %s, thử lại sau %ss", e.code, wait)
                self.stopped.wait(wait)
                wait = min(wait * 2, 300)
            except Exception as e:  # mất mạng, timeout, JSON lạ...
                log.warning("Telegram poll lỗi: %s (thử lại sau %ss)", e, wait)
                self.stopped.wait(wait)
                wait = min(wait * 2, 300)

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="telegram").start()
        return self

    def stop(self):
        self.stopped.set()
