import datetime as dt
"""Bot Telegram: lệnh, nhắn tự nhiên + xác nhận OK/Sửa/Huỷ, hỏi đáp, ảnh AS400, bảo mật chat_id."""
import threading
import time
import urllib.error
from unittest import mock

from focus import ai_client, motivation, persona
from focus.storage import db_path, get_note, open_db
from focus.telegram_bot import TelegramBot
from tests.helpers import FakeTelegramAPI, TempCase, insert_run, msg


class BotTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg["telegram_bot_token"] = "T"
        self.cfg["telegram_chat_id"] = "42"
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.today = self.bot.today()

    def say(self, text, **kw):
        self.api.clear()
        self.bot.handle(msg(text, **kw))
        return self.api.sent()

    def note(self):
        return get_note(self.bot.db, self.today)

    def press(self, verb, n=-1):
        markups = [p for m, p, f in self.api.calls if m == "sendMessage" and p.get("reply_markup")]
        data = markups[n]["reply_markup"]["inline_keyboard"][0]
        cb = {"ok": data[0], "edit": data[1], "no": data[2]}[verb]["callback_data"]
        self.api.clear()
        self.bot.handle_callback({"id": "cb", "data": cb, "message": {"chat": {"id": 42}, "message_id": 5}})
        return self.api.sent()

    # --- lệnh ----------------------------------------------------------
    def test_command_writes_directly(self):
        out = self.say("/tmrtask fix job đối soát")
        self.assertEqual(self.note()["tomorrow"], "fix job đối soát")
        self.assertIn("Sáng mai", out[0])
        self.say("/mai việc khác")
        self.assertEqual(self.note()["tomorrow"], "việc khác")

    def test_command_validation(self):
        out = self.say("/issue")
        self.assertIn("Ví dụ", out[0])
        self.assertEqual(self.note(), {})
        self.assertIn("08:10 17:35", self.say("/as400 abc")[0])
        self.assertIn("1 đến 5", self.say("/energy 9")[0])

    def test_quick_notes_append(self):
        self.say("/issue VDI chậm")
        self.say("/issue thiếu quyền")
        self.say("/output xong batch")
        n = self.note()
        self.assertEqual(n["issues"].count("\n"), 1)
        self.assertIn("thiếu quyền", n["issues"])
        self.assertIn("xong batch", n["output"])

    def test_off_on(self):
        self.say("/off 2026-12-24 nghỉ phép")
        self.assertEqual(get_note(self.bot.db, "2026-12-24")["day_off"], "nghỉ phép")
        self.say("/on 2026-12-24")
        self.assertIsNone(get_note(self.bot.db, "2026-12-24")["day_off"])
        self.assertIn("chưa đọc được ngày", self.say("/off 2026-02-30")[0])

    def test_pause_resume_status(self):
        self.say("/pause")
        self.assertTrue(self.state["paused"].is_set())
        self.assertIn("tạm dừng", self.say("/status")[0])
        self.say("/resume")
        self.assertFalse(self.state["paused"].is_set())
        self.state["last"] = {"idle": 3, "locked": False, "vdi_state": "minimized", "fg_proc": "chrome.exe"}
        self.assertIn("VDI đang thu nhỏ", self.say("/status")[0])

    def test_read_commands_and_unknown(self):
        insert_run(self.bot.db, self.today, "08:00", 60)
        for cmd in ("/today", "/score", "/week", "/golden", "/help", "/start", "/aistatus", "/perf", "/quote", "/bible"):
            with self.subTest(cmd=cmd):
                self.assertTrue(self.say(cmd), cmd)
        self.say("/report")
        self.assertTrue(any(m == "sendDocument" for m, p, f in self.api.calls))
        self.assertIn("Không có lệnh", self.say("/xyz")[0])
        self.assertTrue(self.say("/TODAY@MyFocusBot"))

    def test_clearcache(self):
        with self.bot.db:
            self.bot.db.execute("INSERT INTO ai_cache VALUES ('review:x', 1, 't')")
        self.assertIn("1 nhận xét", self.say("/clearcache")[0])

    # --- nhắn tự nhiên + xác nhận -------------------------------------------
    def test_natural_write_needs_ok(self):
        out = self.say("việc ngày mai cần làm là gửi spec API")
        self.assertIn("Mình hiểu bạn muốn", out[0])
        self.assertIn("gửi spec API", out[0])
        self.assertNotIn("tomorrow", self.note(), "chưa bấm OK thì chưa ghi")
        markups = [p for m, p, f in self.api.calls if m == "sendMessage" and p.get("reply_markup")]
        cb = markups[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.press("ok")
        self.assertEqual(self.note()["tomorrow"], "gửi spec API")
        self.assertTrue(any(m == "editMessageReplyMarkup" for m, p, f in self.api.calls))
        self.api.clear()  # bấm OK lần hai: không ghi lại, báo hết hạn
        self.bot.handle_callback({"id": "cb2", "data": cb, "message": {"chat": {"id": 42}, "message_id": 5}})
        self.assertIn("hết hạn", self.api.last())

    def test_natural_cancel(self):
        self.say("VDI chậm quá chờ restart")
        out = self.press("no")
        self.assertIn("Đã huỷ", out[0])
        self.assertEqual(self.note(), {})

    def test_natural_edit_then_ok(self):
        self.say("việc ngày mai là A")
        self.assertIn("gõ lại", self.press("edit")[0])
        out = self.say("việc ngày mai là B")
        self.assertIn("B", out[0])
        self.press("ok")
        self.assertEqual(self.note()["tomorrow"], "B")

    def test_pending_expires(self):
        self.say("VDI chậm quá")
        for k, v in list(self.bot.pending.items()):
            self.bot.pending[k] = (v[0], v[1], v[2] - 3600, v[3])
        self.assertIn("hết hạn", self.press("ok")[0])
        self.assertEqual(self.note(), {})

    def test_natural_read_runs_directly(self):
        out = self.say("hôm nay mình tập trung được bao nhiêu")
        self.assertNotIn("Nhấn OK", " ".join(out))
        self.assertTrue(out)

    def test_natural_unknown(self):
        self.assertIn("chưa hiểu", self.say("qwerty zxcv")[0])

    def test_natural_with_ai(self):
        self.cfg["gemini_api_key"] = "k"
        with mock.patch.object(ai_client, "generate",
                               return_value=('{"action":"ghi_gio_as400","args":{"start":"8:05","end":"17:30"}}', "m")):
            out = self.say("hôm nay vào AS400 lúc 8 giờ 5, ra lúc 5 rưỡi")
        self.assertIn("vào 08:05, ra 17:30", out[0])
        self.press("ok")
        self.assertEqual((self.note()["as400_start"], self.note()["as400_end"]), ("08:05", "17:30"))

    def test_chat_goes_to_encouragement(self):
        out = self.say("chán quá trời ơi")
        self.assertTrue(out[0])
        self.assertNotIn("Nhấn OK", out[0])

    # --- bảo mật ---------------------------------------------------------
    def test_stranger_ignored(self):
        self.assertEqual(self.say("/today", chat=999), [])
        self.assertEqual(self.say("/tmrtask hack", chat=999), [])
        self.assertEqual(self.note(), {})
        self.say("VDI chậm")
        pid = list(self.bot.pending)[0]
        self.api.clear()
        self.bot.handle_callback({"id": "x", "data": f"ok:{pid}", "message": {"chat": {"id": 999}, "message_id": 1}})
        self.assertEqual(self.note(), {})
        self.assertTrue(any("REJECT_STRANGER" in l for l in self.audit_lines()))

    def test_no_chat_id_yet(self):
        self.bot.chat_id = ""
        self.api.clear()
        self.bot.handle(msg("/start", chat=555))
        self.assertIn("555", self.api.sent()[0])
        self.assertEqual(self.api.calls[0][1]["chat_id"], "555")

    # --- hỏi đáp tổng kết ---------------------------------------------------
    def test_review_conversation(self):
        self.say("/issue VDI chậm")
        self.say("/review")
        self.assertIn("Đã ghi trong ngày", self.say("xong batch A")[0])  # câu hỏi issue hiện issue đã ghi
        self.say("bỏ qua")
        self.say("Zalo")
        self.assertIn("chưa thấy giờ", self.say("không nhớ")[0])
        self.say("8:00 17:00")
        self.say("làm tiếp spec")
        self.assertIn("1 đến 5", self.say("tám")[0])
        self.say("4")
        n = self.note()
        self.assertEqual((n["output"], n["distractions"], n["as400_start"], n["tomorrow"], n["energy"]),
                         ("xong batch A", "Zalo", "08:00", "làm tiếp spec", 4))
        self.assertIn("VDI chậm", n["issues"])
        self.assertIsNone(self.bot.convo)

    def test_review_without_as400(self):
        self.cfg["as400_enabled"] = False
        self.say("/review")
        for answer in ("a", "b", "c", "d", "3"):
            self.say(answer)
        self.assertEqual(self.note()["energy"], 3)
        self.assertNotIn("/as400", self.say("/help")[0])

    def test_cancel_convo_and_command_interrupts(self):
        self.say("/review")
        self.say("/cancel")
        self.assertIsNone(self.bot.convo)
        self.say("/review")
        self.say("/today")  # lệnh khác giữa chừng vẫn chạy, cuộc hỏi vẫn giữ
        self.say("xong A")
        self.assertEqual(self.note()["output"], "xong A")

    def test_convo_expires(self):
        self.say("/review")
        k, q, t, ttl = self.bot.convo
        self.bot.convo = (k, q, t - 4 * 3600, ttl)
        self.say("VDI chậm quá")
        self.assertIsNone(self.bot.convo)
        self.assertIn(self.bot.pending and "Mình hiểu" or "", self.api.sent()[0])

    def test_plan_convo_uses_yesterday(self):
        from focus.storage import save_note
        yday = (dt.date.fromisoformat(self.bot.today()) - dt.timedelta(days=1)).isoformat()
        save_note(self.bot.db, yday, {"tomorrow": "việc từ hôm qua"})
        self.api.clear()
        self.bot.start_convo("plan")
        self.assertTrue(any("việc từ hôm qua" in s for s in self.api.sent()))
        self.say("1. A 2. B")
        self.assertEqual(self.note()["plan"], "1. A 2. B")

    # --- ảnh AS400 -------------------------------------------------------------
    def test_photo_needs_ai(self):
        out = self.say("", photo=[{"file_id": "a", "file_size": 1}])
        self.assertIn("/as400", out[0])

    def test_photo_flow_with_confirm(self):
        self.cfg["gemini_api_key"] = "k"
        with mock.patch.object(motivation, "read_as400_times", return_value=("08:12", "17:40", "QPJOBLOG")):
            out = self.say("", photo=[{"file_id": "a", "file_size": 1}, {"file_id": "b", "file_size": 9}])
        self.assertIn("vào 08:12, ra 17:40", out[-1])
        self.assertTrue(any(p.get("file_id") == "b" for m, p, f in self.api.calls if m == "getFile"))
        self.assertNotIn("as400_start", self.note())
        self.press("ok")
        self.assertEqual(self.note()["as400_start"], "08:12")

    def test_photo_errors(self):
        self.cfg["gemini_api_key"] = "k"
        for side in (ai_client.AIError("hết quota"), ValueError("Ảnh quá lớn."), OSError("net")):
            with self.subTest(side=side), mock.patch.object(motivation, "read_as400_times", side_effect=side):
                out = self.say("", photo=[{"file_id": "a"}])
                self.assertIn("/as400", out[-1])

    # --- xưng hô -----------------------------------------------------------------
    def test_persona_applied_to_bot_text_only(self):
        self.cfg["persona"] = dict(persona.DEFAULT, goi_nguoi_dung="bro", bot_xung="tui")
        out = self.say("việc ngày mai là X")
        self.assertIn("Tui hiểu bro muốn", out[0])
        self.bot.send('"Hỡi bạn" — trích dẫn', raw=True)
        self.assertEqual(self.api.last(), '"Hỡi bạn" — trích dẫn')

    # --- mạng --------------------------------------------------------------------
    def test_send_retries_once(self):
        self.api.fail = 1
        with mock.patch("time.sleep"):
            self.assertIsNotNone(self.bot.send("hi"))
        self.api.fail = 2
        with mock.patch("time.sleep"):
            self.assertIsNone(self.bot.send("hi"))

    def test_long_message_split(self):
        self.api.clear()
        self.bot.send("x" * 9000)
        self.assertEqual(len(self.api.sent()), 3)

    def test_poll_once_handles_updates_and_errors(self):
        self.api.updates = [{"update_id": 7, "message": msg("/tmrtask A")},
                            {"update_id": 8, "callback_query": {"id": "c", "data": "ok:none",
                                                                "message": {"chat": {"id": 42}, "message_id": 1}}},
                            {"update_id": 9, "edited_message": {}}]
        self.bot.poll_once()
        self.assertEqual(self.bot.offset, 10)
        self.assertEqual(self.note()["tomorrow"], "A")
        with mock.patch.object(TelegramBot, "handle", side_effect=RuntimeError("boom")):
            self.api.updates = [{"update_id": 10, "message": msg("/today")}]
            self.bot.poll_once()
        self.assertIn("lỗi", self.api.last().lower())

    def test_bad_token_stops_bot(self):
        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with mock.patch.object(self.api, "call", side_effect=err):
            t = threading.Thread(target=self.bot.run)
            t.start()
            t.join(5)
        self.assertFalse(t.is_alive())
        self.assertTrue(any("TELEGRAM_BAD_TOKEN" in l for l in self.audit_lines()))

    def test_network_error_backoff_then_stop(self):
        calls = []
        def boom(*a, **k):
            calls.append(1)
            raise OSError("down")
        with mock.patch.object(self.api, "call", side_effect=boom), \
                mock.patch.object(self.bot.stopped, "wait", side_effect=lambda s: self.bot.stopped.set()):
            self.bot.run()
        self.assertGreaterEqual(len(calls), 1)

    def test_daily_summary_and_weekly(self):
        insert_run(self.bot.db, self.today, "08:00", 60)
        self.api.clear()
        self.bot.send_daily_summary(self.today)
        sent = self.api.sent()
        self.assertIn("🔋", sent[0], "chưa chấm năng lượng: báo số bot tự tính trước")
        self.assertIn("Tổng kết", sent[1])
        self.assertIn("/tmrtask", sent[1])
        self.assertTrue(any(m == "sendDocument" for m, p, f in self.api.calls))
        self.api.clear()
        self.bot.send_weekly(self.today)
        self.assertIn("Tuần", self.api.sent()[0])

    def test_concurrent_writes_from_two_threads(self):
        errors = []
        def worker(i):
            try:
                for j in range(20):
                    self.bot.handle(msg(f"/issue t{i}-{j}"))
            except Exception as e:
                errors.append(e)
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        writer_db = open_db(db_path(self.cfg))
        for t in ts:
            t.start()
        for k in range(30):
            insert_run(writer_db, self.today, f"09:{k:02d}", 1)
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(get_note(writer_db, self.today)["issues"].splitlines()), 60)
