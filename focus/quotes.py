"""Câu trích dùng trong lời khích lệ, chào buổi sáng, đánh giá ngày / tuần.

Model AI miễn phí không thuộc nguyên văn Kinh Thánh bản Truyền Thống 1926 (hay chép sai chữ, đổi ý), nên app đưa
sẵn danh sách này vào prompt và AI CHỈ được chọn một câu trong đó, chép nguyên văn. Khi AI lỗi, app tự chọn một câu
trong cùng danh sách.

Thêm câu: đối chiếu từng chữ với bản gốc trước (Kinh Thánh: https://kinhthanh.httlvn.org/?v=VI1934, bản VI1934 là
bản Truyền Thống 1926), rồi thêm vào đúng danh sách.
"""

# Kinh Thánh Tin Lành, bản Truyền Thống 1926 (VI1934). Đã đối chiếu nguyên văn ngày 18/10/2026.
BIBLE = [
    ("Tôi làm được mọi sự nhờ Đấng ban thêm sức cho tôi.", "Phi-líp 4:13"),
    ("Chớ mệt nhọc về sự làm lành, vì nếu chúng ta không trễ nải, thì đến kỳ chúng ta sẽ gặt.", "Ga-la-ti 6:9"),
    ("Nhưng ai trông đợi Đức Giê-hô-va thì chắc được sức mới, cất cánh bay cao như chim ưng; "
     "chạy mà không mệt nhọc, đi mà không mòn mỏi.", "Ê-sai 40:31"),
    ("Hãy vững lòng bền chí, chớ run sợ, chớ kinh khủng; vì Giê-hô-va Đức Chúa Trời ngươi "
     "vẫn ở cùng ngươi trong mọi nơi ngươi đi.", "Giô-suê 1:9"),
    ("Hễ làm việc gì, hãy hết lòng mà làm, như làm cho Chúa, chớ không phải làm cho người ta.", "Cô-lô-se 3:23"),
    ("Hỡi những kẻ mệt mỏi và gánh nặng, hãy đến cùng ta, ta sẽ cho các ngươi được yên nghỉ.", "Ma-thi-ơ 11:28"),
    ("Hãy phó các việc mình cho Đức Giê-hô-va, thì những mưu ý mình sẽ được thành công.", "Châm-ngôn 16:3"),
    ("Đừng sợ, vì ta ở với ngươi; chớ kinh khiếp, vì ta là Đức Chúa Trời ngươi! Ta sẽ bổ sức cho ngươi.",
     "Ê-sai 41:10"),
    ("Ân điển ta đủ cho ngươi rồi, vì sức mạnh của ta nên trọn vẹn trong sự yếu đuối.", "II Cô-rinh-tô 12:9"),
    ("Kìa, con cái là cơ nghiệp bởi Đức Giê-hô-va mà ra; bông trái của tử cung là phần thưởng.", "Thi-thiên 127:3"),
    ("Đức Giê-hô-va là Đấng chăn giữ tôi; tôi sẽ chẳng thiếu thốn gì.", "Thi-thiên 23:1"),
    ("Hãy trao gánh nặng ngươi cho Đức Giê-hô-va, Ngài sẽ nâng đỡ ngươi; Ngài sẽ chẳng hề cho người công bình "
     "bị rúng động.", "Thi-thiên 55:22"),
    ("Hãy phó thác đường lối mình cho Đức Giê-hô-va, và nhờ cậy nơi Ngài, thì Ngài sẽ làm thành việc ấy.",
     "Thi-thiên 37:5"),
    ("Đức Chúa Trời là nơi nương náu và sức lực của chúng tôi, Ngài sẵn giúp đỡ trong cơn gian truân.",
     "Thi-thiên 46:1"),
    ("Nầy là ngày Đức Giê-hô-va làm nên, chúng tôi sẽ mừng rỡ và vui vẻ trong ngày ấy.", "Thi-thiên 118:24"),
    ("Hãy hết lòng tin cậy Đức Giê-hô-va, chớ nương cậy nơi sự thông sáng của con; phàm trong các việc làm của "
     "con, khá nhận biết Ngài, thì Ngài sẽ chỉ dẫn các nẻo của con.", "Châm-ngôn 3:5-6"),
    ("Ấy là nhờ sự nhơn từ Đức Giê-hô-va mà chúng ta chưa tuyệt. Vì sự thương xót của Ngài chẳng dứt. Mỗi buổi "
     "sáng thì lại mới luôn, sự thành tín Ngài là lớn lắm.", "Ca-thương 3:22-23"),
    ("Vậy, chớ lo lắng chi về ngày mai; vì ngày mai sẽ lo về việc ngày mai. Sự khó nhọc ngày nào đủ cho ngày ấy.",
     "Ma-thi-ơ 6:34"),
    ("Ta để sự bình an lại cho các ngươi; ta ban sự bình an ta cho các ngươi; ta cho các ngươi sự bình an chẳng "
     "phải như thế gian cho. Lòng các ngươi chớ bối rối và đừng sợ hãi.", "Giăng 14:27"),
    ("Vả, chúng ta biết rằng mọi sự hiệp lại làm ích cho kẻ yêu mến Đức Chúa Trời, tức là cho kẻ được gọi theo ý "
     "muốn Ngài đã định.", "Rô-ma 8:28"),
]

# Châm ngôn, câu nói có thật của người thành đạt, danh nhân, nhà hiền triết (không có Kinh Thánh).
QUOTES = [
    ("Đường tuy ngắn, không đi không bao giờ đến; việc tuy nhỏ, không làm chẳng bao giờ nên.", "Tuân Tử"),
    ("Thất bại là mẹ thành công.", "Tục ngữ"),
    ("Hành trình vạn dặm bắt đầu từ một bước chân.", "Lão Tử"),
    ("Không có việc gì khó, chỉ sợ lòng không bền. Đào núi và lấp biển, quyết chí ắt làm nên.", "Hồ Chí Minh"),
    ("Có công mài sắt, có ngày nên kim.", "Tục ngữ"),
    ("Ngã bảy lần, đứng dậy tám lần.", "Ngạn ngữ Nhật Bản"),
    ("Chúng ta là những gì chúng ta làm lặp đi lặp lại. Xuất sắc không phải là một hành động, mà là một thói quen.",
     "Will Durant"),
    ("Kỷ luật là cầu nối giữa mục tiêu và thành tựu.", "Jim Rohn"),
    ("Việc khó nhất là quyết định hành động, phần còn lại chỉ là sự kiên trì.", "Amelia Earhart"),
    ("Tôi không thất bại. Tôi chỉ tìm ra 10.000 cách không hiệu quả.", "Thomas Edison"),
    ("Ví như đắp núi, chỉ còn thiếu một sọt đất mà dừng, ấy là tự ta dừng.", "Khổng Tử, Luận Ngữ 9.19"),
    ("Trời sắp giao trọng trách cho người nào, ắt trước hết làm khổ tâm chí, nhọc gân cốt người ấy.",
     "Mạnh Tử, Cáo Tử hạ"),
    ("Không phải vì việc khó mà ta không dám làm; chính vì ta không dám làm nên việc mới khó.",
     "Seneca, Thư gửi Lucilius 104"),
    ("Cái cản đường hành động lại thúc đẩy hành động. Chướng ngại trên đường trở thành con đường.",
     "Marcus Aurelius, Suy Tưởng 5.20"),
    ("Làm tốt hơn nói hay.", "Benjamin Franklin"),
    ("Cách duy nhất để làm được việc tuyệt vời là yêu điều bạn làm.", "Steve Jobs, Stanford 2005"),
]

MENU_HEAD = ("DANH SÁCH CÂU TRÍCH ĐƯỢC DÙNG (app đã đối chiếu nguyên văn): cần câu trích thì CHỈ chọn MỘT câu trong "
             "danh sách này, chép đúng từng chữ và ghi đúng nguồn như bên dưới, đặt trong ngoặc kép. Không sửa chữ, "
             "không ghép câu, không dùng câu nào ngoài danh sách.")


def fmt(item, bible):
    text, src = item
    return f'"{text}" ({src})' if bible else f'"{text}" — {src}'


def fresh(items, recent):
    """Bỏ các câu đã gửi gần đây (so 30 chữ đầu); bỏ hết thì giữ nguyên danh sách."""
    joined = " ".join(recent or [])
    return [q for q in items if q[0][:30] not in joined] or list(items)


def menu(bible=False, sages=True, recent=None):
    """Khối danh sách câu trích gửi kèm prompt. bible: thêm Kinh Thánh; sages: thêm danh ngôn."""
    lines = []
    if bible:
        lines += ["Kinh Thánh (bản Truyền Thống 1926):"] + [f"- {fmt(q, True)}" for q in fresh(BIBLE, recent)]
    if sages:
        lines += ["Danh ngôn:"] + [f"- {fmt(q, False)}" for q in fresh(QUOTES, recent)]
    return MENU_HEAD + "\n" + "\n".join(lines) if lines else ""
