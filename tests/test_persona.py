"""Xưng hô và giọng nói: đọc persona.json, đổi "bạn"/"mình", câu mở đầu cảnh báo, lời dặn AI."""
import json
import os
from unittest import mock

from focus import persona
from tests.helpers import TempCase

BRO = dict(persona.DEFAULT, goi_nguoi_dung="bro", bot_xung="tui")


class LoadTest(TempCase):
    def write(self, content):
        path = os.path.join(self.tmp, "persona.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        return path

    def test_missing_file_defaults(self):
        self.assertEqual(persona.load(os.path.join(self.tmp, "không-có.json")), persona.DEFAULT)

    def test_invalid_json_and_non_object(self):
        for junk in ("{hỏng", "[1, 2]", '"chuỗi"', "null", ""):
            self.assertEqual(persona.load(self.write(junk)), persona.DEFAULT, junk)

    def test_values_loaded_and_cleaned(self):
        p = persona.load(self.write({"ten": "  Minh ", "goi_nguoi_dung": "bro", "bot_xung": "tui",
                                     "ten_sep": "anh Tuấn", "giong": "hai_huoc", "mo_ta": 42,
                                     "la": "bỏ qua", "bot_xung_x": "?"}))
        self.assertEqual(p, {"ten": "Minh", "tuoi": "", "noi_song": "", "goi_nguoi_dung": "bro", "bot_xung": "tui", "ten_sep": "anh Tuấn",
                             "giong": "hai_huoc", "mo_ta": "42"})

    def test_inspect_states(self):
        self.assertEqual(persona.inspect(os.path.join(self.tmp, "không-có.json"))["state"], "missing")
        bad = persona.inspect(self.write('{\n  "ten": "Minh",\n}'))
        self.assertEqual(bad["state"], "error")
        self.assertIn("dư dấu phẩy ở dòng cuối", bad["error"])  # Python 3.13 và bản cũ báo khác chữ, cùng gợi ý
        self.assertEqual(persona.inspect(self.write("[1]"))["state"], "error")
        path = os.path.join(self.tmp, "persona.json")
        with open(path, "wb") as f:  # Notepad cũ lưu ANSI: chữ có dấu không phải UTF-8
            f.write(b'{"ten": "Tr\xe2n"}')  # "Trân" kiểu Windows-1252
        info = persona.inspect(path)
        self.assertEqual(info["state"], "error")
        self.assertIn("UTF-8", info["error"])

    def test_inspect_warnings(self):
        info = persona.inspect(self.write({"_huong_dan": "bỏ qua", "ten": "Minh", "goi_nguoi_dung": "anh",
                                           "giong": "dữ dằn", "ten_sepp": "anh Tuấn"}))
        self.assertEqual(info["state"], "ok")
        self.assertEqual(info["unknown"], ["ten_sepp"], "khoá bắt đầu bằng _ là ghi chú, không báo")
        self.assertEqual(info["bad_tone"], "dữ dằn")
        self.assertEqual(info["empty"], ["tuoi", "noi_song", "mo_ta"])
        ok, lines = persona.check_lines(self.write({"ten": "Minh", "tuoi": "35", "noi_song": "Singapore",
                                                    "mo_ta": "Dev AS400", "ten_sep": "anh Tuấn"}))
        self.assertTrue(ok)
        self.assertEqual(lines, ["✓ config/persona.json: bot gọi bạn «bạn», tự xưng «mình», giọng than_mat, tên Minh, "
                                 "sếp anh Tuấn"])

    def test_check_lines_missing_and_broken(self):
        ok, lines = persona.check_lines(os.path.join(self.tmp, "không-có.json"))
        self.assertFalse(ok)
        self.assertIn("persona.example.json", lines[0])
        ok, lines = persona.check_lines(self.write('{"ten": "Minh" "tuoi": "35"}'))
        self.assertFalse(ok)
        self.assertIn("sai cú pháp JSON ở dòng 1, cột 16 (thiếu dấu phẩy cuối dòng trước)", lines[0])
        for broken, hint in (('{"ten": "Minh}', "thiếu dấu ngoặc kép đóng"), ('{"ten" "Minh"}', "thiếu dấu hai chấm"),
                             ('{"ten": Minh}', "thiếu giá trị"), ('{"ten": "Minh"} x', "chữ thừa sau dấu }"),
                             ("", "file trống")):
            self.assertIn(hint, persona.check_lines(self.write(broken))[1][0], broken)

    def test_broken_file_logged(self):
        with self.assertLogs("focus", "WARNING") as cm:
            self.assertEqual(persona.load(self.write("{hỏng")), persona.DEFAULT)
        self.assertIn("dùng xưng hô mặc định", cm.output[0])

    def test_bom_unknown_tone_empty_words(self):
        path = os.path.join(self.tmp, "persona.json")
        with open(path, "w", encoding="utf-8-sig") as f:  # Notepad trên Windows hay lưu kèm BOM
            json.dump({"giong": "dữ dằn", "goi_nguoi_dung": "  ", "bot_xung": None}, f)
        p = persona.load(path)
        self.assertEqual(p["giong"], "than_mat")
        self.assertEqual(p["goi_nguoi_dung"], "bạn")
        self.assertEqual(p["bot_xung"], "mình")


class ApplyTest(TempCase):
    def test_default_unchanged(self):
        s = "Bạn ơi, mình nhắc bạn nghỉ nhé."
        self.assertEqual(persona.apply(s, persona.DEFAULT), s)
        self.assertEqual(persona.apply("", BRO), "")
        self.assertIsNone(persona.apply(None, BRO))

    def test_swap_words_and_capitalise(self):
        self.assertEqual(persona.apply("Bạn ơi, mình nhắc bạn nghỉ nhé. Mình đi đây.", BRO),
                         "Bro ơi, tui nhắc bro nghỉ nhé. Tui đi đây.")
        p = dict(persona.DEFAULT, goi_nguoi_dung="anh Minh", bot_xung="em")
        self.assertEqual(persona.apply("Bạn làm tốt lắm, mình tự hào về bạn!", p),
                         "Anh Minh làm tốt lắm, em tự hào về anh Minh!")

    def test_word_boundaries(self):
        # Chỉ đổi khi "bạn"/"mình" đứng riêng thành một tiếng; dính liền chữ khác thì giữ nguyên.
        for s in ("bạnh", "xbạn", "mìnhx", "bạn_bè", "Mìnhđ", "ABạn", "bạn2", "mình9"):
            self.assertEqual(persona.apply(s, BRO), s, s)
        # Dấu câu, xuống dòng, ngoặc vẫn là ranh giới.
        self.assertEqual(persona.apply("(bạn)\nmình: bạn?", BRO), "(bro)\ntui: bro?")
        # Viết hoa toàn bộ không phải đầu câu: giữ nguyên.
        self.assertEqual(persona.apply("BẠN ƠI", BRO), "BẠN ƠI")

    def test_compound_words_follow_syllable_rule(self):
        # Tiếng Việt mỗi tiếng là một từ: "bạn bè", "một mình" cũng bị đổi theo luật từng tiếng.
        # Vì vậy câu bot tự viết tránh dùng các từ ghép này (câu trích dẫn gửi raw, không qua apply).
        self.assertEqual(persona.apply("bạn bè", BRO), "bro bè")
        self.assertEqual(persona.apply("một mình", BRO), "một tui")

    def test_special_chars_in_replacement(self):
        # Tên tự đặt có "\" hay "\1" không được làm hỏng/sập việc gửi tin.
        p = dict(persona.DEFAULT, goi_nguoi_dung=r"sếp\1", bot_xung=r"t\g<0>")
        self.assertEqual(persona.apply("Bạn ơi, mình đây", p), r"Sếp\1 ơi, t\g<0> đây")


class LeadAndInstructionsTest(TempCase):
    def test_lead_per_tone(self):
        for tone in persona.TONES:
            p = dict(persona.DEFAULT, giong=tone, goi_nguoi_dung="bro", ten_sep="anh Tuấn")
            for kind in ("out_of_vdi", "away", "boss"):
                text = persona.lead(kind, p)
                self.assertTrue(text, (tone, kind))
                self.assertNotIn("{", text)
            self.assertIn("anh Tuấn", persona.lead("boss", p))
        self.assertEqual(persona.lead("không_có", persona.DEFAULT), "")

    def test_lead_uses_address_and_capital(self):
        p = dict(persona.DEFAULT, giong="vui_tuoi", goi_nguoi_dung="bro")
        self.assertEqual(persona.lead("away", p), "Bro ơi, ghế đang trống nè! 🪑")
        with mock.patch.object(persona.random, "choice", lambda xs: xs[0]):
            p = dict(persona.DEFAULT, giong="hai_huoc", goi_nguoi_dung="bro")
            self.assertEqual(persona.lead("out_of_vdi", p), "Bro ơi, Chrome không trả lương cho bro đâu nha 😄")

    def test_boss_lead_empty_without_boss(self):
        for tone in persona.TONES:
            self.assertEqual(persona.lead("boss", dict(persona.DEFAULT, giong=tone)), "")

    def test_ai_instructions(self):
        base = persona.ai_instructions(persona.DEFAULT)
        self.assertIn('Gọi người dùng là "bạn"', base)
        self.assertIn('tự xưng là "mình"', base)
        self.assertIn(persona.TONE_PROMPT["than_mat"], base)
        self.assertNotIn("Sếp", base)
        self.assertNotIn("tên", base.split(".", 2)[-1])
        p = dict(persona.DEFAULT, ten="Minh", goi_nguoi_dung="bro", bot_xung="tui", ten_sep="anh Tuấn",
                 giong="sep_kho_tinh", mo_ta="x" * 800)
        s = persona.ai_instructions(p)
        for part in ('"bro"', '"tui"', persona.TONE_PROMPT["sep_kho_tinh"], "Người dùng tên Minh",
                     "Sếp của người dùng là anh Tuấn"):
            self.assertIn(part, s)
        self.assertIn("x" * 500, s)
        self.assertNotIn("x" * 501, s)  # mô tả bị cắt 500 ký tự
