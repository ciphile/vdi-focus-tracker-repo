import json
import os

from focus.config import ConfigError, load_config, read_secrets
from tests.helpers import TempCase


class ConfigTest(TempCase):
    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def load(self, settings=None, secrets="", env=None):
        s = self.write("settings.json", json.dumps(settings)) if settings is not None else os.path.join(self.tmp, "none.json")
        e = self.write("secrets.env", secrets)
        return load_config(s, e, env=env or {}, make_dirs=False)

    def test_defaults_are_valid(self):
        cfg = self.load()
        self.assertEqual(cfg["work_end"], "17:00")
        self.assertEqual(cfg["lunch_start"], "11:15")
        self.assertEqual(cfg["auto_start_at"], "08:00")
        self.assertIn("cdviewer.exe", cfg["vdi_processes"])
        self.assertIn("persona", cfg)

    def test_time_is_normalised(self):
        self.assertEqual(self.load({"work_start": "8:05"})["work_start"], "08:05")

    def test_bad_values_rejected(self):
        for bad in ({"work_start": "8h"}, {"work_end": "25:00"}, {"auto_stop_at": "24:30"},
                    {"sample_seconds": 0}, {"nudge_out_of_vdi_minutes": -1}, {"weekly_report_day": "xyz"},
                    {"vdi_processes": "cdviewer.exe"}, {"work_start": "18:00"}, {"golden_hours": ["9-8"]},
                    {"ai_provider": "gpt"}, {"daily_focus_goal_hours": 0}, {"away_alert_minutes": True}):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                self.load(bad)

    def test_bad_json_message(self):
        s = self.write("settings.json", "{ work_start: 08:00 }")
        with self.assertRaises(ConfigError) as cm:
            load_config(s, os.path.join(self.tmp, "x.env"), env={}, make_dirs=False)
        self.assertIn("JSON", str(cm.exception))

    def test_utf8_bom_and_unknown_keys(self):
        s = self.write("settings.json", "﻿" + json.dumps({"work_end": "17:30", "wrok_start": "09:00"}))
        cfg = load_config(s, os.path.join(self.tmp, "x.env"), env={}, make_dirs=False)
        self.assertEqual(cfg["work_end"], "17:30")
        self.assertEqual(cfg["_unknown_keys"], ["wrok_start"])

    def test_secrets_file(self):
        p = self.write("s.env", "﻿# comment\nTELEGRAM_BOT_TOKEN = \"123:abc\"\n\nTELEGRAM_CHAT_ID=42\n"
                                "OTHER=1\n#GEMINI_API_KEY=nope\nGEMINI_API_KEY='g-key'\n")
        self.assertEqual(read_secrets(p), {"telegram_bot_token": "123:abc", "telegram_chat_id": "42",
                                           "gemini_api_key": "g-key"})

    def test_secrets_common_paste_mistakes(self):
        """Lỗi hay gặp khi điền secrets.env: dư dấu cách, bọc dấu nháy, nháy cong của Word/Notes, viết thường."""
        p = self.write("s.env", "TELEGRAM_BOT_TOKEN =  '''123:abc'''  \n"
                                "telegram_chat_id= “42”\n"
                                "export GEMINI_API_KEY=`AIzaXYZ`   # key của tôi\n")
        self.assertEqual(read_secrets(p), {"telegram_bot_token": "123:abc", "telegram_chat_id": "42",
                                           "gemini_api_key": "AIzaXYZ"})

    def test_gemini_key_with_inner_space_rejected(self):
        with self.assertRaises(ConfigError) as cm:
            self.load(secrets="GEMINI_API_KEY=AIza Sy123\n")
        self.assertIn("dấu cách ở giữa", str(cm.exception))

    def test_env_fallback(self):
        cfg = self.load(env={"GEMINI_API_KEY": "from-env", "TELEGRAM_CHAT_ID": "7"})
        self.assertEqual(cfg["gemini_api_key"], "from-env")
        self.assertEqual(cfg["telegram_chat_id"], "7")
        cfg = self.load(secrets="GEMINI_API_KEY=file\n", env={"GEMINI_API_KEY": "env"})
        self.assertEqual(cfg["gemini_api_key"], "file")

    def test_golden_hours_manual(self):
        self.assertEqual(self.load({"golden_hours": ["9:00-11:00"]})["golden_hours"], ["09:00-11:00"])
        self.assertEqual(self.load({"golden_hours": []})["golden_hours"], [])

    def test_case_insensitive_lists(self):
        cfg = self.load({"vdi_processes": ["CDViewer.EXE"], "vdi_title_keywords": ["Desktop VIEWER", " "]})
        self.assertEqual(cfg["vdi_processes"], ["cdviewer.exe"])
        self.assertEqual(cfg["vdi_title_keywords"], ["desktop viewer"])
