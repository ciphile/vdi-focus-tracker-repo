"""Khích lệ và nhắc nghỉ: xoay vòng kiểu câu, tránh lặp, dùng AI nếu có, nội dung có sẵn khi AI lỗi; đọc giờ AS400."""
import itertools
import json
import random
import types
from unittest import mock

from focus import ai_client, messages, motivation, scoring
from focus.storage import db_path, open_db
from tests.helpers import TempCase, make_cfg

ALL = ["motivation", "bible", "family"]


class FakeAI:
    def __init__(self, text="AI viết", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def __call__(self, cfg, prompt, system="", image=None, purpose=""):
        self.calls.append({"prompt": prompt, "system": system, "image": image, "purpose": purpose})
        if self.fail:
            raise ai_client.AIError("hết quota")
        return self.text, "fake-model"


class MotivationBase(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg = make_cfg(self.tmp, encouragement_styles=ALL)
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)
        random.seed(1234)
        # Đồng hồ tăng đều: thứ tự câu đã gửi rõ ràng kể cả trên Windows (time.time() thô).
        clock = itertools.count(1_000_000)
        p = mock.patch.object(motivation, "time", types.SimpleNamespace(time=lambda: float(next(clock))))
        p.start()
        self.addCleanup(p.stop)
        # Không để test nào lỡ gọi mạng thật.
        p = mock.patch.object(ai_client, "_http", side_effect=AssertionError("không được gọi mạng"))
        p.start()
        self.addCleanup(p.stop)

    def styles(self):
        return [r[0] for r in self.db.execute("SELECT style FROM quotes ORDER BY ts, rowid")]


class EncouragementTest(MotivationBase):
    def test_local_rotates_styles(self):
        texts = [motivation.encouragement(self.cfg, self.db, "chiều") for _ in range(30)]
        styles = self.styles()
        self.assertEqual(len(styles), 30)
        for a, b in zip(styles, styles[1:]):
            self.assertNotEqual(a, b)  # không lặp kiểu câu hai lần liền
        self.assertEqual(set(styles), set(ALL))
        for text, style in zip(texts, styles):
            if style == "bible":
                self.assertTrue(any(ref in text for _, ref in motivation.BIBLE), text)
            elif style == "family":
                self.assertIn(text, motivation.FAMILY)
            else:
                self.assertTrue(any(author in text for _, author in motivation.QUOTES), text)

    def test_single_style(self):
        cfg = make_cfg(self.tmp, encouragement_styles=["bible"])
        for _ in range(3):
            motivation.encouragement(cfg, self.db, "x")
        self.assertEqual(self.styles(), ["bible"] * 3)

    def test_local_avoids_recent_repeats(self):
        seen = [motivation.encouragement(self.cfg, self.db, "x", style="bible") for _ in range(len(motivation.BIBLE))]
        self.assertEqual(len(set(seen)), len(motivation.BIBLE))  # hết vòng mới lặp lại
        more = motivation.encouragement(self.cfg, self.db, "x", style="bible")  # hết câu mới: vẫn trả câu
        self.assertIn(more, seen)
        fam = [motivation.encouragement(self.cfg, self.db, "x", style="family") for _ in range(len(motivation.FAMILY))]
        self.assertEqual(len(set(fam)), len(motivation.FAMILY))

    def test_uses_ai_when_available(self):
        cfg = make_cfg(self.tmp, encouragement_styles=ALL, gemini_api_key="k")
        motivation.encouragement(cfg, self.db, "trước", style="motivation")
        fake = FakeAI("Câu AI\nLàm ngay một việc nhỏ.")
        with mock.patch.object(ai_client, "generate", fake):
            text = motivation.encouragement(cfg, self.db, "ra khỏi VDI 15 phút", style="bible")
        self.assertEqual(text, "Câu AI\nLàm ngay một việc nhỏ.")
        call = fake.calls[0]
        self.assertEqual(call["purpose"], "encourage:bible")
        self.assertIn("ra khỏi VDI 15 phút", call["prompt"])
        self.assertIn("Truyền Thống 1926", call["prompt"])
        self.assertIn("Đừng lặp lại", call["prompt"])  # gửi kèm câu gần đây để AI tránh lặp
        self.assertTrue(call["system"])
        self.assertEqual(self.styles()[-1], "bible")
        self.assertEqual(motivation._db_recent(self.db, 1), [text])

    def test_ai_error_falls_back_local(self):
        cfg = make_cfg(self.tmp, encouragement_styles=ALL, gemini_api_key="k")
        fake = FakeAI(fail=True)
        with mock.patch.object(ai_client, "generate", fake):
            text = motivation.encouragement(cfg, self.db, "x", style="family")
        self.assertEqual(len(fake.calls), 1)
        self.assertIn(text, motivation.FAMILY)

    def test_no_ai_without_key(self):
        fake = FakeAI()
        with mock.patch.object(ai_client, "generate", fake):
            motivation.encouragement(self.cfg, self.db, "x")
        self.assertEqual(fake.calls, [])


class BreakTest(MotivationBase):
    def test_break_message(self):
        msgs = [motivation.break_message(self.db, 60) for _ in range(6)]
        tips = [m.split("\n\n")[1] for m in msgs]
        for m, tip in zip(msgs, tips):
            self.assertIn("60 phút", m)
            self.assertIn(tip, motivation.EXERCISES)
            science = m.split("\n\n")[2]  # dữ kiện nghiên cứu có thật về ngồi lâu / nghỉ ngắn
            self.assertTrue(science.startswith("🔬 "))
            self.assertIn(science[2:], [scoring.SCIENCE[k] for k in messages.SITTING_SCIENCE])
        self.assertEqual(len(set(tips)), 6)  # 6 lần gần nhất không lặp bài tập
        self.assertEqual(set(self.styles()), {"exercise"})
        for _ in range(len(motivation.EXERCISES) * 2):
            self.assertTrue(motivation.break_message(self.db, 90))

    def test_break_does_not_affect_style_rotation(self):
        motivation.encouragement(self.cfg, self.db, "x", style="bible")
        motivation.break_message(self.db, 60)
        self.assertIn(motivation.pick_style(self.cfg, self.db), ALL)


class AS400Test(MotivationBase):
    def read(self, reply):
        fake = FakeAI(reply)
        with mock.patch.object(ai_client, "generate", fake):
            out = motivation.read_as400_times(self.cfg, b"jpeg", "2026-10-14")
        self.assertEqual(fake.calls[0]["image"], b"jpeg")
        self.assertEqual(fake.calls[0]["purpose"], "as400_photo")
        self.assertIn("2026-10-14", fake.calls[0]["prompt"])
        return out

    def test_parses_json(self):
        self.assertEqual(self.read('{"start": "08:10", "end": "17:35", "note": ""}'), ("08:10", "17:35", ""))
        self.assertEqual(self.read('Đây:\n```json\n{"start": "8:05", "end": null, "note": "mờ"}\n```'),
                         ("8:05", None, "mờ"))
        self.assertEqual(self.read('{"start": null}'), (None, None, ""))

    def test_bad_times_dropped(self):
        for bad in ("25:00", "08:61", "8h10", "0810", "08:1", " 08:10", "", 810, ["08:10"]):
            start, end, _ = self.read('{"start": %s, "end": "17:00"}' % json.dumps(bad))
            self.assertIsNone(start, bad)
            self.assertEqual(end, "17:00")
        self.assertEqual(self.read('{"start": "23:59", "end": "00:00"}')[:2], ("23:59", "00:00"))

    def test_garbage_raises(self):
        for reply in ("không thấy giờ nào", "[1, 2]", "{start: 08:10}", '{"start": "08:10"'):
            with self.assertRaises(ai_client.AIError, msg=reply):
                self.read(reply)

    def test_ai_error_propagates(self):
        with mock.patch.object(ai_client, "generate", FakeAI(fail=True)):
            with self.assertRaises(ai_client.AIError):
                motivation.read_as400_times(self.cfg, b"x", "2026-10-14")


class AskAITest(TempCase):
    def test_error_text_drops_canned_content_phrase(self):
        """Hỏi AI không có "nội dung có sẵn" thay thế: lời báo lỗi không được nói vậy (lỗi /ask 15/10)."""
        cfg = make_cfg(self.tmp)
        for err in ("Gemini đang giới hạn lượt gọi hoặc quá tải, lát nữa thử lại. Bot dùng nội dung có sẵn.",
                    "Server Gemini đang quá tải. Mình dùng nội dung có sẵn, lát nữa tự thử lại.",
                    "AI tạm không dùng được (hết quota), bot dùng nội dung có sẵn. Vài tiếng nữa tự thử lại."):
            with mock.patch.object(ai_client, "generate", side_effect=ai_client.AIError(err)):
                text, ok = motivation.ask_ai(cfg, "giá bitcoin?")
            self.assertFalse(ok)
            self.assertTrue(text.startswith("AI chưa trả lời được: "))
            self.assertNotIn("nội dung có sẵn", text)
            self.assertIn("thử lại", text)


class RecentQuotesTest(TempCase):
    """Danh sách "đừng lặp lại" gửi AI: câu trích đầy đủ (không cắt 120 ký tự), không kèm lời chào, CHỈ hôm nay +
    hôm qua (prompt thật 16/10 có câu bị cắt "...(Ê-s" và cả đoạn chào)."""
    MORNING = ('Chào bờ rồ Minh, chúc ông một ngày thứ Năm thật nhiều năng lượng bên màn hình VDI nhé.\n\n'
               '"Nhưng ai trông đợi Đức Giê-hô-va thì chắc được sức mới, cất cánh bay cao như chim ưng; chạy mà '
               'không mệt nhọc, đi mà không mòn mỏi." (Ê-sai 40:31)\n\nBắt đầu ngay với việc gửi estimation nha!')

    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(make_cfg(self.tmp)))

    def put(self, when, style, text):
        with self.db:
            self.db.execute("INSERT INTO quotes VALUES (?,?,?)", (when.timestamp(), style, text))

    def test_full_quote_only_today_and_yesterday(self):
        import datetime as dt
        now = dt.datetime(2026, 10, 16, 8, 6)
        self.put(dt.datetime(2026, 10, 14, 23, 59), "bible", '"Câu hôm kia rất cũ." (Giăng 3:16)')
        self.put(dt.datetime(2026, 10, 15, 0, 0, 1), "bible", self.MORNING)
        self.put(dt.datetime(2026, 10, 15, 14, 0), "exercise", "Mắt: quy tắc 20-20-20 ...")
        self.put(dt.datetime(2026, 10, 15, 15, 0), "bible", self.MORNING)  # trùng: chỉ 1 dòng
        self.put(dt.datetime(2026, 10, 16, 8, 0), "motivation", '"Kỷ luật là cầu nối giữa mục tiêu và thành tựu." — Jim Rohn\nLàm ngay!')
        recent = motivation._db_recent(self.db, now=now.timestamp())
        self.assertEqual(recent, ['"Kỷ luật là cầu nối giữa mục tiêu và thành tựu." — Jim Rohn',
                                  '"Nhưng ai trông đợi Đức Giê-hô-va thì chắc được sức mới, cất cánh bay cao như chim ưng; '
                                  'chạy mà không mệt nhọc, đi mà không mòn mỏi." (Ê-sai 40:31)'])
        block = motivation._avoid_block(recent)
        self.assertIn("(Ê-sai 40:31)", block)
        self.assertNotIn("Chào bờ rồ", block)
        self.assertNotIn("hôm kia", block)
        self.assertEqual(motivation._avoid_block([]), "")

    def test_remember_stores_quote_not_greeting(self):
        motivation._remember(self.db, "bible", self.MORNING)
        stored = self.db.execute("SELECT text FROM quotes").fetchone()[0]
        self.assertTrue(stored.startswith('"Nhưng ai trông đợi'))
        self.assertTrue(stored.endswith("(Ê-sai 40:31)"))

    def test_quote_of_without_quote_marks_uses_bible_ref_line(self):
        self.assertEqual(motivation.quote_of("Chào buổi sáng!\nTôi làm được mọi sự nhờ Đấng ban thêm sức cho tôi. Phi-líp 4:13\nCố lên"),
                         "Tôi làm được mọi sự nhờ Đấng ban thêm sức cho tôi. Phi-líp 4:13")
        self.assertEqual(motivation.quote_of("Không có câu trích"), "Không có câu trích")

    def test_exercise_rotation_unaffected(self):
        for _ in range(3):
            motivation.break_message(self.db, 60)
        self.assertEqual(len(motivation._recent_exercises(self.db)), 3)
        self.assertEqual(motivation._db_recent(self.db), [])
