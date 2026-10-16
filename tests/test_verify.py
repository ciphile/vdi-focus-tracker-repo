"""Lệnh verify (kiem_tra_may.bat): chạy đủ các bước, ghi file kết quả, không gọi mạng/máy thật trong test."""
import io
import os
import unittest
from unittest import mock

from focus import cli, holidays, persona
from tests.helpers import TOKEN, TempCase, make_cfg, sample


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def sleep(self, s):
        self.t += s

    def monotonic(self):
        return self.t

    def perf_counter(self):
        return self.t


class FakeProbe:
    platform_name = "Windows"
    method = "giả"
    warnings = []

    def __init__(self, script):
        self.script = list(script)  # mỗi lần sample() lấy một phần tử, hết thì giữ phần tử cuối

    def sample(self):
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]


def lines(out):
    return "\n".join(str(c.args[0]) for c in out.call_args_list)


class VerifyProbeTest(unittest.TestCase):
    def run_probe(self, script):
        out = mock.Mock()
        with mock.patch.object(cli, "time", FakeClock()), mock.patch.object(cli, "_wait_enter"), \
                mock.patch.object(cli, "_beep"), \
                mock.patch("focus.probe.make_probe", return_value=FakeProbe(script)):
            return cli._verify_probe({}, out), lines(out)

    def steps_script(self, states):
        """Mẫu đầu (kiểm tra có VDI) rồi đủ mẫu cho từng bước VERIFY_STEPS theo states."""
        rows = [sample("foreground")]
        for (secs, _what, _want, _full), st in zip(cli.VERIFY_STEPS, states):
            rows += [st] * secs
        return rows

    def test_all_steps_pass(self):
        ok, text = self.run_probe(self.steps_script(
            [sample("foreground", full=True), sample("minimized"), sample("foreground", full=False),
             sample("background")]))
        self.assertTrue(ok, text)
        self.assertEqual(text.count("✓ Bước"), len(cli.VERIFY_STEPS))

    def test_minimized_seen_as_foreground_fails(self):
        ok, text = self.run_probe(self.steps_script(
            [sample("foreground"), sample("foreground"), sample("foreground", full=False), sample("background")]))
        self.assertFalse(ok)
        self.assertIn("✗ Bước 2: mong đợi minimized", text)

    def test_windowed_vdi_must_report_not_full(self):
        ok, text = self.run_probe(self.steps_script(
            [sample("foreground"), sample("minimized"), sample("foreground", full=True), sample("background")]))
        self.assertFalse(ok)
        self.assertIn("✗ Bước 3", text)

    def test_no_vdi_window_stops_early(self):
        ok, text = self.run_probe([sample("absent")])
        self.assertFalse(ok)
        self.assertIn("Không thấy cửa sổ VDI", text)
        self.assertNotIn("Bước 1", text)


class VerifyMomTest(TempCase):
    def test_reads_real_layout(self):
        from tests.fixtures.mom_page import page
        out = mock.Mock()
        with mock.patch.object(holidays, "_download", return_value=page()):
            self.assertTrue(cli._verify_mom(self.cfg, out, year=2026))
        self.assertIn("✓ Trang MOM", lines(out))

    def test_blocked_network_reported(self):
        out = mock.Mock()
        self.assertFalse(cli._verify_mom(self.cfg, out, year=2026))  # TempCase chặn mạng
        self.assertIn("✗ Tải trang MOM", lines(out))


class CmdVerifyTest(TempCase):
    def run_verify(self, cfg, probe_ok=True, persona_json='{"ten": "Minh", "goi_nguoi_dung": "anh", "giong": "vui_tuoi"}'):
        sent = []
        persona_path = os.path.join(self.tmp, "persona.json")
        if persona_json is not None:
            with open(persona_path, "w", encoding="utf-8") as f:
                f.write(persona_json)

        def call(method, params=None, **kw):
            sent.append((method, params))
            return {"ok": True, "result": {"username": "test_bot"}}

        empty = unittest.TestSuite()
        with mock.patch("focus.telegram_bot.TelegramAPI.call", side_effect=call), \
                mock.patch("focus.ai_client.list_gemini_models", return_value=["gemini-flash-lite-latest"]), \
                mock.patch("focus.ai_client.generate", return_value=("Chào bạn!", "gemini-flash-lite-latest")), \
                mock.patch.object(cli, "_verify_mom", return_value=True), \
                mock.patch.object(cli, "_verify_autostart", return_value=True), \
                mock.patch.object(cli, "_verify_probe", return_value=probe_ok), \
                mock.patch.object(cli, "_print_probe_info"), \
                mock.patch("focus.probe.make_probe", return_value=FakeProbe([sample("foreground")])), \
                mock.patch("unittest.defaultTestLoader.discover", return_value=empty), \
                mock.patch.object(persona, "PATH", persona_path), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            rc = cli.cmd_verify(cfg)
        logs_dir = os.path.join(cfg["data_dir"], "logs")
        files = [f for f in os.listdir(logs_dir) if f.startswith("kiem_tra-")]
        self.assertEqual(len(files), 1)
        with open(os.path.join(logs_dir, files[0]), encoding="utf-8") as f:
            return rc, f.read(), sent

    def test_everything_ok(self):
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k" * 39)
        rc, text, sent = self.run_verify(cfg)
        self.assertEqual(rc, 0, text)
        self.assertIn("✓ Telegram: bot @test_bot", text, "kết quả lệnh check được ghi vào file")
        self.assertIn("✓ Gọi thử AI (gemini-flash-lite-latest): Chào bạn!", text)
        self.assertIn("== TÓM TẮT ==", text)
        self.assertIn(("sendMessage", {"chat_id": "42", "text": "✅ Kiểm tra máy: bot gửi tin được."}), sent)
        self.assertNotIn("k" * 39, text, "không ghi key ra file")
        self.assertNotIn(TOKEN, text, "không ghi token ra file")

    def test_persona_shown_in_check(self):
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k" * 39)
        rc, text, _ = self.run_verify(cfg)
        self.assertIn("✓ config/persona.json: bot gọi bạn «anh», tự xưng «mình», giọng vui_tuoi, tên Minh", text)
        self.assertIn("! Chưa điền: tuoi, noi_song, mo_ta", text)

    def test_missing_persona_fails_check(self):
        # Cài lần đầu bắt buộc điền persona.json: thiếu file thì phần check báo ✗ (app vẫn chạy với xưng hô mặc định).
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k" * 39)
        rc, text, _ = self.run_verify(cfg, persona_json=None)
        self.assertEqual(rc, 1)
        self.assertIn("✗ Chưa có config/persona.json", text)
        self.assertIn("✗ check", text)

    def test_broken_persona_fails_check_with_line(self):
        cfg = make_cfg(self.tmp, telegram_bot_token=TOKEN, telegram_chat_id="42", gemini_api_key="k" * 39)
        rc, text, _ = self.run_verify(cfg, persona_json='{\n  "ten": "Minh"\n  "tuoi": "35"\n}')
        self.assertEqual(rc, 1)
        self.assertIn("✗ config/persona.json sai cú pháp JSON ở dòng 3, cột 3", text)

    def test_missing_secrets_and_probe_fail(self):
        rc, text, sent = self.run_verify(self.cfg, probe_ok=False)
        self.assertEqual(rc, 1)
        self.assertIn("✗ check", text)
        self.assertIn("✗ vdi", text)
        self.assertEqual(sent, [])


class VerifyStepRuleTest(unittest.TestCase):
    def test_slow_start_but_held_at_the_end_passes(self):
        rows = [sample("background")] * 7 + [sample("foreground", full=True)] * 4
        self.assertTrue(cli._verify_step_ok(rows, "foreground", True))

    def test_flapping_state_fails(self):
        rows = [sample("foreground", full=True), sample("background")] * 6
        self.assertFalse(cli._verify_step_ok(rows, "foreground", True))

    def test_wrong_fullness_fails(self):
        rows = [sample("foreground", full=False)] * 12
        self.assertFalse(cli._verify_step_ok(rows, "foreground", True))
        self.assertTrue(cli._verify_step_ok(rows, "foreground", False))
        self.assertFalse(cli._verify_step_ok([], "foreground", None))


class FakeWinApi:
    def __init__(self, wins):
        self.wins = wins  # hwnd -> (tiêu đề, rect, iconic, tool)

    def top_windows(self):
        return list(self.wins)

    def is_visible(self, h):
        return True

    def title(self, h):
        return self.wins[h][0]

    def rect(self, h):
        return self.wins[h][1]

    def is_iconic(self, h):
        return self.wins[h][2]

    def is_toolwindow(self, h):
        return self.wins[h][3]


class DumpCitrixTest(unittest.TestCase):
    def test_lists_only_citrix_windows(self):
        api = FakeWinApi({1: ("AZ-WIN11 - Desktop Viewer", (0, 0, 1920, 1080), False, False),
                          2: ("Hộp thoại", (10, 10, 400, 300), False, True),
                          3: ("Chrome", (0, 0, 800, 600), False, False)})
        procs = {1: "citrix.desktopviewer.app.exe", 2: "citrix.engineui.app.exe", 3: "chrome.exe"}
        probe = mock.Mock(api=api, proc_name=lambda h: procs[h], window_kind=lambda h: "shown",
                          is_citrix=lambda h, p: p.startswith("citrix"))
        out = mock.Mock()
        cli._dump_citrix_windows(probe, out)
        text = lines(out)
        self.assertIn("citrix.desktopviewer.app.exe «AZ-WIN11 - Desktop Viewer» 1920x1080 hiện", text)
        self.assertIn("citrix.engineui.app.exe «Hộp thoại»", text)
        self.assertIn("tool window", text)
        self.assertNotIn("chrome", text)

    def test_lists_renamed_citrix_app_from_citrix_folder(self):
        api = FakeWinApi({1: ("MockWindow", (0, 0, 1541, 878), False, True),
                          2: ("Chrome", (0, 0, 800, 600), False, False)})
        procs = {1: "sessionsurface.exe", 2: "chrome.exe"}  # Citrix đổi tên, file vẫn trong ...\Citrix\...
        probe = mock.Mock(api=api, proc_name=lambda h: procs[h], window_kind=lambda h: "shown",
                          is_citrix=lambda h, p: h == 1)
        out = mock.Mock()
        cli._dump_citrix_windows(probe, out)
        text = lines(out)
        self.assertIn("sessionsurface.exe «MockWindow» 1541x878 hiện · tool window", text)
        self.assertNotIn("chrome", text)

    def test_no_api_is_silent(self):
        out = mock.Mock()
        cli._dump_citrix_windows(FakeProbe([sample("foreground")]), out)
        out.assert_not_called()


class VerifyPartsTest(TempCase):
    def test_unknown_part_rejected(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as so:
            self.assertEqual(cli.cmd_verify(self.cfg, ["xyz"]), 2)
        self.assertIn("Phần không có: xyz", so.getvalue())

    def test_only_selected_parts_run(self):
        with mock.patch.object(cli, "_verify_mom", return_value=True) as mom, \
                mock.patch.object(cli, "_verify_probe") as probe, \
                mock.patch("unittest.defaultTestLoader.discover") as disc, \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli.cmd_verify(self.cfg, ["mom"]), 0)
        mom.assert_called_once()
        probe.assert_not_called()
        disc.assert_not_called()

    def test_ai_failure_runs_diagnosis(self):
        from focus.ai_client import AIError
        cfg = make_cfg(self.tmp, gemini_api_key="k" * 39)
        calls = []

        def fake_http(c, method, url, headers, payload=None):
            calls.append(payload)
            if payload and "systemInstruction" in payload:
                from focus.ai_client import HTTPStatusError
                raise HTTPStatusError(400, '{"error": {"message": "Request contains an invalid argument."}}')
            return {}

        with mock.patch("focus.ai_client.list_gemini_models", return_value=["m"]), \
                mock.patch("focus.ai_client.generate", side_effect=AIError("Gemini từ chối")), \
                mock.patch("focus.ai_client._gemini_candidates", return_value=["gemini-x"]), \
                mock.patch("focus.ai_client._http", side_effect=fake_http), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as so:
            rc = cli.cmd_verify(cfg, ["ai"])
        text = so.getvalue()
        self.assertEqual(rc, 1)
        self.assertEqual(len(calls), 4)
        self.assertIn("✓ chỉ câu hỏi: được", text)
        self.assertIn("✗ + bối cảnh (systemInstruction)", text)
        self.assertNotIn("k" * 39, text)


class MacAutostartVerifyTest(TempCase):
    PRINT = ("gui/501/com.focustracker.agent = {{\n\tactive count = {active}\n\tpath = /Users/a/Library/LaunchAgents/"
             "com.focustracker.agent.plist\n\tstate = {state}\n\tprogram = /usr/bin/python3\n{exit}}}\n")

    def run_mac(self, plist_exists, rc, state="not running", exit_line="\tlast exit code = 0\n", err_log=None):
        out = mock.Mock()
        cfg = dict(self.cfg, _launch_agents_dir=self.tmp)
        if plist_exists:
            from focus import autostart
            open(autostart.mac_plist_path(cfg), "w").close()
        if err_log is not None:
            os.makedirs(os.path.join(cfg["data_dir"], "logs"), exist_ok=True)
            with open(os.path.join(cfg["data_dir"], "logs", "launchd.err.log"), "w", encoding="utf-8") as f:
                f.write(err_log)
        text = self.PRINT.format(active=int(state == "running"), state=state, exit=exit_line).encode()
        with mock.patch.object(cli.sys, "platform", "darwin"), \
                mock.patch("subprocess.run", return_value=mock.Mock(returncode=rc, stdout=text)), \
                mock.patch.object(cli.os, "getuid", create=True, return_value=501):
            return cli._verify_autostart(out, cfg), lines(out)

    def test_running(self):
        ok, text = self.run_mac(True, 0, state="running", exit_line="\tlast exit code = (never exited)\n")
        self.assertTrue(ok)
        self.assertIn("đang chạy", text)

    def test_last_run_failed_with_permission_error(self):
        log = ("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3: can't open file "
               "'/Users/a/Documents/focus-tracker/focus_tracker.py': [Errno 1] Operation not permitted\n")
        ok, text = self.run_mac(True, 0, exit_line="\tlast exit code = 2\n", err_log=log)
        self.assertFalse(ok, "launchd nạp job nhưng tracker chết ngay: không được báo ✓")
        self.assertIn("mã 2", text)
        self.assertIn("Operation not permitted", text)
        self.assertIn("~/focus-tracker", text)

    def test_last_run_failed_ex_config(self):
        ok, text = self.run_mac(True, 0, exit_line="\tlast exit code = 78: EX_CONFIG\n")
        self.assertFalse(ok)
        self.assertIn("mã 78: EX_CONFIG", text)

    def test_loaded(self):
        ok, text = self.run_mac(True, 0)
        self.assertTrue(ok)
        self.assertIn("✓ launchd", text)

    def test_plist_missing(self):
        ok, text = self.run_mac(False, 0)
        self.assertFalse(ok)
        self.assertIn("cai_tu_khoi_dong.command", text)

    def test_not_loaded(self):
        ok, text = self.run_mac(True, 113)
        self.assertFalse(ok)
        self.assertIn("chưa nạp", text)


class MacAutostartHelpersTest(unittest.TestCase):
    def test_protected_folders(self):
        from focus.autostart import mac_protected_folder
        home = "/Users/an"
        self.assertEqual(mac_protected_folder("/Users/an/Documents/focus-tracker", home), "Documents")
        self.assertEqual(mac_protected_folder("/Users/an/Desktop/x/focus-tracker", home), "Desktop")
        self.assertEqual(mac_protected_folder("/Users/an/Library/Mobile Documents/com~apple~CloudDocs/ft", home),
                         "Library/Mobile Documents")
        self.assertIsNone(mac_protected_folder("/Users/an/focus-tracker", home))
        self.assertIsNone(mac_protected_folder("/Users/an/Documents2/focus-tracker", home))

    def test_installer_checks_same_folders(self):
        from focus.autostart import MAC_PROTECTED
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "cai_tu_khoi_dong_mac.sh"), encoding="utf-8") as f:
            script = f.read()
        for name in MAC_PROTECTED:
            self.assertIn(f'"$HOME/{name}/"*', script)
        for key in ("<key>ExitTimeOut</key>", "<string>Standard</string>"):
            self.assertIn(key, script)

    def test_last_exit_parsing(self):
        from focus.autostart import mac_last_exit
        self.assertEqual(mac_last_exit("\tstate = running\n\tlast exit code = (never exited)\n"), (True, None, ""))
        self.assertEqual(mac_last_exit("\tstate = not running\n\tlast exit code = 78: EX_CONFIG\n"),
                         (False, 78, "EX_CONFIG"))
        self.assertEqual(mac_last_exit("gì đó"), (False, None, ""))


class LauncherFilesTest(unittest.TestCase):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_separate_windows_and_mac_launchers(self):
        with open(os.path.join(self.root, "kiem_tra_may.bat"), "rb") as f:
            bat = f.read()
        with open(os.path.join(self.root, "kiem_tra_may.command"), "rb") as f:
            mac = f.read()
        self.assertIn(b"\r\n", bat)
        self.assertNotIn(b"\r", mac, "script Mac phải dùng LF")
        self.assertTrue(mac.startswith(b"#!/bin/bash"))
        self.assertIn(b"focus_tracker.py verify %*", bat)
        self.assertIn(b'focus_tracker.py verify "$@"', mac)
        self.assertNotIn(b"winsound", mac)
        self.assertNotIn(b".command", bat.replace(b"kiem_tra_may.command", b""))

    def test_every_bat_has_a_mac_command_twin(self):
        bats = sorted(n for n in os.listdir(self.root) if n.endswith(".bat"))
        self.assertGreaterEqual(len(bats), 7)
        for bat in bats:
            mac = os.path.join(self.root, bat[:-4] + ".command")
            self.assertTrue(os.path.exists(mac), f"thiếu bản Mac của {bat}")
            with open(mac, "rb") as f:
                text = f.read()
            self.assertTrue(text.startswith(b"#!/bin/bash"), mac)
            self.assertNotIn(b"\r", text, f"{mac} phải dùng LF")
            self.assertIn(b'cd "$(dirname "$0")"', text, f"{mac} phải chạy trong thư mục app")
            with open(os.path.join(self.root, bat), "rb") as f:
                self.assertIn(b"\r\n", f.read(), f"{bat} phải dùng CRLF")

    def _lines(self, name):
        with open(os.path.join(self.root, name), encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}

    def test_gitignore_keeps_secrets_and_personal_data_off_github(self):
        lines = self._lines(".gitignore")
        for path in ("config/secrets.env", "config/settings.json", "config/settings.json.bak", "config/persona.json",
                     "config/python_path.txt", "config/python_path.cmd", "data/", "reports/", "__pycache__/"):
            self.assertIn(path, lines, f".gitignore thiếu {path}")
        for example in ("secrets.env.example", "settings.example.json", "persona.example.json"):
            self.assertTrue(os.path.exists(os.path.join(self.root, "config", example)))
            self.assertFalse(any(example in ln for ln in lines), f"file mẫu {example} phải được đưa lên")

    def test_gitattributes_keeps_launcher_line_endings(self):
        lines = self._lines(".gitattributes")
        for rule in ("*.bat text eol=crlf", "*.ps1 text eol=crlf", "*.vbs text eol=crlf",
                     "*.command text eol=lf", "*.sh text eol=lf"):
            self.assertIn(rule, lines)

    def test_report_launchers_open_the_report(self):
        for name in ("bao_cao_hom_nay.bat", "bao_cao_hom_nay.command"):
            with open(os.path.join(self.root, name), "rb") as f:
                self.assertIn(b"focus_tracker.py report --open", f.read(), name)

    def test_install_hint_points_to_double_click_uninstall(self):
        with open(os.path.join(self.root, "cai_tu_khoi_dong.ps1"), "rb") as f:
            ps1 = f.read()
        self.assertIn(b"go_tu_khoi_dong.bat", ps1)
        self.assertNotIn(b"chuot phai go_tu_khoi_dong.ps1", ps1)


class MacWindowDumpTest(unittest.TestCase):
    """kiem_tra_may trên Mac ghi danh sách cửa sổ thô vào file kết quả để chẩn đoán từ xa."""

    def test_dump_lists_windows_front_app_and_permission(self):
        from focus.probe import MacProbe
        from tests.test_mac_probe import FakeMacAPI, temp_cfg, win
        api = FakeMacAPI(on=[win("Google Chrome", (0.0, 0.0, 800.0, 600.0))],
                         hidden=[win("Citrix Viewer", (0.0, 0.0, 1512.0, 982.0))])
        api.front_app = lambda: (412, "Google Chrome")
        api.can_read_titles = lambda: False
        probe = MacProbe(temp_cfg(self), api=api)
        out = mock.Mock()
        cli._dump_mac_windows(probe, out)
        text = lines(out)
        self.assertIn("Google Chrome · pid None · 800x600@0,0", text)
        self.assertIn("Citrix Viewer · pid None · 1512x982@0,0", text)
        self.assertIn("App đang ở trước (NSWorkspace): Google Chrome · pid 412", text)
        self.assertIn("Quyền Screen Recording (đọc tiêu đề cửa sổ): chưa", text)

    def test_dump_skips_windows_probe_and_survives_errors(self):
        out = mock.Mock()
        cli._dump_mac_windows(mock.Mock(spec=["api", "proc_name"]), out)
        out.assert_not_called()
        from focus.probe import MacProbe
        from tests.test_mac_probe import FakeMacAPI, temp_cfg
        api = FakeMacAPI()
        probe = MacProbe(temp_cfg(self), api=api)
        api.windows = mock.Mock(side_effect=OSError("boom"))
        cli._dump_mac_windows(probe, out)
        self.assertIn("Không liệt kê được cửa sổ trên Mac", lines(out))
