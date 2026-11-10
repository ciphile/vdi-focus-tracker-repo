"""v2.11.0: /vdi chọn đo VDI mở bằng Citrix, Windows App (Azure Virtual Desktop, msrdc.exe) hay cả hai."""
import tempfile
import threading
import unittest

from focus import intent, prefs
from focus.actions import vdi_lookup
from focus.config import ConfigError, vdi_client, vdi_client_allows, vdi_family
from focus.probe import MacProbe, WindowsProbe
from focus.storage import get_pref
from focus.telegram_bot import TelegramBot
from tests.helpers import TOKEN, FakeTelegramAPI, FakeWin32, TempCase, make_cfg, msg
from tests.test_mac_probe import FULL, HALF, FakeMacAPI, temp_cfg, win
from tests.test_probe import Clock

AVD_TITLE = "may-ao-01.cong-ty.example"


class FamilyTest(unittest.TestCase):
    def test_family_and_aliases(self):
        self.assertEqual(vdi_family("msrdc.exe"), "winapp")
        self.assertEqual(vdi_family("mstsc.exe"), "winapp")
        self.assertEqual(vdi_family("Windows App"), "winapp")
        self.assertEqual(vdi_family("citrix.desktopviewer.app.exe"), "citrix")
        self.assertEqual(vdi_family("citrix.engineui.app.exe"), "citrix")
        self.assertEqual(vdi_family("cdviewer.exe"), "citrix")
        self.assertEqual(vdi_family("citrix viewer"), "citrix")
        self.assertIsNone(vdi_family("vmware-view.exe"))
        self.assertEqual(vdi_client("AVD"), "winapp")
        self.assertEqual(vdi_client("windows app"), "winapp")
        self.assertEqual(vdi_client("both"), "ca_hai")
        self.assertIsNone(vdi_client("xyz"))

    def test_custom_process_counts_in_every_mode(self):
        for mode in ("ca_hai", "citrix", "winapp"):
            self.assertTrue(vdi_client_allows({"vdi_client": mode}, "vmware-view.exe"), mode)
        self.assertFalse(vdi_client_allows({"vdi_client": "citrix"}, "msrdc.exe"))
        self.assertFalse(vdi_client_allows({"vdi_client": "winapp"}, "cdviewer.exe"))

    def test_config_default_and_validation(self):
        self.assertEqual(make_cfg(tempfile.mkdtemp())["vdi_client"], "ca_hai")
        self.assertEqual(make_cfg(tempfile.mkdtemp(), vdi_client="AVD")["vdi_client"], "winapp")
        with self.assertRaises(ConfigError):
            make_cfg(tempfile.mkdtemp(), vdi_client="teamviewer")


class WindowsClientTest(unittest.TestCase):
    """Máy có cả cửa sổ Citrix lẫn cửa sổ Windows App (msrdc.exe) đang mở."""

    def setUp(self):
        self.cfg = make_cfg(tempfile.mkdtemp())
        self.w = FakeWin32()
        self.clock = Clock()
        self.citrix = self.w.add(1, "citrix.desktopviewer.app.exe", "AZ-WIN11 - Desktop Viewer")
        self.avd = self.w.add(2, "msrdc.exe", AVD_TITLE)
        self.devices = self.w.add(3, "windows365.exe", "Windows App")  # danh sách máy, không phải phiên VDI
        self.chrome = self.w.add(4, "chrome.exe", "Báo Mới - Google Chrome")
        self.p = WindowsProbe(self.cfg, api=self.w, clock=self.clock)

    def state(self, fg, mode=None):
        if mode:
            self.cfg["vdi_client"] = mode
        self.w.fg = fg
        self.clock.t += 5
        return self.p.sample()["vdi_state"]

    def test_default_counts_both(self):
        self.assertEqual(self.state(self.citrix), "foreground")
        self.assertEqual(self.state(self.avd), "foreground")
        self.assertEqual(self.state(self.devices), "background", "cửa sổ danh sách máy của Windows App không là VDI")

    def test_winapp_only(self):
        self.assertEqual(self.state(self.avd, "winapp"), "foreground")
        self.assertEqual(self.state(self.citrix), "background", "Citrix ở trước = ngoài VDI, VDI (msrdc) vẫn mở phía sau")
        self.w.windows[self.avd]["iconic"] = True
        self.assertEqual(self.state(self.citrix), "minimized")
        del self.w.windows[self.avd]
        self.clock.t += 60
        self.assertEqual(self.state(self.citrix), "absent", "chỉ còn Citrix: coi như không có VDI")

    def test_citrix_only(self):
        self.assertEqual(self.state(self.citrix, "citrix"), "foreground")
        self.assertEqual(self.state(self.avd), "background")
        del self.w.windows[self.citrix]
        self.clock.t += 60
        self.assertEqual(self.state(self.avd), "absent")

    def test_switch_applies_on_next_sample_without_restart(self):
        self.assertEqual(self.state(self.citrix), "foreground")  # đã nhớ cửa sổ Citrix
        self.w.windows[self.avd]["iconic"] = True
        self.assertEqual(self.state(self.chrome, "winapp"), "minimized", "bỏ ngay cửa sổ Citrix đã nhớ")
        self.assertEqual(self.state(self.chrome, "citrix"), "background")

    def test_winapp_ignores_citrix_fallbacks(self):
        """Chỉ đo Windows App: mặt phiên Citrix, app Citrix tên lạ, cửa sổ không đọc được tên process đều không tính."""
        surface = self.w.add(5, "citrix.engineui.app.exe", "MockWindow", tool=True)
        odd = self.w.add(6, "citrix.newviewer.exe", "AZ-WIN11 - Desktop Viewer")
        admin = self.w.add(7, "", "AZ-WIN11 - Desktop Viewer")
        del self.w.windows[self.avd]
        for h in (surface, odd, admin):
            with self.subTest(h=h):
                self.clock.t += 60
                self.assertEqual(self.state(h, "winapp"), "absent")
        self.assertEqual(self.p.warnings, [], "không cảnh báo cửa sổ Citrix lạ khi không đo Citrix")
        self.clock.t += 60
        self.assertEqual(self.state(odd, "ca_hai"), "foreground")

    def test_custom_process_still_counts(self):
        self.cfg["vdi_processes"].append("vmware-view.exe")
        h = self.w.add(8, "vmware-view.exe", "Horizon")
        for mode in ("citrix", "winapp", "ca_hai"):
            self.clock.t += 60
            self.assertEqual(self.state(h, mode), "foreground", mode)

    def test_method_text_names_the_client(self):
        self.assertIn("Windows App", WindowsProbe(dict(self.cfg, vdi_client="winapp"), api=self.w).method)
        self.assertNotIn("Citrix", WindowsProbe(dict(self.cfg, vdi_client="winapp"), api=self.w).method)
        self.assertIn("Citrix", WindowsProbe(dict(self.cfg, vdi_client="citrix"), api=self.w).method)


class MacClientTest(unittest.TestCase):
    def setUp(self):
        self.cfg = temp_cfg(self)
        self.api = FakeMacAPI()
        self.p = MacProbe(self.cfg, api=self.api)

    def state(self, on, mode):
        self.cfg["vdi_client"] = mode
        self.api.on = list(on)
        return self.p.sample()["vdi_state"]

    def test_modes(self):
        citrix, avd = [win("Citrix Viewer", FULL), win("Finder", HALF)], [win("Windows App", FULL), win("Finder", HALF)]
        self.assertEqual(self.state(citrix, "ca_hai"), "foreground")
        self.assertEqual(self.state(avd, "ca_hai"), "foreground")
        self.assertEqual(self.state(avd, "winapp"), "foreground")
        self.assertNotEqual(self.state(citrix, "winapp"), "foreground")
        self.assertEqual(self.state(citrix, "citrix"), "foreground")
        self.assertNotEqual(self.state(avd, "citrix"), "foreground")


class VdiCommandTest(TempCase):
    def setUp(self):
        super().setUp()
        self.cfg.update(telegram_bot_token=TOKEN, telegram_chat_id="42", ai_provider="off")
        self.api = FakeTelegramAPI()
        self.state = {"paused": threading.Event(), "last": None, "perf": ""}
        self.bot = TelegramBot(self.cfg, self.state, api=self.api)

    def say(self, text):
        self.api.clear()
        self.bot.handle(msg(text))
        return self.api.sent()

    def ok(self):
        pid = list(self.bot.pending)[0]
        self.api.clear()
        self.bot.handle_callback({"id": "c", "data": f"ok:{pid}", "message": {"chat": {"id": 42}, "message_id": 5}})
        return self.api.sent()

    def test_view_lists_options(self):
        out = self.say("/vdi")[0]
        self.assertIn("Đang đo VDI mở bằng: cả hai", out)
        for k in ("/vdi citrix", "/vdi winapp", "/vdi ca_hai", "/vdi mac_dinh"):
            self.assertIn(k, out)
        self.assertFalse(self.bot.pending)

    def test_command_changes_saves_and_survives_restart(self):
        out = self.say("/vdi winapp")[0]
        self.assertIn("Đã đổi VDI mở bằng: chỉ Windows App", out)
        self.assertEqual(self.cfg["vdi_client"], "winapp")
        self.assertEqual(get_pref(self.bot.db, "vdi_client"), "winapp")
        cfg2 = make_cfg(self.tmp)
        prefs.apply(cfg2, self.bot.db)
        self.assertEqual(cfg2["vdi_client"], "winapp", "khởi động lại vẫn giữ")
        for text, want in (("/vdi citrix", "citrix"), ("/vdi windows app", "winapp"), ("/vdi avd", "winapp"),
                           ("/vdi cả hai", "ca_hai"), ("/vdi Citrix", "citrix")):
            self.say(text)
            self.assertEqual(self.cfg["vdi_client"], want, text)
        self.say("/vdi mac_dinh")
        self.assertEqual(self.cfg["vdi_client"], "ca_hai")
        self.assertIsNone(get_pref(self.bot.db, "vdi_client"))
        self.assertIn("Chọn một trong", self.say("/vdi xyz")[0])
        self.assertEqual(self.cfg["vdi_client"], "ca_hai")

    def test_natural_language_asks_before_changing(self):
        cases = {"chuyển sang windows app": "winapp", "chuyển từ citrix sang windows app nhé": "winapp",
                 "chuyển qua citrix": "citrix", "dùng avd từ hôm nay": "winapp", "chỉ đo citrix thôi": "citrix"}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.bot.pending.clear()
                self.cfg["vdi_client"] = "ca_hai"
                out = self.say(text)
                self.assertTrue(self.bot.pending, out)
                self.assertEqual(self.cfg["vdi_client"], "ca_hai", "chưa bấm OK thì chưa đổi")
                self.ok()
                self.assertEqual(self.cfg["vdi_client"], want)

    def test_lookup_and_rules(self):
        self.assertEqual(vdi_lookup("từ windows app về citrix"), "citrix", "lấy app nhắc sau cùng")
        self.assertEqual(vdi_lookup("citrix và windows app, cả hai"), "ca_hai")
        self.assertIsNone(vdi_lookup("hôm nay làm gì"))
        self.assertEqual(intent.by_rules("đang đo vdi nào?")[0].name, "chon_app_vdi")
        self.assertEqual(intent.by_rules("Citrix chậm quá làm mình sao nhãng")[0].name, "ghi_phan_tam")

    def test_status_shows_client(self):
        self.say("/vdi winapp")
        self.assertIn("Đo VDI mở bằng: chỉ Windows App", "\n".join(self.say("/status")))


if __name__ == "__main__":
    unittest.main()
