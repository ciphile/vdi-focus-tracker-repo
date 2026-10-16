"""Các lệnh chạy trên máy (cài đặt, kiểm tra). Dùng hằng ngày thì chỉ qua bot Telegram.

  python focus_tracker.py run            chạy tracker (Task Scheduler gọi lệnh này)
  python focus_tracker.py run --manual   bạn tự bật (start_tracker, lam_bu_ngoai_gio): ngày nghỉ vẫn ghi giờ làm bù
  python focus_tracker.py check          kiểm tra cấu hình, Telegram, AI, nhận diện VDI
  python focus_tracker.py probe          in trạng thái mỗi 2 giây (thử thu nhỏ / chuyển cửa sổ VDI)
  python focus_tracker.py report [NGÀY]  tạo báo cáo HTML (mặc định hôm nay); thêm --open để mở bằng trình duyệt
  python focus_tracker.py week           in tổng kết tuần này
  python focus_tracker.py demo           báo cáo mẫu từ dữ liệu giả (không đụng dữ liệu thật)
  python focus_tracker.py housekeeping   dọn dẹp ngay
  python focus_tracker.py clearcache     xoá cache AI
  python focus_tracker.py ai-models      xem key Gemini dùng được model nào (không tốn quota)
  python focus_tracker.py ai-test        gọi AI thử 1 lần
  python focus_tracker.py selftest       chạy bộ test tự động
  python focus_tracker.py verify [PHẦN]  kiểm tra toàn bộ trên máy thật (có hướng dẫn thao tác), ghi kết quả ra
                                         data/logs/kiem_tra-*.txt (nhấp đúp kiem_tra_may.bat / .command).
                                         PHẦN (tuỳ chọn): check ai mom autostart vdi tests, ví dụ `verify vdi ai`
"""
import datetime as dt
import json
import os
import sys
import time

from . import __version__, logs
from .config import ROOT, ConfigError, load_config


CHAT_ID_WAIT_SECONDS = 600  # chế độ lấy chat ID: chờ tin nhắn đầu tiên tối đa 10 phút


def _chat_id_setup(cfg, api=None, wait=CHAT_ID_WAIT_SECONDS, clock=time.monotonic, sleep=time.sleep):
    """Có token nhưng chưa có TELEGRAM_CHAT_ID: chờ tin nhắn đầu tiên gửi cho bot, trả lời chat ID rồi thoát.

    Chạy ở mọi giờ, mọi ngày. Tracker thường chỉ chạy 08:00-23:59 ngày làm việc, nên trước đây lần cài đặt đầu
    vào buổi tối / cuối tuần thoát ngay, bot không trả lời /start. Không tự ghi secrets.env: người dùng tự điền."""
    import urllib.error
    from .errors import explain
    from .telegram_bot import TelegramAPI
    log = logs.get_logger()
    api = api or TelegramAPI(cfg["telegram_bot_token"])
    bad_token = ("✗ Telegram không nhận TELEGRAM_BOT_TOKEN (token sai hoặc bot đã bị xoá). "
                 "Chép lại token từ @BotFather vào config/secrets.env rồi chạy lại.")
    try:
        me = api.call("getMe", timeout=15)
    except urllib.error.HTTPError as e:
        print(bad_token if e.code in (401, 404) else f"✗ Telegram: {explain(e)}")
        return 1
    except Exception as e:
        print(f"✗ Không kết nối được Telegram: {explain(e)}. Kiểm tra mạng rồi chạy lại.")
        return 1
    username = (me.get("result") or {}).get("username") or "?"
    print("=" * 64)
    print("CHƯA CÓ TELEGRAM_CHAT_ID trong config/secrets.env")
    print(f"Mở Telegram, tìm bot @{username}, bấm Start (hoặc gõ /start) rồi gửi.")
    print(f"Đang chờ tin nhắn của bạn (tối đa {wait // 60} phút)... Đừng tắt cửa sổ này.")
    print("=" * 64)
    log.info("Chế độ lấy chat ID: chờ tin nhắn cho bot @%s", username)
    offset, end, told_net = None, clock() + wait, False
    while clock() < end:
        params = {"timeout": 25, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        try:
            res = api.call("getUpdates", params, timeout=35)
        except urllib.error.HTTPError as e:
            if e.code in (401, 404):
                print(bad_token)
                return 1
            if e.code == 409:
                print("✗ Có chương trình khác đang đọc tin nhắn của bot này (tracker đang chạy ẩn, hoặc một bot khác "
                      "dùng chung token). Tắt chương trình đó (Task Manager > python.exe) rồi chạy lại.")
                return 1
            log.warning("Chế độ lấy chat ID: Telegram HTTP %s", e.code)
            sleep(5)
            continue
        except Exception as e:  # mất mạng, timeout: thử lại tới hết giờ chờ
            if not told_net:
                print(f"  ! {explain(e)}. Đang thử lại...")
                told_net = True
            log.warning("Chế độ lấy chat ID: %s", e)
            sleep(5)
            continue
        for upd in res.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            chat = msg.get("chat") or {}
            if "id" not in chat:
                continue
            chat_id = str(chat["id"])
            who = ((msg.get("from") or {}).get("first_name") or "").strip()
            try:
                api.call("sendMessage", {"chat_id": chat_id, "text": (
                    f"Chat ID của bạn là {chat_id}.\nMở file config/secrets.env, điền dòng TELEGRAM_CHAT_ID={chat_id} "
                    "rồi lưu file và chạy lại start_tracker.")}, timeout=15)
            except Exception as e:  # màn hình vẫn in chat ID, không sao
                log.warning("Không trả lời được chat ID qua Telegram: %s", e)
            try:  # báo Telegram đã đọc tin này, lần chạy sau không đọc lại
                api.call("getUpdates", {"offset": offset, "timeout": 0}, timeout=15)
            except Exception:
                pass
            print()
            print("=" * 64)
            print(f"  ĐÃ NHẬN TIN NHẮN{' CỦA ' + who if who else ''}. CHAT ID CỦA BẠN LÀ:   {chat_id}")
            print()
            mac = sys.platform == "darwin"
            print(f"  Mở config/secrets.env bằng {'TextEdit' if mac else 'Notepad'}, sửa dòng thành:")
            print(f"  TELEGRAM_CHAT_ID={chat_id}")
            print(f"  Lưu file ({'Cmd+S' if mac else 'Ctrl+S'}), rồi chạy lại start_tracker.")
            print("=" * 64)
            log.info("Chế độ lấy chat ID: đã trả chat ID cho %s", who or "?")
            logs.audit("CHAT_ID_SETUP", "ok")
            return 0
    print(f"Hết {wait // 60} phút mà chưa thấy tin nhắn nào gửi cho bot @{username}. "
          "Kiểm tra đúng tên bot rồi chạy lại start_tracker.")
    return 1


class Terminated(BaseException):
    """Hệ điều hành yêu cầu dừng (SIGTERM): tắt máy, đăng xuất, gỡ tự khởi động. Kế thừa BaseException như
    KeyboardInterrupt để không bị các khối `except Exception` trong vòng lặp nuốt mất."""


def _stop_on_sigterm(signal_mod=None):
    """launchd (Mac) gửi SIGTERM khi đăng xuất / tắt máy / gỡ tự khởi động. Mặc định Python chết ngay, mất mẫu còn
    trong bộ đệm và không chốt ngày. Đổi thành một exception để các khối finally (ghi mẫu, chốt ngày) chạy hết.
    Trả hàm khôi phục cách xử lý cũ."""
    import signal
    signal_mod = signal_mod or signal

    def handler(signum, frame):
        raise Terminated()
    try:
        old = signal_mod.signal(signal_mod.SIGTERM, handler)
    except (ValueError, OSError, AttributeError) as e:  # không ở luồng chính / hệ điều hành không hỗ trợ
        logs.get_logger().debug("Không gắn được xử lý SIGTERM: %s", e)
        return lambda: None

    def restore():
        try:
            signal_mod.signal(signal_mod.SIGTERM, old)
        except (ValueError, OSError, TypeError):
            pass
    return restore


def cmd_run(cfg, manual=False):
    from .tracker import InstanceLock, Tracker, lower_priority
    log = logs.get_logger()
    lock = InstanceLock()
    if not lock.acquire():
        log.info("Tracker khác vẫn đang chạy sau khi chờ, bản này thoát.")
        return 0
    if cfg["telegram_bot_token"] and not cfg["telegram_chat_id"]:
        return _chat_id_setup(cfg)  # lần cài đặt đầu: chưa có chat ID thì tracker không có ai để báo
    lower_priority()
    restore_sigterm = _stop_on_sigterm()
    log.info("===== FOCUS TRACKER %s KHỞI ĐỘNG (pid %s) =====", __version__, os.getpid())
    if cfg.get("_unknown_keys"):
        log.warning("settings.json có khoá không dùng tới (gõ sai?): %s", cfg["_unknown_keys"])
    audit = logs.audit
    audit("START", f"v{__version__} pid={os.getpid()}")
    bot = None
    try:
        if cfg["telegram_bot_token"]:
            from .telegram_bot import TelegramBot
            bot = TelegramBot(cfg, state=None)
        def open_bot():
            # Chỉ mở bot khi tracker chắc chắn chạy hôm nay: bật sớm (đăng nhập 07:30, giờ bật 08:00), cuối tuần,
            # ngày lễ -> tracker thoát im lặng, không nhận tin nhắn dở dang. Giờ bật/tắt đã đổi qua /giobot đã được
            # áp vào cfg lúc tạo bot (prefs.apply) nên tracker xét đúng khung giờ mới.
            bot.start()
            if cfg.get("_unknown_keys"):
                bot.send("⚙️ settings.json có dòng app không hiểu (có thể gõ sai tên): "
                         + ", ".join(cfg["_unknown_keys"]) + ". Các dòng này đang bị bỏ qua.")
        tracker = Tracker(cfg, bot=bot, on_start=open_bot if bot else None, manual=manual)
        if bot:
            bot.state = tracker.state
        result = tracker.run()
        log.info("Tracker dừng: %s", result)
        return 0
    except KeyboardInterrupt:
        log.info("Dừng bằng Ctrl+C.")
        return 0
    except Terminated:
        log.info("Dừng theo yêu cầu của hệ điều hành (tắt máy, đăng xuất hoặc gỡ tự khởi động); đã ghi xong dữ liệu.")
        return 0
    except Exception as e:  # "di thư": chạy ẩn không có màn hình thì lý do chết phải nằm trong log
        log.critical("TRACKER SẬP: %s: %s", type(e).__name__, e, exc_info=True)
        audit("CRASH", f"{type(e).__name__}: {e}")
        from .errors import explain
        if bot:  # báo người dùng qua Telegram, câu dễ hiểu
            bot.send(f"🛑 Focus Tracker vừa dừng vì lỗi: {explain(e)}.\n"
                     "Tracker sẽ tự chạy lại lần bật máy / đăng nhập / giờ tự bật (auto_start_at) tới. Muốn chạy ngay: nhấp đúp "
                     f"{'start_tracker.command' if sys.platform == 'darwin' else 'start_tracker.vbs'}. Chi tiết: data/logs/focus.log")
        return 1
    finally:
        restore_sigterm()
        audit("STOP")


def _print_probe_info(probe):
    print(f"Hệ điều hành: {probe.platform_name} · cách đọc: {probe.method}")
    for w in probe.warnings:
        print(f"  ! {w}")


def cmd_probe(cfg):
    from .probe import ProbeError, make_probe
    try:
        probe = make_probe(cfg)
    except ProbeError as e:
        print(f"✗ {e}")
        return 1
    _print_probe_info(probe)
    keys = "Cmd+Ctrl+Q" if probe.platform_name == "macOS" else "Win+L"
    print(f"Thử: làm trong VDI, thu nhỏ VDI, click sang app khác, kéo nhỏ VDI, khoá máy ({keys}). Ctrl+C để dừng.")
    shown = len(probe.warnings)
    while True:
        t = time.perf_counter()
        s = probe.sample()
        ms = (time.perf_counter() - t) * 1000
        print(f"{dt.datetime.now():%H:%M:%S} vdi={s['vdi_state']:10} full={str(s['vdi_full']):5} "
              f"idle={s['idle']:6.1f}s locked={s['locked']!s:5} fg={s['fg_proc'][:24]:24} "
              f"({ms:.1f} ms) {s['fg_title'][:40]}")
        for w in probe.warnings[shown:]:  # cảnh báo mới phát hiện khi đang chạy
            print(f"  ! {w}")
        shown = len(probe.warnings)
        time.sleep(2)


def cmd_check(cfg):
    """Kiểm tra nhanh mọi thứ cần cho lần chạy đầu."""
    ok = True
    print(f"Focus Tracker {__version__} · Python {sys.version.split()[0]} · {sys.platform}")
    print(f"Thư mục dữ liệu: {cfg['data_dir']}")
    if sys.version_info < (3, 9):
        print("✗ Cần Python 3.9 trở lên.")
        ok = False
    from .probe import ProbeError, make_probe
    try:
        probe = make_probe(cfg)
        s = probe.sample()
    except ProbeError as e:
        print(f"✗ {e}")
        ok = False
    except Exception as e:
        logs.get_logger().error("check: đọc trạng thái máy lỗi: %s", e, exc_info=True)
        print(f"✗ Đọc trạng thái máy lỗi: {type(e).__name__}: {e}")
        ok = False
    else:
        _print_probe_info(probe)
        print(f"✓ Đọc trạng thái máy: VDI {s['vdi_state']}, app trước mặt {s['fg_proc'] or '?'}")
        if s["vdi_state"] == "absent":
            app = "Citrix Viewer (Citrix Workspace for Mac)" if probe.platform_name == "macOS" else \
                "Citrix Desktop Viewer"
            print(f"  ! Không thấy cửa sổ VDI. Mở {app} rồi chạy lại 'check', hoặc chạy 'probe'.")
    if cfg["telegram_bot_token"]:
        from .telegram_bot import TelegramAPI
        try:
            me = TelegramAPI(cfg["telegram_bot_token"]).call("getMe", timeout=15)
            print(f"✓ Telegram: bot @{me['result'].get('username')}")
        except Exception as e:
            print(f"✗ Telegram: {e} (token sai hoặc máy chặn api.telegram.org)")
            ok = False
        if not cfg["telegram_chat_id"]:
            print(f"  ! Chưa có TELEGRAM_CHAT_ID: nhấp đúp {'start_tracker.command' if sys.platform == 'darwin' else 'start_tracker.bat'}, "
                  "nhắn /start cho bot để lấy (chạy được mọi giờ, mọi ngày).")
    else:
        print("✗ Chưa có TELEGRAM_BOT_TOKEN trong config/secrets.env (bot là cách duy nhất để dùng app).")
        ok = False
    from . import ai_client
    p = ai_client.provider(cfg)
    print(f"{'✓' if p else '!'} AI: {p or 'chưa có key, dùng nội dung có sẵn và bóc tách bằng từ khoá'}")
    from . import persona
    persona_ok, lines = persona.check_lines(persona.PATH)  # đọc PATH lúc gọi (test đổi được)
    print("\n".join(lines))
    ok = ok and persona_ok
    print("Kết quả:", "SẴN SÀNG" if ok else "CẦN SỬA các dòng ✗ ở trên")
    return 0 if ok else 1


VERIFY_STEPS = [  # (giây, việc người dùng làm, trạng thái mong đợi, cửa sổ VDI phóng to?)
    (20, "Bấm vào cửa sổ VDI (phóng to) rồi gõ phím / di chuột liên tục trong VDI", "foreground", True),
    (20, "Thu nhỏ VDI (Windows: nút _ xuống taskbar; Mac: nút vàng xuống Dock), vẫn di chuột bên ngoài",
     "minimized", None),
    (25, "Mở lại VDI, kéo cho cửa sổ VỪA VỪA (không phóng to), rồi gõ phím / di chuột TRONG VDI", "foreground", False),
    (20, "Bấm sang một app ngoài VDI (Chrome, File Explorer / Finder...) và di chuột trong app đó", "background", None),
]
VERIFY_HOLD_SAMPLES = 4    # đạt nếu 4 mẫu CUỐI của bước đều đúng (bạn chuyển chậm lúc đầu nhưng giữ đúng trạng thái)
VERIFY_SETTLE_SECONDS = 4  # bỏ qua vài giây đầu mỗi bước (lúc bạn đang chuyển cửa sổ)


class _Tee:
    """In ra màn hình và ghi file cùng lúc."""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def __call__(self, *parts, end="\n"):
        text = " ".join(str(p) for p in parts)
        try:
            print(text, end=end, flush=True)
        except UnicodeEncodeError:  # console cp1252: vẫn ghi file đủ dấu
            print(text.encode("ascii", "replace").decode(), end=end, flush=True)
        self.f.write(text + end)
        self.f.flush()


def _wait_enter(prompt):
    try:
        input(prompt)
    except EOFError:  # không có bàn phím (chạy ngầm): đi tiếp luôn
        pass


def _beep():
    try:
        import winsound
        winsound.Beep(880, 400)
    except Exception:
        print("\a", end="", flush=True)



def _step_good(rows, want, full):
    """Danh sách mẫu đúng trạng thái mong đợi (và đúng kiểu phóng to nếu bước yêu cầu)."""
    return [r["vdi_state"] == want and (full is None or r["vdi_full"] == full) for r in rows]


def _verify_step_ok(rows, want, full):
    """Đạt nếu >= 70% mẫu đúng, hoặc VERIFY_HOLD_SAMPLES mẫu cuối đều đúng (chuyển cửa sổ chậm nhưng giữ đúng)."""
    good = _step_good(rows, want, full)
    if not good:
        return False
    return sum(good) / len(good) >= 0.7 or (len(good) >= VERIFY_HOLD_SAMPLES and all(good[-VERIFY_HOLD_SAMPLES:]))


def _dump_citrix_windows(probe, out):
    """Windows: liệt kê mọi cửa sổ đang hiện của process Citrix (tiêu đề, kích thước, loại) để hiểu app Citrix ở trước
    là cửa sổ nào (vd Citrix.EngineUI.App.exe)."""
    api = getattr(probe, "api", None)
    if api is None or not hasattr(probe, "proc_name"):
        return
    is_citrix = getattr(probe, "is_citrix", None)  # tên citrix* hoặc file nằm trong thư mục Citrix (Citrix đổi tên)
    try:
        rows = []
        for h in api.top_windows():
            proc = probe.proc_name(h) or ""
            if not api.is_visible(h) or not (proc.startswith("citrix") or (proc and is_citrix and is_citrix(h, proc))):
                continue
            r = api.rect(h) or (0, 0, 0, 0)
            rows.append(f"    {proc} «{api.title(h)[:50]}» {r[2] - r[0]}x{r[3] - r[1]} "
                        f"{'thu nhỏ' if api.is_iconic(h) else 'hiện'}{' · tool window' if api.is_toolwindow(h) else ''}"
                        f" · loại={probe.window_kind(h)}")
        out("  Cửa sổ Citrix đang hiện:" + ("" if rows else " (không có)"))
        for line in rows:
            out(line)
    except Exception as e:
        out(f"  ! Không liệt kê được cửa sổ Citrix: {type(e).__name__}: {e}")


def _dump_mac_windows(probe, out):
    """Mac: số liệu thô để chẩn đoán trên máy thật (không có tiêu đề cửa sổ trừ khi có quyền Screen Recording):
    cửa sổ đang hiện (từ trước ra sau), cửa sổ VDI chỉ có trong danh sách đầy đủ, app đang ở trước, màn hình."""
    api = getattr(probe, "api", None)
    if api is None or not hasattr(probe, "apps") or not hasattr(api, "windows"):
        return
    def fmt(w):
        b = w.get("bounds")
        size = f"{b[2]:.0f}x{b[3]:.0f}@{b[0]:.0f},{b[1]:.0f}" if b else "?"
        title = w.get("title")
        return (f"    {w.get('owner') or '?'} · pid {w.get('pid')} · {size} · alpha {w.get('alpha')}"
                + (f" · «{title[:50]}»" if title else ""))
    try:
        on = api.windows(True, getattr(probe, "_titles_for", None))
        out(f"  Cửa sổ đang hiện (từ trước ra sau, {len(on)}):")
        for w in on[:12]:
            out(fmt(w))
        shown = {(w.get("owner"), w.get("pid"), w.get("bounds")) for w in on}
        vdi_hidden = [w for w in api.windows(False) if probe.is_vdi(w, [])
                      and (w.get("owner"), w.get("pid"), w.get("bounds")) not in shown]
        out("  Cửa sổ VDI trong danh sách đầy đủ (gồm cả thu nhỏ / ẩn / Space khác):" + ("" if vdi_hidden else " (không có)"))
        for w in vdi_hidden[:8]:
            out(fmt(w))
        front = api.front_app() if hasattr(api, "front_app") else None
        out(f"  App đang ở trước (NSWorkspace): {front[1] + ' · pid ' + str(front[0]) if front else 'không đọc được'}")
        out(f"  Màn hình: {api.displays()}")
        titles = api.can_read_titles() if hasattr(api, "can_read_titles") else None
        out(f"  Quyền Screen Recording (đọc tiêu đề cửa sổ): {'có' if titles else ('chưa' if titles is False else 'không rõ')}")
    except Exception as e:
        out(f"  ! Không liệt kê được cửa sổ trên Mac: {type(e).__name__}: {e}")


def _verify_probe(cfg, out):
    from .probe import ProbeError, make_probe
    try:
        probe = make_probe(cfg)
    except ProbeError as e:
        out(f"✗ Không đọc được trạng thái cửa sổ: {e}")
        return False
    out(f"Hệ điều hành: {probe.platform_name} · cách đọc: {probe.method}")
    for w in probe.warnings:
        out(f"  ! {w}")
    first = probe.sample()
    out(f"Lúc này: VDI {first['vdi_state']}, app trước mặt {first['fg_proc'] or '?'}")
    _dump_citrix_windows(probe, out)
    _dump_mac_windows(probe, out)
    try:  # tiêu đề + process thật của cửa sổ VDI (Windows), để chỉnh vdi_title_keywords nếu cần
        for h, kind in probe.vdi_windows():
            out(f"  Cửa sổ VDI: «{probe.api.title(h)}» · process {probe.proc_name(h) or '?'} · "
                f"{'đang hiện' if kind == 'shown' else 'thu nhỏ'}")
    except Exception:
        pass
    if first["vdi_state"] == "absent":
        app = "Citrix Workspace (cửa sổ Citrix Viewer)" if sys.platform == "darwin" else "Citrix Desktop Viewer"
        out(f"✗ Không thấy cửa sổ VDI. Mở VDI bằng {app} rồi chạy lại {_verify_script()}.")
        return False
    all_ok = True
    for n, (secs, what, want, full) in enumerate(VERIFY_STEPS, 1):
        out(f"\n--- Bước {n}/{len(VERIFY_STEPS)} ({secs} giây): {what}")
        _wait_enter("   Đọc xong thì nhấn Enter, rồi trong 5 giây chuyển sang làm như trên. Nghe tiếng bíp là xong bước.")
        for c in range(5, 0, -1):
            out(f"   bắt đầu sau {c}...", end="\r")
            time.sleep(1)
        rows = []
        t_end = time.monotonic() + secs
        while time.monotonic() < t_end:
            t = time.perf_counter()
            s = probe.sample()
            ms = (time.perf_counter() - t) * 1000
            left = int(t_end - time.monotonic())
            rows.append(s)
            line = (f"   còn {left:2d}s  vdi={s['vdi_state']:10} full={str(s['vdi_full']):5} idle={s['idle']:5.1f}s "
                    f"app={s['fg_proc'][:22]:22} ({ms:.1f} ms)")
            if (s.get("fg_proc") or "").startswith("citrix"):  # cửa sổ Citrix đang ở trước: ghi tiêu đề + cờ để biết là gì
                line += f" «{(s.get('fg_title') or '')[:40]}» {s.get('fg_info') or ''}"
            out(line)
            time.sleep(1)
        _beep()
        rows = rows[VERIFY_SETTLE_SECONDS:] or rows
        states = [r["vdi_state"] for r in rows]
        ok = _verify_step_ok(rows, want, full)
        all_ok &= ok
        seen = ", ".join(f"{k} {states.count(k)}" for k in sorted(set(states)))
        out(f"{'✓' if ok else '✗'} Bước {n}: mong đợi {want}" + (f" (phóng to={full})" if full is not None else "")
            + f" · đo được: {seen}")
    return all_ok


def _verify_mom(cfg, out, year=None):
    from . import holidays
    year = year or dt.date.today().year
    try:
        html = holidays._download(cfg.get("mom_holidays_url") or holidays.MOM_URL, holidays.FETCH_TIMEOUT)
        years, rejected = holidays.parse_mom(html)
    except Exception as e:
        from .errors import explain
        out(f"✗ Tải trang MOM: {explain(e)}")
        return False
    for y in sorted(years):
        out(f"  {y}: {len(years[y])} ngày lễ: " + ", ".join(sorted(years[y])))
    for y, why in sorted(rejected.items()):
        out(f"  ! năm {y} bị loại: {why}")
    known = holidays.holidays(cfg, year)
    if year in years and set(years[year]) - set(known):
        out(f"  ! Lịch {year} trên MOM có ngày app chưa biết: {sorted(set(years[year]) - set(known))}")
    ok = year in years
    out(f"{'✓' if ok else '✗'} Trang MOM: đọc được các năm {sorted(years) or 'không năm nào'}")
    return ok


def _verify_autostart(out, cfg=None):
    if sys.platform.startswith("win"):
        import subprocess
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", "FocusTracker", "/FO", "LIST"], capture_output=True,
                               timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            text = r.stdout.decode("mbcs" if hasattr(__import__("codecs"), "mbcs_encode") else "utf-8", "replace")
        except Exception as e:
            out(f"! Không đọc được Task Scheduler: {type(e).__name__}: {e}")
            return False
        if r.returncode != 0:
            out("✗ Chưa cài tự khởi động: nhấp đúp cai_tu_khoi_dong.bat.")
            return False
        for line in text.splitlines():
            if line.split(":")[0].strip() in ("TaskName", "Next Run Time", "Status", "Logon Mode"):
                out("  " + line.strip())
        out("✓ Task Scheduler: đã có task FocusTracker")
        return True
    if sys.platform == "darwin":
        import subprocess
        from . import autostart
        label = autostart.mac_label()
        plist = autostart.mac_plist_path(cfg)
        if not os.path.exists(plist):
            out(f"✗ Chưa cài tự khởi động: nhấp đúp cai_tu_khoi_dong.command (thiếu {plist}).")
            return False
        try:
            r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"], capture_output=True,
                               timeout=20)
        except Exception as e:
            out(f"! Không chạy được launchctl: {type(e).__name__}: {e}")
            return False
        if r.returncode != 0:
            out(f"✗ Có file {plist} nhưng launchd chưa nạp job {label}: nhấp đúp lại cai_tu_khoi_dong.command.")
            return False
        protected = autostart.mac_protected_folder(ROOT)
        if protected:
            out(f"! Thư mục app nằm trong {protected}: macOS có thể chặn tracker tự chạy nền đọc file ở đây. Nên chuyển "
                "cả thư mục ra thư mục nhà (ví dụ ~/focus-tracker) rồi nhấp đúp lại cai_tu_khoi_dong.command.")
        running, code, what = autostart.mac_last_exit(r.stdout.decode("utf-8", "replace"))
        if code not in (None, 0) and not running:
            out(f"✗ launchd đã nạp job {label} nhưng lần tự chạy gần nhất bị lỗi (mã {code}{': ' + what if what else ''}).")
            err = os.path.join(cfg["data_dir"], "logs", "launchd.err.log")
            try:
                with open(err, encoding="utf-8", errors="replace") as f:
                    tail = [ln.rstrip() for ln in f.readlines()[-5:] if ln.strip()]
            except OSError:
                tail = []
            for ln in tail:
                out(f"    {ln[:200]}")
            if any("not permitted" in ln.lower() for ln in tail):
                out("  macOS không cho tracker chạy nền đọc thư mục app: chuyển thư mục ra ~/focus-tracker (README mục 2.5).")
            else:
                out(f"  Xem thêm {err} và data/logs/focus.log.")
            return False
        state = "đang chạy" if running else ("chưa tự chạy lần nào" if code is None else "lần chạy gần nhất kết thúc bình thường")
        out(f"✓ launchd: job {label} đã nạp, {state} ({plist})")
        return True
    out("  (Linux: không có tự khởi động để kiểm tra)")
    return True



def _verify_script():
    return "kiem_tra_may.bat" if sys.platform.startswith("win") else "kiem_tra_may.command"


def _secrets_hint():
    """Chỉ nói tên khoá có/không và có giá trị hay trống trong secrets.env, không bao giờ in giá trị."""
    from .config import SECRETS_PATH
    try:
        with open(SECRETS_PATH, encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f]
    except OSError:
        return f"  → Không đọc được {SECRETS_PATH}."
    names = []
    for ln in lines:
        if ln and not ln.startswith("#") and "=" in ln:
            k, _, v = ln.partition("=")
            names.append(f"{k.strip()}({'có giá trị' if v.strip() else 'TRỐNG'})")
    return ("  → Các khoá đang có trong secrets.env: " + (", ".join(names) or "không có khoá nào")
            + ".\n  → Cần một dòng GEMINI_API_KEY=AIza... (không có dấu cách thừa, không để # đầu dòng).")

VERIFY_PARTS = ("check", "ai", "mom", "autostart", "vdi", "tests")


def _verify_ai_diagnose(cfg, out):
    """Gọi AI thất bại: thử vài dạng yêu cầu nhỏ vào model đầu tiên để biết Google từ chối phần nào (mỗi dạng 1 lượt)."""
    from . import ai_client, ai_context
    try:
        model = ai_client._gemini_candidates(cfg)[0]
    except Exception as e:
        out(f"  ! Không chọn được model để chẩn đoán: {type(e).__name__}: {e}")
        return
    user = {"contents": [{"role": "user", "parts": [{"text": "Chào bằng 1 câu ngắn."}]}]}
    gen = {"generationConfig": {"maxOutputTokens": ai_client.MAX_OUTPUT_TOKENS}}
    system = {"systemInstruction": {"parts": [{"text": ai_context.system_prompt(cfg)}]}}
    variants = [("chỉ câu hỏi", user), ("+ maxOutputTokens", dict(user, **gen)),
                ("+ bối cảnh (systemInstruction)", dict(user, **system)),
                ("+ cả ba", dict(user, **gen, **system))]
    out(f"  Chẩn đoán model {model} (mỗi dòng 1 lượt gọi):")
    for name, body in variants:
        try:
            ai_client._http(cfg, "POST", f"{ai_client.GEMINI_URL}/models/{model}:generateContent",
                            ai_client._gemini_headers(cfg), body)
            out(f"    ✓ {name}: được")
        except Exception as e:
            from .errors import explain
            out("    ✗ " + ai_client._redact(cfg, f"{name}: {explain(e)}"))


def cmd_verify(cfg, only=None):
    """Kiểm tra trên máy thật, có hướng dẫn thao tác, kết quả ghi ra data/logs/kiem_tra-*.txt để gửi lại.
    only: chỉ chạy một số phần (ví dụ ["vdi"] hoặc ["ai"]), mặc định chạy đủ VERIFY_PARTS."""
    from . import ai_client
    only = [p.lower() for p in (only or [])]
    bad = [p for p in only if p not in VERIFY_PARTS]
    if bad:
        print(f"Phần không có: {', '.join(bad)}. Các phần: {', '.join(VERIFY_PARTS)} (bỏ trống = chạy đủ).")
        return 2

    def want(part):
        return not only or part in only

    os.makedirs(os.path.join(cfg["data_dir"], "logs"), exist_ok=True)
    path = os.path.join(cfg["data_dir"], "logs", f"kiem_tra-{dt.datetime.now():%Y%m%d-%H%M%S}.txt")
    out = _Tee(path)
    results = {}
    out(f"KIỂM TRA FOCUS TRACKER {__version__} · {dt.datetime.now():%Y-%m-%d %H:%M} · Python {sys.version.split()[0]}"
        f" · {sys.platform}" + (f" · chỉ chạy: {', '.join(only)}" if only else ""))
    import contextlib
    import io
    if want("check"):
        out("\n== 1. Cấu hình, Telegram, key AI ==")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            results["check"] = cmd_check(cfg) == 0
        out(buf.getvalue().rstrip())
        if cfg["telegram_bot_token"] and cfg["telegram_chat_id"]:
            from .telegram_bot import TelegramAPI
            try:
                TelegramAPI(cfg["telegram_bot_token"]).call(
                    "sendMessage", {"chat_id": cfg["telegram_chat_id"], "text": "✅ Kiểm tra máy: bot gửi tin được."},
                    timeout=20)
                out("✓ Telegram: đã gửi 1 tin thử vào chat của bạn")
            except Exception as e:
                from .errors import explain
                out(f"✗ Telegram gửi tin: {explain(e)}")
                results["check"] = False
        elif cfg["telegram_bot_token"]:
            out(f"✗ Chưa có TELEGRAM_CHAT_ID: nhấp đúp {'start_tracker.command' if sys.platform == 'darwin' else 'start_tracker.bat'}, "
                "nhắn /start cho bot để lấy (mọi giờ, mọi ngày), rồi ghi vào config/secrets.env")
            results["check"] = False
    if want("ai"):
        out("\n== 2. AI (Gemini) ==")
        if ai_client.provider(cfg) == "gemini":
            try:
                models = ai_client.list_gemini_models(cfg)
                out(f"✓ Key Gemini dùng được {len(models)} model: " + ", ".join(models[:8]))
                text, model = ai_client.generate(cfg, "Chào bằng 1 câu ngắn tiếng Việt.", purpose="test")
                out(f"✓ Gọi thử AI ({model}): {text.strip()[:120]}")
                results["ai"] = True
            except Exception as e:
                from .errors import explain
                out(f"✗ AI: {explain(e)}")
                results["ai"] = False
                _verify_ai_diagnose(cfg, out)
        else:
            out(f"! AI: {ai_client.provider(cfg) or 'chưa có GEMINI_API_KEY'}")
            if not ai_client.provider(cfg):
                out(_secrets_hint())
            results["ai"] = bool(ai_client.provider(cfg))
    if want("mom"):
        out("\n== 3. Lịch lễ Singapore (trang MOM) ==")
        results["mom"] = _verify_mom(cfg, out)
    if want("autostart"):
        out("\n== 4. Tự khởi động ==")
        results["autostart"] = _verify_autostart(out, cfg)
    if want("vdi"):
        out("\n== 5. Nhận diện cửa sổ VDI (làm theo hướng dẫn từng bước) ==")
        results["vdi"] = _verify_probe(cfg, out)
    if want("tests"):
        out("\n== 6. Bộ test tự động ==")
        import unittest
        buf = io.StringIO()
        suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), top_level_dir=ROOT)
        res = unittest.TextTestRunner(stream=buf, verbosity=1).run(suite)
        results["tests"] = res.wasSuccessful()
        out(f"{'✓' if res.wasSuccessful() else '✗'} {res.testsRun} test, lỗi {len(res.failures) + len(res.errors)}, "
            f"bỏ qua {len(res.skipped)}")
        if not res.wasSuccessful():
            out(buf.getvalue()[-6000:])
    out("\n== TÓM TẮT ==")
    for k, v in results.items():
        out(f"{'✓' if v else '✗'} {k}")
    out(f"\nĐã ghi kết quả vào: {path}")
    out.f.close()
    return 0 if all(results.values()) else 1


def cmd_selftest(cfg):
    import unittest
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), top_level_dir=ROOT)
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if res.wasSuccessful() else 1


def _telegram_notice(text):
    """Gửi 1 tin Telegram khi chưa có cấu hình đầy đủ (chỉ cần token + chat id trong secrets.env)."""
    from .config import SECRETS_PATH, read_secrets
    sec = dict(read_secrets(SECRETS_PATH))
    for env, key in (("TELEGRAM_BOT_TOKEN", "telegram_bot_token"), ("TELEGRAM_CHAT_ID", "telegram_chat_id")):
        sec[key] = sec.get(key) or os.environ.get(env, "")
    if not (sec.get("telegram_bot_token") and sec.get("telegram_chat_id")):
        return
    try:
        from .telegram_bot import TelegramAPI
        TelegramAPI(sec["telegram_bot_token"]).call("sendMessage", {"chat_id": sec["telegram_chat_id"], "text": text},
                                                    timeout=20)
    except Exception as e:
        logs.get_logger().warning("Không gửi được tin báo lỗi cấu hình qua Telegram: %s: %s", type(e).__name__, e)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "run"
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    try:
        cfg = load_config()
    except ConfigError as e:
        msg = f"Cấu hình sai: {e}"
        print(msg, file=sys.stderr) if sys.stderr else None
        try:
            os.makedirs(os.path.join(ROOT, "data", "logs"), exist_ok=True)
            with open(os.path.join(ROOT, "data", "logs", "config-error.txt"), "w", encoding="utf-8") as f:
                f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
        except OSError:
            pass
        if cmd == "run":  # chạy ẩn: báo qua Telegram để người dùng biết vì sao tracker không chạy
            _telegram_notice(f"⚙️ Focus Tracker không khởi động được vì {msg[0].lower() + msg[1:]}\n"
                             "Sửa file config/settings.json (hoặc persona.json) rồi bật lại.")
        return 2
    logs.setup(cfg["data_dir"], console=cmd != "run" or bool(sys.stderr))
    from .storage import db_path, open_db
    if cmd == "run":  # --manual: bạn tự bật (start_tracker, lam_bu_ngoai_gio), ngày nghỉ vẫn ghi giờ làm bù
        return cmd_run(cfg, manual="--manual" in argv)
    if cmd == "check":
        return cmd_check(cfg)
    if cmd == "probe":
        return cmd_probe(cfg)
    if cmd == "selftest":
        return cmd_selftest(cfg)
    if cmd == "verify":
        return cmd_verify(cfg, argv[1:])
    if cmd == "report":
        from .report import write_report
        args = [a for a in argv[1:] if not a.startswith("--")]
        day = args[0] if args else dt.date.today().isoformat()
        path, _ = write_report(open_db(db_path(cfg)), cfg, day)
        print(path)
        if "--open" in argv:  # bao_cao_hom_nay.bat / .command: mở luôn bằng trình duyệt
            import pathlib
            import webbrowser
            webbrowser.open(pathlib.Path(path).resolve().as_uri())
        return 0
    if cmd == "week":
        from .analysis import week_facts
        from .report import week_text
        print(week_text(week_facts(open_db(db_path(cfg)), cfg, dt.date.today().isoformat())))
        return 0
    if cmd == "demo":
        from .demo import make_demo
        make_demo(cfg)
        return 0
    if cmd == "housekeeping":
        from . import housekeeping
        print(json.dumps(housekeeping.run(cfg, force=True), ensure_ascii=False, indent=2))
        return 0
    if cmd == "clearcache":
        from . import ai_client
        db = open_db(db_path(cfg))
        with db:
            n = db.execute("DELETE FROM ai_cache").rowcount
        ai_client.clear_cache(cfg)
        print(f"Đã xoá cache model AI và {n} nhận xét AI đã lưu.")
        return 0
    if cmd in ("ai-models", "ai-test"):
        from . import ai_client
        if cmd == "ai-models":
            if ai_client.provider(cfg) != "gemini":
                print("Lệnh này dành cho Gemini. Điền GEMINI_API_KEY trong config/secrets.env trước.")
                return 1
            for name in ai_client.list_gemini_models(cfg):
                print("  -", name)
            return 0
        try:
            print(ai_client.generate(cfg, "Chào bằng 1 câu ngắn tiếng Việt.", purpose="test"))
        except ai_client.AIError as e:
            print("Lỗi:", e)
        print(ai_client.status_text(cfg))
        return 0
    print(__doc__)
    return 1
