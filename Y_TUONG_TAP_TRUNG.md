# Ý tưởng để tập trung tốt hơn

File này gom mọi ý tưởng từ lúc bàn đến giờ, chia 4 phần: thói quen làm được ngay, tính năng app **đã có**, ý tưởng **chưa làm**, và ý tưởng đã cân nhắc rồi **quyết định không làm**. Cách dùng chi tiết từng tính năng: README mục 4 và 5.

## 1. Thói quen làm được ngay, không cần code

| # | Thói quen | App hỗ trợ thế nào |
|---|---|---|
| 1 | **Chốt 3 việc trước 9h.** Mỗi việc ghi rõ output ("gửi spec API cho anh A"), không ghi kiểu "làm spec" | Bot hỏi kế hoạch mỗi sáng (`/plan`) |
| 2 | **Làm theo khối, nghỉ có chủ đích.** Làm 50–60 phút trong VDI, rồi đứng dậy rời máy vài phút. Rời máy có chủ đích thì tốt; rời máy vì bị kéo đi mới là vấn đề | Nhắc đứng dậy sau 60 phút tập trung (`/break`) kèm bài tập mắt / vận động |
| 3 | **Gom chat và email vào khung cố định**, ví dụ 9:00, 11:30, 14:00, 16:30. Ngoài khung thì tắt thông báo Zalo/Teams trên máy local. Đây thường là nguồn "rời VDI" lớn nhất | Nhắc khi làm ngoài VDI quá lâu (`/nudge`) |
| 4 | **Chặn lịch "giờ vàng".** Đặt một event "Focus" lặp lại vào khung giờ bạn tập trung tốt nhất để người khác khó xếp họp | `/golden` chỉ ra khung giờ đó sau 1–2 tuần số liệu |
| 5 | **Để điện thoại, iPad ngoài tầm tay** trong khối tập trung. App không đo được điện thoại, nhưng nó hiện ra thành "không chạm máy 2–4 phút" lặp đi lặp lại | Thấy kiểu đó lặp lại thì bot nhắc cất điện thoại |
| 6 | **Ghi việc đầu tiên của ngày mai trước khi về.** Sáng hôm sau mở máy là bắt tay luôn | `/tmrtask`, sáng hôm sau bot nhắc lại |
| 7 | **Ghi issue ngay khi bị chặn**, không đợi cuối ngày: VDI chậm, thiếu quyền, chờ review | `/issue`; tổng kết tuần chỉ ra issue lặp lại |
| 8 | **Phóng to VDI trên một màn hình**, để Chrome/Zalo ở màn hình kia hoặc tắt hẳn. Ít thấy thì ít bấm | Bot gợi ý phóng to khi VDI mở cỡ nhỏ lâu |
| 9 | **Uống nước, nghỉ mắt đều đặn** | `/water`, bài tập mắt 20-20-20 trong lời nhắc nghỉ |
| 10 | **Báo nghỉ trước** (nghỉ phép, ngày nghỉ bù) để bot không nhắc vô ích | `/leave`, `/off` |

## 2. Tính năng app đã có

**Đo và chấm điểm**

| Tính năng | Lệnh / thời điểm | Ghi chú |
|---|---|---|
| Đo giờ trong VDI, giờ tập trung sâu (khối ≥ 20 phút liên tục), giờ ngoài VDI, VDI thu nhỏ, rời máy | Tự động mỗi 5 giây | Chỉ đọc tên app, trạng thái cửa sổ, số giây chưa chạm phím. Không chụp màn hình, không đọc phím |
| Nhận VDI chính xác: phóng to, vừa vừa, thu nhỏ, nằm sau, đóng; cả mặt phiên Citrix `Citrix.EngineUI.App.exe` | Tự động | VDI thu nhỏ luôn tính là không tập trung; làm ở app bên cạnh VDI cũng vậy |
| Chống Citrix đổi tên app ở bản sau | Tự động | Nhận theo thư mục cài Citrix, tiêu đề, vị trí cửa sổ; `/status` báo tên mới |
| Citrix mở bằng trình duyệt | `vdi_browser_title_keywords` | Nhận tab VDI theo tiêu đề tab; có sẵn tên máy ảo công ty `AZ-WIN11-SGLIFE`, máy ảo khác thì sửa |
| Điểm tập trung 0–100 | `/today`, tổng kết ngày | 70 điểm: giờ tập trung sâu so với mục tiêu 4h; 30 điểm: tỉ lệ thời gian trong VDI. Rời máy không bị trừ |
| **Điểm tổng 0–100 (thang 10) + robot quà tặng** | `/today`, tổng kết ngày/tuần, `/report` | 60% điểm tập trung + 30% ít bị cắt ngang (mốc 20 lần/giờ theo nghiên cứu González & Mark 2004) + 10% năng lượng tự chấm. Robot tự vẽ 5 hạng SD → HG → RG → MG → PG. Trọng số là lựa chọn của app, từng thành phần có căn cứ nghiên cứu |
| AI giải thích điểm tổng | Tổng kết ngày, tuần | AI bắt buộc mở đầu bằng điểm tổng: mức gì, từng thành phần, phần kéo điểm xuống, làm gì để tăng; app tính sẵn số |
| Lời khuyên khoa học khi điểm tổng dưới 50 | Tổng kết ngày | Một câu từ nghiên cứu thật (đã kiểm chứng), kèm lý do vì gia đình |
| Số lần và trung bình mỗi lần: thu nhỏ VDI, ngồi yên, rời máy, ngồi yên ≥ 10 phút, bị cắt ngang mỗi giờ | `/today`, `/report` | Báo cáo HTML có thêm trung bình sao nhãng 14 ngày, giờ hay sao nhãng |
| Cộng giờ làm cho thấy đủ giờ | `/today`, tổng kết ngày, báo cáo HTML | Trong VDI + ngoài VDI + inactive + rời máy + không ghi (tạm dừng, tắt tracker) = giờ làm chính thức trừ giờ trưa. Thu nhỏ VDI nằm trong ngoài VDI |
| Làm thêm ngoài giờ (OT) | Tự động | Trước giờ làm, sau 17:00 chỉ cộng giờ gõ phím / rê chuột trong VDI, không tính sao nhãng; **giờ trưa không tính gì**. Sáng hôm sau báo OT kèm khoảng giờ (ví dụ 17:30–18:15) |
| Tổng OT 14 ngày | Tổng kết 17:00, tổng kết tuần, lời chào sáng, báo cáo HTML | Tổng giờ OT và danh sách chỉ những ngày có OT, mỗi ngày bao nhiêu giờ, giờ nào |
| Làm bù thứ 7, CN, ngày lễ | Nhấp đúp `lam_bu_ngoai_gio.bat` (Mac `.command`) | Chỉ ghi giờ làm trong VDI có gõ phím / chuột, không nhắc, không tính sao nhãng, không chấm điểm; làm xong (qua 17:00 và 30 phút không làm trong VDI) bot gửi ngay 🌙 tổng kết làm bù + file HTML; máy tắt trước đó thì sáng thứ Hai báo |
| Chuỗi ngày đạt mục tiêu (streak) | `/today` | Ngày nghỉ không làm đứt chuỗi |
| Giờ vàng | `/golden` | Khung giờ tập trung tốt nhất 14 ngày qua |
| Hiệu năng | `/perf`, `xem_cpu_ram.bat` | Đo thật trên laptop: CPU khoảng 0,07% một nhân, RAM khoảng 32 MB |

**Nhắc nhở qua Telegram**

| Tính năng | Lệnh | Ghi chú |
|---|---|---|
| Nhắc khi sao nhãng (làm ngoài VDI, VDI thu nhỏ) | `/nudge off` / `nhe` / `vua` / `nghiem` | 4 mức. Mặc định: nhắc khi ra ngoài VDI quá 10 phút |
| Tắt / bật lại tracker giữa ngày vẫn đếm tiếp | Tự động | Số lần, số phút sao nhãng và số lần nhắc hôm nay lưu vào DB mỗi phút; bật lại trong ngày thì đếm tiếp, không về 0. Mức nhẹ đã nhắc rồi thì vẫn im |
| Báo khi rời máy quá lâu, chào khi quay lại | — | Chỉ trong giờ làm, trừ giờ trưa |
| Báo ngay khi cửa sổ VDI biến mất (Citrix tự ngắt sau khoảng 10–20 phút không dùng) | — | Chỉ 08:00–17:00, trừ trưa, và chỉ khi hôm đó đã làm trong VDI |
| Nhắc cất điện thoại, gợi ý phóng to VDI | — | Theo kiểu "không chạm máy" lặp lại |
| Cảnh báo tiến độ lúc 10:30, 14:00, 15:30 | `/pace` | Chậm so với mục tiêu giờ VDI thì nhắc, đúng nhịp thì khen |
| Nhắc đứng dậy sau 60 phút tập trung, kèm bài tập mắt / vận động | `/break` | Bật/tắt, đổi số phút. Kèm một dữ kiện nghiên cứu thật (Dunstan 2012, Ekelund 2016, Albulescu 2022) |
| Nhắc uống nước | `/water on` | **Mặc định tắt** khi cài lần đầu; bật bằng `/water on`, đổi số phút. Kèm dữ kiện nghiên cứu (Borghi 1996, Ganio 2011) |
| Giọng nhắc theo persona | `/style` | Thân mật, vui tươi, hài hước, sếp khó tính; nhắc tên sếp khi lặp lại |

**Ghi chép và tổng kết**

| Tính năng | Lệnh / thời điểm | Ghi chú |
|---|---|---|
| Kế hoạch sáng, tổng kết chiều | `/plan`, `/review` | Bot tự hỏi lúc 08:00 và 16:45. Xem lại kế hoạch: `/today` |
| Ghi nhanh output, issue, điều làm phân tâm, việc mai, năng lượng | `/output` `/issue` `/distraction` `/tmrtask` `/energy` | Nhắn tự nhiên cũng được («nãy giờ bận trông em bé khóc» là ghi điều làm phân tâm). Năng lượng 1–5 bạn tự chấm góp 10% điểm tổng, không ảnh hưởng điểm tập trung |
| Nhắc việc còn tồn mỗi sáng, cộng dồn | Tự động trong lời chào sáng, báo cáo HTML, đánh giá AI | Kế hoạch / issue chưa thấy ghi xong; hôm qua chưa có cập nhật thì thành việc tồn hôm nay (ghi «tồn từ» ngày nào), tối đa 10 ngày làm việc |
| Bot tự tính năng lượng khi bạn chưa chấm | Tự động lúc 17:00, `/autoenergy` | Tập trung sâu càng lâu thì năng lượng càng cạn; sao nhãng thì còn dư. Bot gửi số tính được kèm cách tính, `/energy` để sửa |
| Xem lại một ngày đã qua | `/today hôm qua`, `/today 14/10`, `/report hôm qua` | Số liệu, điểm, kế hoạch, năng lượng, output, issue của ngày đó |
| Giờ vào/ra AS400 | `/as400 08:10 17:35` hoặc gửi ảnh spooled file | AI chỉ đọc giờ sớm nhất và muộn nhất, hỏi lại trước khi lưu |
| Tổng kết ngày + AI đánh giá | Tự động 17:00 | Việc pending, vì sao mất tập trung, cần khắc phục gì |
| Tổng kết tuần + AI phân tích | Tự động thứ Sáu 17:05 (sau tổng kết ngày), `/week` | Giờ vàng, ngày tốt/kém nhất, issue lặp lại, kèm file báo cáo tuần HTML |
| Báo cáo HTML ngày và tuần | `/report`, `bao_cao_hom_nay.bat`, `/week` | Bảng màu Pop Art cổ điển, mỗi loại thời gian một màu cố định; điểm tổng to + robot quà tặng + thang 5 robot; 6 ô màu (ghi «TB mỗi lần») và thẻ lớn cho các chỉ số phụ (OT = 0 thì ẩn); dòng thời gian có chú thích đủ màu; biểu đồ theo giờ; khối tập trung; OT 14 ngày; ghi chú; lời AI. Mở được trên điện thoại |
| Gửi bù | Tự động | Máy tắt trước 17:00 thì sáng mai gửi bù tổng kết |

**AI và động lực**

| Tính năng | Lệnh | Ghi chú |
|---|---|---|
| Chào buổi sáng, khích lệ buổi chiều | `/encourage` | Cài lần đầu **Kinh Thánh tắt**: mọi tin (chào, khích lệ, nhắc, đánh giá AI) dùng câu người thành đạt, danh nhân, hiền triết xưa. `/kinhthanh on` để dùng câu Kinh Thánh Tin Lành |
| Xin câu khích lệ bất kỳ lúc nào | `/quote`, `/bible` | Không lặp câu đã gửi hôm nay và hôm qua (gửi AI nguyên văn) |
| Hỏi AI bất cứ gì | `/ask`, `/hoi`, `/ask on` | AI biết bạn là ai, làm gì; tra web cho câu hỏi thời sự (giá vàng, thời tiết). Hết lượt tra web miễn phí thì tự hỏi lại không tra web |
| Nhắn tự nhiên thay cho lệnh | — | AI hiểu thành thao tác, hiện thẻ "Mình hiểu bạn muốn..." để bấm OK / Sửa. AI lỗi thì hiểu bằng từ khoá |
| Mọi lần gọi AI đều kèm đủ bối cảnh | — | Hồ sơ của bạn, công việc (AS400, COBOL, Life Asia), giọng văn, cách đo |
| Nhật ký prompt AI | `data/logs/ai-prompts-*.log` | Xem AI được hỏi gì, trả lời gì; tự xoá sau 14 ngày |
| Đếm lượt và số từ AI đã dùng | `/aistatus` | Gemini gói miễn phí, tự đổi model khi hết lượt |

**Lịch, nghỉ, cài đặt**

| Tính năng | Lệnh | Ghi chú |
|---|---|---|
| Nghỉ phép nửa ngày / cả ngày | `/leave` | Buổi nghỉ không đo, mục tiêu còn một nửa |
| Báo nghỉ, huỷ nghỉ, tạm dừng theo dõi | `/off` `/on` `/pause` `/resume` | — |
| Lễ Singapore theo lịch MOM, nghỉ bù thứ Hai khi lễ rơi Chủ nhật | Tự động | Tự tải lịch năm sau từ 1/12 |
| Không chạy thứ 7, Chủ nhật, ngày lễ | Tự động | — |
| Tự bật 08:00 thứ 2 – thứ 6, tự tắt 23:59 | `/giobot` | Đổi giờ qua bot, bot tự sửa Task Scheduler |
| Xem tình trạng đầy đủ | `/status` | Lúc này, hôm nay, cài đặt, AI, hệ thống |
| Dùng chung cho đồng nghiệp | `config/persona.json` | Không ghi cứng tên ai; mỗi người bot riêng, key riêng |
| Lấy chat ID lúc cài | `start_tracker.bat` | Chạy được mọi giờ, mọi ngày |
| Kiểm tra máy thật từng phần | `kiem_tra_may.bat [check ai mom autostart vdi tests]` | Có bản Mac `.command` riêng |
| Tự dọn dẹp, sao lưu, log mỗi ngày | Tự động | Lỗi được dịch thành câu tiếng Việt dễ hiểu |

## 3. Ý tưởng chưa làm

| Ý tưởng | Lợi ích | Trạng thái |
|---|---|---|
| Đặt tên cho bot | Bot có cá tính hơn | Gợi ý: Chíp, Tâm, Bít; chờ bạn chọn (tên nằm trong persona, không trong code) |

## 4. Đã cân nhắc và quyết định không làm

| Ý tưởng | Lý do không làm |
|---|---|
| Agent nhỏ chạy bên trong VDI | Chính sách công ty không cho cài gì trong VDI |
| Kéo output tự động từ Jira/Git | Không có tích hợp Jira/Git |
| Đọc lịch Outlook, tách giờ họp | Outlook nằm trong VDI, không đọc được từ máy thật |
| Nút "Bắt đầu focus 50 phút" + Do Not Disturb | Muốn app tự động hoàn toàn, ít thao tác tay; sao nhãng chủ yếu đến từ điện thoại/iPad |
| Gắn nhãn khối tập trung với việc trong kế hoạch | Thêm thao tác tay mỗi ngày |
| AI phân tích sâu nội dung spooled file AS400 | Chỉ cần giờ bắt đầu và kết thúc |
| Dùng Microsoft Viva Insights focus time hoặc Windows Focus thay cho app | Hai công cụ đó đặt lịch tập trung, tắt thông báo, bấm giờ; không đo giờ gõ phím / rê chuột trong cửa sổ Citrix trên laptop cá nhân. So sánh chi tiết ở README mục 1 |

## Gợi ý thứ tự

Chạy thật 1–2 tuần để có số liệu gốc và giờ vàng, rồi chặn lịch "Focus" theo `/golden`. Xem điểm tổng mỗi ngày để biết phần nào kéo điểm xuống nhiều nhất và sửa đúng chỗ đó.
