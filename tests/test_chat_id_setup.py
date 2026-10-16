"""Chế độ lấy chat ID (start_tracker khi chưa có TELEGRAM_CHAT_ID): chạy mọi giờ, trả lời chat ID rồi thoát."""
import contextlib
import io
import urllib.error
from unittest import mock

from focus import cli
from tests.helpers import TOKEN, TempCase, make_cfg


class Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class SetupAPI:
    """getMe trả tên bot; getUpdates lần lượt trả từng phần tử của `rounds` (list update, hoặc Exception để ném)."""

    def __init__(self, rounds=(), me=None, clock=None):
        self.rounds = list(rounds)
        self.me = me
        self.clock = clock
        self.calls = []

    def call(self, method, params=None, files=None, timeout=40):
        self.calls.append((method, dict(params or {})))
        if method == "getMe":
            if isinstance(self.me, Exception):
                raise self.me
            return {"ok": True, "result": {"username": "Focus_test_bot"}}
        if method == "getUpdates":
            if params and params.get("timeout") == 0:
                return {"ok": True, "result": []}
            if self.clock:
                self.clock.t += 25  # long polling: mỗi lần chờ 25 giây
            nxt = self.rounds.pop(0) if self.rounds else []
            if isinstance(nxt, Exception):
                raise nxt
            return {"ok": True, "result": nxt}
        return {"ok": True, "result": {"message_id": 1}}

    def sent(self):
        return [p for m, p in self.calls if m == "sendMessage"]


def upd(uid, chat_id, name="Minh"):
    return {"update_id": uid, "message": {"chat": {"id": chat_id}, "from": {"first_name": name}, "text": "/start"}}


def http(code):
    return urllib.error.HTTPError("https://api.telegram.org/bot***/x", code, "err", {}, None)


class ChatIdSetupTest(TempCase):
    def run_setup(self, api, clock=None, wait=600):
        clock = clock or api.clock or Clock()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli._chat_id_setup(make_cfg(self.tmp, telegram_bot_token=TOKEN), api=api, wait=wait, clock=clock.monotonic, sleep=clock.sleep)
        return rc, out.getvalue()

    def test_first_message_gets_chat_id_reply_and_big_console_line(self):
        clock = Clock()
        api = SetupAPI([[], [upd(7, 123456789)]], clock=clock)
        rc, out = self.run_setup(api)
        self.assertEqual(rc, 0)
        self.assertIn("@Focus_test_bot", out)
        self.assertIn("CHAT ID CỦA BẠN LÀ:   123456789", out)
        self.assertIn("TELEGRAM_CHAT_ID=123456789", out)
        sent = api.sent()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["chat_id"], "123456789")
        self.assertIn("TELEGRAM_CHAT_ID=123456789", sent[0]["text"])

    def test_offset_is_omitted_first_then_acknowledged(self):
        clock = Clock()
        api = SetupAPI([[upd(41, 5)]], clock=clock)
        self.run_setup(api)
        polls = [p for m, p in api.calls if m == "getUpdates"]
        self.assertNotIn("offset", polls[0])  # lần đầu: đọc cả tin đã gửi trước khi chạy
        self.assertEqual(polls[-1], {"offset": 42, "timeout": 0})  # báo đã đọc, lần sau không đọc lại

    def test_update_without_chat_is_skipped(self):
        clock = Clock()
        api = SetupAPI([[{"update_id": 3, "edited_message": {}}], [upd(4, 99)]], clock=clock)
        rc, out = self.run_setup(api)
        self.assertEqual(rc, 0)
        polls = [p for m, p in api.calls if m == "getUpdates"]
        self.assertEqual(polls[1]["offset"], 4)
        self.assertIn("99", out)

    def test_group_chat_negative_id(self):
        clock = Clock()
        rc, out = self.run_setup(SetupAPI([[upd(1, -100123)]], clock=clock))
        self.assertEqual(rc, 0)
        self.assertIn("TELEGRAM_CHAT_ID=-100123", out)

    def test_times_out_without_message(self):
        clock = Clock()
        api = SetupAPI([], clock=clock)
        rc, out = self.run_setup(api, wait=100)
        self.assertEqual(rc, 1)
        self.assertIn("chưa thấy tin nhắn", out)
        self.assertEqual(api.sent(), [])

    def test_bad_token_on_getme(self):
        rc, out = self.run_setup(SetupAPI(me=http(401)))
        self.assertEqual(rc, 1)
        self.assertIn("không nhận TELEGRAM_BOT_TOKEN", out)

    def test_no_network_on_getme(self):
        rc, out = self.run_setup(SetupAPI(me=urllib.error.URLError(OSError("down"))))
        self.assertEqual(rc, 1)
        self.assertIn("Không kết nối được Telegram", out)

    def test_conflict_409_tells_to_close_other_reader(self):
        rc, out = self.run_setup(SetupAPI([http(409)], clock=Clock()))
        self.assertEqual(rc, 1)
        self.assertIn("chương trình khác đang đọc", out)

    def test_network_error_retries_then_succeeds(self):
        clock = Clock()
        api = SetupAPI([OSError("down"), OSError("down"), [upd(9, 77)]], clock=clock)
        rc, out = self.run_setup(api)
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("Đang thử lại"), 1)  # báo mất mạng 1 lần, không spam
        self.assertIn("77", out)

    def test_reply_failure_still_prints_chat_id(self):
        clock = Clock()
        api = SetupAPI([[upd(1, 55)]], clock=clock)
        real = api.call

        def call(method, params=None, files=None, timeout=40):
            if method == "sendMessage":
                raise OSError("down")
            return real(method, params, files, timeout)
        api.call = call
        rc, out = self.run_setup(api)
        self.assertEqual(rc, 0)
        self.assertIn("TELEGRAM_CHAT_ID=55", out)

    def test_token_never_printed(self):
        clock = Clock()
        _, out = self.run_setup(SetupAPI([[upd(1, 5)]], clock=clock))
        self.assertNotIn(TOKEN, out)


class CmdRunSetupModeTest(TempCase):
    def test_missing_chat_id_runs_setup_instead_of_tracker(self):
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="")
        with mock.patch("focus.tracker.InstanceLock.acquire", return_value=True), \
                mock.patch.object(cli, "_chat_id_setup", return_value=0) as setup, \
                mock.patch("focus.tracker.Tracker.run") as run:
            self.assertEqual(cli.cmd_run(cfg), 0)
        setup.assert_called_once()
        run.assert_not_called()

    def test_with_chat_id_tracker_runs_normally(self):
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="123")
        with mock.patch("focus.tracker.InstanceLock.acquire", return_value=True), \
                mock.patch.object(cli, "_chat_id_setup") as setup, \
                mock.patch("focus.tracker.lower_priority"), \
                mock.patch("focus.telegram_bot.TelegramBot.start"), \
                mock.patch("focus.tracker.Tracker.run", return_value="test") as run:
            self.assertEqual(cli.cmd_run(cfg), 0)
        setup.assert_not_called()
        run.assert_called_once()

    def test_no_token_tracker_runs_without_setup(self):
        cfg = make_cfg(self.tmp, telegram_bot_token="", telegram_chat_id="")
        with mock.patch("focus.tracker.InstanceLock.acquire", return_value=True), \
                mock.patch.object(cli, "_chat_id_setup") as setup, \
                mock.patch("focus.tracker.lower_priority"), \
                mock.patch("focus.tracker.Tracker.run", return_value="test"):
            self.assertEqual(cli.cmd_run(cfg), 0)
        setup.assert_not_called()


class SigtermTest(TempCase):
    """launchd gửi SIGTERM khi tắt máy / đăng xuất: tracker phải dừng êm (ghi hết mẫu, chốt ngày), không chết ngang."""

    def test_sigterm_handler_raises_terminated_and_restores(self):
        import signal
        before = signal.getsignal(signal.SIGTERM)
        restore = cli._stop_on_sigterm()
        handler = signal.getsignal(signal.SIGTERM)
        self.assertIsNot(handler, before)
        with self.assertRaises(cli.Terminated):
            handler(signal.SIGTERM, None)
        self.assertFalse(issubclass(cli.Terminated, Exception), "không được để `except Exception` nuốt mất")
        restore()
        self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_handler_install_failure_is_ignored(self):
        fake = mock.Mock(SIGTERM=15)
        fake.signal.side_effect = ValueError("signal only works in main thread")
        cli._stop_on_sigterm(fake)()  # không raise, hàm khôi phục không làm gì

    def test_cmd_run_stops_cleanly_on_terminated(self):
        import signal
        before = signal.getsignal(signal.SIGTERM)
        cfg = make_cfg(self.tmp, telegram_bot_token="", telegram_chat_id="")
        with mock.patch("focus.tracker.InstanceLock.acquire", return_value=True), \
                mock.patch("focus.tracker.lower_priority"), \
                mock.patch("focus.tracker.Tracker.run", side_effect=cli.Terminated()), \
                mock.patch("focus.logs.audit") as audit:
            self.assertEqual(cli.cmd_run(cfg), 0)
        self.assertIn("STOP", [c.args[0] for c in audit.call_args_list])
        self.assertNotIn("CRASH", [c.args[0] for c in audit.call_args_list])
        self.assertIs(signal.getsignal(signal.SIGTERM), before, "trả lại cách xử lý SIGTERM cũ")

