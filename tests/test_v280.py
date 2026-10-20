"""2.8.0: câu nhắc sao nhãng theo ma trận mức nhắc × giọng bot, mỗi ô 20 câu, luân phiên không lặp."""
import re

from focus import messages, persona
from focus.nudge_lines import NUDGE
from tests.helpers import TempCase

LEVELS = ("nhe", "vua", "nghiem")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def nudge(level, vdi="minimized", nth=1, **p):
    data = {"minutes": 5, "nth": nth, "proc": "chrome.exe", "vdi_state": vdi, "golden": False, "level": level,
            "every": 5, "today_count": 3, "today_minutes": 20}
    return messages.out_of_vdi(data, None, dict(persona.DEFAULT, **p))


class MatrixTest(TempCase):
    def test_every_cell_has_20_distinct_lines(self):
        self.assertEqual(set(NUDGE), set(LEVELS))
        for level in LEVELS:
            self.assertEqual(set(NUDGE[level]), set(persona.TONES), level)
            for tone, lines in NUDGE[level].items():
                self.assertGreaterEqual(len(lines), 20, (level, tone))
                self.assertEqual(len(set(lines)), len(lines), (level, tone))

    def test_lines_fit_tone_and_format(self):
        p = dict(persona.DEFAULT, goi_nguoi_dung="bờ rồ", bot_xung="Bíp", ten_sep="Ted")
        for level in LEVELS:
            for tone, lines in NUDGE[level].items():
                for line in lines:
                    text = line.format(u="x", U="X", me="y", Me="Y", boss="z")  # chỉ dùng {u} {U} {me} {Me} {boss}
                    self.assertNotIn("{", text)
                    if tone == "sep_kho_tinh":
                        self.assertIsNone(EMOJI.search(line), line)     # sếp khó tính: không emoji
                    self.assertNotIn("thu nhỏ", line)                  # câu chung cho cả 2 trường hợp
                    for word in ("nghiện", "bỏ bê", "lười biếng"):
                        self.assertNotIn(word, line)
        self.assertTrue(persona.lead("boss", dict(p, giong="hai_huoc")))

    def test_strict_humorous_rotates_without_repeating(self):
        # Đúng trường hợp người dùng gặp: giọng hài hước + /nudge nghiem + VDI thu nhỏ, nhắc mỗi 5 phút.
        pool = len(persona.LEADS["minimized_nghiem"]["hai_huoc"]) + len(NUDGE["nghiem"]["hai_huoc"])
        seen = [nudge("nghiem", giong="hai_huoc", goi_nguoi_dung="bờ rồ").splitlines()[0] for _ in range(pool)]
        self.assertEqual(len(set(seen)), pool)                       # dùng hết các câu rồi mới lặp
        nxt = nudge("nghiem", giong="hai_huoc", goi_nguoi_dung="bờ rồ").splitlines()[0]
        self.assertNotEqual(nxt, seen[-1])                           # vòng mới không lặp ngay câu vừa gửi
        self.assertIn("VDI thu nhỏ lâu thế này chắc nó tưởng bị sa thải rồi. Mở ra ngay bờ rồ!", seen)

    def test_each_tone_level_uses_its_own_list(self):
        for level in LEVELS:
            for tone in persona.TONES:
                first = nudge(level, vdi="foreground", giong=tone, goi_nguoi_dung="bạn").splitlines()[0]
                allowed = [x.format(u="bạn", U="Bạn", me="mình", Me="Mình", boss="")
                           for x in NUDGE[level][tone] + persona.LEADS[
                               "out_of_vdi" + {"nhe": "_nhe", "nghiem": "_nghiem"}.get(level, "")][tone]]
                self.assertIn(first, allowed, (level, tone))

    def test_boss_line_rotates(self):
        p = dict(persona.DEFAULT, giong="hai_huoc", ten_sep="Ted", goi_nguoi_dung="bờ rồ")
        lines = {persona.lead("boss", p) for _ in range(6)}
        self.assertEqual(len(lines), 6)
        self.assertTrue(all("Ted" in x for x in lines))


class PromptStaysSmallTest(TempCase):
    """Nhắc nghiêm mỗi 5 phút kèm câu khích lệ AI: prompt không được dài thêm theo số lần đã gửi."""

    def test_avoid_block_keeps_at_most_5_quotes(self):
        from focus import motivation
        recent = [f'"Câu số {i}." (Nguồn {i})' for i in range(30)]
        block = motivation._avoid_block(recent)
        self.assertEqual(block.count("\n- "), 5)
        self.assertIn("Câu số 0.", block)                    # 5 câu MỚI NHẤT
        self.assertNotIn("Câu số 5.", block)
        self.assertEqual(motivation._avoid_block([]), "")

    def test_encourage_prompt_length_is_bounded(self):
        from unittest import mock
        from focus import ai_client, motivation
        from focus.quotes import BIBLE
        from focus.storage import db_path, open_db
        db = open_db(db_path(self.cfg))
        cfg = dict(self.cfg, ai_provider="gemini", encouragement_styles=["bible"])
        sizes = []

        def fake(cfg_, prompt, system, purpose=""):
            sizes.append(len(prompt))
            q = BIBLE[len(sizes) % len(BIBLE)]
            return f'"{q[0]}" ({q[1]})\\nVề VDI nào.', "gemini"
        with mock.patch.object(ai_client, "provider", lambda c: "gemini"), \
                mock.patch.object(ai_client, "generate", fake):
            for _ in range(40):                                  # 40 lần nhắc trong ngày
                motivation.encouragement(cfg, db, "ra khỏi VDI 10 phút", style="bible")
        self.assertEqual(len(sizes), 40)
        self.assertLessEqual(max(sizes), sizes[0] + 2000)        # có giới hạn, không tăng mãi
        # lần đầu: danh sách đầy đủ, chưa có câu cũ; về sau tối đa thêm 5 câu cũ + tiêu đề
        longest = max(len(f'- "{q[0]}" ({q[1]})') for q in BIBLE)
        self.assertLessEqual(max(sizes), sizes[0] + 5 * (longest + 40) + 200)


class OfflineVarietyTest(TempCase):
    """AI rớt mạng: câu nhắc / khích lệ / chào sáng vẫn đổi ngẫu nhiên, không lặp một câu hoài."""

    def test_every_lead_kind_has_several_lines(self):
        for kind, tones in persona.LEADS.items():
            for tone in persona.TONES:
                need = 1 if kind.endswith("_nhe") or kind in ("out_of_vdi", "minimized", "out_of_vdi_nghiem",
                                                              "minimized_nghiem") else 3
                lines = tones[tone]
                self.assertGreaterEqual(len(lines), need, (kind, tone))   # câu nhắc VDI còn có 20 câu/ô bên NUDGE
                self.assertEqual(len(set(lines)), len(lines), (kind, tone))
                for line in lines:
                    self.assertNotIn("{", line.format(u="x", U="X", me="y", Me="Y", boss="z", m=25))
                    if tone == "sep_kho_tinh":
                        self.assertIsNone(EMOJI.search(line), line)

    def test_dark_humor_only_in_humorous_tone(self):
        self.assertTrue(any("táo bón" in x for x in NUDGE["nghiem"]["hai_huoc"]))
        for level in LEVELS:
            for tone in ("than_mat", "vui_tuoi", "sep_kho_tinh"):
                self.assertFalse(any("táo bón" in x or "điếu văn" in x for x in NUDGE[level][tone]))

    def test_messages_vary_when_ai_is_down(self):
        from unittest import mock
        from focus import ai_client, motivation
        from focus.storage import db_path, open_db
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        with mock.patch.object(ai_client, "provider", lambda c: "gemini"), \
                mock.patch.object(ai_client, "generate", side_effect=ai_client.AIError("mất mạng")):
            enc = {motivation.encouragement(self.cfg, db, "x") for _ in range(10)}
            morning = {motivation.morning_message(self.cfg, db, {"first_task": "sửa job"}).split("\n")[0]
                       for _ in range(30)}
        self.assertGreaterEqual(len(enc), 8)
        self.assertGreaterEqual(len(morning), 4)
        p = dict(persona.DEFAULT, giong="sep_kho_tinh")
        for kind in ("away", "break", "pace_behind", "pace_behind_nghiem", "pace_praise", "water"):
            got = [persona.lead(kind, p) for _ in range(len(persona.LEADS[kind]["sep_kho_tinh"]))]
            self.assertEqual(len(set(got)), len(got), kind)              # xoay hết danh sách rồi mới lặp


class WaterVarietyTest(TempCase):
    """Nhắc uống nước: câu mở, mẹo / bệnh hay gặp, nghiên cứu đều luân phiên, không lặp câu."""

    def test_lists_are_large_and_distinct(self):
        for tone in persona.TONES:
            lines = persona.LEADS["water"][tone]
            self.assertGreaterEqual(len(lines), 12, tone)
            self.assertEqual(len(set(lines)), len(lines), tone)
        self.assertGreaterEqual(len(messages.WATER_TIPS), 12)
        self.assertGreaterEqual(len(messages.WATER_HEALTH), 10)
        self.assertTrue(any("sỏi thận" in x for x in messages.WATER_HEALTH))
        self.assertTrue(any("tiết niệu" in x for x in messages.WATER_HEALTH))
        self.assertTrue(any("huyết khối" in x for x in messages.WATER_HEALTH))

    def test_no_repeat_within_a_round(self):
        p = dict(persona.DEFAULT, giong="hai_huoc", goi_nguoi_dung="bờ rồ")
        msgs = [messages.water({}, p).splitlines() for _ in range(12)]
        self.assertEqual(len({m[0] for m in msgs}), 12)                       # câu mở không lặp
        self.assertEqual(len({m[1] for m in msgs}), 12)                       # mẹo / bệnh không lặp
        self.assertEqual(len({m[2] for m in msgs[:3]}), 3)                    # 3 nghiên cứu xoay vòng
        for m in msgs:
            self.assertNotIn("{", "\n".join(m))
        boss = [messages.water({}, dict(p, giong="sep_kho_tinh")).splitlines()[0] for _ in range(12)]
        self.assertTrue(all(EMOJI.search(x) is None for x in boss))


class BackAndPaceVarietyTest(TempCase):
    """Tin quay lại sau khi rời máy và tin chậm tiến độ: đổi câu theo giọng bot, luân phiên, cùng một ý."""

    def test_back_rotates_per_tone_with_minutes(self):
        for tone in persona.TONES:
            p = dict(persona.DEFAULT, giong=tone, goi_nguoi_dung="bờ rồ")
            seen = [messages.back({"minutes": 25}, p) for _ in range(7)]
            self.assertEqual(len(set(seen)), 7, tone)                 # 7 câu khác nhau rồi mới lặp
            self.assertTrue(all("25 phút" in x for x in seen), tone)  # luôn có số phút
            if tone == "sep_kho_tinh":
                self.assertTrue(all(EMOJI.search(x) is None for x in seen))

    def test_strict_pace_varies_lead_and_closing_line(self):
        info = {"at": "15:30", "actual_h": 1.65, "expected_h": 4.57, "target_h": 6, "end": "17:30",
                "behind_h": 2.9, "remaining_min": 120, "need_per_hour": 80, "left_h": 4.35}
        for tone in persona.TONES:
            p = dict(persona.DEFAULT, giong=tone, goi_nguoi_dung="bờ rồ")
            firsts, lasts = set(), set()
            for _ in range(7):
                text = messages.pace_behind(info, p, level="nghiem")
                lines = text.splitlines()
                firsts.add(lines[0])
                lasts.add(lines[-1])
            self.assertEqual(len(firsts), 7, tone)
            self.assertEqual(len(lasts), 7, tone)
