"""Dịch lỗi kỹ thuật thành câu tiếng Việt dễ hiểu: chuyện gì xảy ra + bạn cần làm gì.

Mọi chỗ báo lỗi cho người dùng (bot Telegram, lệnh trên máy) đều đi qua explain(); log kỹ thuật
(data/logs/focus.log) vẫn giữ traceback đầy đủ để sửa.
"""
import errno
import json
import socket
import sqlite3
import sys
import ssl
import urllib.error

# Việc chạy nền (nhãn trong Notifier) -> tên dễ hiểu.
JOB_NAMES = {
    "morning": "lời chào buổi sáng", "plan": "hỏi kế hoạch", "review": "hỏi tổng kết cuối ngày",
    "summary": "tổng kết cuối ngày", "weekly": "tổng kết tuần", "boost": "câu khích lệ buổi chiều",
    "ai_review_retry": "gửi lại đánh giá AI", "catchup": "gửi bù tổng kết", "holiday_warn": "nhắc lịch lễ", "housekeeping": "dọn dẹp dữ liệu", "holidays": "cập nhật lịch ngày lễ",
    "leave_notice": "báo nghỉ phép nửa ngày",
    "out_of_vdi": "cảnh báo ngoài VDI", "away": "cảnh báo rời máy", "back": "chào quay lại",
    "break": "nhắc nghỉ giải lao", "phone": "nhắc cất điện thoại", "not_fullscreen": "gợi ý phóng to VDI",
    "water": "nhắc uống nước", "pace": "cảnh báo tiến độ", "pace_1030": "cảnh báo tiến độ 10:30", "pace_1400": "cảnh báo tiến độ 14:00",
    "pace_1530": "cảnh báo tiến độ 15:30",
}

HTTP_HINTS = {
    400: "yêu cầu gửi đi không hợp lệ (nội dung hoặc ảnh quá lớn / sai định dạng)",
    401: "khoá bí mật (token / API key) sai hoặc đã bị thu hồi. Kiểm tra lại trong config/secrets.env",
    403: "bị từ chối quyền: key chưa được bật dịch vụ, bị khoá, hoặc mạng công ty chặn",
    404: "không tìm thấy (sai địa chỉ, model đã ngừng, hoặc token bot sai)",
    408: "máy chủ chờ quá lâu",
    409: "đang có một bản bot khác cùng token chạy ở máy khác. Tắt bản kia đi",
    413: "dữ liệu gửi đi quá lớn",
    429: "gọi quá nhiều lần, hết lượt (quota). Đợi một lúc rồi thử lại",
    500: "máy chủ bên kia đang lỗi, thử lại sau",
    502: "máy chủ bên kia đang lỗi tạm thời, thử lại sau",
    503: "máy chủ bên kia đang quá tải, thử lại sau",
    504: "máy chủ bên kia trả lời quá lâu, thử lại sau",
}


def _api_message(body):
    """Lấy câu lỗi trong JSON trả về (Gemini/Claude/Telegram) nếu có, cắt ngắn."""
    try:
        data = json.loads(body or "")
    except ValueError:
        return ""
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or "")[:160]
    if isinstance(data, dict) and data.get("description"):
        return str(data["description"])[:160]
    return ""


def http(code, body=""):
    hint = HTTP_HINTS.get(code) or ("máy chủ bên kia đang lỗi" if code >= 500 else f"lỗi HTTP {code}")
    detail = _api_message(body)
    if code == 400 and "api key" in detail.lower():
        hint = HTTP_HINTS[401]
    return hint + (f" (chi tiết: {detail})" if detail else "")


def explain(exc):
    """Câu tiếng Việt cho người dùng. Không bao giờ raise, không lộ token/key."""
    try:
        return _explain(exc)
    except Exception:  # pragma: no cover - phòng hờ
        return f"lỗi không mong đợi ({type(exc).__name__}), chi tiết trong data/logs/focus.log"


def _explain(exc):
    name = type(exc).__name__
    if name in ("AIError", "ProbeError", "ConfigError"):  # đã là câu tiếng Việt dễ hiểu
        return str(exc)
    if name == "HTTPStatusError":
        return http(getattr(exc, "code", 0), getattr(exc, "body", ""))
    if isinstance(exc, urllib.error.HTTPError):
        return http(exc.code)
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "mạng chậm, máy chủ không trả lời kịp. Kiểm tra mạng / VPN rồi thử lại"
    if isinstance(exc, ssl.SSLError) or "CERTIFICATE" in str(exc).upper():
        if sys.platform == "darwin":
            return ("lỗi chứng chỉ bảo mật khi kết nối. Trên Mac thường do Python cài từ python.org chưa có chứng chỉ: "
                    "mở Finder > Applications > thư mục Python 3.x > nhấp đúp «Install Certificates.command», rồi chạy "
                    "lại. Vẫn lỗi thì có thể do proxy/tường lửa công ty kiểm tra HTTPS")
        return ("lỗi chứng chỉ bảo mật khi kết nối (thường do proxy/tường lửa công ty kiểm tra HTTPS). "
                "Thử mạng khác hoặc hỏi IT cho phép api.telegram.org / generativelanguage.googleapis.com")
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "mạng chậm, máy chủ không trả lời kịp. Kiểm tra mạng / VPN rồi thử lại"
        if isinstance(reason, socket.gaierror):
            return "không có mạng hoặc không phân giải được tên máy chủ (mất mạng, DNS, VPN)"
        if isinstance(reason, ssl.SSLError):
            return _explain(reason)
        return "không kết nối được máy chủ (mất mạng, proxy hoặc tường lửa công ty chặn)"
    if isinstance(exc, (ConnectionError, socket.gaierror)):
        return "kết nối mạng bị ngắt giữa chừng. Thử lại sau"
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return "dữ liệu đang bận (một chương trình khác đang mở file focus.db). Thử lại sau ít giây"
        if "full" in msg:
            return "ổ đĩa đầy, không ghi được dữ liệu. Xoá bớt file rồi thử lại"
        if "no such table" in msg or "malformed" in msg or "corrupt" in msg:
            return "file dữ liệu focus.db bị hỏng. Chép bản sao trong data/backup (giải nén file .zip) đè lên rồi chạy lại"
        return "lỗi đọc/ghi dữ liệu SQLite, chi tiết trong data/logs/focus.log"
    if isinstance(exc, sqlite3.DatabaseError):
        return "file dữ liệu focus.db bị hỏng. Chép bản sao trong data/backup (giải nén file .zip) đè lên rồi chạy lại"
    if isinstance(exc, PermissionError):
        where = getattr(exc, "filename", "") or ""
        return (f"không có quyền ghi file {where}".strip() +
                " (file đang mở ở chương trình khác, hoặc antivirus / OneDrive đang khoá)")
    if isinstance(exc, FileNotFoundError):
        return f"không tìm thấy file {getattr(exc, 'filename', '') or ''}".strip()
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "ổ đĩa đầy, không ghi được. Xoá bớt file rồi thử lại"
    if isinstance(exc, MemoryError):
        return "máy hết bộ nhớ RAM"
    if isinstance(exc, (ValueError, KeyError, TypeError)) and "json" in str(exc).lower():
        return "máy chủ trả về dữ liệu lạ, không đọc được. Thử lại sau"
    return f"lỗi không mong đợi ({name}), chi tiết trong data/logs/focus.log"


def job_name(label):
    if label not in JOB_NAMES and label.startswith("pace_") and len(label) == 9:  # mốc tự đặt: pace_0945
        return f"{JOB_NAMES['pace']} {label[5:7]}:{label[7:]}"
    return JOB_NAMES.get(label, label)
