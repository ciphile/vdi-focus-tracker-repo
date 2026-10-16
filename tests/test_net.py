"""HTTPS dùng chung: Python trên Mac chưa có chứng chỉ gốc (CA) vẫn kết nối được nhờ file CA của hệ điều hành."""
import os
import ssl
import tempfile
import unittest
import urllib.error
from unittest import mock

from focus import errors, net


def _empty_store_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # có kiểm tra chứng chỉ nhưng kho CA trống, giống python.org trên Mac
    return ctx


class MakeContextTest(unittest.TestCase):
    def ca_file(self):
        """File CA thật của máy chạy test (Linux/Mac); Windows không có thì bỏ qua test."""
        path = ssl.get_default_verify_paths().cafile
        for p in [path] + list(net.CA_FALLBACK_FILES):
            if p and os.path.isfile(p):
                return p
        self.skipTest("máy này không có file CA dạng PEM")

    def test_empty_store_loads_os_ca_file(self):
        ca = self.ca_file()
        with mock.patch("ssl.create_default_context", side_effect=_empty_store_context):
            ctx = net.make_context(fallbacks=("/khong/co/file.pem", ca))
        self.assertGreater(ctx.cert_store_stats()["x509_ca"], 0)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED, "không bao giờ tắt kiểm tra chứng chỉ")

    def test_store_with_ca_is_left_alone(self):
        ctx = mock.Mock()
        ctx.cert_store_stats.return_value = {"x509_ca": 140}
        with mock.patch("ssl.create_default_context", return_value=ctx):
            self.assertIs(net.make_context(fallbacks=("/etc/ssl/cert.pem",)), ctx)
        ctx.load_verify_locations.assert_not_called()

    def test_no_fallback_file_keeps_default(self):
        with mock.patch("ssl.create_default_context", side_effect=_empty_store_context):
            ctx = net.make_context(fallbacks=(os.path.join(tempfile.gettempdir(), "khong-co-ca.pem"),))
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 0)

    def test_urlopen_passes_shared_context(self):
        with mock.patch("urllib.request.urlopen") as op:
            net.urlopen("https://example.invalid", timeout=5)
        self.assertIs(op.call_args.kwargs["context"], net.context())
        self.assertEqual(op.call_args.kwargs["timeout"], 5)


class CertificateErrorTextTest(unittest.TestCase):
    def err(self):
        return urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))

    def test_mac_points_to_install_certificates(self):
        with mock.patch.object(errors.sys, "platform", "darwin"):
            text = errors.explain(self.err())
        self.assertIn("Install Certificates.command", text)

    def test_windows_points_to_company_proxy(self):
        with mock.patch.object(errors.sys, "platform", "win32"):
            text = errors.explain(self.err())
        self.assertIn("proxy", text)
        self.assertNotIn("Install Certificates", text)
