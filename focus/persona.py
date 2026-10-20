"""Cách bot xưng hô và giọng nói. Cấu hình trong config/persona.json (file riêng, sửa xong chạy lại tracker).

{
  "ten": "Minh",                  tên của bạn
  "tuoi": "35",                   tuổi (để AI khuyên hợp hoàn cảnh)
  "noi_song": "TP.HCM, Việt Nam", nơi sống (giá vàng, tỷ giá, thời tiết... đúng nơi)
  "goi_nguoi_dung": "bro",        bot gọi bạn là gì: "bạn", "bro", "anh", "chị", tên riêng...
  "bot_xung": "tui",              bot tự xưng: "mình", "em", "tui", "tôi"...
  "ten_sep": "anh Tuấn",          để trống nếu không muốn bot nhắc tới sếp
  "giong": "hai_huoc",            than_mat | vui_tuoi | hai_huoc | sep_kho_tinh
  "mo_ta": "..."                  vài dòng về bạn để AI nói chuyện hợp hơn (nghề, gia đình, niềm tin...)
}

- Mọi câu bot tự viết đều dùng cách xưng hô này (chữ "bạn"/"mình" trong code được thay tự động).
- Câu AI viết: AI được dặn đúng giọng và cách xưng hô.
- Câu trích dẫn (danh ngôn, Kinh Thánh) giữ nguyên, không bị đổi chữ.
"""
import json
import os
import random
import re

from .config import CONFIG_DIR
from .logs import get_logger
from .nudge_lines import NUDGE

log = get_logger()
PATH = os.path.join(CONFIG_DIR, "persona.json")
TONES = ("than_mat", "vui_tuoi", "hai_huoc", "sep_kho_tinh")
DEFAULT = {"ten": "", "tuoi": "", "noi_song": "", "goi_nguoi_dung": "bạn", "bot_xung": "mình", "ten_sep": "", "giong": "than_mat", "mo_ta": ""}
SHOULD_FILL = ("ten", "tuoi", "noi_song", "mo_ta")  # để trống app vẫn chạy, nhưng AI khuyên chung chung hơn
# Lỗi JSON (tiếng Anh, từ thư viện json) -> câu dễ hiểu. Khớp theo đầu câu; không khớp thì giữ nguyên câu gốc.
JSON_HINTS = (
    ("Expecting ',' delimiter", "thiếu dấu phẩy cuối dòng trước"),
    ("Illegal trailing comma", "dư dấu phẩy ở dòng cuối, trước dấu }"),
    ("Expecting property name", "tên khoá phải nằm trong ngoặc kép, hoặc dư dấu phẩy ở dòng cuối trước dấu }"),
    ("Expecting ':' delimiter", "thiếu dấu hai chấm sau tên khoá"),
    ("Expecting value", "thiếu giá trị (file trống, hoặc chữ không có ngoặc kép)"),
    ("Unterminated string", "thiếu dấu ngoặc kép đóng"),
    ("Invalid control character", "giá trị bị xuống dòng giữa chừng, viết liền trên một dòng"),
    ("Extra data", "có chữ thừa sau dấu } cuối cùng"),
)

TONE_PROMPT = {
    "than_mat": "Giọng thân mật, ấm áp như một người bạn thân.",
    "vui_tuoi": "Giọng vui tươi, nhiều năng lượng, tích cực, có thể dùng 1 emoji.",
    "hai_huoc": "Giọng hài hước, dí dỏm, chọc nhẹ cho vui nhưng không xúc phạm, vẫn có ý khuyên rõ ràng.",
    "sep_kho_tinh": ("Giọng một ông sếp 60 tuổi khó tính, lạnh lùng, nói ngắn, cộc, nghiêm khắc, không emoji, "
                     "không khen suông; nhưng không xúc phạm, không chửi thề."),
}

# Câu mở đầu của cảnh báo theo giọng. {u} = cách gọi người dùng, {me} = bot tự xưng, {boss} = tên sếp.
LEADS = {
    "out_of_vdi": {
        "than_mat": ["Ê {u}, quay lại VDI thôi nào."],
        "vui_tuoi": ["Ối {u} ơi, VDI đang nhớ {u} kìa! 🏃"],
        "hai_huoc": ["{U} ơi, app kia không trả lương cho {u} đâu nha 😄", "Báo động: {u} đã đi lạc khỏi VDI 🧭"],
        "sep_kho_tinh": ["Làm việc hay lướt web đấy?", "Tôi không trả lương cho việc ngồi ngoài VDI."],
    },
    # Mức nhắc sao nhãng (/nudge): <loại>_nhe (nhẹ, 1 lần/ngày), <loại> (vừa), <loại>_nghiem (nghiêm, nhắc lặp).
    # minimized = VDI đang thu nhỏ; out_of_vdi = app khác đang ở trước VDI.
    "minimized": {
        "than_mat": ["{U} ơi, VDI đang bị thu nhỏ kìa, mở lại làm tiếp nha."],
        "vui_tuoi": ["VDI bị thu nhỏ xíu xiu rồi {u} ơi, phóng to lên quẩy tiếp nào! 🚀"],
        "hai_huoc": ["VDI bị {u} cất vào túi quần rồi à? Lôi ra đi 😄", "VDI đang thu nhỏ, chắc nó đi ngủ trưa sớm 😴"],
        "sep_kho_tinh": ["VDI thu nhỏ. Mở lên.", "Thu nhỏ VDI là nghỉ làm à?"],
    },
    "out_of_vdi_nhe": {
        "than_mat": ["{U} ơi, nhắc nhẹ một câu thôi: mình quay lại VDI nhé."],
        "vui_tuoi": ["Nhắc xinh một lần thôi nè {u}: về VDI nha! 🌱"],
        "hai_huoc": ["Tin nhắn nhẹ như lông hồng: VDI vẫn đang chờ {u} đó 🪶"],
        "sep_kho_tinh": ["Nhắc một lần. Về VDI."],
    },
    "minimized_nhe": {
        "than_mat": ["{U} ơi, VDI đang thu nhỏ đó, mở lại khi sẵn sàng nhé."],
        "vui_tuoi": ["VDI đang thu nhỏ nè {u}, mở to ra là vào guồng liền! 🌱"],
        "hai_huoc": ["VDI đang trốn dưới thanh taskbar / Dock, {u} kéo nó ra nhẹ nhàng thôi 🪶"],
        "sep_kho_tinh": ["VDI đang thu nhỏ. Nhắc một lần."],
    },
    "out_of_vdi_nghiem": {
        "than_mat": ["{U}, nói thẳng nhé: ngoài VDI vậy là lâu rồi. Quay lại ngay."],
        "vui_tuoi": ["Dừng lại {u}! Không lướt nữa, về VDI ngay bây giờ nha!"],
        "hai_huoc": ["Hết giờ ra chơi rồi {u}. app kia không chấm KPI đâu, về VDI ngay!"],
        "sep_kho_tinh": ["Lại ra ngoài VDI. Tôi nói lần nữa: quay lại làm việc.",
                         "Không chấp nhận. Đóng app kia, về VDI ngay."],
    },
    "minimized_nghiem": {
        "than_mat": ["{U}, VDI vẫn đang thu nhỏ. Mở lại và làm ngay nhé, đừng để trôi nữa."],
        "vui_tuoi": ["VDI vẫn thu nhỏ đó {u}! Phóng to lên và làm liền, không chần chừ!"],
        "hai_huoc": ["VDI thu nhỏ lâu thế này chắc nó tưởng bị sa thải rồi. Mở ra ngay {u}!"],
        "sep_kho_tinh": ["VDI vẫn thu nhỏ. Mở lên, làm việc. Ngay.", "Thu nhỏ VDI không làm việc thay được."],
    },
    # Cảnh báo tiến độ (/pace).
    "pace_behind": {
        "than_mat": ["{U} ơi, xem nhanh tiến độ hôm nay nè.", "{U} ơi, hôm nay hơi chậm chút, mình bắt nhịp lại nhé.",
                     "Còn kịp mà {u}, vào VDI làm thêm một mạch nha.", "Nhìn số giờ một chút nè {u}, mình cố thêm tí nhé.",
                     "{U} ơi, mình đang hơi tụt so với mục tiêu, làm tiếp nhé.",
                     "Từ giờ tới chiều vẫn đủ thời gian đó {u}, bắt đầu luôn nha.", "{U} ơi, mình làm thêm một mạch trong VDI cho kịp nha.", "Chưa muộn đâu {u}, tập trung lại một chút là kịp."],
        "vui_tuoi": ["Tăng tốc chút nào {u}! Vẫn kịp về đúng giờ nếu bắt đầu ngay 💪",
                     "Lên dây cót nào {u}! Một mạch nữa là đẹp ngay 🚀",
                     "Đạp ga nhẹ thôi {u}, mục tiêu còn trong tầm tay nè 🏁",
                     "Cố lên {u} ơi! Mỗi phút trong VDI đều được tính nha ✨",
                     "Bật chế độ chiến binh nào {u}! ⚔️", "Vào guồng lại thôi {u}, mình tin {u} mà 🌟", "Còn nước còn tát {u} ơi, chiến tiếp nào! 🌊", "Một chút nỗ lực nữa thôi {u}, về đích đẹp luôn! 🏆"],
        "hai_huoc": ["Đồng hồ chạy nhanh hơn {u} rồi đó, rượt theo thôi 🏃",
                     "Tiến độ hôm nay đang đi xe đạp, mục tiêu thì đi máy bay ✈️",
                     "Số giờ tập trung đang ăn kiêng hơi quá tay rồi {u} 🥗",
                     "Mục tiêu hôm nay vừa hỏi {me}: ‘ủa {u} đâu rồi?’ 🤔",
                     "Biểu đồ hôm nay phẳng như mặt hồ, khuấy lên chút đi {u} 🌊",
                     "Rùa vẫn thắng thỏ, nhưng rùa không lướt điện thoại nha {u} 🐢", "Kim đồng hồ chạy marathon, {u} đang đi dạo công viên 🏃", "Mục tiêu hôm nay đang ngồi chờ {u} mòn ghế 🪑"],
        "sep_kho_tinh": ["Tiến độ chậm.", "Số giờ làm hôm nay chưa đạt.", "Chưa đủ giờ. Làm tiếp.",
                         "Tôi thấy số liệu rồi. Chưa ổn.", "Hôm nay đang dưới mục tiêu.", "Cần thêm giờ trong VDI.", "Đang chậm so với kế hoạch.", "Cần tăng tốc. Ngay."],
    },
    "pace_behind_nghiem": {
        "than_mat": ["{U}, nói thẳng: hôm nay đang chậm nhiều, phải dồn sức ngay.",
                     "{U} ơi, chậm nhiều rồi, mình tập trung hết sức từ giờ nhé.",
                     "Nói thật lòng nha {u}: phải làm liền mới kịp.", "{U}, gác việc phụ lại, vào VDI làm ngay nhé.",
                     "Hôm nay thiếu nhiều đó {u}, mình dốc sức ngay bây giờ nha.",
                     "{U} ơi, không chần chừ thêm nữa nhé, bắt đầu luôn.", "{U}, chậm khá nhiều rồi, mình dốc sức từ bây giờ tới cuối giờ nhé.", "Nói thật nha {u}: còn ngồi ngoài là không kịp, vào VDI liền nhé."],
        "vui_tuoi": ["Báo động đỏ {u}! Chậm tiến độ rồi, vào VDI chiến ngay!", "Còi báo động réo rồi {u}! Lao vào VDI nào! 🚨",
                     "Không còn thời gian dạo chơi đâu {u}, chiến ngay! 🔥", "Tăng tốc tối đa nào {u}, ngay và luôn! 🏎️",
                     "Giờ vàng còn ít lắm {u} ơi, vào VDI liền! ⏰", "Tất tay luôn {u}! Vào VDI làm cho xong nào! 💥", "Hết giờ khởi động rồi {u}, vào trận thật thôi! ⚽", "Báo động cam {u} ơi! Gom hết sức vào VDI nào! 🔥"],
        "hai_huoc": ["Tiến độ đang đi bộ, deadline đang chạy xe máy. {U} vào VDI ngay!",
                     "Năng suất hôm nay của {u} vừa nhập viện, tình trạng nguy kịch 🏥",
                     "{Me} đã chuẩn bị sẵn điếu văn cho mục tiêu hôm nay rồi, cứu nó đi {u} 🕯️",
                     "Deadline đang mài dao trong góc phòng đó {u} 🔪",
                     "Báo cáo cuối ngày của {u} đang viết thư xin nghỉ việc 💌",
                     "Biểu đồ hôm nay đang hấp hối, hô hấp nhân tạo bằng VDI ngay {u} 🚑", "Deadline vừa gửi lời hỏi thăm sức khoẻ {u} đó, hơi rùng mình 👻", "Tốc độ hôm nay mà đi thi chắc về sau con ốc sên 🐌"],
        "sep_kho_tinh": ["Chậm quá. Không có lý do. Làm ngay.", "Thế này thì tối nay ngồi lại. Muốn vậy không?",
                         "Tôi không chấp nhận số liệu này.", "Còn thiếu nhiều. Không nghỉ nữa.",
                         "Cuối ngày tôi hỏi. Chuẩn bị câu trả lời.", "Làm cho đủ. Không thương lượng.", "Tụt quá xa. Làm việc.", "Hết thời gian lãng phí. VDI. Ngay."],
    },
    "pace_praise": {
        "than_mat": ["Giỏi lắm {u}, đang đúng nhịp.", "Ổn áp lắm {u}, cứ giữ vậy nha.", "{U} làm tốt lắm, tiếp tục nhé.",
                     "Đúng tiến độ rồi {u}, tự hào ghê.", "Nhịp hôm nay đẹp lắm {u}.", "Cứ đều tay vậy là tuyệt {u} ơi."],
        "vui_tuoi": ["Tuyệt vời {u} ơi, đang đúng nhịp nè! 🎉", "Quá đỉnh luôn {u}! 🌟", "Đúng tiến độ rồi, vỗ tay cho {u} nào! 👏",
                     "{U} đang bay cao lắm nè! 🚀", "Hôm nay {u} chất lừ luôn! 😎", "Giữ phong độ này nha {u}! 💪"],
        "hai_huoc": ["Ơ kìa, {u} đang chạy đúng lịch như tàu Nhật 🚄", "Deadline hôm nay đang run sợ trước {u} 😱",
                     "{U} làm nhanh tới mức đồng hồ phải xin chạy chậm lại ⏱️", "Robot quà của {u} đang nhảy múa ăn mừng 🤖",
                     "{Me} chưa kịp nhắc mà {u} đã làm xong, thất nghiệp tới nơi 😅", "KPI hôm nay xin chữ ký {u} đó ✍️"],
        "sep_kho_tinh": ["Được. Giữ vậy.", "Đúng tiến độ. Tiếp tục.", "Tạm ổn. Đừng chủ quan.", "Vậy là được. Làm tiếp.",
                         "Đạt. Giữ nhịp này.", "Không có gì để nói. Tiếp tục."],
    },
    # Quay lại sau khi rời máy ({m} = số phút đã rời máy).
    "back": {
        "than_mat": ["Chào mừng quay lại. {U} rời máy {m} phút. Vào VDI làm tiếp nhé.",
                     "{U} về rồi đó hả, đi {m} phút rồi. Mở VDI làm tiếp nha.",
                     "Mừng {u} quay lại sau {m} phút. Mình làm tiếp thôi.",
                     "{U} vắng {m} phút rồi đó. Ngồi xuống, mở VDI làm tiếp nhé.",
                     "Có {u} rồi. {m} phút vừa qua coi như nghỉ, giờ vào việc lại nha.",
                     "{U} ơi, rời máy {m} phút rồi. Uống ngụm nước rồi vào VDI nhé.",
                     "Quay lại rồi thì tốt. {m} phút đó đủ nghỉ rồi, làm tiếp nha {u}."],
        "vui_tuoi": ["Yay, {u} về rồi! Vắng {m} phút đó, vào VDI quẩy tiếp nào! 🎉",
                     "{U} trở lại rồi kìa! {m} phút xa cách, VDI nhớ {u} lắm đó 💙",
                     "Chào mừng {u} quay về sau {m} phút! Lên dây cót làm tiếp nha 🚀",
                     "A, {u} đây rồi! Nghỉ {m} phút xong, giờ chiến tiếp thôi 💪",
                     "{U} về rồi, bàn làm việc sáng bừng luôn! Đi {m} phút rồi, vào VDI nhé ✨",
                     "Welcome back {u}! {m} phút nạp pin xong, bắt đầu hiệp mới nào 🔋",
                     "{U} quay lại rồi! Vắng {m} phút, giờ vào guồng lại liền nha 🌟"],
        "hai_huoc": ["Ơ, {u} đã trở về sau {m} phút phiêu lưu 🧭 Vào VDI kể chuyện tiếp đi.",
                     "Đội tìm kiếm cứu nạn xin rút quân: {u} đã về sau {m} phút 🚁",
                     "{U} biến mất {m} phút, {me} suýt dán thông báo tìm người 📢",
                     "Chuyến du hành {m} phút của {u} kết thúc. Mời về lại VDI 🛬",
                     "Ghế đã giữ chỗ cho {u} suốt {m} phút, giờ thì ngồi xuống làm tiếp 🪑",
                     "{m} phút vắng mặt, {u} đi đâu mà lâu thế, đi chợ à? 🛒 Vào VDI thôi.",
                     "{U} về rồi! {me} hủy lệnh truy nã sau {m} phút 🕵️ Làm tiếp nha."],
        "sep_kho_tinh": ["Rời máy {m} phút. Vào VDI làm tiếp.", "Đã quay lại. {m} phút. Làm việc.",
                         "Vắng {m} phút. Đủ rồi. VDI.", "Quay lại sau {m} phút. Tiếp tục công việc.",
                         "{m} phút không làm việc. Bù lại đi.", "Về chỗ rồi thì làm ngay. Đã mất {m} phút.",
                         "Rời bàn {m} phút. Không lặp lại."],
    },
    # Câu chốt của cảnh báo tiến độ mức nghiêm (/nudge nghiem), cùng một ý: đóng app khác, VDI toàn màn hình, làm ngay.
    "pace_hard": {
        "than_mat": ["Nói thẳng: đóng hết app khác, mở VDI toàn màn hình và làm ngay bây giờ.",
                     "Mình nói thật nha: tắt bớt app khác, phóng to VDI và làm liền nhé.",
                     "Giờ là lúc gác hết mọi thứ khác, VDI toàn màn hình, làm một mạch nhé.",
                     "Đóng bớt các app khác một lúc, mở to VDI và tập trung nhé.",
                     "Thật lòng khuyên {u}: chỉ để VDI trên màn hình, còn lại tắt hết, làm ngay.",
                     "Tắt hết thông báo, VDI toàn màn hình, bắt đầu luôn nha {u}.",
                     "Dọn màn hình cho gọn: chỉ còn VDI, rồi làm ngay nhé."],
        "vui_tuoi": ["Dọn sạch màn hình, chỉ chừa VDI, chiến liền nào! 🧹",
                     "Tắt hết app phụ, VDI full màn hình, lên đồ đi {u}! ⚔️",
                     "Chế độ tập trung bật! Chỉ VDI thôi, làm ngay nha 🔦",
                     "Bye bye app khác, hello VDI toàn màn hình! Làm liền nha 👋",
                     "Đóng tab, phóng to VDI, bắt đầu luôn {u} ơi! 🚀",
                     "Một màn hình, một VDI, một {u} siêu tập trung! Go! 🎯",
                     "Gom hết sức vào VDI toàn màn hình nha {u}! 💥"],
        "hai_huoc": ["Đóng hết app khác như đóng cửa nhà khi có chủ nợ tới, chỉ mở VDI thôi 🚪",
                     "Màn hình bây giờ chỉ được có một ngôi sao: VDI toàn màn hình 🌟",
                     "Các app khác vui lòng ra ngoài chờ, VDI đang có ca trực 🩺",
                     "Tắt hết app phụ đi {u}, cho VDI làm diễn viên chính 🎬",
                     "Phóng to VDI như phóng to ảnh crush, rồi làm ngay 🔍",
                     "Các app khác tạm thời bị cấm túc. VDI toàn màn hình, làm luôn 🔒",
                     "Đóng hết, để VDI một mình một cõi, làm như chưa từng được làm 🏔️"],
        "sep_kho_tinh": ["Không bàn thêm. Đóng mọi app khác, VDI toàn màn hình, làm ngay.",
                         "Tắt hết app khác. VDI toàn màn hình. Bắt đầu.", "Chỉ VDI. Không gì khác. Làm.",
                         "Đóng app phụ. Phóng to VDI. Ngay bây giờ.", "Dừng mọi thứ khác. Làm việc chính.",
                         "Màn hình chỉ có VDI. Không ngoại lệ.", "Tập trung. VDI toàn màn hình. Hết."],
    },
    # Nhắc sức khoẻ (/break, /water): không phụ thuộc mức nhắc sao nhãng.
    "break": {
        "than_mat": ["{U} ơi, ngồi lâu rồi, mình nghỉ chân chút nha.", "Đứng dậy duỗi người chút đi {u}.",
                     "{U} ơi, vươn vai một cái cho đỡ mỏi nhé.", "Đi vài bước cho máu lưu thông nha {u}.",
                     "Nghỉ mắt chút đi {u}, nhìn xa một lát nhé.", "{U} ơi, xoay cổ xoay vai chút rồi làm tiếp nha."],
        "vui_tuoi": ["Giờ vận động tới rồi {u} ơi! 🤸", "Đứng lên lắc lư chút nào {u}! 🎶", "Vươn vai thật đã nào {u}! 🙆",
                     "Đi dạo một vòng cho khỏe nè {u}! 🚶", "Nạp năng lượng bằng vài động tác nhé {u}! ⚡",
                     "Duỗi người cho sảng khoái nào {u}! 🌈"],
        "hai_huoc": ["Cái ghế than là {u} ngồi lâu quá rồi đó 😄", "Lưng {u} vừa gửi đơn khiếu nại 🪑",
                     "Cột sống của {u} đang nhắn tin cầu cứu 🆘", "Ngồi nữa là {u} mọc rễ luôn đó 🌳",
                     "Chân {u} đang hỏi có phải bị bỏ quên không 🦵", "Ghế đã in hình {u} rồi, đứng dậy cho nó thở 😮‍💨"],
        "sep_kho_tinh": ["Ngồi lâu rồi. Đứng dậy.", "Nghỉ 5 phút. Rồi làm tiếp.", "Đứng lên. Vận động.",
                         "Nghỉ ngắn. Không quá 5 phút.", "Đi lại vài bước. Rồi quay lại.", "Giãn cơ. Sau đó làm việc."],
    },
    "water": {
        "than_mat": ["{U} ơi, uống ngụm nước đi nè.", "Nhắc nhỏ: {u} uống nước chưa?", "Uống miếng nước rồi làm tiếp nha {u}.",
                     "{U} ơi, ly nước trên bàn còn đầy kìa.", "Nghỉ tay một chút, uống vài ngụm nước nha {u}.",
                     "{U} ngồi lâu rồi đó, đứng dậy rót ly nước nhé.", "Cổ họng khô chưa {u}? Uống nước đi nè.",
                     "{Me} nhắc nhẹ thôi: tới giờ uống nước rồi {u}.", "Uống nước đều đều cho khoẻ nha {u}.",
                     "{U} ơi, nạp chút nước rồi làm tiếp cho tỉnh.", "Một ly nước bây giờ là vừa đẹp đó {u}.",
                     "{U} nhớ chăm cho mình chút: uống nước nha."],
        "vui_tuoi": ["Đến giờ nạp nước rồi {u} ơi! 💧", "Một ly nước mát cho {u} tỉnh táo nè! 🥤", "Cạn ly nước nào {u}! 💦",
                     "Ting ting! Giờ uống nước của {u} tới rồi 🔔", "Nước mát đang vẫy tay gọi {u} nè! 👋",
                     "Uống nước xinh da, làm việc vui hơn nha {u}! ✨", "Đứng dậy rót nước, tiện vươn vai luôn {u}! 🙆",
                     "Nạp nước full pin nào {u}! 🔋", "Một ngụm, hai ngụm, ba ngụm, {u} giỏi quá! 🎉",
                     "Cơ thể {u} đang xin chút nước nè! 🌊", "Uống nước rồi quẩy tiếp nha {u}! 🚀",
                     "Giờ giải khát chính thức bắt đầu, mời {u}! 🍹"],
        "hai_huoc": ["Cây xương rồng còn được tưới, {u} cũng cần nước đó 🌵", "Não {u} 75% là nước, đổ thêm vào đi 🧠💧",
                     "Ly nước trên bàn đang buồn vì bị bỏ rơi 🥲", "Thận của {u} vừa gửi thư tay xin nước 💌",
                     "{U} ơi, cá vàng trong bể còn uống nhiều nước hơn {u} 🐠",
                     "Ngồi nhiều uống ít là mời sỏi thận về ở chung đó {u} 🪨",
                     "Bình nước của {u} đầy tới mức sắp được công nhận di tích 🏛️",
                     "{Me} không muốn thấy {u} khô như con mực nướng đâu 🦑",
                     "Uống nước đi {u}, không thì {me} gọi cây xương rồng ra dạy 🌵",
                     "Bàng quang của {u} đang rảnh quá, cho nó chút việc đi 😄",
                     "Nước lọc miễn phí mà {u} tiết kiệm dữ vậy 💸", "Cơ thể {u} báo động: mực nước xuống thấp 🚨"],
        "sep_kho_tinh": ["Uống nước.", "Uống nước rồi làm tiếp.", "Một ly nước. Không bàn.", "Đến giờ uống nước.",
                         "Uống nước. Ngay bây giờ.", "Đứng dậy. Rót nước. Quay lại làm.", "Thiếu nước làm chậm việc. Uống đi.",
                         "Uống đủ nước. Đây là yêu cầu.", "Ly nước còn đầy. Uống.", "Không đợi khát. Uống.",
                         "Nghỉ 1 phút. Uống nước.", "Giữ sức khoẻ để làm việc. Uống nước."],
    },
    "away": {
        "than_mat": ["{U} đi đâu lâu thế?", "{U} ơi, về bàn chưa nè?", "{Me} chờ {u} quay lại làm tiếp nha.",
                     "{U} ơi, xong việc thì về chỗ nhé.", "Bàn làm việc đang chờ {u} đó.", "{U} về rồi thì làm tiếp nhé."],
        "vui_tuoi": ["{U} ơi, ghế đang trống nè! 🪑", "Ủa {u} đi đâu mất tiêu rồi? 👀", "Về nhanh nhanh nào {u}! 🏃",
                     "Bàn phím nhớ {u} quá trời! ⌨️", "Mau quay lại nha {u}, việc đang chờ nè! 🌟",
                     "{U} ơi, trạm làm việc gọi {u} về! 📡"],
        "hai_huoc": ["Toilet hôm nay có wifi hả {u}? 😄", "{U} bị ai bắt cóc rồi à? 🛸",
                     "{Me} không ngờ {u} bị táo bón nặng vậy 🚽", "{U} ơi, nếu bị bắt cóc thì nháy mắt hai cái nha 🆘",
                     "Ghế của {u} đang rao cho thuê đó 🪧", "Chuột máy tính đã báo mất tích {u} 🐭"],
        "sep_kho_tinh": ["Bàn trống. Người đâu?", "Đi đâu mà lâu vậy?", "Rời bàn quá lâu.", "Quay lại chỗ ngồi.",
                         "Tôi không thấy ai ở bàn.", "Về bàn. Làm việc."],
    },
    "boss": {  # thêm vào tin nhắc từ lần thứ 2: nhiều câu để nhắc lặp (mức nghiêm) không nghe một câu hoài
        "than_mat": ["Lỡ {boss} đi ngang thì hơi ngại đó.", "{boss} mà hỏi tiến độ thì mình trả lời sao đây {u}?",
                     "Làm cho xong rồi khoe với {boss} nha.", "{boss} đang chờ kết quả của {u} đó.",
                     "Để {boss} thấy {u} đang làm hết mình nha.", "Nghĩ tới buổi báo cáo với {boss} đi {u}."],
        "vui_tuoi": ["{boss} mà ghé ngang là toang á!", "{boss} sắp xem tiến độ đó, tăng tốc nào!",
                     "Cho {boss} bất ngờ với kết quả hôm nay nha!", "Làm xong khoe {boss} liền nha!",
                     "{boss} mà thấy {u} chiến thế này chắc vui lắm!", "Làm đẹp số liệu cho {boss} gật gù nào!"],
        "hai_huoc": ["{boss} đang đi tuần đó, cẩn thận 👀", "Nghe tiếng giày của {boss} chưa {u}? 👞",
                     "{boss} có radar dò người ngoài VDI đó 📡", "Đừng để {boss} chụp được khoảnh khắc này nha 📸",
                     "{boss} vừa hỏi «{u} đâu rồi?», {me} đỡ không nổi nữa 😅",
                     "{boss} mà biết chắc cho {u} đi họp thêm 2 tiếng 😄"],
        "sep_kho_tinh": ["{boss} mà thấy thì tôi không bênh đâu.", "{boss} hỏi thì tự trả lời.",
                         "Số liệu này {boss} sẽ xem.", "{boss} không chờ ai đâu.", "Đừng để {boss} phải hỏi.",
                         "{boss} cần kết quả, không cần lý do."],
    },
}


def _clean(data):
    """Giá trị đọc từ file -> persona đầy đủ khoá, giọng sai / trống về mặc định."""
    p = dict(DEFAULT)
    if isinstance(data, dict):
        p.update({k: str(v).strip() for k, v in data.items() if k in DEFAULT and v is not None})
    if p["giong"] not in TONES:
        p["giong"] = "than_mat"
    p["goi_nguoi_dung"] = p["goi_nguoi_dung"] or "bạn"
    p["bot_xung"] = p["bot_xung"] or "mình"
    return p


def load(path=PATH):
    data = None
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:  # sai cú pháp / không phải UTF-8: dùng mặc định, ghi log (lệnh check báo rõ)
        log.warning("Không đọc được %s, dùng xưng hô mặc định: %s", path, e)
    return _clean(data)


def inspect(path):
    """Kiểm tra persona.json cho lệnh check / kiem_tra_may. Trả dict: state "missing" | "error" | "ok", error (câu lỗi
    tiếng Việt), persona (giá trị app đang dùng), unknown (khoá lạ, gõ sai tên: app bỏ qua), empty (khoá nên điền còn
    trống), bad_tone (giọng gõ sai, app dùng than_mat)."""
    info = {"state": "ok", "error": "", "persona": dict(DEFAULT), "unknown": [], "empty": [], "bad_tone": ""}
    if not os.path.exists(path):
        info["state"] = "missing"
        return info
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except UnicodeDecodeError:  # trước ValueError (là lớp con của nó)
        info.update(state="error", error="không lưu dạng UTF-8 (Notepad: File > Save As > Encoding: UTF-8)")
        return info
    except ValueError as e:
        where = f" ở dòng {e.lineno}, cột {e.colno}" if getattr(e, "lineno", None) else ""
        msg = str(getattr(e, "msg", e))
        hint = next((vi for en, vi in JSON_HINTS if msg.startswith(en)), msg)
        info.update(state="error", error=f"sai cú pháp JSON{where} ({hint})")
        return info
    except OSError as e:
        info.update(state="error", error=f"không đọc được ({type(e).__name__}: {e})")
        return info
    if not isinstance(data, dict):
        info.update(state="error", error="phải là một khối { ... } như file mẫu persona.example.json")
        return info
    info["persona"] = _clean(data)
    info["unknown"] = [k for k in data if k not in DEFAULT and not str(k).startswith("_")]
    info["empty"] = [k for k in SHOULD_FILL if not info["persona"][k]]
    tone = str(data.get("giong") or "").strip()
    if tone and tone not in TONES:
        info["bad_tone"] = tone
    return info


def check_lines(path):
    """Các dòng in trong lệnh check về persona.json. Trả (ok, [dòng])."""
    info = inspect(path)
    rel = "config/persona.json"
    if info["state"] == "missing":
        return False, [f"✗ Chưa có {rel}: bot sẽ gọi bạn chung chung là «bạn» và AI không biết bạn là ai. Chép "
                       "config/persona.example.json thành persona.json rồi điền (README mục 2.4, bước 6)."]
    if info["state"] == "error":
        return False, [f"✗ {rel} {info['error']}: app đang bỏ qua cả file, dùng mặc định. So với file mẫu "
                       "persona.example.json, sửa xong chạy lại kiem_tra_may (phần check)."]
    p = info["persona"]
    bits = [f"bot gọi bạn «{p['goi_nguoi_dung']}», tự xưng «{p['bot_xung']}», giọng {p['giong']}"]
    if p["ten"]:
        bits.append(f"tên {p['ten']}")
    if p["ten_sep"]:
        bits.append(f"sếp {p['ten_sep']}")
    lines = [f"✓ {rel}: " + ", ".join(bits)]
    if info["bad_tone"]:
        lines.append(f"  ! giong «{info['bad_tone']}» không có, đang dùng than_mat. Chọn một trong: {', '.join(TONES)}")
    if info["unknown"]:
        lines.append(f"  ! Khoá lạ (gõ sai tên?), app bỏ qua: {', '.join(info['unknown'])}")
    if info["empty"]:
        lines.append(f"  ! Chưa điền: {', '.join(info['empty'])} (không bắt buộc, nhưng AI sẽ khuyên chung chung hơn)")
    return True, lines


def _cap(s):
    return s[:1].upper() + s[1:]


_WORD = r"(?<![\wÀ-ỹ]){}(?![\wÀ-ỹ])"


KEEP_OPEN, KEEP_CLOSE = "\ue000", "\ue001"
_KEEP_RE = re.compile("(\ue000.*?\ue001)", re.S)


def keep(text):
    """Bọc chữ của NGƯỜI DÙNG (ghi chú, issue...) để apply() không đổi "bạn"/"mình" bên trong."""
    return f"{KEEP_OPEN}{text}{KEEP_CLOSE}" if text not in (None, "") else text


def strip_keep(text):
    return text.replace(KEEP_OPEN, "").replace(KEEP_CLOSE, "") if text else text


def _apply_part(text, p):
    u, me = p["goi_nguoi_dung"], p["bot_xung"]
    for word, repl in (("bạn", u), ("mình", me)):
        if repl == word:
            continue
        text = re.sub(_WORD.format(word), lambda m: repl, text)  # lambda: "\\" trong tên không bị hiểu là nhóm regex
        text = re.sub(_WORD.format(_cap(word)), lambda m: _cap(repl), text)
    return text


def apply(text, p):
    """Đổi "bạn"/"mình" trong câu bot tự viết sang cách xưng hô đã chọn (giữ chữ hoa đầu câu).
    Phần bọc bằng keep() (chữ người dùng tự gõ) giữ nguyên."""
    if not text:
        return text
    parts = _KEEP_RE.split(text)
    return "".join(part if part.startswith(KEEP_OPEN) else _apply_part(part, p) for part in parts).replace(
        KEEP_OPEN, "").replace(KEEP_CLOSE, "")


_USED = {}  # câu đã dùng theo từng nhóm (trong RAM): luân phiên, hết câu mới lặp lại


def _rotate(key, options):
    """Chọn ngẫu nhiên một câu CHƯA dùng trong nhóm key; dùng hết thì bắt đầu vòng mới (không lặp ngay câu vừa gửi)."""
    used = _USED.setdefault(key, [])
    fresh = [o for o in options if o not in used]
    if not fresh:
        last = used[-1:]
        used[:] = last
        fresh = [o for o in options if o not in last] or list(options)
    pick = random.choice(fresh)
    used.append(pick)
    return pick


def lead_from(key, options, p, **extra):
    """Câu mở đầu luân phiên trong options (đã điền cách xưng hô và các số trong extra, ví dụ {m} phút).
    "" nếu không có câu nào."""
    if not options:
        return ""
    return _rotate(key, options).format(u=p["goi_nguoi_dung"], U=_cap(p["goi_nguoi_dung"]),
                                        me=p["bot_xung"], Me=_cap(p["bot_xung"]), boss=p["ten_sep"], **extra)


def lead(kind, p, **extra):
    """Câu mở đầu theo giọng cho một loại cảnh báo, luân phiên không lặp ("" nếu không có)."""
    if kind == "boss" and not p["ten_sep"]:
        return ""
    return lead_from((kind, p["giong"]), LEADS.get(kind, {}).get(p["giong"]) or [], p, **extra)


def nudge_lead(kind, level, p):
    """Câu mở đầu tin nhắc sao nhãng: kind "minimized" | "out_of_vdi", level "nhe" | "vua" | "nghiem".
    Gộp câu riêng của trường hợp (LEADS) và 20 câu chung của ô mức nhắc × giọng (nudge_lines.NUDGE), luân phiên."""
    level = level if level in NUDGE else "vua"
    key = kind + {"nhe": "_nhe", "nghiem": "_nghiem"}.get(level, "")
    tone = p["giong"]
    options = list(LEADS.get(key, {}).get(tone) or []) + NUDGE[level].get(tone, [])
    return lead_from(("nudge", key, tone), options, p)


def ai_instructions(p):
    """Dặn AI xưng hô và giọng nói."""
    text = (f"Gọi người dùng là \"{p['goi_nguoi_dung']}\", tự xưng là \"{p['bot_xung']}\". "
            f"{TONE_PROMPT[p['giong']]}")
    if p["ten"]:
        text += f" Người dùng tên {p['ten']}."
    if p.get("tuoi"):
        text += f" Tuổi: {p['tuoi']}."
    if p.get("noi_song"):
        text += f" Sống ở: {p['noi_song']}."
    if p["mo_ta"]:
        text += f" Về người dùng: {p['mo_ta'][:500]}"
    if p["ten_sep"]:
        text += f" Sếp của người dùng là {p['ten_sep']}; thỉnh thoảng có thể nhắc tới khi phù hợp."
    return text
