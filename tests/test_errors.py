"""Lỗi kỹ thuật -> câu tiếng Việt dễ hiểu; bot không im lặng khi lỗi."""
import socket
import sqlite3
import ssl
import threading
import urllib.error
from unittest import mock

from focus import ai_client, errors
from focus.notifier import Notifier
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, msg


class ExplainTest(TempCase):
    def test_mapping(self):
        cases = [
            (urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed")), "không có mạng"),
            (urllib.error.URLError(socket.timeout("timed out")), "mạng chậm"),
            (socket.timeout("x"), "mạng chậm"),
            (urllib.error.URLError(ssl.SSLError("CERTIFICATE_VERIFY_FAILED")), "chứng chỉ"),
            (urllib.error.URLError(ConnectionRefusedError()), "không kết nối được"),
            (ConnectionResetError(), "ngắt giữa chừng"),
            (sqlite3.OperationalError("database is locked"), "đang bận"),
            (sqlite3.OperationalError("database or disk is full"), "ổ đĩa đầy"),
            (sqlite3.DatabaseError("file is not a database"), "bị hỏng"),
            (PermissionError(13, "denied", "C:\\x\\focus.db"), "không có quyền ghi file C:\\x\\focus.db"),
            (ai_client.HTTPStatusError(429, ""), "hết lượt"),
            (ai_client.HTTPStatusError(400, '{"error": {"message": "API key not valid"}}'), "secrets.env"),
            (ai_client.HTTPStatusError(409, ""), "bot khác cùng token"),
            (ai_client.AIError("AI tạm nghỉ"), "AI tạm nghỉ"),
            (RuntimeError("boom"), "lỗi không mong đợi (RuntimeError)"),
        ]
        for exc, want in cases:
            with self.subTest(exc=exc):
                self.assertIn(want, errors.explain(exc))

    def test_no_raw_codes_for_ai(self):
        self.cfg["gemini_api_key"] = "k"

        def boom(*a, **k):
            raise urllib.error.URLError(socket.gaierror(11001, "x"))
        with mock.patch.object(ai_client, "_http", boom):
            with self.assertRaises(ai_client.AIError) as cm:
                ai_client.generate(self.cfg, "x")
        self.assertIn("không có mạng", str(cm.exception))


class BotErrorTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42")
        self.api = FakeTelegramAPI()
        self.bot = TelegramBot(self.cfg, {"paused": threading.Event(), "last": None, "perf": ""}, api=self.api)

    def test_handler_crash_is_explained(self):
        self.api.updates = [{"update_id": 1, "message": msg("/today")}]
        with mock.patch("focus.actions.analyze", side_effect=sqlite3.OperationalError("database is locked")):
            self.bot.poll_once()
        self.assertIn("dữ liệu đang bận", self.api.last())
        self.assertTrue(any("BOT_ERROR" in l for l in self.audit_lines()))

    def test_background_job_error_reported_once_per_hour(self):
        n = Notifier(on_error=self.bot.notify_job_error)

        def fail():
            raise urllib.error.URLError(socket.gaierror(1, "x"))
        for _ in range(3):
            n.submit("summary", fail)
        n.drain(5)
        sent = [s for s in self.api.sent() if "tổng kết cuối ngày" in s]
        self.assertEqual(len(sent), 1)
        self.assertIn("không có mạng", sent[0])

    def test_send_failure_is_audited(self):
        self.api.fail = 2
        with mock.patch("focus.telegram_bot.time.sleep"):
            self.assertIsNone(self.bot.send("hi"))
        self.assertTrue(any("TELEGRAM_SEND_FAIL" in l and "ngắt" not in l for l in self.audit_lines()))
