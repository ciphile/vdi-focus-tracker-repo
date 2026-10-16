"""HTTPS dùng chung cho mọi lần gọi mạng (Telegram, AI, lịch lễ MOM): một SSL context cho cả tiến trình.

Python cài từ python.org trên Mac không có sẵn chứng chỉ gốc (CA) cho tới khi chạy «Install Certificates.command»:
khi đó mọi kết nối HTTPS báo CERTIFICATE_VERIFY_FAILED. Context ở đây thấy kho chứng chỉ trống thì nạp thêm file
chứng chỉ có sẵn của macOS (/etc/ssl/cert.pem), nên app vẫn chạy được mà không cần bước đó.
Windows / Linux / Python của Apple hay Homebrew đã có chứng chỉ: không đổi gì.
"""
import os
import ssl
import threading
import urllib.request

from .logs import get_logger

CA_FALLBACK_FILES = ("/etc/ssl/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem", "/usr/local/etc/openssl@3/cert.pem",
                     "/etc/ssl/certs/ca-certificates.crt")

_ctx = None
_lock = threading.Lock()


def _ca_count(ctx):
    try:
        return int(ctx.cert_store_stats().get("x509_ca", 0))
    except Exception:  # không đếm được: coi như có (không đụng vào)
        return 1


def make_context(fallbacks=CA_FALLBACK_FILES):
    """SSL context mặc định (có kiểm tra chứng chỉ). Kho CA trống thì nạp file CA đầu tiên tìm thấy trong fallbacks."""
    ctx = ssl.create_default_context()
    if _ca_count(ctx) == 0:
        for path in fallbacks:
            if not os.path.isfile(path):
                continue
            try:
                ctx.load_verify_locations(cafile=path)
            except (OSError, ssl.SSLError) as e:
                get_logger().warning("Không nạp được chứng chỉ gốc từ %s: %s", path, e)
                continue
            get_logger().info("Python này chưa có chứng chỉ gốc (CA): dùng %s của hệ điều hành.", path)
            break
    return ctx


def context():
    global _ctx
    with _lock:
        if _ctx is None:
            _ctx = make_context()
        return _ctx


def urlopen(req, timeout):
    """urllib.request.urlopen với SSL context chung (vẫn theo proxy hệ thống như cũ)."""
    return urllib.request.urlopen(req, timeout=timeout, context=context())
