"""Bóc tách tin nhắn tự nhiên: AI (giả) và rule dự phòng."""
import datetime as dt
from unittest import mock

from focus import ai_client, intent
from focus.actions import ACTIONS, BY_COMMAND, bot_commands, parse_command_args, validate, BY_NAME, help_text
from tests.helpers import TempCase


class RulesTest(TempCase):
    def rule(self, text):
        found = intent.by_rules(text)
        return (found[0].name, found[1]) if found else (None, {})

    def test_fold_keeps_length(self):
        for s in ("Việc ngày mai cần làm là ĐỐI SOÁT", "Ả Ấ Ẫ đ Đ ơ ư", "abc", "😀 emoji"):
            self.assertEqual(len(intent.fold(s)), len(s))
        self.assertEqual(intent.fold("Việc NGÀY mai đó"), "viec ngay mai do")

    def test_tomorrow_task(self):
        for text, want in [("việc ngày mai cần làm là fix job đối soát CL0123", "fix job đối soát CL0123"),
                           ("Ngày mai: review PR của team", "review PR của team"),
                           ("sáng mai làm tiếp spec API thanh toán", "làm tiếp spec API thanh toán"),
                           ("mai làm tiếp job đối soát", "làm tiếp job đối soát"),
                           ("mai cần làm deploy UAT", "deploy UAT")]:
            with self.subTest(text=text):
                name, args = self.rule(text)
                self.assertEqual(name, "ghi_viec_ngay_mai")
                self.assertEqual(args.get("text"), want)

    def test_various(self):
        cases = {
            "hôm nay mình tập trung được bao nhiêu rồi": "xem_hom_nay",
            "gửi báo cáo cho mình": "gui_bao_cao",
            "tổng kết tuần này sao rồi": "xem_tuan",
            "giờ vàng của mình là mấy giờ": "xem_gio_vang",
            "VDI chậm quá, chờ restart 20 phút": "ghi_issue",
            "bị chặn vì thiếu quyền DB UAT": "ghi_issue",
            "đã xong batch job tính lãi": "ghi_output",
            "as400 vào 8h10 ra 17h35": "ghi_gio_as400",
            "tạm dừng theo dõi nhé": "tam_dung",
            "tiếp tục": "tiep_tuc",
            "cho mình câu kinh thánh": "xin_cau_kinh_thanh",
            "chán quá trời": "tro_chuyen",
            "năng lượng hôm nay 4": "ghi_nang_luong",
            "kế hoạch hôm nay: fix bug A, review B": "ghi_ke_hoach",
            "xóa cache AI giúp": "xoa_cache_ai",
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.rule(text)[0], want)

    def test_args(self):
        self.assertEqual(self.rule("as400 vào 8h10 ra 17h35")[1], {"start": "08:10", "end": "17:35"})
        self.assertEqual(self.rule("năng lượng hôm nay 4")[1], {"energy": 4})
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        self.assertEqual(self.rule("ngày mai mình xin nghỉ phép"), ("bao_nghi", {"day": tomorrow}))
        self.assertEqual(self.rule("xin nghỉ phép mai")[1].get("day"), tomorrow)
        self.assertEqual(self.rule("xin nghỉ phép 2026-12-24 về quê")[1], {"day": "2026-12-24", "reason": "về quê"})

    def test_unknown(self):
        self.assertEqual(self.rule("asdkjh qwe zzz"), (None, {}))
        self.assertEqual(self.rule(""), (None, {}))

    def test_understand_falls_back_when_ai_fails(self):
        self.cfg["gemini_api_key"] = "k"
        with mock.patch.object(ai_client, "generate", side_effect=ai_client.AIError("offline")):
            action, args, source, err = intent.understand(self.cfg, "việc ngày mai là gửi spec")
        self.assertEqual((action.name, args, source, err), ("ghi_viec_ngay_mai", {"text": "gửi spec"}, "rule", None))

    def test_understand_with_ai(self):
        self.cfg["gemini_api_key"] = "k"
        replies = {
            "mai nhớ gọi anh Tuấn về job CL01": '{"action":"ghi_viec_ngay_mai","args":{"text":"gọi anh Tuấn về job CL01"}}',
            "AS400 hôm nay từ 8 giờ 5 tới 5 rưỡi chiều": '```json\n{"action":"ghi_gio_as400","args":{"start":"08:05","end":"17:30"}}\n```',
            "nay mệt ghê": '{"action":"tro_chuyen","args":{}}',
        }
        for text, raw in replies.items():
            with self.subTest(text=text), mock.patch.object(ai_client, "generate", return_value=(raw, "m")):
                action, args, source, err = intent.understand(self.cfg, text)
                self.assertEqual(source, "ai")
                self.assertIsNone(err)
        with mock.patch.object(ai_client, "generate", return_value=(replies["nay mệt ghê"], "m")):
            self.assertEqual(intent.understand(self.cfg, "nay mệt ghê")[1], {"text": "nay mệt ghê"})

    def test_distraction_reason_recorded_even_if_ai_says_chat(self):
        """Log thật 16/10: "Nãy giờ mình bận đi trông em bé khóc" bị AI hiểu là tro_chuyen, không ghi phân tâm."""
        self.cfg["gemini_api_key"] = "k"
        text = "Nãy giờ mình bận đi trông em bé khóc"
        raw = '{"action":"tro_chuyen","args":{"text":"Nãy giờ mình bận đi trông em bé khóc"}}'
        with mock.patch.object(ai_client, "generate", return_value=(raw, "m")) as gen:
            action, args, source, err = intent.understand(self.cfg, text)
        self.assertEqual((action.name, args, source, err), ("ghi_phan_tam", {"text": text}, "rule", None))
        self.assertIn("ghi_phan_tam", gen.call_args[0][1])
        self.assertIn("trông em bé khóc", gen.call_args[0][1], "prompt AI có ví dụ gián đoạn = ghi_phan_tam")
        for t in ("con khóc quá", "bị gián đoạn vì mất điện", "bị làm phiền liên tục"):
            self.assertEqual(self.rule(t)[0], "ghi_phan_tam", t)
        self.assertNotEqual(self.rule("trong con mắt mình")[0], "ghi_phan_tam")
        with mock.patch.object(ai_client, "generate", return_value=('{"action":"tro_chuyen","args":{}}', "m")):
            self.assertEqual(intent.understand(self.cfg, "nay mệt ghê")[0].name, "tro_chuyen")

    def test_ai_bad_output_falls_back(self):
        self.cfg["gemini_api_key"] = "k"
        for raw in ("không biết", '{"action":"xoa_het_du_lieu"}', '{"action":"ghi_issue","args":"x"}', "{bad json"):
            with self.subTest(raw=raw), mock.patch.object(ai_client, "generate", return_value=(raw, "m")):
                action, args, source, err = intent.understand(self.cfg, "VDI chậm quá")
                self.assertEqual((action.name, source), ("ghi_issue", "rule"))

    def test_ai_missing_required_param_reports_error(self):
        self.cfg["gemini_api_key"] = "k"
        with mock.patch.object(ai_client, "generate", return_value=('{"action":"ghi_issue","args":{}}', "m")):
            action, args, source, err = intent.understand(self.cfg, "ghi issue giúp")
        self.assertEqual(action.name, "ghi_issue")
        self.assertTrue(err)


class ActionsTest(TempCase):
    def test_every_action_is_complete(self):
        names, cmds = set(), set()
        for a in ACTIONS:
            self.assertRegex(a.name, r"^[a-z_0-9]+$")
            self.assertNotIn(a.name, names)
            names.add(a.name)
            for c in a.commands:
                self.assertRegex(c, r"^/[a-z0-9_]{1,32}$")
                self.assertNotIn(c, cmds)
                cmds.add(c)
            self.assertTrue(callable(a.run))
            if a.writes:
                self.assertTrue(a.confirm, a.name)
        self.assertIn("/tmrtask", BY_COMMAND)
        self.assertEqual(BY_COMMAND["/tmrtask"].name, "ghi_viec_ngay_mai")
        self.assertEqual(len(bot_commands()), len([a for a in ACTIONS if a.commands]))
        for a in ACTIONS:
            if a.commands and a.name != "tro_giup":
                self.assertIn(a.command, help_text())

    def test_validate(self):
        as400 = BY_NAME["ghi_gio_as400"]
        self.assertEqual(validate(as400, {"start": "8:05", "end": "17.30"}), ({"start": "08:05", "end": "17:30"}, None))
        self.assertIsNotNone(validate(as400, {"start": "18:00", "end": "08:00"})[1])
        self.assertIsNotNone(validate(as400, {})[1])
        self.assertIsNotNone(validate(as400, {"start": "25:00"})[1])
        energy = BY_NAME["ghi_nang_luong"]
        self.assertEqual(validate(energy, {"energy": "5"})[0], {"energy": 5})
        for bad in (0, 6, "x"):
            self.assertIsNotNone(validate(energy, {"energy": bad})[1])
        off = BY_NAME["bao_nghi"]
        self.assertIsNotNone(validate(off, {"day": "2026-13-01"})[1])
        self.assertEqual(validate(off, {})[0], {})
        self.assertIsNotNone(validate(BY_NAME["ghi_issue"], {"text": "  "})[1])

    def test_parse_command_args(self):
        self.assertEqual(parse_command_args(BY_NAME["ghi_gio_as400"], "08:10 17:35"), {"start": "08:10", "end": "17:35"})
        self.assertEqual(parse_command_args(BY_NAME["bao_nghi"], "2026-12-24 nghỉ phép"),
                         {"day": "2026-12-24", "reason": "nghỉ phép"})
        self.assertEqual(parse_command_args(BY_NAME["ghi_viec_ngay_mai"], "  fix A "), {"text": "fix A"})
