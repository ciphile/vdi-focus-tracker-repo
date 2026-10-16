"""Focus Tracker: theo dõi thời gian tập trung thực sự trong VDI.

Mỗi module một việc, sửa tính năng nào mở đúng file đó:

| Module          | Việc                                                              |
|-----------------|-------------------------------------------------------------------|
| config          | Đọc + kiểm tra settings.json, secrets.env                         |
| logs            | Log kỹ thuật (data/logs/focus.log) và nhật ký sự kiện (audit.log) |
| storage         | SQLite: bảng, ghi mẫu theo lô, ghi chú ngày, sent_log             |
| probe           | Đọc trạng thái máy: idle, khoá máy, cửa sổ VDI (Win32)            |
| analysis        | Mẫu thô -> số liệu ngày, khối tập trung, điểm, streak, tuần       |
| report          | Số liệu báo cáo ngày/tuần, OT 14 ngày, tóm tắt chữ cho Telegram   |
| report_html     | Vẽ trang HTML báo cáo ngày/tuần (bảng màu Pop Art, robot, OT)     |
| schedule        | Giờ làm, nghỉ trưa, khung chạy, việc theo giờ (hỏi kế hoạch...)   |
| alerts          | Cảnh báo tức thời: ngoài VDI, rời máy, nhắc nghỉ                  |
| messages        | Câu chữ của các cảnh báo                                          |
| notifier        | Hàng đợi gửi Telegram/AI chạy nền (vòng lấy mẫu không bao giờ chờ mạng) |
| tracker         | Vòng lấy mẫu chính, đo hiệu năng, khoá 1 tiến trình               |
| telegram_bot    | Bot Telegram: nhận tin, xác nhận OK/Sửa/Huỷ, hỏi đáp, ảnh AS400   |
| actions         | Danh sách thao tác: action name + lệnh + từ khoá (thêm tính năng ở đây) |
| intent          | Tin nhắn tự nhiên -> action (AI, dự phòng bằng từ khoá)           |
| persona         | Cách xưng hô, giọng văn (config/persona.json)                     |
| prefs           | Tuỳ chọn đổi qua Telegram: /aireview, /style, /encourage          |
| ai_context      | Ngữ cảnh đầy đủ gửi kèm mọi lần gọi AI (công việc, luật, giọng)   |
| ai_client       | Gọi Gemini / Claude, chọn model, cache, quota                     |
| energy          | Tự tính năng lượng 1–5 lúc tổng kết khi bạn chưa chấm                          |
| motivation      | Lời chào sáng, khích lệ, Kinh Thánh, bài tập, AI đánh giá ngày/tuần, ảnh AS400 |
| holidays        | Lịch lễ Singapore                                                 |
| net             | HTTPS dùng chung (SSL context, chứng chỉ gốc dự phòng cho Mac)    |
| housekeeping    | Dọn dẹp, backup DB                                                |
| demo            | Dữ liệu giả để xem báo cáo mẫu                                    |
| cli             | Các lệnh `python focus_tracker.py ...`                            |

Không cần cài thêm gói nào: chỉ dùng thư viện chuẩn của Python 3.9+.
"""

__version__ = "2.5.1"
