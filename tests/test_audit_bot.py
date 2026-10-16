"""Hồi quy các lỗi tìm ra khi audit bot: ngày của tin nhắn cũ, /off mai, hỏi tự động, ảnh AS400, xưng hô,
gửi lại khi Telegram lỗi, gửi bù tổng kết, từ khoá dự phòng."""
import datetime as dt
import threading
import time
from unittest import mock

from focus import ai_client, intent, motivation, persona
from focus.actions import parse_day
from focus.storage import get_note, mark_sent, save_note
from focus.telegram_bot import AUTO_CONVO_TTL_SECONDS, TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, TempCase, insert_run, msg


def prev_workday(day):
    d = dt.date.fromisoformat(day) - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


class AuditBotTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)
        self.day = self.bot.today()

    def say(self, text, **kw):
        self.api.clear()
        self.bot.handle(msg(text, **kw))
        return self.api.sent()

    # --- ngày ----------------------------------------------------------------
    def test_parse_day_relative(self):
        today = dt.date(2026, 10, 14)  # thứ Tư
        self.assertEqual(parse_day("mai", today)[0], "2026-10-15")
        self.assertEqual(parse_day("ngày mai nghỉ ốm", today), ("2026-10-15", "nghỉ ốm"))
        self.assertEqual(parse_day("thứ 6", today)[0], "2026-10-16")
        self.assertEqual(parse_day("thứ 4", today)[0], "2026-10-14")
        self.assertEqual(parse_day("20/10", today)[0], "2026-10-20")
        self.assertEqual(parse_day("nghỉ một ngày", today)[0], None, "\"một\" không phải \"mốt\"")
        self.assertEqual(parse_day("05/01", dt.date(2026, 12, 20))[0], "2027-01-05")

    def test_off_mai_marks_tomorrow_not_today(self):
        tomorrow = (dt.date.fromisoformat(self.day) + dt.timedelta(days=1)).isoformat()
        self.say("/off mai")
        self.assertFalse(get_note(self.bot.db, self.day).get("day_off"))
        self.assertTrue(get_note(self.bot.db, tomorrow).get("day_off"))

    def test_late_message_goes_to_its_own_day(self):
        sent = time.time() - 11 * 3600
        out = self.say("/tmrtask viết spec", date=sent)
        day = dt.date.fromtimestamp(sent).isoformat()
        self.assertEqual(get_note(self.bot.db, day).get("tomorrow"), "viết spec")
        self.assertTrue(any("app chưa chạy" in s for s in out))
        self.assertIsNone(self.bot._local.day, "xong tin cũ thì quay về hôm nay")

    def test_late_pause_is_ignored(self):
        out = self.say("/pause", date=time.time() - 10 * 3600)
        self.assertFalse(self.state["paused"].is_set())
        self.assertIn("Bỏ qua", out[0])
        self.say("/pause", date=time.time() - 30)
        self.assertTrue(self.state["paused"].is_set())

    # --- hỏi tự động ------------------------------------------------------------
    def test_auto_convo_short_ttl_and_questions_not_captured(self):
        self.bot.start_convo("plan")
        self.assertEqual(self.bot.convo[3], AUTO_CONVO_TTL_SECONDS)
        with mock.patch.object(self.bot, "answer_question") as ask:
            self.say("giá vàng hôm nay bao nhiêu?")
        ask.assert_called_once()
        self.assertFalse(get_note(self.bot.db, self.day).get("plan"), "câu hỏi không bị lưu thành kế hoạch")
        k, q, t, ttl = self.bot.convo
        self.bot.convo = (k, q, t - AUTO_CONVO_TTL_SECONDS - 1, ttl)
        self.assertFalse(self.bot.convo_active())

    def test_manual_convo_long_ttl(self):
        self.say("/plan")
        self.assertGreater(self.bot.convo[3], AUTO_CONVO_TTL_SECONDS)
        self.say("làm job đối soát")
        self.assertEqual(get_note(self.bot.db, self.day)["plan"], "làm job đối soát")

    def test_edit_wins_over_convo(self):
        self.say("/review")
        self.bot.awaiting_edit = time.time()
        with mock.patch.object(self.bot, "handle_text") as ht:
            self.say("VDI chậm quá")
        ht.assert_called_once_with("VDI chậm quá")

    def test_energy_parsing(self):
        self.say("/review")
        for _ in range(5):  # bỏ qua tới câu năng lượng
            self.say("bỏ qua")
        out = self.say("hôm nay 10 điểm")
        self.assertIn("1 đến 5", out[0])
        self.say("tầm 4 thôi")
        self.assertEqual(str(get_note(self.bot.db, self.day)["energy"]), "4")

    # --- ảnh AS400 ----------------------------------------------------------------
    def test_photo_in_review_waits_for_ok(self):
        self.cfg.update(gemini_api_key="k", as400_photo_ai=True)
        self.say("/review")
        for _ in range(3):
            self.say("bỏ qua")
        self.assertTrue(self.bot._convo_at("as400"))
        with mock.patch.object(motivation, "read_as400_times", return_value=("08:10", "17:35", "")):
            self.bot.handle({"chat": {"id": 42}, "photo": [{"file_id": "f", "file_size": 10}]})
        self.assertTrue(self.bot._convo_at("as400"), "chưa bấm OK thì chưa sang câu sau")
        pid = list(self.bot.pending)[0]
        self.api.clear()
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        self.assertEqual(get_note(self.bot.db, self.day)["as400_start"], "08:10")
        self.assertTrue(self.bot._convo_at("tomorrow"))

    def test_photo_bad_times_rejected(self):
        self.cfg.update(gemini_api_key="k", as400_photo_ai=True)
        with mock.patch.object(motivation, "read_as400_times", return_value=("17:35", "08:10", "")):
            out = self.say("", photo=[{"file_id": "f", "file_size": 10}])
        self.assertIn("chưa hợp lý", out[-1])
        self.assertEqual(self.bot.pending, {})

    def test_image_document_accepted(self):
        self.cfg.update(gemini_api_key="k", as400_photo_ai=True)
        with mock.patch.object(motivation, "read_as400_times", return_value=("08:10", None, "")):
            self.say("", document={"file_id": "d", "mime_type": "image/png"})
        self.assertTrue(self.bot.pending)

    # --- xưng hô -------------------------------------------------------------------
    def test_persona_does_not_rewrite_user_text(self):
        self.cfg["persona"] = dict(persona.DEFAULT, goi_nguoi_dung="anh", bot_xung="em")
        insert_run(self.bot.db, self.day, "09:00", 60)
        save_note(self.bot.db, self.day, {"output": "- gửi bạn Nam bản fix"})
        out = self.say("/today")
        self.assertIn("gửi bạn Nam bản fix", out[0])
        self.assertNotIn("", out[0])
        self.assertEqual(persona.apply("bạn " + persona.keep("bạn") + " mình", self.cfg["persona"]), "anh bạn em")

    # --- gửi lại / gửi bù ------------------------------------------------------------
    def test_summary_unmarked_when_telegram_down(self):
        insert_run(self.bot.db, self.day, "09:00", 60)
        mark_sent(self.bot.db, self.day, "summary")
        self.api.fail = 10
        with mock.patch("time.sleep"):
            self.assertFalse(self.bot.send_daily_summary(self.day))
        self.assertTrue(mark_sent(self.bot.db, self.day, "summary"), "đã gỡ dấu để lần sau gửi lại")

    def test_catch_up_sends_missed_summary_once(self):
        prev = prev_workday(self.day)
        insert_run(self.bot.db, prev, "09:00", 60)
        self.api.clear()
        self.bot.catch_up(self.day)
        self.assertTrue(any("Gửi bù tổng kết ngày " + prev in s for s in self.api.sent()))
        self.api.clear()
        self.bot.catch_up(self.day)
        self.assertFalse(any("Gửi bù tổng kết ngày" in s for s in self.api.sent()))

    def test_review_retry_only_when_due_and_not_running(self):
        self.bot._set_retry("day", self.day, time.time() + 600)
        self.assertFalse(self.bot.has_review_retry())
        self.bot._set_retry("day", self.day, 0)
        self.assertTrue(self.bot.has_review_retry())
        self.assertFalse(self.bot.has_review_retry(), "đang có lượt gửi lại: không xếp thêm")
        with mock.patch.object(self.bot, "send_ai_review"):
            self.bot.retry_ai_reviews(self.day)
        self.assertTrue(self.bot.has_review_retry())

    def test_permanent_error_no_retry(self):
        self.cfg["gemini_api_key"] = ""
        self.bot.send_ai_review("day", self.day)
        self.assertEqual(self.bot._retries(), {})

    # --- từ khoá dự phòng -------------------------------------------------------------
    def test_rules_misroutes(self):
        rule = lambda t: (lambda r: (r[0].name, r[1]))(intent.by_rules(t))
        self.assertEqual(rule("tắt kinh thánh"), ("cai_khich_le", {"mode": "quote"}))
        self.assertEqual(rule("nghỉ ốm hôm nay")[0], "bao_nghi")
        self.assertEqual(rule("hôm nay đã xong deploy UAT")[0], "ghi_output")
        self.assertEqual(rule("hôm nay thế nào")[0], "xem_hom_nay")

    def test_ask_toggle_only_exact_words(self):
        with mock.patch.object(self.bot, "answer_question") as ask:
            self.say("/ask mơ thấy rắn")
        ask.assert_called_once()
        self.assertFalse(self.bot.ask_mode())
        self.say("/ask on")
        self.assertTrue(self.bot.ask_mode())

    def test_wish_when_ai_off(self):
        insert_run(self.bot.db, self.day, "09:00", 60)
        self.cfg["ai_review_enabled"] = False
        self.api.clear()
        self.bot.send_daily_summary(self.day)
        self.assertTrue(any(w in self.api.sent() for w in sum(motivation.WISHES.values(), [])))
        fri = "2026-10-16"
        self.assertIn(motivation.local_wish(fri), motivation.WISHES["weekend"])
        self.assertIn("cuối tuần", motivation.evening_wish_hint(fri))
        self.assertIn("buổi tối", motivation.evening_wish_hint("2026-10-14"))

    # --- thẻ xác nhận: ghi rõ action đã bóc tách --------------------------------------
    def test_confirm_card_shows_parsed_action(self):
        self.cfg["gemini_api_key"] = "k"
        with mock.patch.object(intent, "by_ai", return_value=(intent.BY_NAME["gio_bot"], {"stop": "18:00"})):
            out = self.say("tắt bot lúc 6 giờ chiều")
        card = out[0]
        for part in ("Mình hiểu bạn muốn: Đổi giờ bot", "Hành động: gio_bot", "lệnh /giobot", "giờ TẮT bot: 18:00",
                     "«tắt bot lúc 6 giờ chiều»", "AI bóc tách", "✅ OK"):
            self.assertIn(part, card)
        self.assertNotIn("⚠️", card, "AI và từ khoá đọc giống nhau: không cảnh báo")
        self.assertEqual(len(self.bot.pending), 1)

    def test_confirm_card_warns_when_ai_disagrees_with_keywords(self):
        self.cfg["gemini_api_key"] = "k"
        with mock.patch.object(intent, "by_ai", return_value=(intent.BY_NAME["gio_bot"], {"stop": "19:00"})):
            card = self.say("tắt bot lúc 6 giờ chiều")[0]
        self.assertIn("⚠️ Đọc theo từ khoá thì ra giờ TẮT bot = 18:00", card)
        with mock.patch.object(intent, "by_ai", return_value=(intent.BY_NAME["ghi_issue"], {"text": "nghỉ chiều"})):
            card = self.say("chiều nay mình nghỉ phép buổi chiều")[-1]
        self.assertIn("Hành động: ghi_issue", card)
        self.assertIn("⚠️ Theo từ khoá thì tin này lại giống «Nghỉ phép", card)

    def test_leave_card_spells_out_default_day(self):
        card = self.say("mình xin nghỉ phép buổi chiều")[0]
        self.assertIn("Hành động: nghi_phep", card)
        self.assertIn("buổi nghỉ: buổi chiều", card)
        self.assertIn(f"hôm nay {self.day} (mặc định)", card)
        self.assertIn("từ khoá", card)

    def test_commands_run_without_confirm(self):
        out = self.say("/giobot 08:30 18:00")
        self.assertEqual(self.bot.pending, {}, "gõ lệnh thì không cần AI bóc tách, không hỏi lại")
        self.assertFalse(any("Mình hiểu bạn muốn" in s for s in out))
        out = self.say("/leave pm")
        self.assertEqual(self.bot.pending, {})
        self.assertEqual(get_note(self.bot.db, self.day).get("leave_part"), "pm")

    # --- audit vòng 3 ----------------------------------------------------------------------
    def test_unreadable_date_never_defaults_to_today(self):
        today = dt.date(2026, 10, 14)
        self.assertEqual(parse_day("24/12/26 nghỉ Noel", today)[0], "2026-12-24")
        self.assertEqual(parse_day("24.12", today)[0], "2026-12-24")
        self.assertEqual(parse_day("nghỉ phép 20 tháng 10", today)[0], "2026-10-20")
        self.assertEqual(parse_day("mốt mình nghỉ phép", today)[0], "2026-10-16")
        self.assertEqual(parse_day("một ngày", today)[0], None)
        self.assertEqual(parse_day("thứ 6 tuần sau", today)[0], "2026-10-23")
        self.assertEqual(parse_day("thứ 2 tuần sau", dt.date(2026, 10, 12))[0], "2026-10-19")
        out = self.say("/off 31/02 nghỉ")
        self.assertIn("chưa đọc được ngày", out[0])
        self.assertFalse(get_note(self.bot.db, self.day).get("day_off"), "không lặng lẽ đánh dấu hôm nay")

    def test_edit_expires_and_new_convo_clears_it(self):
        self.bot.awaiting_edit = time.time() - 31 * 60
        with mock.patch.object(self.bot, "handle_text") as ht:
            self.say("/plan")
            self.say("fix job đối soát")
        ht.assert_not_called()
        self.assertEqual(get_note(self.bot.db, self.day)["plan"], "fix job đối soát")
        self.bot.awaiting_edit = time.time()
        self.bot.start_convo("review")
        self.assertFalse(self.bot.awaiting_edit)

    def test_ask_mode_does_not_swallow_scheduled_answers(self):
        self.say("/ask on")
        self.bot.start_convo("plan")
        with mock.patch.object(self.bot, "answer_question") as ask:
            self.say("fix job đối soát, viết spec API")
        ask.assert_not_called()
        self.assertEqual(get_note(self.bot.db, self.day)["plan"], "fix job đối soát, viết spec API")

    def test_nl_ask_toggle_needs_ok(self):
        self.say("bật chế độ hỏi AI")
        self.assertFalse(self.bot.ask_mode())
        self.assertEqual(len(self.bot.pending), 1)
        self.assertIn("BẬT chế độ hỏi AI", self.api.sent()[0])

    def test_encourage_tat_ca_is_both(self):
        from focus.actions import ENC_WORDS, _word_lookup
        self.assertEqual(_word_lookup(ENC_WORDS, "tất cả"), "both")
        self.assertEqual(_word_lookup(ENC_WORDS, "tắt"), "off")

    def test_rules_prefer_write_and_allow_filler(self):
        rule = lambda t: intent.by_rules(t)[0].name
        self.assertEqual(rule("đã xong báo cáo tuần cho sếp"), "ghi_output")
        self.assertEqual(rule("vừa xong deploy UAT"), "ghi_output")
        self.assertEqual(rule("mai mình làm tiếp báo cáo tuần"), "ghi_viec_ngay_mai")
        self.assertEqual(rule("hôm nay mình sẽ fix job đối soát"), "ghi_ke_hoach")
        self.assertEqual(rule("báo cáo tuần"), "xem_tuan")

    def test_every_help_example_routes_to_its_action(self):
        from focus.actions import EXAMPLES
        for name, (_, examples) in EXAMPLES.items():
            for ex in examples:
                if ex.startswith("/"):
                    continue
                found = intent.by_rules(ex, self.day)
                self.assertIsNotNone(found, ex)
                self.assertEqual(found[0].name, name, ex)

    def test_old_promise_is_not_yesterday(self):
        from focus.storage import last_tomorrow
        save_note(self.bot.db, "2026-09-01", {"tomorrow": "việc cũ"})
        self.assertIsNone(last_tomorrow(self.bot.db, "2026-10-14"))
        save_note(self.bot.db, "2026-10-09", {"tomorrow": "việc thứ Sáu"})  # thứ Sáu -> thứ Hai
        self.assertEqual(last_tomorrow(self.bot.db, "2026-10-12"), "việc thứ Sáu")
        save_note(self.bot.db, "2026-10-12", {"plan": "làm việc khác"})
        self.assertIsNone(last_tomorrow(self.bot.db, "2026-10-13"), "đã qua một ngày làm việc khác")

    def test_decomposed_unicode_and_newline_command(self):
        import unicodedata
        self.say(unicodedata.normalize("NFD", "/leave chiều mai"))
        tomorrow = (dt.date.fromisoformat(self.day) + dt.timedelta(days=1)).isoformat()
        self.assertEqual(get_note(self.bot.db, tomorrow).get("leave_part"), "pm")
        self.say("/issue\nVDI chậm")
        self.assertIn("VDI chậm", get_note(self.bot.db, self.day).get("issues") or "")

    def test_card_keeps_user_words(self):
        self.cfg["persona"] = dict(persona.DEFAULT, goi_nguoi_dung="bro", bot_xung="tui")
        card = self.say("bị chặn vì chờ bạn Lan cấp quyền")[0]
        self.assertIn("chờ bạn Lan cấp quyền", card)

