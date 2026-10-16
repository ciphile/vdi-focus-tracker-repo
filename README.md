# Focus Tracker

Đo **thời gian tập trung thật sự** khi làm việc trong máy ảo VDI (Citrix Desktop Viewer / Citrix Viewer), nhắc nhở qua **bot Telegram** riêng của bạn, và nhờ **AI** (Gemini hoặc Claude) đánh giá, khích lệ mỗi ngày.

| | |
|---|---|
| Tác giả | Khang Nguyen, viết cùng AI Claude (Anthropic). App dùng chung cho đồng nghiệp: mỗi người tự cài trên máy mình, tự tạo bot Telegram và key AI riêng |
| Phiên bản | 2.5.1 (`focus/__init__.py`) |
| Chạy trên | Windows 10/11 và macOS. Citrix mở bằng app (Workspace / Desktop Viewer) hoặc bằng trình duyệt (mục [4.2](#42-trạng-thái-cửa-sổ-vdi-phóng-to-thu-nhỏ-vừa-vừa-ẩn-trình-duyệt)) |
| Cần | Python 3.9+. **Chỉ dùng thư viện chuẩn** của Python (`requirements.txt` trống), không cần `pip install` |
| Ngôn ngữ bot | Tiếng Việt |

---

## Mục lục

1. [Mục đích, đo gì, riêng tư](#1-mục-đích-đo-gì-riêng-tư)
2. [Cài đặt và chạy từng file (Windows, Mac)](#2-cài-đặt-và-chạy-từng-file-windows-mac)
3. [Một ngày làm việc với bot](#3-một-ngày-làm-việc-với-bot)
4. [Danh mục tính năng (từng tính năng + tình huống mẫu)](#4-danh-mục-tính-năng)
5. [Danh sách lệnh](#5-danh-sách-lệnh)
6. [Nhắn tự nhiên: bot hiểu tin nhắn thế nào](#6-nhắn-tự-nhiên-bot-hiểu-tin-nhắn-thế-nào)
7. [AI: gọi thế nào, gửi gì, prompt mẫu](#7-ai-gọi-thế-nào-gửi-gì-prompt-mẫu)
8. [Dữ liệu lưu ở đâu](#8-dữ-liệu-lưu-ở-đâu)
9. [Log](#9-log)
10. [Tự dọn dẹp (housekeeping), sao lưu, khôi phục](#10-tự-dọn-dẹp-housekeeping-sao-lưu-khôi-phục)
11. [Cấu hình: settings.json, secrets.env, persona.json](#11-cấu-hình)
12. [Lỗi thường gặp](#12-lỗi-thường-gặp)
13. [Giới hạn và việc cần kiểm tra trên máy thật](#13-giới-hạn-và-việc-cần-kiểm-tra-trên-máy-thật)
14. [Cho lập trình viên](#14-cho-lập-trình-viên)

---

## 1. Mục đích, đo gì, riêng tư

Làm trong VDI rất dễ "trôi": thu nhỏ VDI lướt Chrome, đọc Zalo, cầm điện thoại, rời bàn lâu. Cuối ngày ngồi máy 8 tiếng nhưng không biết thật sự làm được bao nhiêu. Focus Tracker:

| Việc | Cách làm |
|---|---|
| **Đo** | Mỗi 5 giây xem cửa sổ nào đang ở trước, có chạm phím/chuột không, máy có khoá không. Tính giờ trong VDI, giờ **tập trung sâu**, điểm tập trung 0–100, **điểm tổng** kèm robot quà tặng, số lần thu nhỏ VDI / ngồi yên / rời máy và thời gian trung bình mỗi lần, chuỗi ngày đạt mục tiêu, giờ vàng, **giờ làm ngoài giờ (OT)** và tổng OT 14 ngày. Chỉ chấm sao nhãng trong giờ làm chính thức; làm ngoài giờ trong VDI thì cộng thêm giờ làm |
| **Nhắc ngay** | Qua Telegram: ra ngoài VDI quá lâu, rời máy, ngồi lâu cần đứng dậy, chậm tiến độ, uống nước (mặc định tắt, bật bằng `/water on`). Mức nhắc chọn được: tắt / nhẹ / vừa / nghiêm (`/nudge`, bước 11 mục 2.4) |
| **Ghi chép** | Kế hoạch, việc xong, issue, điều làm phân tâm (nhắn tự nhiên «nãy giờ bận trông em bé khóc» cũng được), việc đầu tiên sáng mai, năng lượng, giờ AS400. Việc còn tồn (kế hoạch, issue chưa thấy ghi xong) **cộng dồn** qua các ngày: hôm qua chưa xong thì sáng nay bot nhắc lại, chưa xong nữa thì mai nhắc tiếp |
| **Tổng kết** | 17:00 mỗi ngày và chiều thứ Sáu: số liệu + AI đánh giá (điểm tổng nghĩa là gì, việc pending, vì sao mất tập trung, cần khắc phục gì) + file báo cáo HTML (ngày, tuần) có biểu đồ, robot quà, OT 14 ngày. Thứ 7 / CN có bật bot làm bù: tổng kết làm bù khi làm xong |
| **Khích lệ** | Đầu ngày, 14:30. Cài lần đầu: **Kinh Thánh tắt**, mọi tin (chào sáng, khích lệ, nhắc nhở, AI đánh giá) dùng châm ngôn của người thành đạt, danh nhân, hiền triết xưa. `/kinhthanh on`: dùng câu Kinh Thánh Tin Lành (bản Truyền Thống 1926). Luôn tích cực |

**Bot đo từ bên ngoài VDI: biết gì, không biết gì**

Công ty không cho cài gì trong VDI, nên bot không nhìn thấy bên trong VDI. Nó chỉ biết 3 điều từ máy thật: cửa sổ VDI có đang ở trước và có phóng to không, Windows / macOS ghi nhận lần chạm phím hoặc chuột cuối cách đây bao nhiêu giây, máy có khoá không. Cho nên **VDI đang mở và phóng to mà bạn không chạm phím / chuột thì bot vẫn đo được**, theo thời gian không chạm:

```
VDI đang ở trước, phóng to. Bạn không chạm phím / chuột bao lâu?
   |
   |-- dưới 60 giây --> vẫn tính là làm trong VDI (đang đọc, đang nghĩ)
   |
   |-- 60 giây tới 5 phút --> "ngồi yên" (inactive): không tính vào giờ làm trong VDI.
   |                          Ngồi yên rồi làm tiếp lặp 3 lần trong 30 phút
   |                          --> bot nhắc cất điện thoại (mục 4.5)
   |
   |-- từ 5 phút (hoặc khoá máy, máy ngủ) --> "rời máy": không tính là làm việc, không bị
   |                                           trừ điểm; số rời máy hiện trong /today
   |
   |-- từ 15 phút --> bot nhắn "bạn đã rời máy N phút" (mục 4.4)
```

| Tình huống | Bot thấy gì | Bot tính là |
|---|---|---|
| Gõ, rê chuột trong VDI | VDI ở trước, có chạm phím / chuột | Làm trong VDI |
| VDI phóng to, bạn đọc màn hình AS400 hoặc chờ job chạy, vài chục giây không chạm gì | VDI ở trước, chưa chạm dưới 60 giây | Vẫn làm trong VDI |
| Cùng cảnh trên nhưng kéo dài trên 1 phút | Chưa chạm từ 60 giây | Ngồi yên: không tính vào giờ làm. Chạm lại là tính tiếp |
| Họp chỉ nghe, hoặc xem người khác chia sẻ màn hình trong VDI, không gõ | Như trên | Ngồi yên, rồi rời máy. **Bot không biết bạn đang họp.** Họp lâu: nhắn `/pause`, họp xong nhắn `/resume` |
| Đi pha cà phê, đi vệ sinh, khoá máy | Không chạm, hoặc máy khoá | Rời máy |
| Đang ngồi yên mà đụng chuột đúng một lần rồi lại im (đi ngang bàn, chuột Bluetooth tự gửi tín hiệu) | Một lần chạm lẻ | Chưa phải quay lại: quãng ngồi yên / rời máy tính liền một mạch (mục 4.1) |
| Chạm phím / chuột nhưng cửa sổ trước mặt là app khác, hoặc VDI thu nhỏ | Có chạm, VDI không ở trước | Làm ngoài VDI (không phải ngồi yên) |
| Làm việc bằng điện thoại / iPad, máy tính để yên | Không chạm | Ngồi yên hoặc rời máy. Bot không thấy điện thoại, chỉ thấy máy tính im |

Hai điều bot **không** phân biệt được: bạn đang suy nghĩ, đọc, họp (không chạm máy nhưng vẫn làm việc) với bạn đang làm việc riêng (không chạm máy). Cả hai đều là «không chạm máy». Vì vậy tin nhắc rời máy có sẵn câu «Đang họp chỉ nghe trong VDI thì bỏ qua tin này, hoặc gõ /pause» (mục 4.4). Ngưỡng 60 giây, 5 phút, 15 phút đổi trong `settings.json`: `idle_threshold_seconds`, `away_threshold_seconds`, `away_alert_minutes` (mục 11.1).

**Giờ làm chính thức và làm thêm ngoài giờ (OT)**

Tracker chạy tới 23:59, nhưng chỉ chấm sao nhãng trong giờ làm chính thức. Ngoài giờ bot chỉ ghi nhận phần bạn **làm thật trong VDI**, để giờ làm bù buổi tối được cộng vào ngày đó. **OT** = thời gian gõ phím / rê chuột trong VDI ngoài giờ làm chính thức: trước giờ làm, sau 17:00, thứ 7 / CN / ngày lễ (khi bạn tự bật bot). **Giờ nghỉ trưa không tính gì cả**: không sao nhãng, cũng không phải OT.

```
Mẫu 5 giây này rơi vào lúc nào?
   |
   |-- trong giờ làm (work_start – work_end, mặc định 08:00 – 17:00), trừ giờ trưa
   |      --> đo đủ: trong VDI, ngoài VDI, thu nhỏ, ngồi yên, rời máy; nhắc ngay khi cần
   |
   |-- giờ nghỉ trưa (lunch_start – lunch_end, mặc định 11:15 – 12:30)
   |      --> không tính gì: gõ trong VDI cũng không cộng, không phải OT, không nhắc
   |
   |-- /pause, buổi nghỉ phép nửa ngày --> không đo, không nhắc
   |
   |-- ngày nghỉ (thứ 7, CN, lễ, /off)
   |      |-- tracker không tự bật --> không đo gì
   |      |-- BẠN tự bật (lam_bu_ngoai_gio.bat / start_tracker.bat)
   |             --> cả ngày tính như "ngoài giờ" bên dưới
   |
   |-- ngoài giờ: trước work_start, sau work_end (tới lúc tracker tắt)
          |-- gõ phím / rê chuột trong VDI --> "làm ngoài giờ" (OT): cộng vào giờ làm,
          |                                      khối tập trung sâu, điểm
          |-- mọi thứ khác (app khác, thu nhỏ VDI, ngồi yên, rời máy)
                 --> bỏ qua: không tính sao nhãng, không trừ điểm, không nhắc
```

| Ví dụ | Bot ghi |
|---|---|
| 19:00 – 19:40 mở VDI làm bù giờ thiếu ban ngày | OT 40 phút. Khối 19:00–19:40 được cộng vào tập trung sâu, điểm tập trung, điểm tổng của **ngày đó** |
| 16:30 đang làm, làm tiếp liền tới 17:30 | Một khối liền 16:30–17:30; mốc 17:00 không bị coi là ngắt quãng |
| 20:00 lướt web, xem phim trên laptop | Không ghi gì, không tính sao nhãng |
| Ăn trưa tại bàn mà vẫn gõ trong VDI 12:00 – 12:20 | Không ghi gì: giờ trưa không tính, cũng không phải OT. Lướt web giờ trưa cũng không ghi, không nhắc |
| 07:40 mở VDI sớm, đi pha cà phê | Không tính rời máy, không nhắc (chưa tới giờ làm) |
| Thứ Bảy nhấp đúp `lam_bu_ngoai_gio.bat`, làm trong VDI 09:00 – 11:00, giữa chừng lướt web, cầm điện thoại | Bot nhắn 1 câu «Hôm nay nghỉ (cuối tuần) mà bạn tự bật bot: mình chỉ ghi giờ làm bù trong VDI...». Ghi làm bù = phần có gõ phím / rê chuột trong VDI. Lướt web, thu nhỏ VDI, ngồi yên, rời máy: không ghi, không nhắc. Không chấm điểm ngày nghỉ |
| Thứ Bảy không bật gì | Tracker không tự bật cuối tuần, không ghi gì |
| Thứ Bảy làm bù xong (sau 17:00 và đã ngưng làm trong VDI 30 phút) | Bot gửi 1 tin «🌙 Tổng kết làm bù Thứ bảy 17/10 (cuối tuần): 2h 00m trong VDI (09:00–11:00), tập trung sâu ...» + tổng OT 14 ngày + file báo cáo HTML của ngày đó. Làm tới chiều tối thì đợi bạn ngưng 30 phút mới báo. Gập máy trước đó thì sáng thứ Hai bot báo |
| Báo cáo HTML ngày / tuần | Mục «Làm ngoài giờ (OT) 14 ngày gần nhất»: chỉ liệt kê ngày có OT, mỗi ngày số giờ và các khoảng giờ (ví dụ «T3 13/10 · 45m · 17:30–18:15»), kèm tổng. Tin tổng kết 17:00 và tổng kết tuần cũng có khối này |
| Sáng ngày làm việc kế tiếp | Mỗi ngày có làm bù một dòng 🌙, kể cả thứ 7, CN: «🌙 Thứ bảy 17/10 (cuối tuần) bạn bật bot làm bù 2h 00m trong VDI (09:00–11:00), tập trung sâu .... Bot đã ghi nhận giờ làm, không tính sao nhãng.» Ngày làm việc: «🌙 Thứ năm 15/10 bạn làm thêm ngoài giờ (OT) 40m trong VDI (19:00–19:40). Bot đã cộng vào số liệu ngày đó: tập trung sâu ..., điểm tập trung ..., điểm tổng .../100. Ngoài giờ bot chỉ cộng giờ làm, không tính sao nhãng.» Dòng cuối: «⏱ Tổng OT 14 ngày qua: 3h 10m trong 4 ngày». `/today hôm qua`, `/report hôm qua`, tổng kết tuần dùng số đã cộng. Tin tổng kết 17:00 hôm trước thì đã gửi rồi, không gửi lại |

**So với Microsoft Viva Insights và Windows Focus**

Hai công cụ có sẵn của Microsoft hay bị nhầm là "đo tập trung", nhưng chúng làm việc khác: chặn thông báo và giữ lịch, không đo bạn thật sự làm trong VDI bao lâu.

| | Focus Tracker (app này) | Viva Insights: focus time / focus plan | Windows Focus (Focus sessions) |
|---|---|---|---|
| Làm gì | Đo thời gian bạn thật sự làm trong cửa sổ VDI, nhắc khi trôi ra ngoài, tổng kết, chấm điểm | Tự đặt khối "Focus time" vào lịch Outlook mỗi ngày, trong khối đó tắt thông báo Teams (trừ người ưu tiên), đổi trạng thái Teams thành "Focusing", có hẹn giờ và nghỉ ngắn | Bật hẹn giờ trên máy, tự bật Do not disturb, tắt chấm đỏ / nhấp nháy trên taskbar; nối được Microsoft To Do, Spotify |
| Chạy ở đâu | Laptop cá nhân của bạn, nhìn cửa sổ Citrix từ bên ngoài | Trong Teams / Outlook của công ty (tức là bên trong VDI), theo tài khoản và quyền Microsoft 365 công ty bật | Windows của máy đang dùng |
| Biết VDI đang ở trước, phóng to, thu nhỏ, hay bạn đang ở app khác | Có, mỗi 5 giây | Không | Không |
| Đo gõ phím / rê chuột, ngồi yên, rời máy | Có (chỉ số giây chưa chạm, không ghi phím gì) | Không | Không |
| Giờ tập trung sâu, số lần bị cắt ngang, điểm tổng, OT, OT 14 ngày | Có, tính từ dữ liệu đo thật | Không đo; chỉ biết lịch bạn đã giữ giờ tập trung | Không |
| Nhắc khi bạn bỏ VDI quá lâu, rời máy, ngồi lâu | Có, qua Telegram, mức tắt / nhẹ / vừa / nghiêm | Không | Không (chỉ chặn thông báo trong lúc hẹn giờ) |
| Báo cáo ngày / tuần + AI nhận xét | Có, gửi Telegram + file HTML | Có thẻ thông tin thói quen làm việc trong Teams, dựa trên lịch, email, họp | Không |
| Ai thấy dữ liệu | Chỉ bạn (DB trên laptop, bot Telegram của bạn) | Nằm trong hệ thống Microsoft 365 của công ty | Trên máy bạn |
| Cần gì | Python + bot Telegram riêng, laptop cá nhân là đủ | Tài khoản Microsoft 365 công ty có Viva Insights | Windows 11 |

Khác biệt quan trọng nhất khi làm qua Citrix trên laptop cá nhân:

```
Bạn làm việc thật ở đâu?            Công cụ nào nhìn thấy?
   |
   |-- bên trong VDI (AS400, COBOL, Outlook, Teams của công ty)
   |      |-- Viva Insights: thấy lịch, email, họp trong M365, KHÔNG thấy bạn có đang
   |      |                  ngồi trước VDI hay không
   |      |-- Focus Tracker: không thấy bên trong, nhưng thấy cửa sổ VDI có ở trước
   |                         và bạn có đang gõ / rê chuột vào nó không
   |
   |-- trên laptop, ngoài VDI (Chrome, Zalo, YouTube...)
          |-- Viva Insights: không thấy (laptop cá nhân không thuộc M365 công ty)
          |-- Windows Focus: chỉ chặn thông báo trong lúc hẹn giờ, không đo
          |-- Focus Tracker: thấy, tính là "ngoài VDI", nhắc bạn quay lại
```

Focus Tracker **không** chấm hiệu suất theo kết quả công việc (số việc xong, số bug sửa, email đã gửi) và **không biết bạn làm gì bên trong VDI**. Nó chỉ đo **thời gian** bạn có làm trong VDI và mức độ liền mạch. Điểm tổng nói ngày đó bạn làm liền mạch tới đâu, có bị cắt ngang nhiều không, không nói bạn làm giỏi hay dở. Ba công cụ dùng chung được: Viva / Windows Focus giúp giữ lịch và chặn thông báo, Focus Tracker cho biết thực tế bạn có ngồi làm trong VDI không.

**Riêng tư** (đọc kỹ trước khi dùng):

| Điều | Chi tiết |
|---|---|
| Không chạy gì trong VDI | App chỉ nhìn từ máy thật (Windows / Mac). Không cài, không chạy gì bên trong VDI |
| Không đọc nội dung màn hình | Không chụp màn hình, không đọc email, code, tài liệu. Chỉ lấy: tên process của cửa sổ đang ở trước, trạng thái cửa sổ VDI, số giây chưa chạm phím/chuột, máy khoá hay không |
| Tiêu đề cửa sổ | Đọc để nhận VDI (và tab Citrix trong trình duyệt) nhưng **không lưu** vào DB, trừ khi bạn bật `store_window_titles` |
| Ra khỏi máy | (1) Tin nhắn Telegram tới bot **của bạn**. (2) Nếu có key AI: số liệu đã tổng hợp + ghi chú bạn tự gõ gửi tới Gemini/Claude (mục 7). (3) Tải lịch lễ từ trang MOM Singapore (chỉ đọc). Không gửi mẫu thô hay tiêu đề cửa sổ cho AI |
| Bí mật | Token Telegram, key AI chỉ nằm trong `config/secrets.env`. **Không commit, không gửi file này cho ai** |

> ⚠️ **Ảnh AS400 được gửi tới AI bên ngoài.** Khi bạn gửi ảnh màn hình AS400 (spooled file / job log) cho bot, nguyên ảnh được chuyển tới Gemini/Claude để đọc giờ. Màn hình AS400 có thể chứa **dữ liệu khách hàng / dữ liệu nội bộ**. Hỏi chính sách công ty trước. Tắt hẳn bằng `"as400_photo_ai": false` và gõ giờ bằng `/as400 08:10 17:35`.

---

## 2. Cài đặt và chạy từng file (Windows, Mac)

Mục này đi theo đúng thứ tự làm. Cài lần đầu trên Windows: đọc 2.1 → 2.4. Trên Mac: 2.1 → 2.3 rồi 2.5. File cấu hình nào bắt buộc (`secrets.env`, `persona.json`), file nào bỏ qua được (`settings.json`), bot tự lưu gì: đầu mục 2.4. Mọi file trong thư mục app được giải thích ở 2.7, việc nào chạy file nào ở 2.8.

### 2.1 Vài thao tác dùng xuyên suốt

**Chạy một file**

| Thao tác | Windows | Mac |
|---|---|---|
| **Nhấp đúp** | Bấm nhanh 2 lần chuột trái vào file `.bat`. Một cửa sổ nền đen hiện ra, chạy xong thường dừng lại chờ bạn bấm phím bất kỳ (hoặc Enter) để đóng | Nhấp đúp file `.command`: Terminal mở ra và chạy. Xong bấm Enter để đóng |
| **Run with PowerShell** | Chuột phải file `.ps1` > *Run with PowerShell* (Windows 11: chuột phải > *Show more options* > *Run with PowerShell*). Nếu hiện câu hỏi «Execution Policy Change ... Do you want to change the execution policy?»: gõ `Y` rồi Enter. Câu trả lời chỉ có hiệu lực trong cửa sổ đó, không đổi cài đặt máy. **Không cần làm cách này**: nhấp đúp file `.bat` cùng tên làm y hệt mà không bị hỏi | Không có |
| **Chạy kèm chữ phía sau** (ví dụ `kiem_tra_may.bat vdi`) | Mở thư mục app trong File Explorer > bấm vào **thanh địa chỉ** (ô hiện đường dẫn phía trên, ví dụ `Documents > ClaudeProjects > focus-tracker`) > gõ `cmd` > Enter. Cửa sổ cmd mở sẵn đúng thư mục đó. Gõ `kiem_tra_may.bat vdi` > Enter | Mở *Terminal* (Launchpad > Other > Terminal) > gõ `cd ` (chữ cd và **một dấu cách**) > kéo thư mục app từ Finder thả vào cửa sổ Terminal > Enter. Rồi gõ `./kiem_tra_may.command vdi` > Enter |
| Mac chặn file `.command` lần đầu («cannot be opened», «Apple could not verify...») | — | Chuột phải file > *Open* > *Open*. Vẫn bị chặn: *System Settings > Privacy & Security* > kéo xuống > *Open Anyway*. Báo «không có quyền chạy» (permission denied): trong Terminal đã `cd` vào thư mục app, gõ `chmod +x *.command` > Enter, rồi nhấp đúp lại |

**Thấy đuôi file (Windows, nên bật trước khi làm gì khác)**

Windows mặc định giấu đuôi file, nên `secrets.env` và `secrets.env.txt` trông giống hệt nhau, nhưng app chỉ đọc `secrets.env`. Bật hiện đuôi file:

| Windows 11 | Windows 10 |
|---|---|
| File Explorer > *View* > *Show* > tích *File name extensions* | File Explorer > tab *View* > tích *File name extensions* |

**Sửa file cấu hình**

| | Windows | Mac |
|---|---|---|
| Mở | Chuột phải file > *Open with* > *Notepad* (Windows 11: *Open with* > *Choose another app* > *Notepad*) | Chuột phải > *Open With* > *TextEdit* |
| Lưu | Ctrl+S | Cmd+S |
| Không dùng | Word, WordPad (thêm định dạng, hỏng file) | Pages |
| Trước khi gõ | — | TextEdit tự đổi dấu `"` thành `“ ”`, làm hỏng file `.json` và `secrets.env`. Mở file xong: menu *Edit > Substitutions* > bỏ tích *Smart Quotes*. Bỏ hẳn cho mọi file: *TextEdit > Settings* > tab *New Document* > bỏ tích *Smart quotes* |

Quy tắc khi điền `config/secrets.env`:

| Quy tắc | Đúng | Sai |
|---|---|---|
| Mỗi khoá một dòng, giá trị ngay sau dấu `=` | `GEMINI_API_KEY=AIzaSyA...` | `GEMINI_API_KEY: AIzaSyA...` |
| Dòng có giá trị **không** bắt đầu bằng `#` (dòng `#` là ghi chú, app bỏ qua) | `GEMINI_API_KEY=AIzaSyA...` | `# GEMINI_API_KEY=AIzaSyA...` |
| Tên khoá giữ nguyên như mẫu (chữ hoa, gạch dưới) | `TELEGRAM_CHAT_ID=987654321` | `telegram chat id=987654321` |
| Key Gemini điền vào dòng `GEMINI_API_KEY`, không điền vào dòng Claude | `GEMINI_API_KEY=AIza...` | `# ANTHROPIC_API_KEY=AIza...` |
| Tên file đúng `secrets.env` | `secrets.env` | `secrets.env.txt`, `secrets.env - Copy.example` |

Mẫu điền đúng và bảng các lỗi hay gặp khi dán (dấu cách, dấu nháy, chép thiếu): cuối mục 2.3. **Không gửi token, key, file `secrets.env` cho ai** (kể cả khi nhờ người hỗ trợ: gửi file kết quả `kiem_tra-*.txt`, file đó không chứa token/key).

### 2.2 Tạo bot Telegram

Mỗi người tạo **bot riêng**, không dùng chung bot (2 máy cùng một token thì Telegram báo lỗi 409 và bot ngừng nhận tin). Tạo bot miễn phí, mất khoảng 3 phút, làm trên điện thoại hay máy tính đều được.

| # | Làm gì | Màn hình thấy gì |
|---|---|---|
| 1 | Cài Telegram (điện thoại: App Store / CH Play; máy tính: https://desktop.telegram.org) và đăng nhập bằng số điện thoại của bạn | Danh sách chat |
| 2 | Bấm ô **tìm kiếm** (kính lúp) > gõ `BotFather` > chọn đúng **@BotFather** có **dấu tích xanh** cạnh tên. Có nhiều tài khoản giả tên gần giống, đừng chọn cái không có tích xanh | Trang giới thiệu của BotFather |
| 3 | Bấm **Start** (hoặc *Bắt đầu*) ở cuối màn hình | BotFather gửi một danh sách lệnh dài |
| 4 | Gõ `/newbot` > gửi | BotFather hỏi «Alright, a new bot. How are we going to call it? Please choose a name for your bot.» |
| 5 | Gõ **tên hiển thị** của bot, tiếng Việt có dấu được, ví dụ `Chíp tập trung` > gửi | BotFather hỏi «Good. Now let's choose a username for your bot. It must end in `bot`...» |
| 6 | Gõ **username**: chỉ chữ không dấu, số và dấu gạch dưới, **phải kết thúc bằng `bot`**, chưa ai dùng. Ví dụ `minh_taptrung_bot` > gửi. BotFather báo «Sorry, this username is already taken» thì thêm số, ví dụ `minh_taptrung_2026_bot` | BotFather trả «Done! Congratulations on your new bot...» |
| 7 | Trong tin «Done!» có dòng «Use this token to access the HTTP API:» và ngay dưới là **token**, dạng `123456789:AAH...` (một dãy số, dấu hai chấm, rồi khoảng 35 chữ và số). Chạm vào token để chép (điện thoại: chạm giữ > *Copy*) | Token đã nằm trong bộ nhớ tạm |
| 8 | Dán token vào dòng `TELEGRAM_BOT_TOKEN=` của `config/secrets.env` (mục 2.4 bước 4, mẫu điền đúng và các lỗi hay gặp ở cuối mục 2.3) | — |
| 9 | Chat ID (số định danh cuộc trò chuyện giữa bạn và bot) **chưa cần**: lấy ở mục 2.4 bước 5 bằng `start_tracker.bat` | — |

Lưu ý:

| Điều | Chi tiết |
|---|---|
| Token là **mật khẩu** của bot | Ai có token là điều khiển được bot. Không chụp màn hình gửi người khác, không dán vào nhóm chat |
| Lỡ để lộ token | Vào @BotFather > gõ `/revoke` > chọn bot > BotFather cấp token mới. Dán token mới vào `secrets.env` và khởi động lại tracker (mục 2.8). Token cũ hết tác dụng ngay |
| Quên token | @BotFather > `/mybots` > chọn bot > *API Token* |
| Đổi tên, ảnh đại diện bot | @BotFather > `/mybots` > chọn bot > *Edit Bot*. Không ảnh hưởng app |
| Ai nhắn được cho bot | Ai tìm ra username cũng nhắn được, nhưng bot **chỉ trả lời đúng chat ID đã điền**. Người lạ nhắn bị bỏ qua và ghi `REJECT_STRANGER` vào `data/audit.log` |
| Menu lệnh | Nút `/` trong ô chat: bot tự cài khi tracker chạy, không cần làm gì trong BotFather |

### 2.3 Key AI

Key AI là một chuỗi chữ để app được gọi AI thay bạn. **Không bắt buộc**: không có key app vẫn đo, vẫn nhắc, hiểu tin nhắn bằng từ khoá, câu khích lệ lấy từ danh sách có sẵn. Có key thì có thêm: hiểu tin nhắn tự nhiên, lời chào sáng, đánh giá cuối ngày, hỏi AI, đọc ảnh AS400.

**Lấy key Gemini (miễn phí, khuyên dùng)**

| # | Làm gì | Màn hình thấy gì |
|---|---|---|
| 1 | Trên máy tính, mở trình duyệt (Chrome, Edge), vào **https://aistudio.google.com/apikey** | Trang đăng nhập Google |
| 2 | Đăng nhập bằng tài khoản Gmail cá nhân. Tài khoản Google của công ty có thể bị chặn dùng AI Studio: gặp thông báo kiểu «not available» thì dùng Gmail cá nhân | Lần đầu: hộp thoại điều khoản sử dụng. Tích ô đồng ý > *Continue* |
| 3 | Bấm nút **Create API key** (hoặc *+ Create API key*). Hỏi chọn project thì chọn project có sẵn hoặc *Create API key in new project* | Hộp thoại hiện key dạng `AIzaSy...` (39 ký tự, bắt đầu bằng `AIza`) |
| 4 | Bấm **Copy** cạnh key. Đóng hộp thoại rồi vẫn xem lại được: key nằm trong danh sách ở trang đó, bấm vào để chép lại | Key đã nằm trong bộ nhớ tạm |
| 5 | Dán vào dòng `GEMINI_API_KEY=` của `config/secrets.env` (mục 2.4 bước 4) | — |

| Câu hỏi | Trả lời |
|---|---|
| Có mất tiền không? | Không, khi project **không** gắn thẻ thanh toán (billing). Hết lượt miễn phí thì Google báo lỗi 429, app tự đổi model hoặc dùng nội dung có sẵn tới hôm sau (mục 7.1). Đừng bật billing nếu không định trả tiền |
| Được bao nhiêu lượt? | Gói free khoảng 20 lượt/ngày **mỗi model**, app tự xoay nhiều model. Xem đã dùng bao nhiêu: nhắn `/aistatus` |
| Hỏi AI giá vàng, tin tức mà bot nói không tra web được | Gói free cho tra Google rất ít (có model không cho). App tự hỏi lại không tra web, AI sẽ nói rõ là không có số liệu mới (mục 4.17) |
| Lỡ để lộ key | Vào lại trang ở bước 1 > bấm vào key > *Delete* (xoá key) > tạo key mới, dán vào `secrets.env`, khởi động lại tracker |

**Key Claude (trả phí, không bắt buộc)**: https://console.anthropic.com/ > *API Keys* > *Create Key* > chép key dạng `sk-ant-...`. Trong `secrets.env` xoá dấu `#` ở đầu dòng `# ANTHROPIC_API_KEY=` rồi dán key ngay sau dấu `=`. `ai_provider: "auto"` (mặc định) dùng Gemini nếu có key Gemini, không thì Claude. Muốn ép dùng Claude: `"ai_provider": "claude"` trong `settings.json`.

**Mẫu `secrets.env` điền đúng** (số giả, chỉ để xem hình dạng):

```
TELEGRAM_BOT_TOKEN=123456789:AAHk3vZq_vi-du-token-gia
TELEGRAM_CHAT_ID=987654321
GEMINI_API_KEY=AIzaSyA1b2C3_vi-du-key-gia
# ANTHROPIC_API_KEY=
```

Mỗi dòng: **tên khoá**, dấu **`=`**, rồi **dán thẳng** giá trị. Không dấu nháy, không dấu cách, không xuống dòng giữa chừng.

**Lỗi hay gặp khi dán** (cột «App tự sửa?»: «Có» là app tự bỏ phần thừa và vẫn chạy, nhưng nên sửa cho gọn):

| Gõ sai | Ví dụ sai | Đúng | App tự sửa? |
|---|---|---|---|
| Dấu cách quanh dấu `=` hoặc cuối dòng | `TELEGRAM_BOT_TOKEN = 123456789:AAH...␣␣` | `TELEGRAM_BOT_TOKEN=123456789:AAH...` | Có |
| Bọc giá trị trong dấu nháy kép | `GEMINI_API_KEY="AIzaSyA1b2..."` | `GEMINI_API_KEY=AIzaSyA1b2...` | Có |
| Bọc trong dấu nháy đơn, ba dấu nháy | `GEMINI_API_KEY='AIzaSyA1b2...'`, `GEMINI_API_KEY='''AIzaSyA1b2...'''` | `GEMINI_API_KEY=AIzaSyA1b2...` | Có |
| Nháy cong `“ ”` `‘ ’` (dán qua Word, Notes, TextEdit trên Mac) | `TELEGRAM_CHAT_ID=“987654321”` | `TELEGRAM_CHAT_ID=987654321` | Có |
| Dấu nháy ngược (dán từ tin nhắn có định dạng code) | ``GEMINI_API_KEY=`AIzaSyA1b2...` `` | `GEMINI_API_KEY=AIzaSyA1b2...` | Có |
| Ghi chú cuối dòng sau dấu cách | `TELEGRAM_CHAT_ID=987654321   # chat của tôi` | Ghi chú để dòng riêng, bắt đầu bằng `#` | Có |
| Viết thường tên khoá | `gemini_api_key=AIzaSyA1b2...` | `GEMINI_API_KEY=AIzaSyA1b2...` | Có |
| Dấu cách **ở giữa** token / key (chép thiếu, xuống dòng) | `TELEGRAM_BOT_TOKEN=123456789: AAHk3vZq...`, `GEMINI_API_KEY=AIzaSy A1b2...` | Chép lại nguyên chuỗi, liền một mạch | **Không**: `kiem_tra_may` báo ✗ «không đúng dạng» / «có dấu cách ở giữa» |
| Chép thiếu đầu hoặc cuối token | `TELEGRAM_BOT_TOKEN=AAHk3vZq...` (mất phần số và dấu `:`) | Token có **đủ** phần số, dấu `:` và phần chữ | **Không**: báo ✗ «không đúng dạng (phải giống 123456789:AAH...)» |
| Dán cả câu của BotFather | `TELEGRAM_BOT_TOKEN=Use this token to access the HTTP API: 1234...` | Chỉ dán token | **Không**: báo ✗ |
| Dùng dấu `:` thay dấu `=` | `GEMINI_API_KEY: AIzaSyA1b2...` | `GEMINI_API_KEY=AIzaSyA1b2...` | **Không**: app coi như chưa điền |
| Để dấu `#` ở đầu dòng đã điền | `# GEMINI_API_KEY=AIzaSyA1b2...` | Xoá `#` | **Không**: dòng `#` là ghi chú |
| Key Gemini dán vào dòng Claude | `ANTHROPIC_API_KEY=AIzaSyA1b2...` | Dán vào dòng `GEMINI_API_KEY=` | **Không**: Claude báo key sai |
| Gõ chữ vào chat ID | `TELEGRAM_CHAT_ID=@minh_taptrung_bot` | Chat ID là **con số** bot gửi ở bước 5 | **Không**: báo ✗ «phải là một con số» |
| Tên file sai | `secrets.env.txt`, `secrets.env - Copy.example` | `secrets.env` (bật hiện đuôi file, mục 2.1) | **Không**: app không thấy file |

Điền xong, nhấp đúp `kiem_tra_may.bat` (Mac: `kiem_tra_may.command`): dòng nào sai sẽ hiện ✗ kèm cách sửa (mục 2.6). **Không gửi token, key, file `secrets.env` cho ai.**

### 2.4 Cài lần đầu trên Windows (từng bước)

Làm lần lượt 11 bước trong bảng «Các bước». Bước 4 – 7 là điền cấu hình: bảng ngay dưới đây cho biết file nào phải điền, file nào bỏ qua được, và cái gì bot tự lưu.

**Ba file cấu hình trong thư mục `config`**

| File | Bắt buộc? | Ai tạo, ai ghi | Chứa gì | Không có / để trống thì |
|---|---|---|---|---|
| `secrets.env` | **Bắt buộc** | **Bạn** tạo từ `secrets.env.example` (bước 4, 5). App chỉ đọc, không bao giờ tự ghi | Token bot, chat ID, key AI (bảng «Bước 4») | Không có bot, mà bot là cách duy nhất để dùng app |
| `persona.json` | **Bắt buộc** | **Bạn** tạo từ `persona.example.json` (bước 6). App chỉ đọc | Bạn là ai, bot gọi bạn thế nào, giọng văn (bảng «Bước 6») | App vẫn đo và nhắc, nhưng bot gọi chung chung «bạn», AI không biết tên, tuổi, hoàn cảnh nên khuyên chung chung. `kiem_tra_may` báo ✗ |
| `settings.json` | **Không bắt buộc**, đa số người bỏ qua | **Bạn** tạo khi cần đổi mặc định (bước 7). Lệnh `/giobot` cũng tự tạo / tự ghi 2 dòng giờ bật, tắt | Giờ làm, giờ trưa, mục tiêu, công việc gửi kèm AI... (bảng «Bước 7») | App dùng mặc định |

Sửa một trong 3 file trên lúc tracker đang chạy thì phải **khởi động lại tracker** mới có hiệu lực (mục 2.8, dòng «Khởi động lại tracker»), hoặc đợi tracker tự bật sáng hôm sau.

**Bot tự lưu gì (không cần sửa file)**

| Đổi bằng | Lưu ở đâu | Có hiệu lực | Quay về như trong file |
|---|---|---|---|
| `/nudge`, `/break`, `/water`, `/pace`, `/aireview`, `/autoenergy`, `/encourage`, `/kinhthanh`, `/style` | CSDL `data/focus.db`, **không** ghi vào file. Đè lên giá trị trong `settings.json` / `persona.json` | Ngay | Gõ lệnh kèm `mac_dinh`, ví dụ `/nudge mac_dinh`, `/style mac_dinh` |
| `/giobot 08:30 18:00` | Ghi vào `settings.json` (chưa có file thì tự tạo, bản cũ lưu `settings.json.bak`) và lịch tự bật của máy | Ngay | `/giobot mac_dinh` |
| Tên Telegram của bạn | CSDL. Bot tự lấy khi bạn nhắn; AI dùng tên này khi `persona.json` để trống `ten` | Ngay | — |
| Chat ID | **Không** tự ghi. Bot và cửa sổ đen chỉ in số ra, bạn chép vào `secrets.env` (bước 5) | — | — |

**Các bước**

| Bước | Làm gì | Thấy gì là đúng |
|---|---|---|
| **1. Cài Python** | Tải Python 3.9 trở lên từ https://www.python.org/downloads/windows/ (3.10 – 3.13 đều được). Chạy file cài, **tích ô «Add python.exe to PATH»** ở màn hình đầu, bấm *Install Now*. Gõ `python` mà Windows mở Microsoft Store: *Settings > Apps > Advanced app settings > App execution aliases*, tắt `python.exe` và `python3.exe` | Mở cmd, gõ `python --version` > hiện `Python 3.x.x` |
| **2. Chép thư mục app** | Chép thư mục `focus-tracker` vào chỗ cố định, ví dụ `C:\Users\<tên bạn>\Documents\focus-tracker\`. **Không** để trong thư mục OneDrive đang đồng bộ (CSDL dễ lỗi). Sau này đừng đổi chỗ thư mục; lỡ đổi thì làm lại bước 8 | — |
| **3. Bot Telegram và key AI** | Mục 2.2 và 2.3 | Có token bot, có key Gemini |
| **4. Tạo `secrets.env`** (bắt buộc) | Mở thư mục `config`. Chuột phải `secrets.env.example` > *Copy*, chuột phải chỗ trống > *Paste*: ra `secrets.env - Copy.example`. Chuột phải file mới > *Rename* (hoặc F2) > đặt tên đúng `secrets.env` > Enter > Windows hỏi đổi đuôi file > *Yes*. Mở `secrets.env` bằng Notepad, điền theo bảng «Bước 4» bên dưới, **để trống `TELEGRAM_CHAT_ID=`**, Ctrl+S | Trong `config` có file `secrets.env` (cột *Type*: *ENV File*, không phải *Text Document*) |
| **5. Lấy chat ID** | Nhấp đúp **`start_tracker.bat`**. Cửa sổ đen hiện khung «CHƯA CÓ TELEGRAM_CHAT_ID ... Đang chờ tin nhắn của bạn (tối đa 10 phút)». **Để nguyên cửa sổ**, mở Telegram, tìm bot (tên in trong khung) > *Start* (hoặc gõ `/start`) > gửi. Bot trả: «Chat ID của bạn là 987654321...». Cửa sổ đen cũng in to `CHAT ID CỦA BẠN LÀ: 987654321`. Mở `secrets.env` bằng Notepad, sửa thành `TELEGRAM_CHAT_ID=987654321`, Ctrl+S. Bấm phím bất kỳ để đóng cửa sổ đen. Bước này chạy được **mọi giờ, mọi ngày** (kể cả tối, cuối tuần) | Telegram có tin bot báo chat ID; `secrets.env` có đủ 3 dòng |
| **6. Tạo `persona.json`** (bắt buộc) | Trong `config`: chép `persona.example.json` thành `persona.json` (chép, dán, đổi tên như bước 4; Windows hỏi đổi đuôi > *Yes*). Mở `persona.json` bằng Notepad, điền theo bảng «Bước 6» bên dưới, Ctrl+S | Bước 9 có dòng `✓ config/persona.json: bot gọi bạn «...»` |
| **7. Xem có cần `settings.json` không** (thường bỏ qua) | Đọc bảng «Bước 7» bên dưới. Mặc định hợp với bạn thì **bỏ qua bước này**. Có dòng cần đổi (ví dụ giờ làm 08:30 – 17:30) thì tạo `settings.json` chỉ chứa các dòng đó | Không có file vẫn đúng |
| **8. Cài tự khởi động** | Nhấp đúp **`cai_tu_khoi_dong.bat`**. Script tìm Python, ghi đường dẫn vào `config\python_path.txt`, tạo task **FocusTracker** trong Task Scheduler (không cần quyền Admin). Cuối cùng hỏi «Chay tracker ngay bay gio? (y/n)»: gõ `y` > Enter (ngoài giờ chạy hay ngày nghỉ thì tracker tự thoát, không sao), rồi Enter để đóng | Dòng xanh «DA CAI XONG.» |
| **9. Kiểm tra toàn bộ** | **Mở VDI trước** (Citrix Desktop Viewer, đang kết nối). Nhấp đúp **`kiem_tra_may.bat`**, làm theo chữ trên màn hình khoảng 3 phút (mục 2.6). Trong lúc chạy cứ thao tác trong VDI để nó không tự ngắt | Cuối cửa sổ: `== TÓM TẮT ==` toàn ✓ |
| **10. Dùng** | Nhắn `/help` cho bot xem mọi lệnh, `/status` xem tình trạng. Từ giờ **chỉ dùng bot Telegram**; tracker tự bật 08:00 thứ 2 – thứ 6 | Bot trả lời, gọi bạn đúng như `goi_nguoi_dung` |
| **11. ⚠️ Chọn mức cảnh báo (làm ngay hôm đầu)** | Mặc định bot nhắc ở mức **vừa**. Đọc khung «Bước 11» ngay dưới bảng này, chọn mức hợp với bạn rồi gõ lệnh cho bot, ví dụ `/nudge nhe`. Đổi lại lúc nào cũng được, có hiệu lực ngay, không cần sửa file | Bot trả «Đã đổi mức nhắc khi sao nhãng: ...». Gõ `/nudge` không kèm gì để xem mức đang dùng |

> **⚠️ Bước 11: chọn mức cảnh báo khi sao nhãng (đừng bỏ qua)**
>
> Ngày đầu nhiều người thấy bot **nhắc nhiều quá** (hoặc quá ít) rồi tắt hẳn app. Hãy chọn mức trước khi bắt đầu làm. «Sao nhãng» = đang dùng phím / chuột mà VDI không ở trước (Chrome, Zalo, VDI thu nhỏ...), chỉ tính trong giờ làm.
>
> | Mức | Gõ cho bot | Bot nhắc khi nào | Hợp với ai |
> |---|---|---|---|
> | Tắt | `/nudge off` | Không nhắc sao nhãng. **Vẫn** nhắc rời máy, đứng dậy, tiến độ | Chỉ muốn xem số liệu cuối ngày |
> | Nhẹ | `/nudge nhe` | 1 lần mỗi ngày: lần đầu ở ngoài VDI từ 15 phút | Mới dùng, muốn làm quen trước |
> | **Vừa (mặc định)** | `/nudge vua` | Mỗi lần ở ngoài VDI từ 15 phút nhắc 1 lần (giờ vàng: 5 phút) | Đa số người |
> | Nghiêm | `/nudge nghiem` | Ra ngoài 5 phút là nhắc, còn ở ngoài thì 5 phút nhắc lại, kèm số lần sao nhãng và tổng phút đã mất, giọng gắt hơn | Muốn bị "ép" quay lại VDI |
>
> Nhắn tự nhiên cũng được: «nhắc nhẹ thôi», «nhắc nghiêm khắc hơn» (bot hỏi lại, bấm ✅ OK). Các nhắc khác chỉnh riêng: rời máy (`away_alert_minutes`, mặc định 15 phút), đứng dậy (`/break 45`, `/break off`), uống nước (mặc định **tắt**, bật bằng `/water on`), cảnh báo tiến độ (`/pace off`), lời khích lệ (`/encourage off`). Chi tiết từng mức và ví dụ một ngày: mục 4.3.

**Bước 4: điền `secrets.env`**

| Dòng | Là gì | Lấy ở đâu | Bắt buộc? |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN=` | Mã để app điều khiển bot riêng của bạn | @BotFather (mục 2.2) | Có |
| `TELEGRAM_CHAT_ID=` | Số định danh cuộc trò chuyện giữa bạn và bot. Bot chỉ trả lời đúng số này, người khác nhắn bị bỏ qua | Bước 5. Để trống tới lúc đó | Có |
| `GEMINI_API_KEY=` | Key gọi AI Gemini (gói free): hiểu tin nhắn tự nhiên, chào sáng, tổng kết, khích lệ, đọc ảnh AS400 | https://aistudio.google.com/apikey (mục 2.3) | Nên có. Không có thì app vẫn chạy nhưng không có AI |
| `# ANTHROPIC_API_KEY=` | Key AI Claude (trả phí) | https://console.anthropic.com/ | Không. Muốn dùng thì xoá dấu `#` đầu dòng rồi điền |

Sau khi điền xong bước 5 (số dưới đây là số giả):

```
TELEGRAM_BOT_TOKEN=123456789:AAH...(token của bạn)
TELEGRAM_CHAT_ID=987654321
GEMINI_API_KEY=AIzaSy...(key của bạn)
# ANTHROPIC_API_KEY=
```

Quy tắc điền (dấu `=`, dấu `#`, tên file đúng): mục 2.1. Mẫu điền đúng và các lỗi hay gặp khi dán: cuối mục 2.3.

**Bước 6: điền `persona.json`**

Nội dung file ngay sau khi chép từ mẫu:

```json
{
  "_huong_dan": "Copy file này thành persona.json rồi sửa. AI nhận các thông tin này mỗi lần gọi để trả lời hợp hoàn cảnh của bạn. giong: than_mat | vui_tuoi | hai_huoc | sep_kho_tinh. Để trống ten_sep nếu không muốn bot nhắc tới sếp. Nghề/hệ thống bạn làm ghi ở work_context trong settings.json.",
  "ten": "",
  "tuoi": "",
  "noi_song": "",
  "goi_nguoi_dung": "bạn",
  "bot_xung": "mình",
  "ten_sep": "",
  "giong": "than_mat",
  "mo_ta": ""
}
```

Chỉ sửa chữ **giữa hai dấu ngoặc kép bên phải** dấu `:`. Từng dòng:

| Khoá | Điền gì | Ví dụ | Bot / AI dùng vào đâu | Để trống thì |
|---|---|---|---|---|
| `_huong_dan` | Dòng ghi chú của file mẫu, không phải điền | — | App bỏ qua mọi khoá bắt đầu bằng `_` | Giữ hay xoá cả dòng đều được |
| `ten` | Tên bạn muốn được gọi | `"Minh"` | AI gọi tên trong lời chào sáng, tổng kết, khích lệ | AI dùng tên Telegram của bạn |
| `tuoi` | Tuổi | `"35"` | AI khuyên hợp tuổi (nghỉ ngơi, sức khoẻ, gia đình) | AI không biết tuổi |
| `noi_song` | Thành phố, nước | `"Singapore"`, `"TP.HCM, Việt Nam"` | Hỏi AI giá vàng, tỷ giá, thời tiết: AI tra đúng nơi | AI trả lời chung chung, có thể hỏi lại |
| `goi_nguoi_dung` | Bot gọi bạn là gì | `"bạn"`, `"anh"`, `"chị"`, `"bro"`, `"anh Minh"` | **Mọi** tin bot tự viết: chữ «bạn» được đổi thành từ này. AI cũng được dặn gọi như vậy | `"bạn"` |
| `bot_xung` | Bot tự xưng là gì | `"mình"`, `"em"`, `"tui"`, `"tôi"` | Như dòng trên, đổi chữ «mình» | `"mình"` |
| `ten_sep` | Tên sếp, để bot "doạ nhẹ" cho vui (tuỳ bạn) | `"anh Tuấn"` | Tin nhắc rời máy, tin nhắc ngoài VDI lặp lại (mức nghiêm) thêm một câu kiểu «anh Tuấn đang đi tuần đó, cẩn thận 👀». AI thỉnh thoảng nhắc tới | Bot không bao giờ nhắc sếp |
| `giong` | Một trong 4 giọng ở bảng dưới, gõ đúng chữ không dấu | `"hai_huoc"` | Giọng của mọi câu nhắc và câu AI viết | `"than_mat"`. Gõ sai chữ cũng dùng `than_mat`, `kiem_tra_may` báo `!` |
| `mo_ta` | Vài câu về bạn, **viết liền một dòng**: công việc, kinh nghiệm, gia đình, điều muốn cải thiện, niềm tin | `"Dev COBOL 8 năm, có 2 con nhỏ, hay bị điện thoại kéo đi đầu giờ chiều."` | Gửi kèm **mọi** lần gọi AI (tối đa 500 ký tự) để lời khuyên hợp hoàn cảnh | AI chỉ dựa vào số liệu tập trung |

| `giong` | Kiểu nói | Câu mẫu khi bạn làm ngoài VDI |
|---|---|---|
| `than_mat` | Thân mật, ấm áp như bạn thân | «Ê bạn, quay lại VDI thôi nào.» |
| `vui_tuoi` | Vui, nhiều năng lượng, có emoji | «Ối bạn ơi, VDI đang nhớ bạn kìa! 🏃» |
| `hai_huoc` | Dí dỏm, chọc nhẹ, không xúc phạm | «Bạn ơi, Chrome không trả lương cho bạn đâu nha 😄» |
| `sep_kho_tinh` | Ông sếp khó tính: ngắn, cộc, nghiêm, không emoji | «Tôi không trả lương cho việc ngồi ngoài VDI.» |

Đổi giọng sau này không cần sửa file: nhắn `/style hai_huoc` (mục 4.19). Nghề và hệ thống bạn làm thì ghi ở `work_context` (bước 7), không ghi ở đây.

> ⚠️ Mọi thông tin trong `persona.json` được gửi tới AI (Google hoặc Anthropic) mỗi lần gọi. Đừng ghi số điện thoại, địa chỉ nhà, mật khẩu hay thông tin nội bộ công ty.

Ví dụ đã điền đủ:

```json
{
  "ten": "Minh",
  "tuoi": "35",
  "noi_song": "Singapore",
  "goi_nguoi_dung": "anh",
  "bot_xung": "em",
  "ten_sep": "anh Tuấn",
  "giong": "vui_tuoi",
  "mo_ta": "Dev COBOL trên AS400 8 năm, có 2 con nhỏ, hay bị điện thoại kéo đi đầu giờ chiều."
}
```

**Quy tắc viết file `.json`** (`persona.json` và `settings.json`):

| Quy tắc | Đúng | Sai |
|---|---|---|
| Chữ đặt giữa hai dấu ngoặc kép thẳng `"` | `"ten": "Minh",` | `"ten": Minh,` |
| Mỗi dòng kết thúc bằng dấu phẩy, **trừ dòng cuối** ngay trước dấu `}` | `"giong": "vui_tuoi",` rồi dòng cuối `"mo_ta": "..."` | Dòng cuối `"mo_ta": "...",` rồi tới `}` |
| Giữ nguyên tên khoá bên trái dấu `:` | `"goi_nguoi_dung": "anh",` | `"gọi người dùng": "anh",` |
| Giữ dấu `{` ở đầu file và `}` ở cuối file | `{` ... `}` | Xoá mất `{` hoặc `}` |
| Trong giá trị không dùng dấu `"`; cần trích thì dùng « » | `"mo_ta": "Hay nói «để mai tính»"` | `"mo_ta": "Hay nói "để mai tính""` |
| Giá trị viết liền một dòng | `"mo_ta": "Câu 1. Câu 2."` | Bấm Enter giữa câu 1 và câu 2 |
| Lưu dạng UTF-8 để giữ chữ có dấu | Notepad Windows 10/11: Ctrl+S, góc dưới bên phải hiện `UTF-8` (hoặc `UTF-8 with BOM`) | Hiện `ANSI`: *File > Save As* > ô *Encoding* chọn `UTF-8` > *Save* |

Kiểm tra: ở bước 9 (sau này sửa lại thì chạy `kiem_tra_may.bat check`, mục 2.1 «Chạy kèm chữ phía sau»), phần «Cấu hình» có:

| Thấy | Nghĩa là | Làm gì |
|---|---|---|
| `✓ config/persona.json: bot gọi bạn «anh», tự xưng «em», giọng vui_tuoi, tên Minh, sếp anh Tuấn` | Đọc được, đúng như bạn điền | Không cần làm gì |
| `! Chưa điền: tuoi, noi_song, mo_ta` | Vẫn chạy, chỉ là AI biết ít về bạn | Điền thêm nếu muốn |
| `! Khoá lạ (gõ sai tên?), app bỏ qua: ten_sepp` | Gõ sai tên khoá, dòng đó không có tác dụng | Sửa đúng tên như bảng trên |
| `✗ Chưa có config/persona.json` | Chưa chép file, hoặc đặt tên sai (ví dụ `persona.json.txt`) | Làm lại bước 6, bật hiện đuôi file (mục 2.1) |
| `✗ config/persona.json sai cú pháp JSON ở dòng 5, cột 3 (thiếu dấu phẩy cuối dòng trước)` | File sai quy tắc ở bảng trên; app **bỏ qua cả file** | Mở file, sửa đúng chỗ được nêu (lỗi thiếu dấu phẩy thường nằm ở dòng ngay trên), lưu, chạy lại `check` |

**Bước 7: có cần `settings.json` không?**

Không có `settings.json` thì app dùng mặc định dưới đây. Việc nào đổi được bằng lệnh bot thì không cần file.

| Việc | Mặc định | Đổi bằng lệnh bot | Đổi bằng `settings.json` (khoá) |
|---|---|---|---|
| Giờ làm (chỉ nhắc trong giờ này) | 08:00 – 17:00 | — | `work_start`, `work_end` |
| Nghỉ trưa (không nhắc, không tính) | 11:15 – 12:30 | — | `lunch_start`, `lunch_end` |
| Tracker tự bật / tự tắt, thứ 2 – thứ 6 | 08:00 / 23:59 | `/giobot 08:30 18:00` | `auto_start_at`, `auto_stop_at` |
| Mục tiêu tập trung sâu mỗi ngày | 4 giờ | — | `daily_focus_goal_hours` |
| Mục tiêu giờ làm trong VDI (cảnh báo tiến độ 10:30, 14:00, 15:30) | 6 giờ | `/pace on`, `/pace off` (bật, tắt) | `pace_target_vdi_hours` |
| Công việc của bạn, gửi kèm **mọi** lần gọi AI | Lập trình viên/BA Life Asia trên IBM i (AS400), COBOL, CL, DB2 for i, làm qua VDI Citrix | — | `work_context` |
| Lời khích lệ đầu ngày, buổi chiều (xem khung ngay dưới bảng này) | Châm ngôn danh nhân, hiền triết + vì gia đình (**Kinh Thánh tắt**) | `/kinhthanh` (đổi qua lại Kinh Thánh / danh ngôn), `/encourage quote`, `/encourage off` | `encouragement_styles`, `encouragement_enabled` |
| Mức nhắc khi sao nhãng (**bước 11**) | Vừa | `/nudge nhe`, `/nudge nghiem`, `/nudge off` | `nudge_level` |
| Nhắc rời máy | Sau 15 phút | — | `away_alert_minutes` |
| Nhắc đứng dậy | Mỗi 60 phút | `/break 45`, `/break off` | `break_reminder_minutes`, `break_reminder_enabled` |
| Nhắc uống nước | **Tắt** (cài lần đầu) | `/water on`, `/water 45` | `water_reminder_enabled`, `water_reminder_minutes` |
| Hỏi tổng kết, tổng kết ngày, tổng kết tuần | 16:45, 17:00, thứ 6 16:50 | — | `review_prompt_at`, `daily_summary_at`, `weekly_report_day`, `weekly_report_at` |
| AI tự đánh giá cuối ngày, cuối tuần | Bật | `/aireview off` | `ai_review_enabled` |
| Nghỉ phép | — | `/leave` (nửa ngày hoặc cả ngày) | `extra_off_days` (ngày nghỉ cố định, ví dụ `["2026-12-24"]`) |

**Lời chào sáng và lời khích lệ: cài lần đầu thì Kinh Thánh TẮT.** Bot tự gửi 2 tin mỗi ngày (lời chào lần đầu dùng máy sau 08:00, lời khích lệ 14:30) và thỉnh thoảng thêm một câu vào cuối tin nhắc. Cài xong **không đổi gì thì mọi câu đó là châm ngôn của người thành đạt, danh nhân, hiền triết xưa** (và câu vì gia đình), không có câu Kinh Thánh nào. Ai theo đạo Tin Lành muốn nhận câu Kinh Thánh, hoặc muốn đổi kiểu khác, chọn một trong các cách sau (cách 1 và 2 không cần sửa file, đổi có hiệu lực ngay, gõ cho bot trên Telegram):

| Muốn | Gõ cho bot | Kết quả |
|---|---|---|
| 1. Dùng danh ngôn, không Kinh Thánh (**mặc định khi cài**) | Không cần làm gì; đã bật Kinh Thánh rồi muốn tắt lại: `/kinhthanh off` (hoặc `/encourage quote`) | Mọi tin (lời chào, lời khích lệ, câu kèm tin nhắc, AI đánh giá ngày / tuần) chỉ dùng châm ngôn của người thành đạt, danh nhân, nhà hiền triết xưa (Khổng Tử, Mạnh Tử, Lão Tử, Seneca, Marcus Aurelius, Edison...) và câu vì gia đình. Không còn câu Kinh Thánh nào, trừ khi bạn tự xin `/bible` |
| 1b. Bật Kinh Thánh | `/kinhthanh on` (gõ `/kinhthanh` không kèm gì thì đảo qua lại) | Chỉ câu Kinh Thánh Tin Lành |
| 2. Không muốn nhận lời khích lệ nào | `/encourage off` (bật lại `/encourage on`) | Hết cả lời chào kiểu khích lệ lẫn tin 14:30. Tin tổng kết, nhắc việc vẫn gửi |
| 3. Cài sẵn từ đầu bằng file | Thêm vào `settings.json`: `"encouragement_styles": ["bible"]` (Kinh Thánh) hoặc `"encouragement_enabled": false` (tắt hẳn) | Là mặc định mới; lệnh bot ở trên vẫn đè lên được. `/encourage mac_dinh` quay về giá trị trong file |
| 4. Đổi giờ tin buổi chiều, hoặc tắt riêng tin đó | `"afternoon_boost_at": "15:00"` hoặc `""` trong `settings.json` | Chỉ tin chiều |

Chi tiết từng chế độ: mục 4.8.

```
Giờ làm, giờ trưa, mục tiêu 4 giờ, work_context ở bảng trên đúng với bạn?
   |
   |-- ĐÚNG HẾT --> bỏ qua bước 7, không tạo settings.json
   |
   |-- CÓ DÒNG KHÁC --> tạo config\settings.json chỉ chứa các dòng cần đổi
```

Tạo trên Windows: trong `config`, chuột phải chỗ trống > *New* > *Text Document* > đặt tên `settings.json` > Enter > *Yes*. Mở bằng Notepad, gõ theo mẫu dưới (chỉ giữ dòng bạn cần đổi), Ctrl+S:

```json
{
  "work_start": "08:30",
  "work_end": "17:30",
  "daily_focus_goal_hours": 5,
  "work_context": "Tester hệ thống Life Asia trên AS400: viết test case, chạy batch, đối soát dữ liệu hợp đồng; làm qua VDI Citrix."
}
```

| Lưu ý | |
|---|---|
| **Không** chép nguyên `settings.example.json` thành `settings.json` | File mẫu có mọi khoá. Chép nguyên thì bản app mới đổi mặc định bạn cũng không được hưởng. Chỉ ghi dòng cần đổi |
| Giờ viết `"HH:MM"` trong ngoặc kép; số và `true` / `false` **không** có ngoặc kép | `"work_start": "08:30"`, `"daily_focus_goal_hours": 5`, `"vdi_closed_alert": false` |
| Quy tắc dấu phẩy, ngoặc kép, UTF-8 | Như bảng «Quy tắc viết file `.json`» ở bước 6 |
| Gõ sai tên khoá | App bỏ qua dòng đó và nhắn báo qua Telegram lúc khởi động |
| Giá trị sai (giờ `8h30`, số âm, JSON lỗi) | App báo lỗi rõ lúc khởi động, ghi `data/logs/config-error.txt`, nhắn Telegram nếu gửi được (mục 2.10) |
| Ý nghĩa mọi khoá | Mục 11.1 |

**Thứ tự cài lần đầu (Windows)**

```
Cài Python 3.9+ (tích "Add python.exe to PATH")
   |
   v
Chép thư mục focus-tracker vào Documents (không để trong OneDrive)
   |
   v
@BotFather -> có TOKEN bot ;  aistudio.google.com -> có KEY Gemini
   |
   v
config\secrets.env.example  --chép, đổi tên-->  config\secrets.env
điền TELEGRAM_BOT_TOKEN, GEMINI_API_KEY ; để trống TELEGRAM_CHAT_ID
   |
   v
Nhấp đúp start_tracker.bat  (cửa sổ báo "Đang chờ tin nhắn")
   |
   v
Telegram: nhắn /start cho bot  ->  bot trả "Chat ID của bạn là 987654321"
   |
   v
Điền TELEGRAM_CHAT_ID=987654321 vào secrets.env, lưu, đóng cửa sổ đen
   |
   v
config\persona.example.json  --chép, đổi tên-->  config\persona.json
điền ten, tuoi, noi_song, goi_nguoi_dung, bot_xung, ten_sep, giong, mo_ta
   |
   v
Mặc định ở bảng "Bước 7" hợp với bạn?
   |-- CÓ --> bỏ qua settings.json
   |-- KHÔNG --> tạo config\settings.json chỉ với các dòng cần đổi
   |
   v
Nhấp đúp cai_tu_khoi_dong.bat  ->  "Chay tracker ngay bay gio? (y/n)" gõ y
   |
   v
Mở VDI, nhấp đúp kiem_tra_may.bat, làm theo hướng dẫn (~3 phút)
   |
   v
== TÓM TẮT == toàn ✓ ?
   |-- KHÔNG --> đọc dòng ✗, sửa theo gợi ý, chạy lại đúng phần lỗi
   |             (ví dụ kiem_tra_may.bat check) rồi quay lại ô "TÓM TẮT"
   |-- CÓ
   |
   v
⚠️ Chọn mức cảnh báo (bước 11): gõ cho bot /nudge off | nhe | vua | nghiem
   |
   v
Xong. Từ giờ chỉ dùng bot Telegram. HẾT
```

### 2.5 Cài lần đầu trên Mac (từng bước)

Ba file cấu hình, cái nào bắt buộc, bot tự lưu gì: như đầu mục 2.4. Ý nghĩa từng dòng trong file: các bảng «Bước 4», «Bước 6», «Bước 7» ở mục 2.4.

| Bước | Làm gì | Thấy gì là đúng |
|---|---|---|
| **1. Cài Python** | Tải bản macOS từ https://www.python.org/downloads/macos/ và cài. Sau đó mở *Applications > Python 3.x*, nhấp đúp **`Install Certificates.command`** (cài chứng chỉ gốc cho HTTPS. App vẫn tự dùng chứng chỉ có sẵn của macOS nếu thiếu bước này, nhưng nên làm cho chắc). Có Homebrew thì `brew install python` cũng được. Đừng dùng `/usr/bin/python3` của Apple khi chưa cài Command Line Tools | Terminal: `python3 --version` > `Python 3.x.x` |
| **2. Chép thư mục app** | Vào **thư mục nhà**: Finder > *Go* > *Home*, chép thư mục app vào đó thành `~/focus-tracker`. **Không** để trong Documents, Desktop, Downloads hay iCloud Drive: macOS chặn tracker tự chạy nền đọc các thư mục đó (chạy tay vẫn được nên khó nhận ra; `cai_tu_khoi_dong.command` sẽ cảnh báo). Mở Terminal, `cd ~/focus-tracker`, gõ `chmod +x *.command *.sh` > Enter (file chép từ Windows, tải từ GitHub hoặc file nén thường mất quyền chạy) | — |
| **3. Bot Telegram và key AI** | Mục 2.2 và 2.3 | — |
| **4. Tạo `secrets.env`** (bắt buộc) | Trong `config`: chọn `secrets.env.example` > Cmd+D (nhân bản) > đổi tên thành `secrets.env` (Finder hỏi đổi đuôi > *Use .env*). Mở bằng TextEdit, điền token và key theo bảng «Bước 4» mục 2.4, để trống `TELEGRAM_CHAT_ID=`, Cmd+S | — |
| **5. Lấy chat ID** | Nhấp đúp **`start_tracker.command`**, nhắn `/start` cho bot, điền số bot trả vào `TELEGRAM_CHAT_ID=`, lưu, Enter để đóng Terminal. Như Windows bước 5 | Bot báo chat ID |
| **6. Tạo `persona.json`** (bắt buộc) | Trong `config`: chọn `persona.example.json` > Cmd+D > đổi tên thành `persona.json`. Mở bằng TextEdit, **tắt Smart Quotes trước khi gõ** (mục 2.1, bảng «Sửa file cấu hình»), điền theo bảng «Bước 6» mục 2.4, Cmd+S | Bước 9 có dòng `✓ config/persona.json` |
| **7. Xem có cần `settings.json` không** (thường bỏ qua) | Bảng «Bước 7» mục 2.4. Cần đổi thì: chọn `persona.example.json` > Cmd+D > đổi tên thành `settings.json` > mở bằng TextEdit > Cmd+A, xoá hết > gõ các dòng cần đổi theo mẫu ở bước 7 > Cmd+S (nhân bản file `.json` có sẵn để TextEdit mở dạng chữ thường, không thành file định dạng) | Không có file vẫn đúng |
| **8. Cài tự khởi động** | Nhấp đúp **`cai_tu_khoi_dong.command`** (gọi `cai_tu_khoi_dong_mac.sh`): ghi file `~/Library/LaunchAgents/com.focustracker.agent.plist`, nạp vào launchd, tracker chạy luôn. macOS 13 trở lên có thể hiện thông báo «Background Items Added»: để nguyên, **đừng** tắt Python / python3 trong *System Settings > General > Login Items > Allow in the Background* | «ĐÃ CÀI XONG» |
| **9. Kiểm tra toàn bộ** | Mở Citrix Viewer, nhấp đúp **`kiem_tra_may.command`** (mục 2.6) | `== TÓM TẮT ==` toàn ✓ |
| **10. Dùng** | Như Windows bước 10 | Bot trả lời |
| **11. ⚠️ Chọn mức cảnh báo (làm ngay hôm đầu)** | Như Windows bước 11: đọc khung «Bước 11» mục 2.4, gõ `/nudge off`, `/nudge nhe`, `/nudge vua` hoặc `/nudge nghiem` | Bot báo đã đổi mức |

App trên Mac **không cần cấp quyền gì** khi dùng app Citrix (nhận cửa sổ «Citrix Viewer» theo tên app, không cần đọc tiêu đề). Chỉ khi mở VDI bằng trình duyệt mới cần quyền *Screen Recording* để đọc tiêu đề tab: tracker tự hiện hộp thoại macOS xin quyền cho **Python** (bản chạy nền) lúc khởi động, bấm cho phép trong *System Settings > Privacy & Security > Screen Recording* rồi chạy lại tracker; chạy bằng `start_tracker.command` thì quyền thuộc về **Terminal**. `/status` ghi rõ đường dẫn chương trình cần bật (mục 4.2).

### 2.6 Kiểm tra máy: `kiem_tra_may.bat` (Windows) và `kiem_tra_may.command` (Mac)

Hai file làm cùng một việc (gọi `python focus_tracker.py verify`) nhưng viết riêng cho từng hệ điều hành, vì cách tìm Python, cách báo hiệu và cách tự khởi động khác nhau. **Windows chỉ chạy `.bat`, Mac chỉ chạy `.command`**; nhấp nhầm file của hệ kia sẽ không chạy.

| | `kiem_tra_may.bat` (Windows) | `kiem_tra_may.command` (Mac) |
|---|---|---|
| Chạy đủ | Nhấp đúp | Nhấp đúp |
| Chạy một phần | cmd trong thư mục app: `kiem_tra_may.bat vdi` (mục 2.1) | Terminal trong thư mục app: `./kiem_tra_may.command vdi` |
| Chạy 2 phần AI + VDI | Nhấp đúp `kiem_tra_ai_vdi.bat` | Nhấp đúp `kiem_tra_ai_vdi.command` |
| Tìm Python | `config\python_path.cmd` (do `cai_tu_khoi_dong.ps1` tạo) > `py -3` > `python` | `config/python_path.txt` > python.org > Homebrew > `python3` |
| Phần `autostart` xem | Task **FocusTracker** trong Task Scheduler (lần chạy tới, kết quả lần trước) | File plist trong `~/Library/LaunchAgents` và `launchctl print gui/<uid>/com.focustracker.agent` (launchd đã nạp job chưa) |
| Báo chuyển bước (phần `vdi`) | Tiếng bíp | Tiếng chuông Terminal |
| Thao tác ở phần `vdi` | Thu nhỏ bằng nút `_` xuống taskbar | Thu nhỏ bằng nút vàng xuống Dock |

**Các phần** (gõ một hoặc nhiều tên sau tên file, cách nhau dấu cách; không gõ gì = chạy đủ theo thứ tự dưới):

| Phần | Làm gì | Cần trước | Lâu |
|---|---|---|---|
| `check` | Đọc cấu hình, thử đọc trạng thái máy, kiểm tra token Telegram (`getMe`), có chat ID chưa, **gửi 1 tin thử** «✅ Kiểm tra máy: bot gửi tin được.», có key AI chưa, đọc `persona.json` (thiếu file hay sai cú pháp là ✗, mục 2.4 bước 6) | `secrets.env` đã điền đủ | vài giây |
| `ai` | Liệt kê model Gemini mà key dùng được, gọi thử 1 câu (tốn 1 lượt free). Gọi lỗi thì tự thử 4 dạng yêu cầu nhỏ để biết Google từ chối phần nào | `GEMINI_API_KEY` | khoảng 10 giây |
| `mom` | Tải trang lịch lễ MOM Singapore, in ngày lễ từng năm đọc được, so với lịch app đang dùng | Có mạng | vài giây |
| `autostart` | Như bảng trên | Đã chạy `cai_tu_khoi_dong` | vài giây |
| `vdi` | 4 bước có hướng dẫn: (1) phóng to VDI và gõ trong VDI, (2) thu nhỏ VDI, (3) mở VDI cỡ vừa vừa và gõ trong VDI, (4) bấm sang app khác. Mỗi bước 20 – 25 giây; đạt khi 4 lần đo cuối của bước đều đúng. Gặp cửa sổ Citrix lạ thì ghi lại chi tiết để chẩn đoán (mục 4.2) | VDI **đang mở và đang kết nối** | khoảng 1,5 phút |
| `tests` | Chạy bộ test tự động của app | — | dưới 1 phút |

| Câu hỏi | Trả lời |
|---|---|
| Kết quả nằm đâu? | Trên màn hình và trong `data\logs\kiem_tra-YYYYMMDD-HHMMSS.txt` (không chứa token/key). Nhờ người hỗ trợ thì gửi file này |
| Chạy lúc nào? | (1) Lần cài đầu, sau `cai_tu_khoi_dong` (bước 9 mục 2.4). (2) Sau khi Citrix Workspace cập nhật bản mới: chạy phần `vdi`. (3) Sau khi đổi `secrets.env`: `check ai`; sau khi sửa `persona.json`: `check`. (4) Bot báo sai trạng thái VDI (đang làm mà bảo ngoài VDI): `vdi`. (5) Bot không trả lời: `check`. (6) Sau khi chép bản app mới: chạy đủ. (7) Đầu tháng 12, xem MOM đã có lịch năm sau chưa: `mom` |
| Thứ tự so với các file khác? | Sau `secrets.env` + chat ID (`start_tracker`) + `persona.json` + `cai_tu_khoi_dong`. Trước đó chạy cũng được, chỉ là phần `check` báo thiếu chat ID và phần `autostart` báo ✗. Sau khi cài xong thì chạy lúc nào cũng được, **không cần tắt tracker** (kiểm tra không đọc tin nhắn của bot nên không tranh với tracker) |
| VDI tự ngắt giữa chừng? | Citrix tự ngắt phiên khi không thao tác khoảng 10 – 15 phút (tuỳ máy). Trước khi chạy phần `vdi`, bấm vào VDI cho phiên còn kết nối; bước 1 báo «không thấy cửa sổ» thì thường là VDI vừa tự ngắt: mở lại VDI, chạy lại `kiem_tra_may.bat vdi` |
| Phần không có? | Gõ sai tên phần (ví dụ `kiem_tra_may.bat vdl`): báo «Phần không có» và danh sách phần đúng |

### 2.7 Mọi file và thư mục trong app

**File bạn nhấp đúp** (mỗi việc có 2 file: `.bat` cho Windows, `.command` cho Mac):

| Windows | Mac | Làm gì | Chạy khi nào |
|---|---|---|---|
| `start_tracker.bat` | `start_tracker.command` | Chạy tracker **có cửa sổ** để xem log trực tiếp. Chưa có `TELEGRAM_CHAT_ID` thì chuyển sang chế độ **lấy chat ID** (chạy mọi giờ, mọi ngày, chờ tối đa 10 phút). Đây là bạn tự bật nên ngày nghỉ vẫn chạy, chỉ ghi giờ làm bù trong VDI; đóng cửa sổ là tắt tracker | Lần cài đầu (lấy chat ID). Khi cần xem log lúc tracker chạy: **tắt bản chạy ẩn trước** (mục 2.8), nếu không bản này chờ 2 phút rồi tự thoát vì đã có tracker đang chạy |
| `cai_tu_khoi_dong.bat` | `cai_tu_khoi_dong.command` | Cài tự khởi động: thứ 2 – thứ 6 lúc `auto_start_at` (mặc định 08:00), lúc đăng nhập và (Windows) lúc máy thức dậy. Không cần quyền Admin | Lần cài đầu. Chạy lại khi: đổi Python, dời thư mục app, `/giobot` báo chưa sửa được giờ tự bật |
| `go_tu_khoi_dong.bat` | `go_tu_khoi_dong.command` | Gỡ tự khởi động **và tắt tracker đang chạy**. Dữ liệu trong `data` giữ nguyên | Khi không dùng app nữa, hoặc trước khi dời thư mục app |
| `kiem_tra_may.bat` | `kiem_tra_may.command` | Kiểm tra toàn bộ trên máy thật, chạy được từng phần (mục 2.6) | Mục 2.6 |
| `kiem_tra_ai_vdi.bat` | `kiem_tra_ai_vdi.command` | Gọi `kiem_tra_may` với 2 phần `ai vdi`, khỏi phải gõ lệnh | Sau khi đổi key AI hoặc Citrix cập nhật |
| `xem_cpu_ram.bat` | `xem_cpu_ram.command` | Đo tracker đang dùng bao nhiêu CPU, RAM trong 10 giây (mục 4.18) | **Khi tracker đang chạy** (thứ 2 – thứ 6 sau giờ tự bật). Ngoài giờ sẽ báo «Tracker chưa chạy.» |
| `lam_bu_ngoai_gio.bat` | `lam_bu_ngoai_gio.command` | Bật tracker **chạy ẩn** ở chế độ bạn tự bật (`run --manual`): ngày nghỉ (thứ 7, CN, lễ, `/off`) vẫn chạy, bật trước giờ tự bật cũng được. Ngày nghỉ / ngoài giờ chỉ ghi giờ làm trong VDI, không nhắc, không tính sao nhãng. Tự tắt lúc `auto_stop_at` (23:59) | Muốn làm bù cuối tuần, ngày lễ, hoặc làm sớm trước 08:00. Tracker đang chạy rồi thì bản mới tự thoát |
| `bao_cao_hom_nay.bat` | `bao_cao_hom_nay.command` | Tạo báo cáo HTML hôm nay trong thư mục `reports` và **mở bằng trình duyệt** | Muốn xem báo cáo chi tiết trên máy (qua Telegram thì nhắn `/report`) |

**File app tự dùng** (không cần mở):

| File | Là gì |
|---|---|
| `focus_tracker.py` | Điểm vào của mọi lệnh (`run`, `check`, `probe`, `verify`, `report`...). Các file `.bat` / `.command` đều gọi file này |
| `start_tracker.vbs` | (Windows) Task Scheduler gọi file này để chạy tracker **ẩn**, không cửa sổ. Không tìm thấy Python thì ghi `data\logs\launcher-error.txt`. Nhấp đúp cũng được: chạy ẩn, không thấy gì |
| `cai_tu_khoi_dong.ps1`, `go_tu_khoi_dong.ps1` | (Windows) Script PowerShell thật làm việc cài / gỡ. `cai_tu_khoi_dong.bat` / `go_tu_khoi_dong.bat` gọi chúng với `-ExecutionPolicy Bypass` (chỉ cho lần chạy đó) nên không bị hỏi. Chuột phải > *Run with PowerShell* cũng được (mục 2.1) |
| `cai_tu_khoi_dong_mac.sh` | (Mac) Script cài / gỡ launchd thật. `cai_tu_khoi_dong.command` gọi nó; `go_tu_khoi_dong.command` gọi nó với `--go` |
| `requirements.txt` | Ghi chú: app chỉ dùng thư viện có sẵn của Python, **không cần `pip install`** |
| `README.md` | Tài liệu này |
| `Y_TUONG_TAP_TRUNG.md` | Ý tưởng giữ tập trung: thói quen làm ngay, tính năng đã có, ý tưởng chưa làm, ý tưởng đã bỏ |
| `.gitignore` | Dùng khi đưa code lên GitHub: liệt kê file **không bao giờ** đưa lên (`config/secrets.env`, `settings.json`, `persona.json`, `data/`, `reports/`...). Tên bắt đầu bằng dấu chấm nên Mac ẩn đi (Finder: `Cmd+Shift+.` để hiện) |
| `.gitattributes` | Dùng khi đưa code lên GitHub: giữ kiểu xuống dòng đúng cho `.bat` (Windows) và `.command` (Mac) khi tải code về |

**Thư mục**

| Thư mục / file | Có sẵn hay app tạo | Là gì |
|---|---|---|
| `config/secrets.env.example` | Có sẵn | Mẫu. Chép thành `secrets.env` |
| `config/secrets.env` | **Bạn tạo** (bắt buộc) | Token bot, chat ID, key AI (mục 2.4 bước 4, mục 11.2). Không chia sẻ |
| `config/persona.example.json` | Có sẵn | Mẫu cách bot gọi bạn, thông tin về bạn, tên sếp, giọng văn |
| `config/persona.json` | **Bạn tạo** (bắt buộc) | Chép từ mẫu trên rồi điền (mục 2.4 bước 6, mục 11.3). App chỉ đọc; `/style` đổi giọng lưu trong CSDL, không sửa file này |
| `config/settings.example.json` | Có sẵn | Mẫu có mọi tuỳ chọn với giá trị mặc định. Chỉ để tra, **không** chép nguyên thành `settings.json` |
| `config/settings.json` | Bạn tạo nếu cần (không bắt buộc); `/giobot` cũng tự tạo | Chỉ chứa các dòng muốn khác mặc định (mục 2.4 bước 7, mục 11.1). Không có file thì dùng mặc định |
| `config/python_path.txt`, `config/python_path.cmd` | `cai_tu_khoi_dong` tạo | Python dùng để chạy tracker. Đổi Python thì chạy lại `cai_tu_khoi_dong` |
| `config/settings.json.bak` | `/giobot` tạo | Bản sao trước khi bot sửa giờ bật/tắt |
| `data/` | App tạo | CSDL `focus.db`, log, bản sao lưu, lịch lễ đã tải (mục 8, 9, 10). App tự dọn file cũ |
| `reports/` | App tạo | Báo cáo HTML từng ngày, tự xoá sau 30 ngày |
| `sample/bao-cao-mau.html` | Có sẵn | Báo cáo mẫu từ dữ liệu giả, mở bằng trình duyệt để xem trước |
| `focus/` | Có sẵn | Mã nguồn app, mỗi tính năng một file (mục 14.1). Không cần mở |
| `tests/` | Có sẵn | Bộ test tự động (phần `tests` của `kiem_tra_may`) |

### 2.8 Khi nào chạy file nào

| Tình huống | Làm gì |
|---|---|
| Ngày làm việc bình thường | Không chạy file nào. Tracker tự bật 08:00, mọi thứ qua bot Telegram |
| Làm bù thứ 7, CN, ngày lễ, hoặc làm trước 08:00 | Nhấp đúp `lam_bu_ngoai_gio.bat` (Mac `.command`) trước khi làm. Bot nhắn xác nhận (ngày nghỉ). Xong việc không cần tắt (tự tắt 23:59), muốn tắt sớm thì làm như dòng «Muốn xem log trực tiếp» (*End task*) |
| Muốn xem log trực tiếp | Tắt bản chạy ẩn: Ctrl+Shift+Esc > tab *Details* > `python.exe` (chuột phải tiêu đề cột > *Select columns* > *Command line* để thấy dòng `focus_tracker.py run`) > *End task*. Rồi nhấp đúp `start_tracker.bat`. Xong thì đóng cửa sổ; mai 08:00 tự chạy ẩn lại. Hoặc mở file `data\logs\focus.log` bằng Notepad (không cần tắt gì) |
| Xem tracker tốn bao nhiêu máy | Trong giờ chạy: nhấp đúp `xem_cpu_ram.bat` (Mac `.command`), hoặc nhắn `/perf` |
| Xem báo cáo trên máy | `bao_cao_hom_nay.bat`, hoặc nhắn `/report` |
| Đổi giờ tự bật / tắt | Nhắn `/giobot` cho bot, không cần chạy lại file cài |
| Đổi token / key / chat ID | Sửa `secrets.env`, rồi chạy `kiem_tra_may.bat check ai`, rồi khởi động lại tracker (dòng dưới) |
| Sửa `persona.json` / `settings.json` | Lưu file, chạy `kiem_tra_may.bat check` (báo lỗi cú pháp nếu có), rồi khởi động lại tracker (dòng dưới) |
| Khởi động lại tracker (để đọc lại file cấu hình) | Ctrl+Shift+Esc > tab *Details* > `python.exe` > *End task* (như dòng «Muốn xem log trực tiếp»), rồi nhấp đúp `start_tracker.vbs` (chạy ẩn) hoặc `start_tracker.bat` (có cửa sổ). Không gấp thì đợi tracker tự bật sáng hôm sau. Mac: nhấp đúp `go_tu_khoi_dong.command` rồi `cai_tu_khoi_dong.command` |
| Citrix Workspace vừa cập nhật | `kiem_tra_may.bat vdi` (mục 4.2) |
| Cài Python mới / gỡ Python cũ | `cai_tu_khoi_dong.bat` |
| Dời thư mục app chỗ khác | `go_tu_khoi_dong.bat` ở chỗ cũ > dời thư mục > `cai_tu_khoi_dong.bat` ở chỗ mới |
| Chép bản app mới đè lên | Giữ nguyên `config` và `data`, chép đè phần còn lại, rồi `kiem_tra_may.bat` |

### 2.9 Tự khởi động làm gì

| | Windows (Task Scheduler, task **FocusTracker**) | Mac (launchd, `~/Library/LaunchAgents/com.focustracker.agent.plist`) |
|---|---|---|
| Bật lúc | Thứ 2 – thứ 6 lúc `auto_start_at` (máy tắt lúc đó thì chạy khi bật: StartWhenAvailable) · đăng nhập Windows (chờ 1 phút) · máy thức dậy sau sleep (sự kiện Power-Troubleshooter ID 1, chờ 30 giây) | `RunAtLoad` (lúc đăng nhập) · `StartCalendarInterval` thứ 2 – thứ 6 lúc `auto_start_at` |
| Chạy gì | `wscript.exe start_tracker.vbs` → `python.exe focus_tracker.py run` chạy ẩn. Không tìm thấy Python thì ghi `data/logs/launcher-error.txt` | Python 3.9+ tìm được lúc cài (python.org > Homebrew > PATH) |
| Chạy trùng | `IgnoreNew` + khoá một bản (mục 14.2) | Khoá một bản |
| Ưu tiên | Tracker tự hạ xuống Below Normal + EcoQoS | `Nice 10`, `LowPriorityIO`, `ProcessType Standard` (kiểu Background bị macOS gom hẹn giờ, nhắc trễ); tracker tự `nice(5)` |
| Lỗi khởi động | `data/logs/launcher-error.txt` | `data/logs/launchd.err.log` |
| Python | Script cài ghi đường dẫn vào `config/python_path.txt` (UTF-16) và `config/python_path.cmd`. Bỏ qua bản giả `WindowsApps`. Đổi Python thì chạy lại script cài | Ghi vào plist |

Tracker tự thoát lúc `auto_stop_at`, ngoài khung giờ chạy và ngày nghỉ. Đăng nhập / thức dậy sớm hơn `auto_start_at` thì tracker thoát im lặng, tới giờ bật thì lịch tự bật. Kiểm tra trên Windows: *Task Scheduler* > **FocusTracker** > cột *Last Run Result* `0x0` hoặc `0x41301` (đang chạy).

### 2.10 Lệnh gõ tay

Các file nhấp đúp ở trên đều gọi `focus_tracker.py`. Gõ thẳng trong cmd / Terminal (đã mở trong thư mục app) khi cần xem kỹ; Mac gõ `python3` thay cho `python`. Danh sách đủ ở mục 5.2.

| Lệnh | Kiểm tra gì | Đạt khi |
|---|---|---|
| `python focus_tracker.py check` | Cấu hình hợp lệ · đọc thử trạng thái máy (thấy cửa sổ VDI không) · token Telegram đúng không (gọi `getMe`), đã có chat ID chưa · có key AI chưa | «Kết quả: SẴN SÀNG» (dòng ✗ là phải sửa). Gọi thử AI thật: `ai-test` |
| `python focus_tracker.py probe` | In trạng thái mỗi 2 giây | Thu nhỏ VDI → `minimized`; bấm sang Chrome → `background`; bấm vào VDI → `foreground`; đóng VDI → `absent`. Ctrl+C để dừng |
| `python focus_tracker.py ai-models` / `ai-test` | Key dùng được model nào (không tốn lượt) / gọi thử 1 câu | In danh sách model / câu chào |
| `python focus_tracker.py selftest` | Chạy toàn bộ bộ test tự động | `OK` |
| `python focus_tracker.py verify [phần]` | Như `kiem_tra_may` (mục 2.6) | `== TÓM TẮT ==` toàn ✓ |

Cấu hình sai (giờ không đúng dạng `HH:MM`, số âm, JSON lỗi...) thì app báo lỗi rõ ràng lúc khởi động, ghi vào `data/logs/config-error.txt`, và với lệnh `run` còn nhắn qua Telegram nếu gửi được. Khoá lạ trong `settings.json` (gõ sai tên) cũng được nhắn báo.

### 2.11 Gỡ cài đặt

| Bước | Windows | Mac |
|---|---|---|
| 1. Gỡ tự khởi động, tắt tracker | Nhấp đúp `go_tu_khoi_dong.bat` | Nhấp đúp `go_tu_khoi_dong.command` |
| 2. Giữ số liệu? | Muốn giữ thì chép thư mục `data` đi chỗ khác | Như Windows |
| 3. Xoá app | Xoá thư mục `focus-tracker` | Như Windows |
| 4. Xoá bot (tuỳ chọn) | Telegram > @BotFather > `/deletebot` | Như Windows |
| 5. Xoá key AI (tuỳ chọn) | https://aistudio.google.com/apikey > xoá key | Như Windows |

---

## 3. Một ngày làm việc với bot

Với cấu hình mặc định (giờ làm 08:00–17:00, trưa 11:15–12:30, mục tiêu tập trung sâu 4h):

```
08:00  ── tracker tự bật (auto_start_at), lặng lẽ đo mỗi 5 giây
  │      lần đầu bạn dùng máy trong giờ làm (sau plan_prompt_after 08:00):
  │        ☀️  chào buổi sáng + câu khích lệ / Kinh Thánh (AI viết), nhắc việc hôm qua hẹn làm trước
  │        📝 hỏi kế hoạch (nếu chưa có /plan), kèm giờ vàng
  │      suốt giờ làm: nhắc sao nhãng (/nudge), rời máy, đứng dậy (/break), uống nước (/water),
  │        cất điện thoại, phóng to VDI
  │        VDI tự đóng (Citrix ngắt sau khoảng 10–15 phút không dùng): báo ngay
10:30  ── mốc tiến độ 1 (/pace): chậm thì nhắc
11:15  ── nghỉ trưa: im lặng tới 12:30
14:00  ── mốc tiến độ 2: chậm thì nhắc, đúng nhịp thì khen 1 câu
14:30  ── câu khích lệ buổi chiều (nếu đang dùng máy)
15:30  ── mốc tiến độ 3
16:45  ── hỏi tổng kết (output, issue, phân tâm, AS400, việc mai, năng lượng); không trả lời cũng được
16:50  ── (thứ Sáu) tổng kết tuần + AI phân tích + lời chúc cuối tuần
17:00  ── chưa chấm năng lượng thì bot tự tính và báo (🔋), rồi tổng kết ngày + AI đánh giá + lời chúc buổi tối
         + file báo cáo HTML
17:00+ ── không cảnh báo gì nữa
23:59  ── tracker chốt số liệu và tự thoát (auto_stop_at)
sáng mai ── nếu hôm qua máy tắt trước 17:00 (hoặc thứ Sáu chưa gửi tuần): gửi bù khi mở máy
```

| Ngày | Bot làm gì |
|---|---|
| Thứ 7, Chủ nhật | Không chạy (Task Scheduler / launchd chỉ hẹn thứ 2 – thứ 6; lỡ bật do đăng nhập thì tự thoát im lặng) |
| Ngày lễ Singapore, ngày `/off`, `/leave` cả ngày | Tracker thoát ngay khi khởi động, nhắn 1 câu (ngày nghỉ là gì, ngày làm việc tới) |
| Nghỉ phép nửa ngày | Buổi nghỉ không đo, không nhắc; mục tiêu còn một nửa; các việc theo giờ dời lại (mục 4.15) |

---

## 4. Danh mục tính năng

Mỗi tính năng: làm gì · bật/tắt · khoá cấu hình · tình huống mẫu. Câu trả lời của bot dưới đây được **chạy ra từ code thật** (bot với Telegram giả, persona mặc định), không viết tay. «...» là tin nhắn bạn gõ.

**Tổng quan**

| # | Tính năng | Lệnh | Bật/tắt nhanh | Khoá settings.json chính |
|---|---|---|---|---|
| 4.1 | Đo tập trung, điểm tập trung, **điểm tổng + robot quà tặng**, streak, xem lại kế hoạch / năng lượng / ngày cũ | `/today [ngày]` `/score` | — | `daily_focus_goal_hours`, `min_focus_block_minutes` |
| 4.2 | Nhận trạng thái cửa sổ VDI | — | — | `vdi_processes`, `vdi_session_processes`, `vdi_browser_title_keywords` |
| 4.3 | Nhắc khi sao nhãng | `/nudge` | `/nudge off` | `nudge_level` |
| 4.4 | Rời máy / quay lại, VDI tự đóng | — | `away_alert_minutes: 0`, `vdi_closed_alert: false` | `away_alert_minutes`, `vdi_closed_alert` |
| 4.5 | Nhắc cất điện thoại, phóng to VDI | — | `/nudge off` | `phone_pattern_count`, `fullscreen_tip_minutes` |
| 4.6 | Cảnh báo tiến độ | `/pace` | `/pace off` | `pace_check_enabled` |
| 4.7 | Nhắc đứng dậy, uống nước | `/break` `/water` | `/break off` `/water off` | `break_reminder_*`, `water_reminder_*` |
| 4.8 | Chào buổi sáng, khích lệ | `/encourage` `/kinhthanh` `/quote` `/bible` | `/encourage off` | `encouragement_*`, `afternoon_boost_at` |
| 4.9 | Hỏi kế hoạch / tổng kết | `/plan` `/review` | — | `plan_prompt_after`, `review_prompt_at` |
| 4.10 | Ghi chép nhanh, năng lượng (tự chấm hoặc bot tự tính lúc 17:00) | `/output` `/issue` `/distraction` `/tmrtask` `/energy` `/autoenergy` | `/autoenergy off` | `energy_auto_enabled`, `energy_capacity_hours` |
| 4.11 | Giờ AS400 (gõ hoặc ảnh) | `/as400` | `as400_enabled`, `as400_photo_ai` | — |
| 4.12 | Tổng kết ngày + AI đánh giá | (tự động 17:00) | `/aireview off` | `daily_summary_at`, `ai_review_enabled` |
| 4.13 | Tổng kết tuần + AI | `/week` | `/aireview off` | `weekly_report_day`, `weekly_report_at` |
| 4.14 | Giờ vàng | `/golden` | `golden_hours: []` | `golden_hours`, `golden_nudge_minutes` |
| 4.15 | Nghỉ phép, ngày nghỉ, tạm dừng | `/leave` `/off` `/on` `/pause` `/resume` | — | `extra_off_days`, `run_on_off_days` |
| 4.16 | Lễ Singapore, cuối tuần | — | `holiday_fetch_enabled` | `timesheet_data_dir`, `mom_holidays_url` |
| 4.17 | Hỏi AI | `/ask` `/hoi` | `/ask on` `/ask off` | `ai_provider` |
| 4.18 | Trạng thái, AI đã dùng, hiệu năng | `/status` `/aistatus` `/perf` | — | `ai_daily_call_budget`, `gemini_free_calls_per_model` |
| 4.19 | Giọng văn, xưng hô | `/style` | `/style mac_dinh` | `config/persona.json` |
| 4.20 | Giờ bot tự bật / tắt | `/giobot` `/hours` | `/giobot mac_dinh` | `auto_start_at`, `auto_stop_at` |
| 4.21 | Gửi bù, tin nhắn cũ, báo lỗi | — | — | — |
| 4.22 | Báo cáo HTML | `/report` | — | `report_refresh_minutes`, `keep_reports_days` |

### 4.1 Đo tập trung, điểm tập trung, điểm tổng, streak

Mỗi `sample_seconds` (5 giây) tracker lấy 1 mẫu: trạng thái VDI, tên process ở trước, số giây chưa chạm phím/chuột, máy khoá không, VDI có toàn màn hình không.

| Mẫu | Tính là |
|---|---|
| VDI ở trước (`foreground`) **và** chạm phím/chuột trong `idle_threshold_seconds` (60 giây) | Làm trong VDI |
| Process trong `extra_focus_processes` ở trước (ví dụ `["code.exe"]`) | Cũng tính là làm việc |
| Các đoạn làm trong VDI cách nhau ≤ `focus_gap_seconds` (120 giây), dài ≥ `min_focus_block_minutes` (20 phút) | Khối **tập trung sâu** (con số chính) |
| VDI thu nhỏ, nằm sau app khác, hoặc chưa mở, mà bạn vẫn dùng máy | Ngoài VDI (thu nhỏ đếm riêng) |
| Không chạm 60 giây – 5 phút (kể cả khi VDI đang phóng to ở trước) | Ngồi yên (inactive). Bot đo từ bên ngoài nên không biết bạn đang họp hay đọc: mục 1, «Bot đo từ bên ngoài VDI» |
| Không chạm ≥ `away_threshold_seconds` (300 giây), khoá máy, hoặc máy ngủ | Rời máy |
| Ngoài giờ làm chính thức (trước `work_start`, sau `work_end`; thứ Bảy, Chủ nhật, ngày lễ khi bạn tự bật bot) | Chỉ ghi phần gõ phím / rê chuột trong VDI, là «làm ngoài giờ» (OT). Ngoài VDI, ngồi yên, rời máy ngoài giờ: bỏ qua (mục 1) |
| Giờ nghỉ trưa (`lunch_start`–`lunch_end`, ngày làm việc) | **Không tính gì cả**: không phải giờ làm, không phải OT, kể cả khi bạn làm trong VDI |
| Buổi nghỉ phép nửa ngày | Không đo |
| Đang ngồi yên / rời máy mà chạm phím/chuột **lẻ một lần** (mọi lần chạm nằm gọn trong 5 giây) rồi lại không chạm ≥ 60 giây: đi ngang bàn đụng chuột, chuột / bàn phím Bluetooth tự gửi tín hiệu | Chưa phải quay lại: quãng ngồi yên / rời máy tính liền một mạch. Ví dụ vắng 8 phút có 1 lần chạm ở giữa = rời máy 8 phút, không phải 2 lần ngồi yên ngắn |

| Chỉ số | Cách tính |
|---|---|
| Điểm tổng 0–100 (thang 10) | Con số chính, gộp điểm tập trung, mức bị cắt ngang và năng lượng tự chấm: bên dưới |
| Điểm tập trung 0–100 | `70 × min(tập trung sâu / mục tiêu, 1) + 30 × (giờ trong VDI / giờ có thao tác)`. Ví dụ: tập trung sâu 3h / mục tiêu 4h = 52,5 điểm; 5h trong VDI trên 6h có thao tác = 25 điểm; tổng 78. Ngồi yên, rời máy không nằm trong "giờ có thao tác" nên không bị trừ ở phần 30 điểm. Năng lượng không ảnh hưởng điểm này |
| Streak | Số ngày làm việc liên tiếp đạt mục tiêu. Bỏ qua ngày nghỉ; hôm nay chưa đạt thì chưa cộng nhưng không đứt chuỗi; ngày nghỉ nửa ngày dùng mục tiêu một nửa |
| Số lần rời VDI | Không tính lần chuyển dưới 10 giây |
| Thu nhỏ VDI (số lần) | Số lần VDI bị thu nhỏ từ 10 giây trở lên. Đang thu nhỏ mà ngồi yên một lúc rồi dùng tiếp app khác vẫn là cùng một lần |
| Ngồi yên 1–5 phút: số lần, trung bình | Số đoạn ngồi yên ngắn rồi làm tiếp (thường là cầm điện thoại), và thời gian trung bình mỗi lần |
| Ngồi yên / rời máy ≥ 10 phút | Số quãng không chạm phím/chuột liền từ 10 phút trở lên |
| Rời máy: số lần, trung bình | Số lần rời máy (≥ 5 phút) và thời gian trung bình mỗi lần |
| Bị cắt ngang mỗi giờ | (Số lần rời VDI + số lần ngồi yên 1–5 phút) / giờ có thao tác. Dùng trong điểm tổng |
| Làm ngoài giờ (OT) | Giờ gõ phím / rê chuột trong VDI trước `work_start`, sau `work_end`, hoặc ngày nghỉ có bật bot (mục 1). Giờ trưa không tính. Cộng vào tập trung sâu nếu thành khối ≥ 20 phút. Lưu kèm các khoảng giờ (ví dụ 17:30–18:15; hai đoạn cách nhau ≤ 10 phút gộp làm một) |
| OT 14 ngày | Tổng OT và danh sách các ngày có OT ≥ 1 phút trong 14 ngày gần nhất (tính cả hôm nay), ngày không OT không liệt kê. Có trong báo cáo HTML ngày / tuần, tổng kết 17:00, tổng kết tuần, lời chào sáng |
| Bảng «app ngoài VDI» | Không bao giờ liệt kê chính Citrix (`citrix.desktopviewer.app.exe`, `citrix.engineui.app.exe`, các process trong `vdi_processes`, `vdi_session_processes`). Lúc VDI thu nhỏ mà khung Citrix vẫn ở trước, thời gian đó vẫn tính là «thu nhỏ VDI» |

Tình huống: «/today»

```
Tổng kết 2026-10-14 (08:02–19:40)
⭐ Điểm tổng: 91/100 (9.1/10) · quà robot PG Celestial
Tập trung sâu: 4h 05m / mục tiêu 4h · điểm tập trung 97/100
Trong VDI: 5h 10m · làm ngoài giờ (OT) 40m
Ngoài VDI: 35m (9 lần rời), thu nhỏ VDI 12m (4 lần)
Inactive phím/chuột: 26m (11 lần, TB 2m) · ≥ 10 phút: 0 lần
Rời máy: 38m (3 lần, TB 13m)
Bị cắt ngang: 3.5 lần/giờ làm
Chuỗi ngày đạt mục tiêu: 3 ngày 🔥
Khối tập trung: 08:05–09:50, 10:10–11:15, 13:00–14:35, 19:00–19:40
Năng lượng tự chấm: 4/5

Kế hoạch đầu ngày:
1. Fix job đối soát, gửi anh A test
2. Đọc spec API, góp ý qua email

Output:
- fix job đối soát (10:30)

Issue:
- VDI chậm (09:05)
```

Dòng năng lượng, OT, VDI đã đóng và các ô kế hoạch / output / issue chỉ hiện khi có. Nhắn tự nhiên «hôm nay mình tập trung được bao nhiêu rồi», «xem kế hoạch hôm nay», «năng lượng hôm nay bao nhiêu» cũng ra kết quả này (bot in thêm dòng «🔎 Mình hiểu là: Tổng kết hôm nay (xem_hom_nay, lệnh /today)»).

Xem lại ngày đã qua: kèm ngày sau lệnh.

| Gõ | Xem ngày |
|---|---|
| `/today hôm qua`, `/today hôm kia` | Hôm qua, hôm kia |
| `/today thứ 2` | Thứ Hai gần nhất đã qua (hôm nay là thứ Hai thì là hôm nay) |
| `/today 14/10`, `/today 14 tháng 10` | Ngày đó năm nay; chưa tới thì là năm trước |
| `/today 2026-10-14`, `/today 14/10/2026` | Đúng ngày đó |
| `/today mai`, ngày ghi rõ năm mà chưa tới | Bot trả «Ngày … chưa tới nên chưa có gì để xem» |
| «hôm qua tập trung thế nào», «xem năng lượng hôm qua» | Nhắn tự nhiên, như trên |

Ngày không có số liệu (nghỉ, tạm dừng) vẫn hiện kế hoạch, năng lượng đã ghi hôm đó. `/report` cũng nhận ngày như vậy (mục 4.22).

**Điểm tổng và robot quà tặng**

Điểm tổng là **con số chính** để biết một ngày tốt hay chưa (0–100, kèm thang 10). Có trong `/today`, tổng kết 17:00, báo cáo HTML (kèm hình robot và cách tính), tổng kết tuần (điểm tổng trung bình). AI đánh giá cuối ngày, cuối tuần **bắt buộc mở đầu bằng điểm tổng** và giải thích lại cho bạn: điểm đó là mức gì, từng thành phần bao nhiêu và đến từ số liệu nào, phần nào kéo điểm xuống nhiều nhất, làm gì để tăng và tăng khoảng bao nhiêu. App tính sẵn các con số này (trường `total_score_explained`, mục 7.4) và gửi kèm cách tính điểm tổng trong prompt, nên AI không phải tự tính.

```
Điểm tập trung  = 70 × min(tập trung sâu / mục tiêu, 1) + 30 × (giờ trong VDI / giờ có thao tác)
Ít bị cắt ngang = 100 × max(0, 1 − số lần bị cắt ngang mỗi giờ / 20)
Năng lượng      = (năng lượng tự chấm − 1) / 4 × 100             (chỉ khi BẠN tự chấm /energy)

Điểm tổng = 60% × điểm tập trung + 30% × ít bị cắt ngang + 10% × năng lượng
Chưa tự chấm năng lượng: điểm tổng = 65% × điểm tập trung + 35% × ít bị cắt ngang
Thang 10 = điểm tổng / 10

Số lần bị cắt ngang = số lần rời VDI sang app khác / thu nhỏ VDI + số lần ngồi yên 1–5 phút rồi làm tiếp,
                      chia cho số giờ có thao tác trong giờ làm
```

Ví dụ (ngày ở `/today` phía trên): tập trung sâu 4h 05m / mục tiêu 4h, 5h 10m trong VDI trên 5h 45m có thao tác → điểm tập trung 97. Rời VDI 9 lần + ngồi yên 11 lần = 20 lần trong 5,75 giờ = 3,5 lần/giờ → ít bị cắt ngang 83. Tự chấm năng lượng 4/5 → 75. Điểm tổng = 60% × 97 + 30% × 83 + 10% × 75 = 91/100 (9,1/10), robot PG.

| Thành phần | Căn cứ (đã đối chiếu bài gốc) |
|---|---|
| Ngưỡng 20 lần/giờ = 0 điểm | González và Mark (hội nghị CHI 2004) quan sát nhân viên IT thật: trung bình khoảng 3 phút lại chuyển việc (= 20 lần/giờ), mỗi mảng việc chỉ làm liền khoảng 11 phút. Ngày bị cắt ngang dày như mức đó được 0 điểm phần này |
| Bị cắt ngang có hại | Mark, Gudith và Klocke (CHI 2008, 48 người): bị cắt ngang thì làm nhanh hơn để bù nhưng căng thẳng, bực bội, áp lực thời gian tăng rõ |
| Giờ tập trung sâu (khối làm liền ≥ 20 phút) | Leroy (2009, tạp chí Organizational Behavior and Human Decision Processes): chuyển việc khi việc trước còn dở để lại «dư âm chú ý», làm việc kế tiếp kém hơn; làm liền một mạch thì tránh được |
| Năng lượng tự chấm | Sức sống / mệt mỏi tự đánh giá là thước đo các nghiên cứu nghỉ ngắn dùng (Albulescu và cộng sự, PLOS ONE 2022, gộp 22 nghiên cứu) |
| Trọng số 60 / 30 / 10 | **Lựa chọn của app.** Chưa có nghiên cứu nào công bố một công thức gộp đã kiểm chứng cho đúng bộ số liệu này, nên app không tự đặt ra công thức «khoa học»: chỉ gộp các thành phần có căn cứ ở trên, ưu tiên giờ tập trung (con số bạn đặt mục tiêu) |
| Năng lượng **bot tự tính** | **Không** đưa vào điểm tổng: đó là quy tắc của app (mục 4.10), không phải số đo |

| Điểm tổng | Robot quà tặng | Hình |
|---|---|---|
| dưới 30 | **SD** Mini | Tí hon, nhựa xám sơn lót, ăng-ten lò xo, một mắt to một mắt nhỏ |
| 30 – 49 | **HG** Scout | Trắng + xanh lam, ăng-ten bi vàng, kính visor xanh |
| 50 – 69 | **RG** Guardian | Trắng + xanh lá, vây đầu, giáp vai, khiên lục giác ngôi sao vàng |
| 70 – 84 | **MG** Vanguard | Thêm vương miện vàng 3 mũi, ba lô phản lực, kiếm năng lượng |
| từ 85 | **PG** Celestial | Thêm vầng hào quang, cánh sáng, lõi ngực phát sáng, lấp lánh |

Robot do app tự vẽ (SVG trong `focus/robots.py`) kiểu **đồ chơi nhựa 3D**: đổ bóng bằng gradient, vệt bóng nhựa, tông sáng trắng - xanh - vàng theo màu báo cáo, không có màu đỏ, mặt là kính visor một dải (không phải mặt nạ + ăng-ten chữ V kiểu Gundam). Tên hạng SD, HG, RG, MG, PG mượn cách gọi các cỡ mô hình lắp ráp Nhật. App **không** tải hình Gundam trên mạng: hình của Bandai / Sunrise có bản quyền, không được chép vào app chia sẻ cho đồng nghiệp.

**Điểm tổng dưới 50**: tổng kết ngày có thêm **một** câu dựa trên nghiên cứu thật, chọn theo điểm yếu nhất của ngày, kèm lý do làm vì gia đình, các con. Bot chỉ dùng các câu có sẵn trong `focus/scoring.py` (`SCIENCE`), AI không được tự bịa nghiên cứu.

| Điểm yếu nhất | Câu khoa học |
|---|---|
| Ít bị cắt ngang dưới 50, chủ yếu do rời VDI | Mark và cộng sự 2008: bị cắt ngang làm tăng căng thẳng |
| Ít bị cắt ngang dưới 50, chủ yếu do ngồi yên ngắn (cầm điện thoại) | González và Mark 2004: chuyển việc mỗi 3 phút, mỗi mảng việc chỉ làm liền khoảng 11 phút |
| VDI tự đóng, hoặc rời máy lâu hơn giờ trong VDI | Albulescu 2022: nghỉ ngắn 10 phút trở xuống giúp tăng sức sống, đỡ mệt (nghỉ ngắn rồi quay lại thay vì bỏ đi lâu) |
| Còn lại | Leroy 2009: dư âm chú ý, chốt điểm dừng rõ trước khi chuyển việc |

**Năng lượng có ảnh hưởng điểm không**

| Điểm | Năng lượng có tính vào không |
|---|---|
| Điểm tập trung 0–100 | **Không.** Giữ nguyên công thức từ bản đầu |
| Điểm tổng | Có, 10%, **chỉ** khi bạn tự chấm `/energy`. Năng lượng bot tự tính không tính |
| Chuỗi ngày 🔥 | Không (chỉ xét tập trung sâu so với mục tiêu) |

### 4.2 Trạng thái cửa sổ VDI (phóng to, thu nhỏ, vừa vừa, ẩn, trình duyệt)

Mỗi mẫu có `vdi_state` là một trong 4 giá trị:

| `vdi_state` | Nghĩa | Tính là |
|---|---|---|
| `foreground` | Cửa sổ VDI chính đang nhận bàn phím (bạn đã bấm vào nó) | Trong VDI (nếu có thao tác) |
| `background` | VDI đang hiện nhưng app khác ở trước | Ngoài VDI |
| `minimized` | Mọi cửa sổ VDI đang thu nhỏ / ẩn | Ngoài VDI (đếm riêng "thu nhỏ VDI") |
| `absent` | Không thấy cửa sổ VDI nào | Ngoài VDI |

| Bạn làm gì với cửa sổ VDI | Windows thấy gì | Mac thấy gì | Kết quả |
|---|---|---|---|
| **Phóng to** (maximize / toàn màn hình), gõ trong VDI | VDI là cửa sổ foreground; `IsZoomed` hoặc khung cửa sổ phủ màn hình (lệch ≤ 8 px) | Cửa sổ Citrix Viewer đứng đầu danh sách cửa sổ trên màn hình, phủ ≥ 85% một màn hình | `foreground`, `vdi_full` = có |
| **Gõ trong VDI** (Windows, Citrix Desktop Viewer bản mới) | Cửa sổ ở trước thường là **mặt phiên** `Citrix.EngineUI.App.exe` «MockWindow» chứ không phải khung `Citrix.DesktopViewer.App.exe` (xem «Citrix Desktop Viewer trên Windows» bên dưới). Mặt phiên đang hiện thật, đủ lớn, trong màn hình thì tính là cửa sổ VDI. Khung đã thu nhỏ thì không tính | Không áp dụng | `foreground` |
| **Full screen của Citrix** (Windows, nút Full screen trên thanh công cụ Citrix; chưa thấy trên máy thật) | Khung Desktop Viewer có thể ẩn, chỉ còn thanh công cụ bé và mặt phiên phủ cả màn hình. Mặt phiên đang hiện nên không bị báo `absent` (tránh báo nhầm «cửa sổ VDI biến mất») | Không áp dụng | `foreground` khi ở trước, `background` khi app khác ở trước, `vdi_full` = có |
| **Mở vừa vừa** (không phóng to, không thu nhỏ), gõ trong VDI | VDI foreground, kích thước nào cũng được (miễn ≥ 200×200 px) | Citrix Viewer đứng đầu | `foreground`, `vdi_full` = không. **Vẫn tính là làm trong VDI**; chỉ cộng phút "VDI không toàn màn hình" và gợi ý phóng to (mục 4.5). Lúc VDI nằm sau app khác hay thu nhỏ thì không cộng phút này |
| Mở vừa vừa, nhưng gõ ở app bên cạnh | App kia foreground | App kia đứng đầu | `background` |
| **Thu nhỏ** xuống taskbar / Dock | `IsIconic`, hoặc cửa sổ ở toạ độ -32000. Kể cả khi Windows vẫn báo VDI là cửa sổ "đang chọn" | Cửa sổ không còn trong danh sách "đang hiện trên màn hình" nhưng vẫn có trong danh sách mọi cửa sổ, dù tên Citrix Viewer vẫn ở thanh menu | `minimized`: **luôn không tập trung** |
| **Ẩn bằng Cmd+H** (Mac) | — | Như thu nhỏ: chỉ có trong danh sách mọi cửa sổ | `minimized` |
| VDI toàn màn hình ở **Space khác**, bạn vuốt sang Space khác | — | Không trong danh sách đang hiện | `minimized` |
| VDI ở màn hình ngoài, gõ ở app trên màn hình laptop | App kia foreground | App kia đứng đầu | `background` |
| Chỉ rê chuột qua VDI, chưa bấm | Hệ điều hành vẫn coi app kia ở trước | Như Windows | Chưa tính là trong VDI |
| Khoá máy | Process trước mặt là `logonui.exe` / `lockapp.exe`, hoặc không mở được input desktop | `CGSSessionScreenIsLocked`, hoặc phiên của bạn không ở trên màn hình (người khác đăng nhập bằng Fast User Switching) | Rời máy |
| Đóng hẳn phiên VDI (Mac), app Citrix Viewer vẫn mở | — | Chỉ còn cửa sổ phụ vô hình / tí hon của Citrix Viewer: không tính là cửa sổ VDI | `absent` (cảnh báo VDI bị ngắt vẫn chạy) |

**Cách đọc trên từng hệ điều hành**

| | Windows (`WindowsProbe`, Win32 qua ctypes) | Mac (`MacProbe`, CoreGraphics qua ctypes) |
|---|---|---|
| Cửa sổ ở trước | `GetForegroundWindow` | Cửa sổ lớp 0 đầu tiên trong `CGWindowListCopyWindowInfo` (chỉ cửa sổ đang hiện). Đối chiếu app đang nhận phím/chuột qua `NSWorkspace.frontmostApplication` (không cần quyền; chỉ tin sau khi đã thấy giá trị đổi ít nhất một lần): nếu app đó không phải chủ cửa sổ trên cùng (bấm ra desktop Finder, Cmd+Tab sang app khác) thì cửa sổ ở trước là cửa sổ trên cùng của chính app đó. Không đọc được thì dùng cửa sổ trên cùng |
| Thu nhỏ | `IsIconic`, toạ độ -32000; cửa sổ phụ của cửa sổ đang thu nhỏ không tính | Có trong danh sách mọi cửa sổ, không có trong danh sách đang hiện |
| Bỏ cửa sổ phụ | Ẩn (`IsWindowVisible`), `WS_EX_TOOLWINDOW` (trừ mặt phiên Citrix, xem bên dưới), nhỏ hơn 200×200 px (thanh công cụ Citrix); hộp thoại của VDI thì xét cửa sổ gốc (`GetAncestor` root owner) | Lớp khác 0, trong suốt, nhỏ hơn 50×50 (áp dụng cho cả danh sách đang hiện lẫn danh sách mọi cửa sổ) |
| Toàn màn hình | `IsZoomed` hoặc phủ màn hình (lệch ≤ 8 px) | Một cửa sổ VDI bất kỳ của app đó phủ ≥ 85% một màn hình (thanh công cụ Citrix nằm trên không làm sai) |
| Idle | `GetLastInputInfo` | `CGEventSourceSecondsSinceLastEventType` |
| Nhận VDI | Tên process trong `vdi_processes` (khung) hoặc `vdi_session_processes` (mặt phiên). App Citrix tên lạ: xem «Citrix đổi tên app ở bản sau» bên dưới. Tiêu đề (`vdi_title_keywords`) chỉ dùng cho app Citrix, hoặc khi **không đọc được tên process** (Citrix chạy quyền Admin), để Outlook/Chrome có chữ "Desktop Viewer" trong tiêu đề không bị tính nhầm | Tên app trong `vdi_processes`. Thấy app tên có "citrix" mà chưa khai báo thì cảnh báo trong `/status` |
| Quét lại danh sách cửa sổ VDI | Mỗi 30 giây; app có nhận DPI | — |
| Quyền cần | Không cần admin | **Không cần quyền gì** khi dùng app Citrix. Chỉ khi dùng Citrix trong trình duyệt mới cần **Screen Recording** (để đọc tiêu đề tab). Không dùng được CoreGraphics thì dự phòng bằng AppleScript/System Events (cần **Accessibility**, chậm hơn, có thể không nhận ra Space khác) |

Tên process VDI mặc định (`vdi_processes`): `citrix.desktopviewer.app.exe` (Citrix Desktop Viewer bản mới), `cdviewer.exe` (bản cũ), `wfica32.exe`, `msrdc.exe`, `mstsc.exe` (Windows); `citrix viewer`, `windows app`, `microsoft remote desktop` (Mac).

#### Citrix Desktop Viewer trên Windows: khung và mặt phiên

Trên máy thật (Citrix Workspace 26.3.20.5, kiểm tra 14–15/10/2026), một VDI đang mở gồm **hai cửa sổ chồng lên nhau**:

| | Khung Desktop Viewer | Mặt phiên |
|---|---|---|
| Process | `Citrix.DesktopViewer.App.exe` | `Citrix.EngineUI.App.exe` |
| Tiêu đề | «AZ-WIN11-CONGTY-REGULAR - Desktop Viewer» (tên máy ảo + «Desktop Viewer») | «MockWindow» |
| Là gì | Cửa sổ bao ngoài: thanh tiêu đề, nút thu nhỏ / phóng to / đóng, thanh công cụ Citrix. Có biểu tượng trên taskbar | Lớp Citrix đặt **đè đúng lên vùng bên trong khung** để vẽ màn hình máy ảo và nhận phím, chuột. Là *tool window*: không có biểu tượng trên taskbar, không có thanh tiêu đề. «MockWindow» là tên nội bộ Citrix đặt, người dùng không thấy |
| Thuộc | Citrix Workspace | Citrix Workspace: file có chữ ký số của Citrix, nằm ở `C:\Program Files (x86)\Citrix\ICA Client\Citrix.EngineUI.App\`, viết bằng WinUI 3. **Không phải virus, không phải app lạ** |
| Kích thước đo được | Theo cửa sổ (phóng to = cả màn hình; thu nhỏ = 237×39 ở toạ độ -32000) | Bằng vùng bên trong khung: 1541×878 khi VDI vừa vừa, 1920×1080 khi phóng to |
| Windows coi là cửa sổ ở trước khi | Bấm vào thanh tiêu đề, thanh công cụ Citrix | **Đang gõ / bấm chuột trong VDI** (gần như mọi lúc làm việc) |
| Thu nhỏ VDI | Khung xuống taskbar | Mặt phiên có thể vẫn «hiện» theo Windows, nên app **không** tin nó mà xét khung |

Trước đây app chỉ biết khung, nên lúc gõ trong VDI (mặt phiên ở trước) bị tính nhầm là «ngoài VDI». Nay app nhận cả hai, theo luồng sau (mỗi 5 giây):

```
Cửa sổ đang ở trước thuộc process nào?
   |
   v
Có trong vdi_processes (ví dụ citrix.desktopviewer.app.exe)?
   |-- CÓ --> là khung VDI --> foreground; phóng to hay không xét theo chính nó. HẾT
   |-- KHÔNG
   v
Có trong vdi_session_processes (ví dụ citrix.engineui.app.exe)?
   |-- CÓ --> là mặt phiên. Đang hiện thật, đủ lớn (từ 200×200), không ở toạ độ thu nhỏ?
   |            |-- KHÔNG --> không tính là VDI. HẾT
   |            |-- CÓ --> khung Desktop Viewer đang thu nhỏ hết?
   |                         |-- CÓ --> minimized (không tập trung). HẾT
   |                         |-- KHÔNG --> foreground; phóng to hay không xét theo khung. HẾT
   |-- KHÔNG
   v
Là app Citrix tên lạ? (tên bắt đầu bằng "citrix", hoặc file .exe nằm trong thư mục ...\Citrix\...)
   |-- KHÔNG --> app khác --> background / minimized / absent tuỳ khung VDI. HẾT
   |-- CÓ
   v
Tiêu đề có chữ trong vdi_title_keywords ("Desktop Viewer")?
   |-- CÓ --> là khung VDI (Citrix đã đổi tên file khung). HẾT
   |-- KHÔNG
   v
Là tool window phủ từ 80% trở lên lên khung Desktop Viewer đang hiện?
   |-- CÓ --> tạm tính là mặt phiên (Citrix đã đổi tên file mặt phiên)
   |          + /status cảnh báo «Cửa sổ Citrix "tên.exe" phủ lên VDI, đang tạm tính là VDI...». HẾT
   |-- KHÔNG --> chưa tính là VDI; cửa sổ to (từ 800×500) thì /status cảnh báo
                 «Thấy cửa sổ Citrix lạ "tên.exe" ở trước nhưng chưa tính là VDI...». HẾT
```

**Khoá `vdi_session_processes`**

| | |
|---|---|
| Là gì | Danh sách tên file `.exe` của **mặt phiên** Citrix |
| Mặc định | `["citrix.engineui.app.exe"]`, **đã có sẵn trong app**. File `settings.json` của bạn **không cần** dòng này; chỉ thêm khi Citrix đổi tên (bảng dưới) |
| Khác `vdi_processes` | Process trong `vdi_processes` là **khung**: thu nhỏ / phóng to xét theo chính nó. Process trong `vdi_session_processes` là **tool window**: chỉ tính khi đang hiện thật trên màn hình, và luôn xét khung để biết VDI có đang thu nhỏ không. Ghi `citrix.engineui.app.exe` vào `vdi_processes` sẽ **không** có tác dụng (tool window bị bỏ qua) |
| Chữ hoa / thường | Không phân biệt (app tự đổi về chữ thường) |
| Mac | Không dùng (Citrix Viewer trên Mac chỉ có một cửa sổ) |

**Citrix đổi tên app ở bản sau**

Citrix từng đổi tên file (`cdviewer.exe` → `Citrix.DesktopViewer.App.exe`) nên app không chỉ dựa vào tên file:

| Citrix đổi gì | App còn nhận đúng VDI? | Nhờ đâu |
|---|---|---|
| Tên file khung, tiêu đề vẫn «... - Desktop Viewer» | **Có** | App Citrix (tên bắt đầu bằng `citrix` hoặc nằm trong thư mục `\Citrix\`) + tiêu đề có `vdi_title_keywords` |
| Tên file mặt phiên, VDI mở vừa vừa hoặc phóng to | **Có**, kèm cảnh báo trong `/status` | Tool window Citrix phủ từ 80% khung đang hiện |
| Tên file mặt phiên, dùng nút Full screen của Citrix (khung ẩn) | Có thể không: báo «ngoài VDI» hoặc «không thấy VDI» | Không còn khung để đối chiếu. `/status` cảnh báo «Thấy cửa sổ Citrix lạ...» |
| Bỏ chữ «Desktop Viewer» trong tiêu đề **và** đổi tên file khung | Không | Thêm tên / chữ mới vào `vdi_processes` / `vdi_title_keywords` |
| Thư mục cài không còn chữ `Citrix`, tên file không bắt đầu bằng `citrix` | Chỉ với tên đã khai báo | Thêm tên mới (bảng dưới) |
| Bỏ hẳn kiểu cửa sổ riêng | Không | Cần sửa code |

Việc cần làm sau mỗi lần Citrix Workspace cập nhật:

```
Mở VDI, chạy kiem_tra_may.bat vdi
   |
   v
4 bước đều ✓ và /status không có cảnh báo Citrix?
   |-- CÓ --> không cần làm gì. HẾT
   |-- KHÔNG
   v
Đọc tên .exe trong cảnh báo (hoặc trong file data\logs\kiem_tra-*.txt, dòng «Cửa sổ Citrix»)
   |
   v
Mở config\settings.json (chưa có thì chép settings.example.json, xoá hết chỉ giữ { }), thêm:
   "vdi_session_processes": ["citrix.engineui.app.exe", "ten-moi.exe"]
   (nếu là khung thì thêm vào "vdi_processes", nhớ chép đủ các tên mặc định ở trên)
   |
   v
Lưu, chạy lại start_tracker.bat (hoặc đợi sáng mai), rồi kiem_tra_may.bat vdi lần nữa. HẾT
```

Khoá dạng danh sách trong `settings.json` **thay cả danh sách mặc định**, nên luôn giữ tên cũ và thêm tên mới vào sau. Không chắc thì gửi file `kiem_tra-*.txt` cho người hỗ trợ.

**Citrix mở bằng app hay bằng trình duyệt**

| | Mở bằng **app Citrix** (Workspace, cửa sổ Desktop Viewer / Citrix Viewer) | Mở bằng **trình duyệt** (trang StoreWeb > "mở trong trình duyệt", bản HTML5) |
|---|---|---|
| VDI nằm ở đâu | Cửa sổ riêng của app Citrix | Một **tab** trong Chrome / Edge / Safari... |
| Nhận ra bằng | Tên process | Tiêu đề tab (process là trình duyệt, giống mọi trang web) |
| Cần cấu hình | Không | **Có sẵn** `vdi_browser_title_keywords` = `["AZ-WIN11-SGLIFE"]` (phần đầu tên máy ảo VDI công ty). Máy ảo tên khác thì sửa (xem khung dưới). `[]` = tắt chế độ này |
| Trình duyệt được xét | — | `browser_processes` |
| Độ chính xác | Cao nhất | Tốt, nhưng: tab có chữ "storeweb" (trang danh sách desktop) không bao giờ tính; đổi sang tab khác trong cùng trình duyệt = ngoài VDI; trang khác trùng từ khoá sẽ tính nhầm |
| Thu nhỏ trình duyệt | Không tập trung | Không tập trung |
| Mac | Không cần quyền | Cần **Screen Recording**: tracker tự hiện hộp thoại xin quyền cho Python lúc khởi động (bản chạy nền), Terminal khi chạy bằng `start_tracker.command`. Thiếu quyền thì `/status` báo «macOS không cho đọc tiêu đề cửa sổ: tab VDI sẽ KHÔNG...» kèm đường dẫn chương trình cần bật |

> **Tên máy ảo VDI và từ khoá tab trình duyệt (có sẵn, sửa khi cần)**
>
> | Trường hợp | Cần làm gì |
> |---|---|
> | Mở VDI bằng **app Citrix** (cửa sổ «... - Desktop Viewer») | **Không làm gì.** App nhận ra qua tên chương trình Citrix (`Citrix.DesktopViewer.App.exe`, `Citrix.EngineUI.App.exe`) và chữ «Desktop Viewer», tên máy ảo là gì cũng được |
> | Mở VDI bằng **trình duyệt**, tên máy ảo bắt đầu bằng `AZ-WIN11-SGLIFE` (ví dụ `AZ-WIN11-SGLIFE-REGULAR`) | **Không làm gì.** Từ khoá mặc định đã khớp |
> | Mở VDI bằng **trình duyệt**, tên máy ảo **khác** | Sửa từ khoá trong `config\settings.json` (bảng dưới) |
> | Không bao giờ mở VDI bằng trình duyệt, máy Mac | Nên tắt: ghi `[]` (bảng dưới). Bật chế độ này thì Mac xin quyền Screen Recording lúc khởi động |
>
> **Cách xem tên máy ảo:** mở VDI, nhìn tiêu đề cửa sổ / tab (chữ trước « - Desktop Viewer» hoặc trước tên trình duyệt), hoặc chạy `kiem_tra_may.bat vdi` (Mac: `kiem_tra_may.command vdi`) rồi mở file `data\logs\kiem_tra-*.txt`: dòng tiêu đề cửa sổ VDI có tên máy ảo.
>
> **Cách sửa** (mở `config\settings.json` bằng Notepad, thêm một dòng vào trong cặp `{ }`, nhớ dấu phẩy giữa các dòng, lưu lại rồi tắt / mở lại tracker):
>
> | Muốn | Dòng ghi vào `settings.json` |
> |---|---|
> | Đổi sang tên máy ảo của mình | `"vdi_browser_title_keywords": ["AZ-WIN10-TENMAYAO"]` (ghi phần đầu tên là đủ, không phân biệt hoa thường) |
> | Nhận nhiều máy ảo | `"vdi_browser_title_keywords": ["AZ-WIN11-SGLIFE", "AZ-WIN10-TENMAYAO"]` |
> | Tắt nhận tab trình duyệt | `"vdi_browser_title_keywords": []` |
>
> Không có dòng này trong `settings.json` = dùng mặc định `["AZ-WIN11-SGLIFE"]`. Sau khi sửa, mở VDI trong trình duyệt rồi gõ `/status`: dòng «nhận VDI qua» có «tab trình duyệt» là đã bật.

Mở trang StoreWeb trong trình duyệt nhưng bấm desktop mà nó mở bằng app Citrix (file `.ica`) thì là cột trái, không cần cấu hình. **Khuyên dùng app Citrix**: đo chính xác hơn, VDI cũng mượt hơn.

### 4.3 Nhắc khi sao nhãng (`/nudge`)

Sao nhãng = đang dùng phím/chuột nhưng VDI không ở trước (app khác, VDI thu nhỏ hoặc nằm sau). Chỉ trong giờ làm, trừ trưa, ngày nghỉ, phần nghỉ phép. Một **lần sao nhãng** kết thúc khi: quay lại VDI, khoá máy / rời máy hẳn (≥ 5 phút), `/pause`, máy ngủ, vào trưa / hết giờ, sang ngày mới. Ra ngoài dưới 1 phút (liếc Zalo) không đếm là một lần.

| Mức | Lệnh | Nhắc khi | Khoá settings.json |
|---|---|---|---|
| Tắt | `/nudge off` | Không nhắc sao nhãng, kể cả nhắc cất điện thoại và gợi ý phóng to VDI. **Vẫn** nhắc rời máy, đứng dậy, uống nước, tiến độ | `nudge_level: "off"` |
| Nhẹ | `/nudge nhe` | 1 lần/ngày: lần đầu sao nhãng ≥ 15 phút, sau đó im cả ngày (giữ cả khi tracker khởi động lại) | `nudge_light_minutes` (15) |
| Vừa (mặc định) | `/nudge vua` | Mỗi lần sao nhãng ≥ 15 phút nhắc đúng 1 lần; trong giờ vàng 5 phút | `nudge_out_of_vdi_minutes` (15), `golden_nudge_minutes` (5) |
| Nghiêm | `/nudge nghiem` | Sau 5 phút nhắc, còn ở ngoài thì 5 phút nhắc lại; kèm "lần sao nhãng thứ N, đã mất X phút hôm nay"; giọng gắt hơn. Giờ vàng: lấy ngưỡng nhỏ hơn | `nudge_strict_minutes` (5) |

Kèm một câu khích lệ (AI nếu có, tắt bằng `/encourage off`): mức vừa từ lần nhắc thứ 2 trong ngày; mức nghiêm ở lần nhắc lại đầu tiên của mỗi lần sao nhãng; mức nhẹ không. Lần nhắc thứ 2 trở đi của cùng một lần sao nhãng có thêm câu "doạ nhẹ" nhắc tên sếp (nếu `ten_sep` có trong persona). Có kế hoạch hôm nay thì thêm dòng «Quay lại: <việc đầu tiên>».

Ví dụ một ngày (kiểm bằng `tests/test_nudge_levels.py`): 08:30–08:50 Chrome 20' · 09:10–09:28 VDI thu nhỏ 18' · 09:38 Chrome 8' · 09:56 Chrome 7' rồi khoá máy 30', mở lại Chrome 10' · 10:53 giờ vàng Chrome 6'.

| Mức | Số tin | Lúc nào |
|---|---|---|
| Tắt | 0 | — |
| Nhẹ | 1 | 08:45 |
| Vừa | 3 | 08:45 · 09:25 (thu nhỏ) · 10:58 (giờ vàng) |
| Nghiêm | 10 | 08:35, 08:40, 08:45 · 09:15, 09:20, 09:25 · 09:43 · 10:01 · 10:38 (sau khoá máy tính lại, không nhắc dồn) · 10:58 |

Tin nhắc mẫu (mức vừa, persona mặc định, có kế hoạch):

```
Ê bạn, quay lại VDI thôi nào.
⚠️ 15 phút làm việc ngoài VDI (VDI nằm sau app khác, đang dùng chrome.exe).
Quay lại: fix job đối soát
Bị chặn (VDI chậm, thiếu quyền, chờ người khác)? Ghi ngay: /issue nội dung
```

Mức nghiêm, giọng `sep_kho_tinh`, `ten_sep` = "anh Tuấn", lần nhắc thứ 2:

```
VDI vẫn thu nhỏ. Mở lên, làm việc. Ngay.
⚠️ 10 phút làm việc ngoài VDI (VDI đang thu nhỏ, đang dùng zalo.exe).
📌 Hôm nay: lần sao nhãng thứ 3, đã mất tổng 28 phút ngoài VDI.
anh Tuấn mà thấy thì tôi không bênh đâu.
Còn ở ngoài thì 5 phút nữa tôi nhắc tiếp.
Bị chặn (VDI chậm, thiếu quyền, chờ người khác)? Ghi ngay: /issue nội dung
```

Đổi mức:

```
» /nudge nghiem
Đã đổi mức nhắc khi sao nhãng: nghiêm khắc (nhắc lặp, đếm số lần).
Nhắc sau 5 phút, còn ở ngoài thì 5 phút nhắc lại, kèm số lần sao nhãng + tổng phút mất hôm nay, giọng gắt hơn.

» nhắc nhẹ thôi            (nhắn tự nhiên: bot hỏi lại, bấm ✅ OK)
Đã đổi mức nhắc khi sao nhãng: nhẹ (1 lần/ngày).

» /nudge mac_dinh          (về giá trị trong settings.json)
Đã đổi mức nhắc khi sao nhãng: vừa (1 lần mỗi lần sao nhãng).
```

`/nudge` (hoặc `/nhac`) không kèm mức: xem mức hiện tại + giải thích 4 mức. settings.json nhận cả `tat`, `light`, `normal`/`medium`, `strict`/`chat`.

### 4.4 Rời máy, quay lại

| | |
|---|---|
| Nhắc khi | Không chạm phím/chuột (hoặc khoá máy) liên tục `away_alert_minutes` (15) phút trong giờ làm. Tính từ lần chạm cuối, không sớm hơn lúc vào giờ làm / máy thức dậy. Chạm lẻ một lần rồi lại ngồi yên (mục 4.1) không làm đồng hồ về 0 |
| Quay lại | Chạm phím/chuột ở 2 mẫu 5 giây liền nhau (hoặc mở khoá máy) sau khi đã bị nhắc; chạm lẻ một lần thì chưa báo: «Chào mừng quay lại. Bạn rời máy 32 phút. Vào VDI làm tiếp nhé.» |
| Tắt | `"away_alert_minutes": 0`. Không phụ thuộc `/nudge` |
| VDI tự đóng | Citrix tự ngắt VDI khi không đụng VDI 10–20 phút: máy ảo vẫn chạy nhưng **cửa sổ Desktop Viewer biến mất**. Hôm nay bạn **đã làm trong VDI** (đã gõ phím / rê chuột trong VDI ít nhất một lần) mà cửa sổ mất ≥ 1 phút trong giờ làm thì bot báo ngay 1 lần: «🔌 Cửa sổ VDI đã đóng từ 10:42 … Lần cuối bạn làm trong VDI lúc 10:23, cách đây 20 phút.» Tổng kết ngày có dòng «VDI đã đóng (rời VDI quá lâu): 10:42–11:05», AI nhận trường `vdi_closed` |
| VDI tự đóng: không báo khi | Nghỉ trưa, ngoài giờ làm (mất lúc trưa mà vào giờ làm vẫn chưa mở lại thì báo lúc đó), sáng chưa mở VDI lần nào, VDI mở sẵn từ sớm nhưng **chưa làm gì trong VDI** (ví dụ mở VDI 07:45 rồi đi pha cà phê, Citrix tự ngắt 08:02: không báo, tổng kết cũng không ghi), máy ngủ / `/pause` / nghỉ phép, cửa sổ mất dưới 1 phút (đang kết nối lại). Tắt hẳn: `"vdi_closed_alert": false` |

```
Bạn đi đâu lâu thế?
⏰ Bạn đã rời máy 15 phút (từ 09:31). Xong việc thì quay lại bàn nhé. Máy đang khoá.
```

VDI ở trước mà không gõ (họp chỉ nghe) thì tin có thêm «(Đang họp chỉ nghe trong VDI thì bỏ qua tin này, hoặc gõ /pause.)».

### 4.5 Nhắc cất điện thoại, gợi ý phóng to VDI

| | Cất điện thoại | Phóng to VDI |
|---|---|---|
| Dấu hiệu | VDI ở trước, ngồi yên 1–5 phút rồi mới làm tiếp, lặp `phone_pattern_count` (3) lần trong 30 phút. "Làm tiếp" = chạm phím/chuột ở 2 mẫu 5 giây liền nhau (báo trễ 5 giây); chạm lẻ một lần ở giữa không cắt quãng ngồi yên làm hai | Cộng dồn `fullscreen_tip_minutes` (15) phút bạn đang dùng VDI (VDI ở trước, có gõ phím/chuột) mà VDI không toàn màn hình. VDI nằm sau / thu nhỏ: đồng hồ dừng (phần đó đã tính là sao nhãng); phóng to VDI: đồng hồ về 0 |
| Tần suất | Cách nhau ít nhất 60 phút; mức nhẹ: tối đa 1 lần/ngày | 1 lần/ngày |
| Tắt | `phone_pattern_count: 0` hoặc `/nudge off` | `fullscreen_tip_minutes: 0` hoặc `/nudge off` |

```
📱 3 lần trong 30 phút bạn ngồi yên 1–5 phút trước VDI rồi mới làm tiếp. Thường là đang cầm điện thoại/iPad. Úp điện thoại xuống, để ngoài tầm tay cho tới giờ nghỉ nhé. (Đang đọc code/tài liệu thì bỏ qua tin này.)

🖥️ Bạn đã làm 15 phút trong VDI mà VDI không toàn màn hình. Phóng to VDI trên một màn hình, để Chrome/Zalo ở màn hình kia hoặc tắt hẳn: ít thấy thì ít bấm.
```

### 4.6 Cảnh báo tiến độ (`/pace`)

So **giờ làm thật trong VDI** hôm nay với nhịp cần để đạt `pace_target_vdi_hours` (6h) trước `work_end`, không gợi ý làm thêm giờ.

```
mức cần lúc T = mục tiêu × (giờ làm đã qua tới T, trừ trưa) / (tổng giờ làm trừ trưa = 7,75h)
chậm nếu       thực tế < (1 − pace_behind_ratio) × mức cần    (mặc định: < 60%)
```

| Mốc (`pace_checkpoints`) | Giờ làm đã qua | Mức cần | Nhắc nếu dưới |
|---|---|---|---|
| 10:30 | 2,5h | 1h56 | 1h10 |
| 14:00 | 4,75h | 3h41 | 2h12 |
| 15:30 | 6,25h | 4h50 | 2h54 |

| Luật | |
|---|---|
| Mỗi mốc | Tối đa 1 lần/ngày, chạy cả khi bạn không ngồi máy |
| Mở máy muộn | Chỉ chạy mốc gần nhất đã qua; trễ hơn 60 phút (cộng giờ trưa nếu vắt qua trưa) thì bỏ |
| Đúng nhịp | Im lặng; riêng mốc đầu tiên từ 14:00 trở đi khen 1 câu (1 lần/ngày) |
| Nghỉ nửa ngày | Mục tiêu còn một nửa (3h), bỏ mốc trong buổi nghỉ |
| Không kịp nữa | Bảo dồn sức cho việc quan trọng nhất |
| Bật/tắt | `/pace on`, `/pace off` (`/tiendo`); settings: `pace_check_enabled`. Không phụ thuộc `/nudge` |

Ví dụ 14:00 mới làm 2h, giọng `vui_tuoi`:

```
Tăng tốc chút nào bạn! Vẫn kịp về đúng giờ nếu bắt đầu ngay 💪
📉 14:00: mới làm thật trong VDI 2h00, lúc này cần khoảng 3h41 để kịp 6h trước 17:00. Chậm 1h41.
Còn 3h00 giờ làm.
Kể cả ở VDI liền tay 3h00 còn lại cũng chỉ được khoảng 5h00: dồn hết sức cho việc quan trọng nhất, tắt Zalo/Chrome, họp thì /pause.
```

Đúng nhịp ở mốc khen: «Giỏi lắm bạn, đang đúng nhịp. ✅ 14:00: đã làm thật trong VDI ... Giữ nhịp này là đạt 6h, về đúng 17:00.»

«/pace» (xem ngay, lúc 09:44 chưa làm gì):

```
📈 Tiến độ lúc 09:44: làm thật trong VDI 0 phút / cần khoảng 1h21 lúc này (chậm 1h21 ⚠️).
Mục tiêu 6h trong VDI trước 17:00 · còn 6h01 giờ làm.
Để đạt 6h và về đúng 17:00 không OT: mỗi giờ còn lại cần 60 phút làm trong VDI.
Cảnh báo tiến độ tự động: ĐANG BẬT (mốc 10:30, 14:00, 15:30).
Đổi: /pace on hoặc /pace off
```

Mốc tự đặt phải nằm trong giờ làm và không rơi vào giờ trưa (app tự sắp xếp, bỏ trùng).

### 4.7 Nhắc đứng dậy (`/break`), uống nước (`/water`)

Nhắc sức khoẻ **không phụ thuộc** `/nudge` (kể cả `/nudge off` vẫn nhắc).

| | Đứng dậy, vận động, tập mắt | Uống nước |
|---|---|---|
| Khi nào | Làm trong VDI liên tục `break_reminder_minutes` (60) phút (ngắt ≤ 2 phút vẫn tính liên tục); chưa nghỉ thì cứ mỗi 60 phút nhắc lại | **Mặc định TẮT** khi cài lần đầu (giống Kinh Thánh). Bật bằng `/water on`: mỗi `water_reminder_minutes` (60) phút giờ làm |
| Nội dung | Câu mở theo giọng + đứng dậy 3–5 phút, đi lại, vươn vai, quy tắc mắt 20-20-20 + 1 bài tập ngắn (không lặp 6 lần gần nhất) + **1 dữ kiện nghiên cứu y khoa có thật** (🔬, bảng dưới) | Câu ngắn theo giọng + đôi khi một mẹo + **1 dữ kiện nghiên cứu** (🔬) |
| Không nhắc lúc | Ngoài giờ làm, trưa, nghỉ phép | Trưa, nghỉ phép, `/pause`; đang khoá máy / ngồi yên thì chờ tới lúc bạn quay lại (chạm lẻ một lần không tính) |
| Trùng giờ | Hai nhắc tới hạn cách nhau ≤ 1 phút: gộp vào **một** tin | |
| Lệnh | `/break` (`/nghingoi`) `on` · `off` · `45` · `mac_dinh` | `/water` (`/uongnuoc`) `on` · `off` · `45` · `mac_dinh` |
| Nhắn tự nhiên | «tắt nhắc đứng dậy», «nhắc nghỉ mỗi 45 phút» | «nhắc uống nước», «tắt nhắc uống nước» |
| settings.json | `break_reminder_enabled`, `break_reminder_minutes` | `water_reminder_enabled`, `water_reminder_minutes` |

```
Bạn ơi, ngồi lâu rồi, mình nghỉ chân chút nha.
Bạn đã tập trung liên tục 60 phút, giỏi lắm. Đứng dậy nghỉ 3–5 phút: đi lại vài vòng, vươn vai, cho mắt nghỉ theo quy tắc 20-20-20 (nhìn xa 6 mét trong 20 giây) để đỡ mỏi mắt, đỡ cận.
💧 Tiện thể rót một ly nước uống luôn nhé.

Cổ vai: nghiêng đầu sang trái giữ 15 giây, sang phải 15 giây. Rụt vai lên tai rồi thả xuống 10 lần.

🔬 Dunstan và cộng sự (Diabetes Care 2012, 19 người 45–65 tuổi thừa cân): cứ 20 phút đứng dậy đi bộ nhẹ 2 phút thì đường huyết sau ăn giảm khoảng một phần tư, insulin giảm khoảng 23% so với ngồi liền.
```

Dữ kiện 🔬 lấy ngẫu nhiên từ danh sách cố định trong `focus/scoring.py` (`SCIENCE`), đã đối chiếu bản tóm tắt / bài gốc. AI không tham gia, nên không có nghiên cứu bịa.

| Nhắc | Nghiên cứu | Kết quả chính |
|---|---|---|
| Đứng dậy | Dunstan và cộng sự, Diabetes Care 2012 (19 người) | Cứ 20 phút đi bộ nhẹ 2 phút: đường huyết sau ăn giảm khoảng 1/4, insulin giảm khoảng 23% |
| Đứng dậy | Ekelund và cộng sự, The Lancet 2016 (hơn 1 triệu người, 16 nghiên cứu) | Ngồi trên 8 giờ/ngày, ít vận động: nguy cơ tử vong sớm cao hơn; vận động vừa 60–75 phút/ngày xoá phần nguy cơ tăng thêm |
| Đứng dậy | Albulescu và cộng sự, PLOS ONE 2022 (gộp 22 nghiên cứu) | Nghỉ ngắn ≤ 10 phút tăng sức sống, giảm mệt mỏi |
| Uống nước | Borghi và cộng sự, Journal of Urology 1996 (199 người, 5 năm) | Uống nhiều nước: sỏi thận tái phát 12% so với 27% |
| Uống nước | Ganio và cộng sự, British Journal of Nutrition 2011 (26 người) | Mất nước nhẹ khoảng 1,6% cân nặng: tăng lỗi khi canh chừng, chậm trí nhớ làm việc, căng thẳng và mệt hơn |

```
» /break 45
Nhắc đứng dậy, đi lại, vươn vai, tập mắt 20-20-20 khi ngồi làm liên tục: ĐANG BẬT, mỗi 45 phút.
Đổi: /break on | /break off | /break 45 (số phút) | /break mac_dinh
(Nhắc sức khoẻ không phụ thuộc mức nhắc sao nhãng /nudge.)

» /water off
Nhắc uống nước trong giờ làm: ĐANG TẮT.
```

### 4.8 Chào buổi sáng, khích lệ (`/encourage`, `/quote`, `/bible`)

| Lúc | Gì |
|---|---|
| Lần đầu dùng máy trong giờ làm sau `plan_prompt_after` | Chào + câu trích (danh ngôn / Kinh Thánh / vì gia đình) + nối với việc đầu tiên hôm nay (từ `/tmrtask` hôm trước) và điểm tốt của ngày làm việc trước. Có nghỉ phép nửa ngày, ngày lễ trong 7 ngày tới thì thêm dòng cố định. Ngày làm việc trước (hoặc cuối tuần, ngày lễ xen giữa) có làm ngoài giờ: thêm dòng 🌙 kèm khoảng giờ và dòng ⏱ tổng OT 14 ngày (mục 1). Ngày làm việc trước còn việc tồn: thêm khối 📌 (bên dưới) |
| `afternoon_boost_at` (14:30), nếu đang dùng máy | Một câu khích lệ hợp tình hình (đang chậm thì động viên, đang tốt thì giữ nhịp). `""` = tắt |
| Sau nhắc sao nhãng | Xem mục 4.3 |
| `/resume`, `/quote`, `/bible`, nhắn tâm sự («mệt quá») | Một câu khích lệ theo tình huống |

| Chế độ | Lệnh | `encouragement_styles` |
|---|---|---|
| Tắt / bật tự gửi | `/encourage off` · `/encourage on` | `encouragement_enabled` |
| **Nút gạt Kinh Thánh** (bật ↔ tắt) | `/kinhthanh` (đảo), `/kinhthanh on`, `/kinhthanh off` | on = `["bible"]`, off = `["motivation", "family"]`. **Tắt** thì **mọi** tin (chào sáng, khích lệ, nhắc nhở, cảnh báo, đánh giá AI) chỉ dùng câu của người thành đạt, danh nhân, hiền triết xưa (Khổng Tử, Mạnh Tử, Seneca, Marcus Aurelius…), không câu Kinh Thánh nào, trừ khi bạn tự gõ `/bible` |
| Chỉ danh ngôn (không Kinh Thánh) | `/encourage quote` | `["motivation", "family"]` (**mặc định khi cài lần đầu**) |
| Chỉ Kinh Thánh | `/encourage bible` | `["bible"]` |
| Cả hai | `/encourage both` | `["motivation", "bible", "family"]` |
| Về settings.json | `/encourage mac_dinh` | |

| Kiểu | AI được dặn |
|---|---|
| `motivation` | Một câu nói nổi tiếng **có thật**, đúng tác giả, câu nước ngoài dịch tự nhiên |
| `bible` | Một câu Kinh Thánh **Tin Lành**, chỉ 66 sách, không dùng sách Thứ Kinh/Đệ Nhị Kinh, **nguyên văn bản Truyền Thống 1926**, ghi đúng sách chương câu (ví dụ Ga-la-ti 6:9) |
| `family` | Lời khích lệ vì gia đình, con cái |
| Kinh Thánh tắt | Lời dặn hệ thống của **mọi** lần gọi AI có câu «TUYỆT ĐỐI không dùng câu Kinh Thánh hay nội dung tôn giáo…, chỉ dùng châm ngôn người thành đạt, danh nhân, hiền triết xưa» (mục 7.3) |
| Mọi kiểu | Luôn tích cực: không chê trách, không nhắc thất bại, không doạ (kể cả giọng sếp khó tính). **Không lặp các câu đã gửi hôm nay và hôm qua**: app gửi kèm **nguyên văn** từng câu trích đã gửi trong 2 ngày đó (tối đa 30 câu, không cắt ngắn) |

**Việc còn tồn, cộng dồn** (`focus/pending.py`, không dùng AI nên luôn có): lời chào sáng có thêm khối liệt kê việc trong kế hoạch và issue **chưa thấy ghi xong**, cộng dồn qua các ngày làm việc. App chỉ biết những gì bạn ghi, nên tin ghi «chưa thấy ghi xong».

| Quy tắc | Cách làm |
|---|---|
| Việc tồn của một ngày | Việc trong kế hoạch chưa thấy trong output hôm đó + các issue đã ghi hôm đó |
| Coi là xong | Một dòng output (hôm đó hoặc ngày sau) chứa ≥ 60% từ có nghĩa của việc (bỏ dấu, bỏ số thứ tự). Issue hết tồn khi output ngày sau khớp với nó (ví dụ issue «thiếu quyền PRDLIB», output «đã có quyền PRDLIB») |
| Hôm qua chưa có cập nhật | Việc tồn hôm qua mà hôm nay không có dòng output nào khớp thì **thành việc tồn hôm nay**, giữ ngày bắt đầu tồn («tồn từ T3 13/10»). Ngày không ghi gì cũng giữ nguyên việc tồn |
| Trùng | Ghi lại cùng việc vào kế hoạch ngày sau không bị nhắc 2 lần (giữ ngày tồn đầu tiên) |
| Bỏ qua | Ngày nghỉ, cuối tuần, lễ. Việc tồn quá 10 ngày làm việc (khoảng 2 tuần) thì thôi nhắc |
| Hiện ở đâu | Lời chào sáng (tối đa 10 dòng, còn nữa thì «… và N việc nữa»), báo cáo HTML ngày (ô «📌 Việc tồn sang ngày mai»), đánh giá AI cuối ngày (`pending_carry`: mục «Việc pending cho ngày mai») |

```
📌 Việc còn tồn, cộng dồn từ các ngày trước (chưa thấy ghi xong):
• Đọc spec API, góp ý qua email (tồn từ T3 13/10)
• Gửi estimation UAT release
• ⚠️ issue: thiếu quyền PRDLIB, chờ anh A cấp (tồn từ T4 14/10)
Xong việc nào thì báo bot (ví dụ «xong gửi estimation») để bot ghi output. Chưa ghi xong thì mai bot nhắc tiếp.
```

Muốn bỏ một việc khỏi danh sách: báo bot là đã xong (bot ghi vào output), hoặc đợi quá 10 ngày làm việc.

Mỗi lần chọn kiểu ngẫu nhiên trong danh sách, tránh trùng kiểu lần trước. Không có AI / AI lỗi: dùng câu có sẵn trong code (danh ngôn, câu Kinh Thánh, câu vì gia đình), không trùng câu gần đây.

```
» /encourage
Tự gửi lời khích lệ (đầu ngày, buổi chiều 14:30, kèm cảnh báo): ĐANG BẬT.
Loại câu: danh ngôn, vì gia đình.
Đổi: /encourage on | off | quote (không Kinh Thánh) | bible (chỉ Kinh Thánh) | both

» /kinhthanh
📖 Kinh Thánh: BẬT. Lời chào buổi sáng và lời khích lệ dùng câu Kinh Thánh Tin Lành.
Gõ /kinhthanh lần nữa để đổi lại.

» /kinhthanh off
💬 Kinh Thánh: TẮT. Lời chào buổi sáng, lời khích lệ, nhắc nhở và đánh giá AI chỉ dùng châm ngôn của người thành đạt, danh nhân xưa; không tin nào dùng Kinh Thánh (trừ khi bạn tự xin /bible).

» /resume
Theo dõi lại rồi. "Có công mài sắt, có ngày nên kim." — Tục ngữ
```

### 4.9 Hỏi kế hoạch (`/plan`), hỏi tổng kết (`/review`)

| | Kế hoạch | Tổng kết cuối ngày |
|---|---|---|
| Tự hỏi | Lần đầu dùng máy trong giờ làm sau `plan_prompt_after`, nếu chưa có kế hoạch | Lần đầu dùng máy từ `review_prompt_at` (16:45) tới hết giờ làm, nếu hôm nay bạn chưa tự gõ `/review` tới câu cuối. Gõ `/energy` giữa ngày không làm mất câu hỏi này |
| Tự gõ | `/plan` (hỏi; đã có kế hoạch thì bot in kế hoạch đó trước, trả lời để thay, `/cancel` để giữ nguyên), hoặc `/plan nội dung` (ghi luôn, thay kế hoạch cũ) | `/review` |
| Xem lại | `/today` (mục 4.1), ngày cũ `/today hôm qua` | `/today` |
| Câu hỏi | «3 việc quan trọng nhất hôm nay là gì? Ghi rõ output cụ thể.» (kèm việc hôm qua hẹn làm trước, giờ vàng) | Lần lượt: việc đã xong · issue/blocker · điều làm mất tập trung · giờ vào/ra AS400 (bỏ nếu `as400_enabled: false`) · việc đầu tiên sáng mai · năng lượng 1–5 |
| Bỏ qua 1 câu | Gõ «bỏ qua» (hoặc `skip`, `-`, `/skip`) | |
| Dừng | `/cancel` | |
| Hết hạn chờ | Bạn tự gõ: 3 giờ. Bot tự hỏi theo lịch: 20 phút (để không "bắt" tin nhắn khác của bạn) | |
| Xong | «Đã lưu kế hoạch. Bắt đầu với việc số 1 trong 25 phút đầu tiên nhé.» | Gửi ngay tổng kết ngày (nếu chưa gửi), không chờ 17:00 |

Đang hỏi dở thì tin nhắn thường là câu trả lời, **kể cả khi bật `/ask on`**. Riêng lúc bot **tự** hỏi theo lịch mà bạn gõ một **câu hỏi**, câu đó được hiểu bình thường / gửi AI (mục 6.1). Câu trả lời cho «việc đã xong», «issue» được **nối thêm** vào các dòng đã ghi nhanh trong ngày (bot in lại phần đã ghi trước khi hỏi); AS400 và việc sáng mai đã ghi thì bot cho xem và hỏi có sửa không. Giờ AS400 phải có dạng giờ, năng lượng phải là số 1–5, sai thì bot hỏi lại. Lời hỏi kế hoạch nhắc việc đã hẹn: «Hôm qua bạn hẹn sáng nay làm trước: …» (hoặc «Hôm thứ Sáu 10/10 …»); lời hẹn chỉ tính nếu ghi trong 4 ngày gần đây và chưa có ngày làm việc nào khác (có kế hoạch / output) sau nó.

```
» /review
2026-10-14: chưa có dữ liệu.

Hôm nay bạn đã xong những gì?
(gõ "bỏ qua" để bỏ qua câu này, /cancel để dừng)
» xong fix job đối soát
Có issue / blocker gì không?
» VDI chậm buổi sáng
Điều gì làm bạn mất tập trung nhất?
...
Năng lượng hôm nay từ 1 đến 5?
» mệt quá
Gõ một số từ 1 đến 5 nhé (hoặc "bỏ qua").
```

### 4.10 Ghi chép nhanh trong ngày

| Lệnh | Ghi vào | Ví dụ | Bot trả |
|---|---|---|---|
| `/output nội dung` | `output` (nối dòng, kèm giờ) | `/output xong test CL0123` | «Đã ghi output.» |
| `/issue nội dung` | `issues` (nối dòng) | `/issue VDI chậm từ 9h` | «Đã ghi issue.» |
| `/distraction nội dung` | `distractions` | `/distraction Zalo nhóm`, hoặc nhắn tự nhiên «nãy giờ mình bận đi trông em bé khóc», «bị gọi đi họp gấp», «bị làm phiền liên tục» | Nhắn tự nhiên: thẻ xác nhận «Ghi điều làm mất tập trung: «...»», bấm ✅ OK |
| `/tmrtask nội dung` (`/mai`) | `tomorrow`: sáng mai bot nhắc đầu tiên, AI kiểm tra lời hẹn | `/tmrtask fix job đối soát` | «Đã ghi. Sáng mai mình nhắc việc này đầu tiên.» |
| `/energy 1-5` | `energy`: bạn **tự chấm** sức lực còn lại trong ngày (1 = kiệt sức, 5 = rất sung). Thường trả lời ở câu cuối của tổng kết 16:45. Không chấm thì 17:00 bot tự tính (bên dưới) | `/energy 4` | «Đã ghi năng lượng hôm nay: 4/5.» Sai số: «Năng lượng là một số từ 1 đến 5. Ví dụ: /energy 4» |
| `/plan nội dung` | `plan` | `/plan fix job, viết spec` | «Đã lưu kế hoạch hôm nay. Bắt đầu với việc số 1 nhé.» |

Năng lượng dùng để làm gì: AI tổng kết ngày và tuần đối chiếu nó với số liệu để tìm quy luật (ví dụ ngày năng lượng thấp đi cùng ít khối tập trung, nhiều lần ngồi yên 1–5 phút). Năng lượng **bạn tự chấm** góp 10% vào điểm tổng; **không** ảnh hưởng điểm tập trung, chuỗi ngày 🔥; năng lượng bot tự tính không vào điểm nào (mục 4.1, «Năng lượng có ảnh hưởng điểm không»). Xem lại mọi thứ đã ghi: `/today`, ngày cũ `/today hôm qua`.

**Bot tự tính năng lượng** (`focus/energy.py`): tới giờ tổng kết (`daily_summary_at`, 17:00) mà hôm đó bạn chưa chấm, bot tính từ số liệu tập trung, lưu lại (đánh dấu «bot tự tính») và gửi tin 🔋 kèm cách tính, ngay trước tin tổng kết. Tập trung càng sâu, càng lâu thì năng lượng càng cạn; sao nhãng, ngồi ngoài VDI không tốn sức tập trung nên còn dư.

```
tải (giờ)  = tập trung sâu + 0,5 × làm vụn trong VDI + 0,5 × phần quá 90 phút của mỗi khối làm liền
năng lượng = 5 − 4 × min(tải / energy_capacity_hours, 1)   → làm tròn, trong khoảng 1–5
```

| Thành phần | Vì sao |
|---|---|
| Sức tập trung tối đa `energy_capacity_hours` = 4 giờ | Mượn từ nghiên cứu luyện tập có chủ đích (Ericsson và cộng sự, 1993) quan sát nhạc công giỏi nhất chỉ luyện tập tập trung cao độ khoảng 4 giờ mỗi ngày. Đây là quan sát ở nhạc công, không phải số đo cho dân văn phòng, nên app dùng làm mặc định và cho đổi |
| Phần quá 90 phút của một khối làm liền × 0,5 | Làm liên tục không nghỉ thì sự chú ý giảm dần (vigilance decrement, nhịp ultradian khoảng 90 phút), nên làm liền dài tốn thêm sức |
| Làm vụn trong VDI × 0,5 | Giờ trong VDI không thành khối tập trung (đoạn ngắn, chuyển qua lại) vẫn tốn sức nhưng ít hơn. Hệ số 0,5 là giả định của app |
| Ngoài VDI, thu nhỏ VDI, ngồi yên, rời máy | Không cộng vào tải, nên ngày sao nhãng nhiều thì năng lượng còn dư |

| Ví dụ trong ngày | Tải | Năng lượng |
|---|---|---|
| Hầu như không vào VDI | 0h | 5/5 (còn rất sung) |
| Tập trung sâu 1h, làm vụn 1h | 1h 30m | 4/5 (còn khá) |
| Tập trung sâu 2h trong một khối 2h liền | 2h 15m | 3/5 (vừa phải) |
| Tập trung sâu 3h (hai khối 1h 30m), làm vụn 30m | 3h 15m | 2/5 (còn ít) |
| Tập trung sâu 4h trở lên | ≥ 4h | 1/5 (kiệt sức) |

```
🔋 Hôm nay bạn chưa chấm năng lượng nên mình tự tính: 1/5 (kiệt sức).
Cách tính: tập trung sâu 3h 00m + làm vụn trong VDI 1h 00m × 0,5 + làm liền quá 90 phút 30m × 0,5 = tải 3h 45m, so với sức tập trung tối đa 4h/ngày → 5 − 4 × 0,94 = 1,2.
Tập trung càng sâu, càng lâu thì năng lượng càng cạn; sao nhãng thì còn dư.
Thấy chưa đúng thì gõ /energy 1–5 để sửa, số bạn tự chấm luôn được ưu tiên.
```

| | |
|---|---|
| Sửa | Gõ `/energy 1–5` bất cứ lúc nào: số bạn chấm thay số bot tính. Đang trả lời tổng kết mà bot đã tự tính thì câu hỏi năng lượng ghi «Bot đã tự tính năng lượng hôm nay: 2/5», gõ số của bạn để thay hoặc «bỏ qua» để giữ |
| Xem | `/today`: «Năng lượng bot tự tính: 2/5» hoặc «Năng lượng tự chấm: 4/5». File HTML ghi «2 (bot tự tính)» |
| AI | Dữ liệu gửi AI có `"energy_source": "app_uoc_tinh"`, prompt dặn AI đây là số ước tính, không phải cảm nhận của bạn |
| Bật/tắt | `/autoenergy on`, `/autoenergy off`, `/autoenergy mac_dinh`; `/autoenergy` không kèm gì: xem công thức và số tính được lúc này. Settings: `energy_auto_enabled`, `energy_capacity_hours` |
| Gửi bù | Máy tắt lúc 17:00, sáng hôm sau gửi bù tổng kết thì tin ghi «Ngày 14/10 bạn chưa chấm…» |
| Không tính | Ngày không có số liệu, ngày nghỉ, hoặc bạn đã chấm |

Nhắn tự nhiên cũng được: «bị chặn vì thiếu quyền vào thư viện PRDLIB» → bot hiểu là ghi issue, hỏi lại, bấm ✅ OK mới ghi (mục 6). Câu có chữ «xem» («xem kế hoạch hôm nay», «xem năng lượng hôm qua») là xem, không ghi. Nếu cả ngày chưa ghi việc sáng mai, tin tổng kết 17:00 nhắc «Chưa ghi việc đầu tiên sáng mai. Gõ: /tmrtask nội dung».

### 4.11 Giờ AS400 (`/as400`, gửi ảnh)

| Cách | Làm gì |
|---|---|
| Gõ | `/as400 08:10 17:35` → «Đã ghi giờ AS400: 08:10 – 17:35.» Nhận `8h10`, `8:10`... Giờ ra trước giờ vào thì bị từ chối |
| Nhắn tự nhiên | «AS400 vào 8h10 ra 17h35» → hỏi lại, OK mới ghi |
| Gửi ảnh | Ảnh (hoặc file ảnh, ≤ 10 MB) màn hình spooled file / job log. AI tìm giờ **sớm nhất và muộn nhất của hôm nay** trong ảnh → bot hỏi lại trước khi ghi. Đang trong `/review` thì bấm OK xong chuyển sang câu kế |
| Tắt hỏi AS400 | `"as400_enabled": false` (bỏ câu AS400 trong `/review`) |
| Tắt gửi ảnh cho AI | `"as400_photo_ai": false`: gửi ảnh thì bot trả «Mình chưa đọc ảnh được (chưa bật AI đọc ảnh). Gõ giờ giúp mình: /as400 08:10 17:35» |

> ⚠️ Ảnh được gửi **nguyên văn** tới AI bên ngoài (Gemini/Claude). Xem cảnh báo ở mục 1.

### 4.12 Tổng kết ngày + AI đánh giá (17:00)

| Thứ tự gửi | Nội dung |
|---|---|
| 0 | Chưa chấm năng lượng: tin 🔋 năng lượng bot tự tính kèm cách tính (mục 4.10) |
| 1 | Số liệu hôm nay (như `/today`: điểm tổng, robot, số lần và trung bình mỗi lần thu nhỏ / ngồi yên / rời máy), năng lượng, kế hoạch, output, issue; chưa có `/tmrtask` thì nhắc. Cuối tin: khối 🌙 **OT 14 ngày gần nhất** (tổng + từng ngày có OT kèm khoảng giờ; không có OT thì bỏ khối này) |
| 2 | **🤖 AI đánh giá cuối ngày**: 7 mục, tối đa 19 dòng: **điểm tổng hôm nay** (bắt buộc: điểm, thang 10, mức, robot, giải thích từng thành phần, phần kéo điểm xuống, cách tăng điểm; rồi so mục tiêu, 7 ngày trước, làm ngoài giờ nếu có) · việc pending cho ngày mai · mất tập trung vì đâu · cần khắc phục (issue lặp lại, sát bối cảnh AS400/COBOL/Life Asia) · ngày mai cải thiện (điểm tổng dưới 50: thêm một câu khoa học có sẵn, mục 4.1) · câu khích lệ · **lời chúc buổi tối** bên gia đình |
| 2' | AI tắt (`/aireview off`) hoặc không có key: chỉ gửi **lời chúc có sẵn** (không có đánh giá soạn sẵn). AI lỗi tạm thời: báo một lần «AI chưa đánh giá được hôm nay (...). Mình sẽ tự gửi khi AI dùng lại được.» rồi cứ 15 phút thử lại (ngày trong 2 ngày gần đây) |
| 3 | File báo cáo HTML (có chèn lời AI, mục 4.22) |

| | |
|---|---|
| Khi nào | `daily_summary_at` (17:00), hoặc ngay khi bạn trả lời xong `/review`, hoặc gửi bù sáng hôm sau |
| Lời chúc | Thứ 2 – thứ 5: chúc buổi tối. Thứ 6 (và thứ 7, CN nếu có): chúc cuối tuần |
| Bật/tắt AI | `/aireview on` · `/aireview off` · `/aireview mac_dinh`; settings: `ai_review_enabled` |
| Cache | Lời AI lưu trong `ai_cache` theo ngày + băm dữ liệu: dữ liệu không đổi thì không gọi AI lại |

```
» /aireview
AI tự đánh giá cuối ngày (17:00) và cuối tuần: ĐANG BẬT. Nhưng chưa có API key AI nên chưa có đánh giá AI, bot chỉ gửi số liệu (xem README phần AI).
Đổi: /aireview on hoặc /aireview off
```

### 4.13 Tổng kết tuần + AI (`/week`)

| | |
|---|---|
| Khi nào | `weekly_report_day` (`fri`) lúc `weekly_report_at` (16:50). Lỡ (máy tắt, thứ Sáu nghỉ) thì gửi bù lần mở máy kế. `/week` xem bất cứ lúc nào |
| Nội dung | Tổng giờ tập trung sâu, trung bình/ngày, số ngày đạt, điểm tập trung TB, **điểm tổng TB**, giờ làm ngoài giờ (cả làm bù ngày nghỉ, dòng «Làm bù ngày nghỉ»), chuỗi, ngày tốt/kém nhất, giờ vàng, từng ngày, khối 🌙 **OT 14 ngày gần nhất** + **🤖 AI tổng kết tuần** (9 mục, tối đa 24 dòng: **điểm tổng của tuần** (bắt buộc: điểm tổng trung bình nghĩa là gì, thành phần trung bình, ngày cao / thấp nhất và vì sao, phần kéo điểm xuống, tuần sau cải thiện gì), đánh giá chung, ngày tốt/kém, việc xong/pending, issue lặp lại, quy luật mất tập trung, mục tiêu tuần sau, câu khích lệ, **lời chúc**: cuối tuần nếu tuần tính tới thứ Sáu trở đi, chúc buổi tối nếu xem `/week` giữa tuần) |
| AI đọc gì | Báo cáo đầy đủ **từng ngày** (số liệu, kế hoạch, output, issue, phân tâm, năng lượng, giờ AS400, việc hẹn sáng mai, lời AI đánh giá đã gửi hôm đó), ngày nghỉ, tuần trước để so sánh (mục 7.4) |
| File | Sau lời AI: file **báo cáo tuần HTML** `reports/focus-week-YYYY-Www.html` (mục 4.22), cả khi gõ `/week` |
| AI lỗi | Như tổng kết ngày; thử lại cho tuần trong 9 ngày gần đây. Không AI: lời chúc có sẵn (cuối tuần nếu từ thứ Sáu, buổi tối nếu `/week` giữa tuần) |

```
Tuần 2026-W42 (10-12 → 10-14)
Tập trung sâu: 12.3h, trung bình 4.1h/ngày
Đạt mục tiêu: 2/3 ngày · điểm TB 93 · điểm tổng TB 84 · làm ngoài giờ 0.7h
Chuỗi hiện tại: 2 ngày
Ngày tốt nhất: Thứ 4 10-14 (4.1h) · kém nhất: Thứ 2 10-12 (3.8h)
Giờ vàng: 09:00–10:00, 10:00–11:00

Từng ngày:
  10-12 3.8h điểm 89 điểm tổng 79
  10-13 4.4h điểm 95 điểm tổng 84
  10-14 4.1h điểm 96 điểm tổng 90
```

### 4.14 Giờ vàng (`/golden`)

| | |
|---|---|
| `golden_hours: "auto"` | 2 khung 1 giờ có nhiều phút làm trong VDI nhất trong 14 ngày làm việc gần nhất. Cần ≥ 5 ngày có số liệu |
| Tự đặt | `["09:00-11:00"]`; `[]` = tắt |
| Tác dụng | Trong giờ vàng nhắc sao nhãng sớm hơn (`golden_nudge_minutes` 5 phút, mức vừa / nghiêm); gợi ý chặn lịch Outlook trong lời hỏi kế hoạch, tổng kết tuần |

```
» /golden
Chưa đủ số liệu (cần ít nhất 5 ngày làm việc) để tìm giờ vàng.
(khi đủ) Giờ vàng của bạn (14 ngày gần nhất): 09:00–11:00. Đặt một lịch "Focus" lặp lại vào khung này trong Outlook để người khác khó xếp họp.
```

### 4.15 Nghỉ phép, ngày nghỉ, tạm dừng

| Lệnh | Làm gì |
|---|---|
| `/leave sang` · `/leave chieu` · `/leave ca ngay` (`/nghiphep`), kèm ngày và lý do | Nghỉ phép. Không ghi buổi = cả ngày |
| `/off [ngày] [lý do]` | Báo nghỉ cả ngày (như `/leave ca ngay`) |
| `/on [ngày]` | Huỷ ngày nghỉ / nghỉ phép |
| `/pause` · `/resume` | Tạm dừng / theo dõi lại (họp dài, việc riêng). Đang tạm dừng: không lấy mẫu, không cảnh báo, bỏ mốc tiến độ; tổng kết ngày / tuần và hỏi tổng kết vẫn gửi đúng giờ. Sang ngày mới thì tự bỏ tạm dừng của hôm trước |
| `extra_off_days` | Ngày nghỉ cố định trong settings.json, ví dụ `["2026-12-24"]` |
| `run_on_off_days: true` | Lịch tự bật cũng chạy cả ngày nghỉ (không nhắc), ghi giờ làm bù trong VDI như khi bạn tự bật |
| `lam_bu_ngoai_gio.bat` / `start_tracker.bat` (bạn tự bật) | Ngày nghỉ vẫn chạy: chỉ ghi giờ làm trong VDI (làm bù), không nhắc, không tính sao nhãng, không chấm điểm. Làm xong (đã qua `work_end` và 30 phút không làm trong VDI) bot gửi ngay **🌙 Tổng kết làm bù** (giờ OT, khoảng giờ, OT 14 ngày, file HTML), một lần mỗi ngày. Máy ngủ / tắt trước đó thì sáng ngày làm việc kế tiếp bot báo (mục 1, «Giờ làm chính thức và làm thêm ngoài giờ»). Buổi nghỉ phép nửa ngày thì vẫn không đo |

| Loại nghỉ | Không đo, không nhắc | Việc theo giờ | Mục tiêu |
|---|---|---|---|
| **Buổi sáng** | Tới hết `lunch_end` | Chào + hỏi kế hoạch dời tới lần đầu dùng máy buổi chiều; tổng kết giữ giờ cũ | Một nửa |
| **Buổi chiều** | Từ `lunch_start` | Tổng kết ngày (và tuần nếu là ngày gửi tuần) gửi lúc `lunch_start`; hỏi tổng kết sớm hơn chừng đó (mặc định 15 phút, tối đa 60); bỏ câu khích lệ 14:30 | Một nửa |
| **Cả ngày** (`/leave ca ngay`, `/off`) | Cả ngày | Tracker không chạy. Báo `/off` cho hôm nay khi đang chạy: dừng ngay, nhắn 1 câu, tắt; hôm sau tự bật | — |

Tình huống:

```
» /leave chieu 2026-12-24 đi khám
Đã ghi 2026-12-24: nghỉ phép buổi chiều (đi khám). Không theo dõi từ 11:15; tổng kết ngày gửi lúc 11:15. Mục tiêu ngày đó còn 2h. Huỷ: /on 2026-12-24

» /on 2026-12-24
Đã huỷ nghỉ phép buổi chiều. 2026-12-24 là ngày làm việc, mình nhắc như bình thường.

» /off 2026-12-31 nghỉ phép năm
Đã ghi 2026-12-31 là ngày nghỉ (nghỉ phép năm), mình không nhắc gì ngày đó. Đổi ý thì gõ /on 2026-12-31

» /pause
Đã tạm dừng theo dõi. Gõ /resume khi quay lại.
```

**Cách ghi ngày** (dùng cho `/leave`, `/off`, `/on` và tin nhắn tự nhiên; bỏ trống = hôm nay):

| Dạng | Ví dụ |
|---|---|
| ISO | `2026-12-24` |
| Ngày/tháng(/năm) | `24/12`, `24/12/2026`, `24/12/26`, `24.12` (không ghi năm mà ngày đã qua hơn 180 ngày thì hiểu là năm sau) |
| Chữ | `20 tháng 10` |
| Tương đối | `hôm nay`, `mai`, `ngày kia`, `mốt` (có dấu hay không dấu đều được) |
| Thứ | `thứ 2` … `thứ 7`, `CN` / `chủ nhật`: lần tới gần nhất (hôm nay đúng thứ đó thì là hôm nay); `thứ 6 tuần sau` / `tuần tới` = thứ 6 của tuần kế |
| Viết giống ngày mà không đọc được | Bị từ chối kèm ví dụ (không tự hiểu thành hôm nay) |

Nhắn tự nhiên: «hôm nay mình nghỉ nửa ngày sáng», «chiều nay nghỉ phép», «mai nghỉ phép cả ngày», «thứ 6 nghỉ buổi chiều», «huỷ nghỉ chiều nay», «mai mình xin nghỉ phép». «nghỉ nửa ngày» (không nói buổi) → bot hỏi «Nghỉ nửa ngày buổi sáng hay buổi chiều?…». Báo nghỉ cho một ngày đã qua thì số liệu ngày đó được tính lại. Lệnh `/off`, `/on`, `/leave` có hiệu lực ngay (tracker đọc lại ở vòng kế).

### 4.16 Ngày lễ Singapore, cuối tuần

| | |
|---|---|
| Cuối tuần | Lịch tự bật không chạy (trừ `run_on_off_days: true`), thoát im lặng. Bạn tự bật (`lam_bu_ngoai_gio.bat`) thì chạy, chỉ ghi giờ làm bù trong VDI (cả giờ trưa), cuối buổi gửi 🌙 tổng kết làm bù (mục 4.15) |
| Ngày lễ | Lịch tự bật: tracker thoát ngay khi khởi động, nhắn 1 câu. Máy để qua đêm sang ngày lễ cũng tự tắt. Bạn tự bật: chạy như cuối tuần |
| Nghỉ bù | Lễ rơi **Chủ nhật** → thứ Hai nghỉ (thứ Hai cũng là lễ → thứ Ba). Nếu thứ Hai đó đã có sẵn trong lịch là ngày bù (tên có "observed" / "in lieu" / "nghỉ bù", hoặc lịch lấy từ file timesheet vốn liệt kê sẵn ngày bù) thì không dời thêm. Lễ rơi thứ Bảy → không tự nghỉ; tự chọn ngày bù bằng `/off` |
| Nguồn lịch (theo thứ tự) | (1) `data/holidays_<năm>.json` · (2) `sg_holidays_<năm>.json` trong `timesheet_data_dir` (app khác đã tải) · (3) trang MOM `mom_holidays_url` · (4) bảng năm 2026 có sẵn trong code (11 ngày) |
| Tải MOM | Ở nền, tối đa 1 lần/ngày, chỉ khi máy chưa có lịch năm đó; từ 1/12 tải luôn năm sau. Năm nay chưa có lịch nào: lúc khởi động chờ tải tối đa 20 giây |
| Đọc trang MOM | Theo mốc `id="Year-NNNN"` và năm của chính các ngày; bảng lẫn năm → bỏ; đọc ra dưới 5 ngày → bỏ (đọc sai trang) |
| Thiếu lịch | Coi như không có lễ, ghi cảnh báo, không sập. Qua 15/12 chưa có lịch năm sau → nhắn 1 lần |
| Tắt tải | `"holiday_fetch_enabled": false` |
| Xem | `/status`: nguồn lịch và lễ tới. Lời chào sáng báo lễ trong 7 ngày tới |

### 4.17 Hỏi AI (`/ask`, `/hoi`)

| Cách | Làm gì |
|---|---|
| `/ask câu hỏi` | Hỏi nhanh 1 câu |
| `/ask on` | Mọi tin nhắn thường (không phải lệnh) đều gửi AI; trả lời kèm «(Đang ở chế độ hỏi AI: /ask off để tắt)» |
| `/ask off` | Tắt; tin nhắn thường lại được hiểu thành thao tác |
| Nhắn câu hỏi tự nhiên | «giá vàng hôm nay bao nhiêu?» → hiểu là `hoi_ai`, trả lời luôn (không cần OK) |
| Nhắn «bật chế độ hỏi AI» / «tắt chế độ hỏi AI» | Bật/tắt qua thẻ xác nhận (bấm ✅ OK); lệnh `/ask on`, `/ask off` thì chạy ngay |

| | |
|---|---|
| AI biết | Tên, tuổi, nơi sống, mô tả trong persona, công việc (`work_context`), giờ làm, giờ hiện tại, thứ, số liệu tập trung hôm nay |
| Tra web | Gửi kèm công cụ tìm kiếm: Gemini `google_search`, Claude `web_search` (tối đa 3 lần). Gói Gemini free cho tra Google **rất ít lượt, tính riêng** với lượt hỏi thường (Gemini 3.x: 0 lượt). Hết lượt tra web (lỗi 429), hoặc model không hỗ trợ: app hỏi lại ngay **cùng model, không tra web**, AI nói rõ lần này không tra được web nên không có số liệu mới (giá vàng, tin tức). Log ghi nguyên lời Google trả |
| Model không còn | Model trả lỗi 404 (Google ngừng cho tài khoản mới, ví dụ `gemini-2.0-flash-lite`): app nhớ 30 ngày và bỏ qua model đó; `/aistatus` liệt kê |
| Trí nhớ | **Mỗi câu độc lập**: AI không thấy câu trước |
| Không có key | «Chưa có API key AI nên mình chưa trả lời được. Xem README mục 2.3 để thêm key (GEMINI_API_KEY trong config/secrets.env).» |

### 4.18 Trạng thái (`/status`), AI đã dùng (`/aistatus`), hiệu năng (`/perf`)

`/status` gồm 5 phần (chạy thật, máy chưa có key AI):

```
📍 LÚC NÀY
Tracker chưa có mẫu nào (tracker chưa chạy hoặc vừa khởi động).

📊 HÔM NAY
Chưa có số liệu hôm nay.
Tiến độ: làm thật trong VDI 0m / cần khoảng 1h 22m lúc này (chậm ⚠️) · chi tiết: /pace
Ghi chú: kế hoạch ✗ · output 0 · issue 0 · việc sáng mai ✗

⚙️ CÀI ĐẶT
Bot bật 08:00 – tắt 23:59 (thứ 2 – thứ 6) · /giobot
Giờ làm 08:00–17:00, trưa 11:15–12:30 · rời máy 15' · nhắc nghỉ (/break): 60' · uống nước (/water): 60'
Nhắc sao nhãng: vừa (1 lần mỗi lần sao nhãng) (/nudge) · Cảnh báo tiến độ: bật, mốc 10:30, 14:00, 15:30, mục tiêu 6h VDI (/pace)
AI đánh giá ngày/tuần: bật (/aireview) · Khích lệ tự động: bật [bible] (/encourage)
Giọng: than_mat (/style) · Hỏi AI: tắt (/ask) · Gọi bạn là “bạn”
Lịch lễ 2026: bảng có sẵn trong app (chưa tải được bản MOM) · lễ tới: Deepavali 08/11

🤖 AI
AI: chưa cấu hình key, đang dùng nội dung có sẵn.

🖥️ HỆ THỐNG
Dung lượng app: 137.1 KB (DB 136.6 KB, backup 0 B, log 489 B) · tự dọn mỗi ngày · phiên bản 2.5.1
```

Khi tracker đang chạy: "LÚC NÀY" cho biết trong VDI / VDI thu nhỏ / nằm sau / không thấy / máy khoá, app đang dùng, số giây chưa chạm phím, hôm nay nghỉ hay nghỉ phép; "HÔM NAY" thêm số liệu, điểm, số lần sao nhãng và số lần đã nhắc từng loại (đếm từ `audit.log`); "HỆ THỐNG" thêm cách đọc trạng thái máy (Win32 / CoreGraphics), cảnh báo nhận diện VDI (tối đa 5), CPU/RAM.

Phần AI khi có key (từ `ai_client.status_text`): provider và model gần nhất · số lượt, số **từ** gửi/nhận hôm nay và tháng này · hôm nay dùng cho việc gì (hiểu tin nhắn, đánh giá ngày, hỏi AI...) · hạn mức tự đặt `ai_daily_call_budget` còn bao nhiêu · với Gemini: từng model `đã gọi/quota (còn ~N | hết)`, quota lấy từ `gemini_free_calls_per_model`. `/aistatus` chỉ in phần AI.

`/perf`: CPU, RAM tracker đang dùng (đo mỗi 10 phút; mới chạy thì «Chưa đo xong, đợi 10 phút sau khi tracker chạy.»).

**Đo CPU/RAM từ máy (không qua bot)**

| Cách | Làm gì | Kết quả (số ví dụ) |
|---|---|---|
| Nhấp đúp `xem_cpu_ram.bat` (Mac: `xem_cpu_ram.command`) khi tracker đang chạy | Đo tracker trong 10 giây | `PID 1234 \| RAM 31.5 MB \| CPU 0.012 phan tram ca may (trung binh 10 giay) \| tong CPU 4.2 giay \| chay tu 14/10/2026 08:00:05` |
| Gõ lệnh vào **cmd** (Windows) | Copy nguyên dòng bên dưới, dán vào cmd, Enter | Như trên |
| Xem nhanh RAM (cmd) | `tasklist /fi "imagename eq python.exe"` | Cột *Mem Usage*. Lưu ý: liệt kê **mọi** `python.exe` đang chạy, không chỉ tracker |
| Task Manager | Ctrl+Shift+Esc > tab *Details* > `python.exe` (chuột phải tiêu đề cột > *Select columns* > *Command line* để thấy dòng `focus_tracker.py run`) | Cột *CPU*, *Memory* |
| Mac (Terminal) | `ps -o pid,%cpu,rss,etime,command -p $(pgrep -f "focus_tracker.py run")` | `%CPU`, `RSS` (KB) |

Lệnh cmd (một dòng, chạy được trên Windows 10/11 có sẵn PowerShell 5.1, không cần quyền admin):

```
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*focus_tracker.py*run*' }); if ($ps.Count -eq 0) { 'Tracker chua chay.' } else { foreach ($w in $ps) { $p = Get-Process -Id $w.ProcessId; $c1 = $p.CPU; Start-Sleep -Seconds 10; $p.Refresh(); $cpu = ($p.CPU - $c1) / 10 / [Environment]::ProcessorCount * 100; 'PID {0} | RAM {1:N1} MB | CPU {2:N3} phan tram ca may (trung binh 10 giay) | tong CPU {3:N1} giay | chay tu {4}' -f $p.Id, ($p.WorkingSet64 / 1MB), $cpu, $p.CPU, $p.StartTime } }"
```

| Cột | Nghĩa |
|---|---|
| `RAM` | Bộ nhớ tiến trình tracker đang giữ (Working Set, MB) |
| `CPU ... phan tram ca may` | % CPU của **cả máy** (mọi nhân) tracker dùng trung bình trong 10 giây đo. Tracker ngủ giữa các lần đo 5 giây nên số này thường rất nhỏ |
| `tong CPU` | Tổng số giây CPU tracker đã dùng từ lúc bật |
| `Tracker chua chay.` | Không thấy tiến trình `python ... focus_tracker.py run` (chưa tới 08:00, ngày nghỉ, hoặc chưa cài tự khởi động) |

### 4.19 Giọng văn, xưng hô (`/style`, `persona.json`)

| Giọng (`giong`) | AI được dặn |
|---|---|
| `than_mat` (mặc định) | Thân mật, ấm áp như một người bạn thân |
| `vui_tuoi` | Vui tươi, nhiều năng lượng, tích cực, có thể 1 emoji |
| `hai_huoc` | Hài hước, dí dỏm, chọc nhẹ nhưng không xúc phạm, vẫn có ý khuyên rõ |
| `sep_kho_tinh` | Ông sếp 60 tuổi khó tính, lạnh lùng, nói ngắn, không emoji, không khen suông; không xúc phạm, không chửi thề |

Giọng áp dụng cho cả câu bot tự viết (câu mở đầu cảnh báo) và câu AI viết. Cách xưng hô (`goi_nguoi_dung`, `bot_xung`) được thay vào mọi tin. Đổi nhanh: `/style hai_huoc`, «nói chuyện kiểu sếp khó tính đi»; `/style mac_dinh` về `persona.json`. Cách điền `persona.json`: mục 2.4 bước 6; các khoá: mục 11.3.

### 4.20 Giờ bot tự bật / tự tắt (`/giobot`, `/hours`)

| Gõ | Việc |
|---|---|
| `/giobot` | Xem giờ đang dùng |
| `/giobot 08:30 18:00` | Đổi cả hai |
| `/giobot bat 08:30` · `/giobot tat 19:00` | Đổi một |
| `/giobot mac_dinh` | Về giờ trong settings.json trước lần đổi đầu tiên qua Telegram |
| «bật bot lúc 8 rưỡi», «tắt bot lúc 6 giờ chiều», «cho bot chạy từ 8h đến 18h» | Nhắn tự nhiên: bot hỏi lại, OK mới đổi. Nhận `08:30`, `8:30`, `8h30`, `8h`, `8 rưỡi`, `6 giờ chiều` (= 18:00) |

| Kiểm tra | Nếu sai |
|---|---|
| Giờ bật trước giờ tắt | Từ chối |
| Giờ tắt sau `daily_summary_at`, `weekly_report_at`, `review_prompt_at`, `plan_prompt_after` | Từ chối (tắt sớm hơn thì không kịp gửi tổng kết) |
| Giờ bật muộn hơn `work_start` | Vẫn đổi, kèm cảnh báo: trước giờ bật không đo, không nhắc |

| Đổi xong | Hiệu lực |
|---|---|
| Bot đang chạy | Giờ tắt: ngay (giờ tắt mới đã qua: chốt số liệu rồi tắt luôn). Giờ bật mới muộn hơn bây giờ: hôm nay vẫn chạy |
| `config/settings.json` | Ghi `auto_start_at`, `auto_stop_at`, giữ nguyên dòng khác, bản cũ ở `settings.json.bak` |
| Windows | Tự sửa giờ trong task FocusTracker (PowerShell COM, dự phòng `schtasks`), không cần admin; từ ngày làm việc tới. Không sửa được thì bot báo: chạy lại `cai_tu_khoi_dong.ps1` |
| Mac | Ghi giờ mới vào `StartCalendarInterval` trong plist (không gọi `launchctl`): áp dụng từ lần đăng nhập / khởi động lại máy tới. Muốn ngay: chạy lại `bash cai_tu_khoi_dong_mac.sh` |

```
» /giobot 08:30 16:00
Giờ tắt 16:00 phải sau giờ gửi tổng kết ngày (17:00), nếu không bot tắt trước khi kịp gửi tổng kết ngày. Chọn giờ tắt sau 17:00, hoặc đổi "daily_summary_at" trong settings.json.
Ví dụ: /giobot 08:30 18:00

» /giobot 08:30 18:00
✅ Giờ bot mới: bật 08:30 – tắt 18:00 (thứ 2 – thứ 6).
⚠️ Giờ bật 08:30 muộn hơn giờ bắt đầu làm (08:00): từ 08:00 tới 08:30 bot chưa chạy nên không đo, không nhắc, không hỏi gì.
Hôm nay bot tắt lúc 18:00.
```

(Khi chạy thật, dòng cuối cho biết đã sửa lịch tự bật của máy hay chưa.)

### 4.21 Gửi bù, tin nhắn cũ, báo lỗi

| Tình huống | Bot làm |
|---|---|
| Hôm qua máy tắt trước 17:00 | Lần khởi động kế: «📌 Gửi bù tổng kết ngày ... (hôm đó máy tắt trước giờ tổng kết):» (ngày làm việc gần nhất có số liệu, trong 7 ngày) |
| Tuần trước chưa gửi tổng kết tuần | Gửi bù «📌 Gửi bù tổng kết tuần ...» |
| Tin nhắn gửi lúc app tắt (cũ hơn 1 giờ khi đọc) | Ghi vào **ngày bạn gửi**, kèm «(Tin nhắn gửi lúc ... khi app chưa chạy, nên mình ghi vào ngày ...)». `/pause`, `/resume` cũ thì bỏ qua |
| Telegram lỗi lúc gửi tổng kết | Gỡ dấu "đã gửi" để lần sau gửi lại, không mất tổng kết |
| AI lỗi lúc đánh giá | Mục 4.12 |
| Việc chạy nền lỗi | «⚠️ Không làm được «tổng kết cuối ngày»: <lý do dễ hiểu>.» tối đa 1 lần/giờ mỗi việc |
| Xử lý tin nhắn lỗi | «⚠️ Mình chưa làm được việc vừa rồi: <lý do>. Bạn thử lại, hoặc dùng lệnh (/help xem danh sách).» |
| Lệnh không có | «Không có lệnh này.» + danh sách lệnh |

### 4.22 Báo cáo HTML (`/report`)

Bảng màu «Pop Art cổ điển»: nền kem, chữ đen, viền và bóng nâu đậm. Màu cố định cho từng loại thời gian, dùng chung ở mọi ô, thanh dòng thời gian, biểu đồ, bảng:

| Màu | Mã | Loại thời gian |
|---|---|---|
| Xanh lá rêu | `#3D8A6F` | Tập trung sâu |
| Xanh lam xám | `#4A8A9E` | Trong VDI (chưa thành khối sâu) |
| Cam | `#DD814B` | Ngoài VDI |
| Vàng mù tạt | `#DFAB36` | VDI thu nhỏ |
| Xám ấm | `#9E938B` | Ngồi yên |
| Đỏ gạch | `#C35850` | Rời máy |

| | Báo cáo ngày | Báo cáo tuần |
|---|---|---|
| Tạo | `/report` (gửi file qua Telegram), `/report hôm qua`, `/report 14/10` (cách gõ ngày như mục 4.15), tổng kết 17:00, `bao_cao_hom_nay.bat`, `python focus_tracker.py report [YYYY-MM-DD]`. Ngày nghỉ có làm bù: gửi cùng 🌙 tổng kết làm bù (mục 4.15) | Tổng kết tuần (thứ Sáu 16:50) và `/week` |
| Ở đâu | `reports/focus-YYYY-MM-DD.html` | `reports/focus-week-YYYY-Www.html` (ví dụ `focus-week-2026-W42.html`) |
| Phần đầu | **Điểm tổng** thật to + robot quà tặng trong vòng tròn chấm bi, mức (kém / HG / RG / MG / PG), thanh từng thành phần (bao nhiêu điểm, góp bao nhiêu), phần kéo điểm xuống nhiều nhất, cách tăng điểm, **thang 5 robot** (robot hôm nay được tô nổi) | **Điểm tổng trung bình tuần** + robot, thành phần trung bình, ngày cao / thấp nhất, **bộ sưu tập robot** từng ngày |
| Ô số liệu (6 ô màu) | Tập trung sâu (so mục tiêu), trong VDI, ngoài VDI (số lần rời, **TB mỗi lần**), thu nhỏ VDI (số lần, **TB mỗi lần**), ngồi yên (số lần, **TB mỗi lần**), rời máy (số lần, **TB mỗi lần**). «TB mỗi lần» = trung bình một lần kéo dài bao lâu, không phải trung bình cả ngày | Cùng 6 ô, cộng cả tuần; thêm TB mỗi ngày |
| Thẻ lớn nền kem (dải màu trên đầu) | Điểm tập trung, OT (khoảng giờ), khối tập trung dài nhất, bị cắt ngang mỗi giờ, inactive / rời máy ≥ 10 phút, chuỗi ngày đạt mục tiêu, VDI bị đóng / tự ngắt. **OT = 0 thì không hiện thẻ OT**; các thẻ khác = 0 vẫn hiện | Điểm tập trung TB, ngày đạt mục tiêu, OT cả tuần (ẩn nếu 0), khối dài nhất, inactive ≥ 10 phút, chuỗi; chip nhỏ: giờ vàng, ngày nhiều / ít nhất |
| Dòng thời gian | Thanh màu cả ngày, có vạch giờ. Chú thích đủ mọi màu, kể cả **sọc mờ = nghỉ trưa (không tính)** và **trắng = không ghi** (trước khi bắt đầu / sau khi ngừng dùng máy, hoặc ngoài giờ làm mà không làm trong VDI) | Mỗi ngày một thanh, cùng chú thích |
| Bảng, biểu đồ | Khối tập trung (cột «Ngoài giờ»), app ngoài VDI (không có Citrix), biểu đồ theo giờ, 7 ngày gần nhất | Biểu đồ tập trung sâu mỗi ngày có vạch mục tiêu, bảng 12 cột từng ngày, app ngoài VDI cả tuần |
| **OT 14 ngày** | Tổng OT + mỗi ngày có OT một thanh sọc: ngày, số giờ, khoảng giờ. Ngày không OT không ghi; 14 ngày không có OT thì một dòng «14 ngày qua không có ngày nào làm ngoài giờ trong VDI.» | Như báo cáo ngày |
| Ghi chú | Kế hoạch, output, issue, sao nhãng (kèm trung bình 14 ngày: giờ sao nhãng mỗi ngày, số lần thu nhỏ, giờ hay sao nhãng nhất), năng lượng (chấm 1–5, ghi «bot tự tính» nếu bạn chưa chấm), việc ngày mai, giờ AS400, **📌 Việc tồn sang ngày mai** (cộng dồn, ghi ngày bắt đầu tồn, mục 4.8) | Output, issue, sao nhãng, năng lượng, giờ AS400 cả tuần |
| AI | Mục «Lời khuyên của AI» luôn có: lời AI đánh giá cuối ngày, hoặc dòng giải thích vì sao chưa có (chưa tới 17:00, `/aireview` tắt, chưa có key). Báo cáo mẫu có lời AI **mẫu** ghi rõ là mẫu | «Đánh giá tuần của AI», cùng cách |
| Cuối trang | «Cách tính điểm và căn cứ khoa học» (bấm để mở): công thức bằng số của ngày đó, các nghiên cứu (mục 4.1) | Như báo cáo ngày |
| Ngày nghỉ | Chỉ 3 ô (giờ làm bù, tập trung sâu, khối dài nhất), dòng thời gian, OT 14 ngày; **không chấm điểm** | Ngày nghỉ có làm bù hiện riêng (giờ làm bù thay cho robot), không tính vào điểm TB |

| | |
|---|---|
| Giữ file | `keep_reports_days` (30) ngày, tự xoá file cũ (tạo lại được từ DB) |
| Mở bằng | Trình duyệt bất kỳ, kể cả trên điện thoại (tự xếp 3 hoặc 2 cột khi màn hình hẹp). File tự chứa hết, không tải gì từ mạng |
| Robot | Tự vẽ bằng SVG trong `focus/robots.py`, chỉ lấy cảm hứng từ các mức HG / RG / MG / PG; không phải hình Gundam / Bandai thật (bản quyền) |
| Mẫu | `sample/bao-cao-mau.html` (ngày), `sample/bao-cao-tuan-mau.html` (tuần); `python focus_tracker.py demo` tạo cả hai từ dữ liệu giả trong `data/demo` |
| Làm mới tự động | `report_refresh_minutes` > 0: tracker ghi lại file mỗi N phút (mặc định 0 = chỉ khi cần) |

---

## 5. Danh sách lệnh

### 5.1 Lệnh Telegram

Bảng dưới đây **sinh tự động từ `focus/actions.py`** (danh sách `ACTIONS`, nhóm `HELP_GROUPS`, ví dụ `EXAMPLES`), cùng nguồn với menu lệnh và `/help` của bot.

- Lệnh gạch chéo (`/giobot 08:30 18:00`, `/leave chieu`) **chạy ngay, không hỏi lại**, vì không cần đoán ý.
- Nhắn tự nhiên mà có ghi / đổi dữ liệu thì bot gửi **thẻ xác nhận**, bấm ✅ OK mới làm (cột "cần OK?"). Xem mục 6.
- `/help` (`/start`) in mọi tính năng và mọi lệnh kèm ví dụ. Gõ lệnh không có: «Không có lệnh này.» + danh sách lệnh.
- `/skip`: trong lúc bot hỏi từng câu (`/plan`, `/review`), bỏ qua câu đang hỏi (như gõ «bỏ qua»).
- Lệnh kèm tham số sai: bot nói lỗi + ví dụ đúng, ví dụ `/energy 9` → «Năng lượng là một số từ 1 đến 5. Ví dụ: /energy 4».

**📊 XEM SỐ LIỆU**

| Lệnh | Action | Tham số | Nhắn tự nhiên cần OK? | Làm gì | Ví dụ |
|---|---|---|---|---|---|
| `/today` `/score` | `xem_hom_nay` | `day` (pastdate, tuỳ chọn) | không | Giờ tập trung sâu, trong/ngoài VDI, điểm, streak, kế hoạch đầu ngày, năng lượng, output, issue. Kèm ngày để xem lại ngày đã qua | `/today` · `/today hôm qua` · `/today 14/10` · «hôm nay mình tập trung được bao nhiêu rồi» · «xem kế hoạch hôm nay» |
| `/status` | `xem_trang_thai` | — | không | Tình trạng đầy đủ: lúc này trong hay ngoài VDI, số liệu hôm nay, số lần đã nhắc, cài đặt, AI đã dùng bao nhiêu lượt/từ, còn bao nhiêu quota, CPU/RAM | `/status` |
| `/report` | `gui_bao_cao` | `day` (pastdate, tuỳ chọn) | không | File báo cáo HTML chi tiết (biểu đồ theo giờ, khối tập trung). Kèm ngày để lấy ngày đã qua | `/report` · `/report hôm qua` |
| `/week` | `xem_tuan` | — | không | Tổng kết tuần: giờ vàng, ngày tốt/kém, issue lặp lại | `/week` |
| `/golden` | `xem_gio_vang` | — | không | Khung giờ bạn tập trung tốt nhất 14 ngày qua, nên chặn lịch Outlook | `/golden` |

**📝 GHI CHÉP TRONG NGÀY**

| Lệnh | Action | Tham số | Nhắn tự nhiên cần OK? | Làm gì | Ví dụ |
|---|---|---|---|---|---|
| `/plan` | `ghi_ke_hoach` | `text` (chữ, tuỳ chọn) | có | Ghi kế hoạch hôm nay. Không kèm nội dung: bot hiện kế hoạch đã lưu rồi hỏi lại (gõ /cancel để giữ nguyên). Xem lại kế hoạch: /today | `/plan fix job đối soát, viết spec API` · «hôm nay mình sẽ fix job đối soát» |
| `/output` | `ghi_output` | `text` (chữ) | có | Ghi việc vừa làm xong | `/output xong test CL0123` · «vừa xong deploy UAT» |
| `/issue` | `ghi_issue` | `text` (chữ) | có | Ghi ngay khi bị chặn: VDI chậm, thiếu quyền, chờ người khác | `/issue VDI chậm từ 9h` · «bị chặn vì thiếu quyền vào thư viện PRDLIB» |
| `/distraction` | `ghi_phan_tam` | `text` (chữ) | có | Ghi điều làm bạn mất tập trung | `/distraction Zalo nhóm` · «mất tập trung vì họp kéo dài» · «nãy giờ bận trông em bé khóc» |
| `/tmrtask` `/mai` | `ghi_viec_ngay_mai` | `text` (chữ) | có | Việc đầu tiên sáng mai, sáng mai bot nhắc lại | `/tmrtask làm tiếp job đối soát` · «mai làm tiếp spec API thanh toán» |
| `/energy` | `ghi_nang_luong` | `energy` (1–5) | có | Tự chấm sức lực hôm nay 1–5 (thường trả lời lúc tổng kết cuối ngày). AI dùng để tìm quy luật năng lượng với số liệu tập trung. Không chấm thì 17:00 bot tự tính (/autoenergy). Xem lại: /today | `/energy 4` |
| `/as400` | `ghi_gio_as400` | `times` (giờ vào [giờ ra]) | có | Giờ vào/ra AS400 (hoặc gửi ảnh spooled file, AI đọc giờ) | `/as400 08:10 17:35` · «AS400 vào 8h10 ra 17h35» |
| `/review` | `tong_ket_ngay` | — | không | Bot hỏi từng câu: output, issue, giờ AS400, việc mai, năng lượng | `/review` |

**🌴 NGÀY NGHỈ, NGHỈ PHÉP, TẠM DỪNG**

| Lệnh | Action | Tham số | Nhắn tự nhiên cần OK? | Làm gì | Ví dụ |
|---|---|---|---|---|---|
| `/leave` `/nghiphep` | `nghi_phep` | `part` (sang/chieu/ca ngay, tuỳ chọn), `day` (ngày, tuỳ chọn), `reason` (chữ, tuỳ chọn) | có | Nghỉ phép sáng / chiều / cả ngày: phần nghỉ không theo dõi, không nhắc; nửa ngày thì mục tiêu còn một nửa. Cả ngày thì tracker tắt luôn, mai bật lại | `/leave sang` · `/leave chieu mai đi khám` · `/leave ca ngay 2026-12-24` · `/nghiphep chieu thứ 6` · «hôm nay mình nghỉ nửa ngày sáng» · «chiều nay nghỉ phép» · «mai nghỉ phép cả ngày» · «thứ 6 nghỉ buổi chiều» |
| `/off` | `bao_nghi` | `day` (ngày, tuỳ chọn), `reason` (chữ, tuỳ chọn) | có | Báo nghỉ để bot không nhắc gì ngày đó | `/off` · `/off 2026-12-24 nghỉ phép` · «mai mình xin nghỉ phép» |
| `/on` | `bao_di_lam` | `day` (ngày, tuỳ chọn) | có | Huỷ ngày nghỉ / nghỉ phép đã báo | `/on` · `/on 2026-12-24` |
| `/pause` | `tam_dung` | — | có | Tạm dừng theo dõi (họp dài, việc riêng) | `/pause` · «tạm dừng theo dõi nhé» |
| `/resume` | `tiep_tuc` | — | có | Theo dõi lại | `/resume` |

**🤖 AI, ĐỘNG VIÊN, CÀI ĐẶT**

| Lệnh | Action | Tham số | Nhắn tự nhiên cần OK? | Làm gì | Ví dụ |
|---|---|---|---|---|---|
| `/ask` `/hoi` | `hoi_ai` | `text` (chữ, tuỳ chọn) | chỉ khi bật/tắt chế độ hỏi AI | Hỏi AI bất cứ gì; AI biết bạn là ai, làm gì, và tra web cho giá vàng, tỷ giá, tin tức. /ask on: mọi tin nhắn thường đều gửi AI · /ask off: tắt | `/ask giá vàng SJC hôm nay bao nhiêu` · `/ask làm sao để kiếm thêm thu nhập` · `/ask on` |
| `/quote` | `xin_cau_dong_luc` | — | không | Một câu nói truyền động lực | `/quote` |
| `/bible` | `xin_cau_kinh_thanh` | — | không | Một câu Kinh Thánh Tin Lành khích lệ | `/bible` |
| `/aireview` | `bat_tat_ai_danh_gia` | `state` (on/off, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Bật/tắt AI tự đánh giá cuối ngày (17:00) và cuối tuần | `/aireview` · `/aireview off` · `/aireview on` |
| `/encourage` | `cai_khich_le` | `mode` (on/off/quote/bible/both, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Bật/tắt lời khích lệ tự động; chọn chỉ danh ngôn, chỉ Kinh Thánh hoặc cả hai | `/encourage off` · `/encourage bible` · `/encourage quote` · `/encourage both` |
| `/style` | `doi_giong` | `tone` (giọng, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Đổi giọng bot và AI: than_mat, vui_tuoi, hai_huoc, sep_kho_tinh | `/style hai_huoc` · `/style sep_kho_tinh` · `/style mac_dinh` |
| `/nudge` `/nhac` | `doi_muc_nhac` | `level` (off/nhe/vua/nghiem, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Mức nhắc khi sao nhãng: off (tắt hẳn), nhe (1 lần/ngày), vua (1 lần mỗi lần sao nhãng, mặc định), nghiem (nhắc lặp + đếm số lần, gắt hơn). Không kèm mức: xem mức hiện tại | `/nudge` · `/nudge nghiem` · `/nhac nhe` · `/nudge off` · `/nudge mac_dinh` · «nhắc nghiêm khắc hơn» · «chỉ nhắc 1 lần mỗi ngày thôi» · «tắt nhắc nhở sao nhãng» |
| `/pace` `/tiendo` | `canh_bao_tien_do` | `state` (on/off, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Tiến độ hôm nay: giờ làm thật trong VDI so với nhịp cần để đạt mục tiêu và về đúng giờ; on/off bật tắt cảnh báo tự động ở các mốc | `/pace` · `/pace off` · `/tiendo on` · «tiến độ hôm nay sao rồi» · «tắt cảnh báo tiến độ» |
| `/autoenergy` `/tunangluong` | `tu_tinh_nang_luong` | `state` (on/off, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Tới giờ tổng kết mà bạn chưa chấm năng lượng: bot tự tính từ số liệu (tập trung càng sâu, càng lâu thì càng cạn; sao nhãng thì còn dư) rồi báo kèm cách tính. Không kèm on/off: xem công thức và số tính được lúc này | `/autoenergy` · `/autoenergy off` · `/autoenergy on` · «bot tự tính năng lượng thế nào» |
| `/break` `/nghingoi` | `nhac_nghi_ngoi` | `every` (on/off/số phút, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Nhắc đứng dậy đi lại, vươn vai, tập mắt 20-20-20 khi ngồi làm liên tục; bật/tắt hoặc đổi số phút. Không phụ thuộc /nudge | `/break` · `/break off` · `/break 45` · `/nghingoi on` · «tắt nhắc đứng dậy» · «nhắc nghỉ mỗi 45 phút» |
| `/water` `/uongnuoc` | `nhac_uong_nuoc` | `every` (on/off/số phút, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Nhắc uống nước trong giờ làm (trưa, nghỉ phép, khoá máy thì không); bật/tắt hoặc đổi số phút | `/water` · `/water off` · `/water 45` · `/uongnuoc on` · «nhắc uống nước» · «tắt nhắc uống nước» |

**🛠 HỆ THỐNG**

| Lệnh | Action | Tham số | Nhắn tự nhiên cần OK? | Làm gì | Ví dụ |
|---|---|---|---|---|---|
| `/giobot` `/hours` | `gio_bot` | `start` (HH:MM, tuỳ chọn), `stop` (HH:MM, tuỳ chọn), `time` (HH:MM, tuỳ chọn), `reset` (mac_dinh, tuỳ chọn) | có, khi đổi (không kèm gì = xem) | Giờ bot tự bật / tự tắt (thứ 2 – thứ 6). Không kèm giờ: xem. Đổi xong máy tự bật bot đúng giờ mới từ hôm sau (Task Scheduler / launchd); giờ tắt có hiệu lực ngay | `/giobot` · `/giobot 08:30 18:00` · `/giobot bat 08:30` · `/giobot tat 19:00` · `/giobot mac_dinh` · «bật bot lúc 8 rưỡi» · «tắt bot lúc 6 giờ chiều» · «cho bot chạy từ 8h đến 18h» |
| `/aistatus` | `xem_ai` | — | không | AI đang dùng model nào, đã gọi bao nhiêu lần, bao nhiêu từ | `/aistatus` |
| `/clearcache` | `xoa_cache_ai` | — | có | Xoá cache model và nhận xét AI đã lưu (khi AI trả lời lạ) | `/clearcache` |
| `/perf` | `xem_hieu_nang` | — | không | Tracker đang tốn bao nhiêu CPU/RAM | `/perf` |
| `/cancel` | `huy` | — | không | Huỷ thao tác đang chờ xác nhận hoặc đang hỏi dở | `/cancel` |
| `/help` `/start` | `tro_giup` | — | không | Hướng dẫn này | `/help` |

**Không có lệnh gạch chéo**

| Action | Làm gì | Ví dụ |
|---|---|---|
| `bat_tat_kinh_thanh` | Nút gạt Kinh Thánh: on = lời chào buổi sáng và lời khích lệ dùng Kinh Thánh, off (mặc định khi cài lần đầu) = mọi tin chỉ dùng châm ngôn người thành đạt, danh nhân xưa (cho người không theo đạo); không kèm gì thì đảo trạng thái hiện tại |  |
| `tro_chuyen` | Tâm sự, than mệt, chán, cần động viên, hoặc tin nhắn không thuộc thao tác nào ở trên | «mệt quá» |

### 5.2 Lệnh trên máy (CLI)

Chạy trong thư mục app (`python` trên Windows, `python3` trên Mac):

| Lệnh | Làm gì |
|---|---|
| `python focus_tracker.py run` | Chạy tracker + bot (Task Scheduler / launchd gọi lệnh này). Có token mà chưa có `TELEGRAM_CHAT_ID`: chế độ lấy chat ID (mục 2.4 bước 5), chạy mọi giờ, mọi ngày |
| `python focus_tracker.py check` | Kiểm tra cấu hình, đọc thử trạng thái máy / VDI, token Telegram (`getMe`), có key AI chưa |
| `python focus_tracker.py probe` | In trạng thái máy mỗi 2 giây (thử thu nhỏ / chuyển cửa sổ VDI) |
| `python focus_tracker.py report [YYYY-MM-DD] [--open]` | Tạo báo cáo HTML (mặc định hôm nay); `--open` mở luôn bằng trình duyệt (`bao_cao_hom_nay` dùng cách này) |
| `python focus_tracker.py week` | In tổng kết tuần |
| `python focus_tracker.py demo` | Báo cáo mẫu từ dữ liệu giả (`data/demo`) |
| `python focus_tracker.py housekeeping` | Dọn dẹp ngay (bỏ qua cờ "đã dọn hôm nay") |
| `python focus_tracker.py clearcache` | Xoá cache model AI và nhận xét AI đã lưu |
| `python focus_tracker.py ai-models` | Liệt kê model Gemini key dùng được (không tốn lượt sinh nội dung) |
| `python focus_tracker.py ai-test` | Gọi AI thử 1 câu |
| `python focus_tracker.py selftest` | Chạy bộ test tự động |
| `python focus_tracker.py verify [phần]` | Kiểm tra toàn bộ trên máy thật, có hướng dẫn thao tác, ghi `data/logs/kiem_tra-*.txt`. Phần: `check ai mom autostart vdi tests` (mục 2.6) |
| `python focus_tracker.py help` | Trợ giúp |

---

## 6. Nhắn tự nhiên: bot hiểu tin nhắn thế nào

### 6.1 Đường đi của một tin nhắn

```
Tin nhắn Telegram tới
  |
  v
Đúng TELEGRAM_CHAT_ID của bạn?
  |-- KHÔNG --> bỏ qua, ghi audit REJECT_STRANGER. HẾT
  |
  v (có)
Là ảnh (hoặc ảnh gửi dạng file)?
  |-- CÓ --> AI đọc giờ AS400 trong ảnh --> thẻ xác nhận ✅ OK / ✏️ Sửa / ❌ Huỷ. HẾT
  |
  v (không)
Bắt đầu bằng "/" (lệnh, ví dụ /giobot 18:00)?
  |-- CÓ --> chạy lệnh NGAY, không hỏi lại. HẾT
  |
  v (không)
Vừa bấm ✏️ Sửa lại (trong 30 phút)?
  |-- CÓ --> nhảy xuống bước "HIỂU TIN NHẮN"
  |
  v (không)
Bot đang hỏi dở (/plan, /review)?
  |-- CÓ --> tin này là câu trả lời cho câu đang hỏi. HẾT
  |          (trừ khi bot TỰ hỏi theo lịch mà tin của bạn là một câu hỏi)
  |
  v (không)
Đang bật chế độ hỏi AI (/ask on)?
  |-- CÓ --> gửi AI, trả lời bạn. HẾT
  |
  v (không)
HIỂU TIN NHẮN (intent.understand)
  |
  |-- có key AI --> AI chọn action + tham số (purpose=intent)
  |                   |-- AI lỗi / hết quota / trả JSON lạ --> dùng từ khoá dự phòng
  |-- không có key -> dùng từ khoá dự phòng (by_rules)
  |                   |-- không khớp gì --> «Mình chưa hiểu...» + danh sách lệnh. HẾT
  v
Kiểm tra tham số (validate)
  |-- thiếu / sai --> «Mình hiểu bạn muốn: X. Nhưng ...» (chỉ chỗ sai). HẾT
  |
  v
Action có ghi / đổi dữ liệu không?
  |-- CÓ --> thẻ xác nhận: tên action + tham số + nguồn (AI / từ khoá)
  |          + ⚠️ nếu AI và từ khoá hiểu khác nhau
  |            |-- bấm ✅ OK    --> chạy action, audit CONFIRMED
  |            |-- bấm ✏️ Sửa  --> bạn gõ lại, quay lại bước "HIỂU TIN NHẮN"
  |            |-- bấm ❌ Huỷ  --> không làm gì
  |
  |-- KHÔNG (chỉ xem) --> «🔎 Mình hiểu là: ...» rồi chạy luôn
```

| Bước | Chi tiết |
|---|---|
| Chuẩn hoá | Tin được chuẩn hoá Unicode NFC (gõ Unikey kiểu "tổ hợp" vẫn hiểu). `/issue⏎nội dung` (xuống dòng sau lệnh) vẫn là lệnh |
| Thứ tự xét | Ảnh → tin không có chữ (sticker, file: bỏ qua) → lệnh (trừ `/skip`) → đang chờ "Sửa lại" → đang hỏi dở → chế độ hỏi AI → hiểu tin nhắn |
| Đang hỏi dở | Tin thường là câu trả lời, kể cả khi `/ask on`. Riêng lúc bot **tự** hỏi theo lịch mà tin là **câu hỏi** thì không coi là câu trả lời |
| Mọi tin tự nhiên | Ghi `log.info` và audit `PARSED` (nguồn ai/rule, action, tham số) |
| Thẻ xác nhận | Hết hạn sau 30 phút. ✏️ Sửa lại: tin kế tiếp (trong 30 phút) được hiểu lại từ đầu; một lượt hỏi kế hoạch/tổng kết mới bắt đầu thì huỷ trạng thái chờ sửa. Tin gốc gửi ngày nào thì OK ghi vào ngày đó |
| Chỉ xem | Chạy luôn nhưng trước đó gửi 1 dòng «🔎 Mình hiểu là: ...» để bạn thấy bot hiểu thành gì (trừ hỏi AI và trò chuyện) |
| `hoi_ai` | Câu hỏi trả lời luôn. Riêng bật/tắt chế độ hỏi AI bằng tin nhắn tự nhiên thì phải OK |
| `tro_chuyen` | Tâm sự, than mệt → một câu khích lệ hợp tình huống |

### 6.2 Thẻ xác nhận (render từ `actions.confirm_card()`)

AI hiểu đúng («tắt bot lúc 6 giờ chiều»):

```
🤖 Mình hiểu bạn muốn: Đổi giờ bot: tắt 18:00 (giờ bật giữ nguyên)
• Hành động: gio_bot (Giờ bot tự bật / tự tắt, lệnh /giobot)
• Chi tiết đã bóc tách:
   - giờ TẮT bot: 18:00
• Tin bạn nhắn: «tắt bot lúc 6 giờ chiều»
• Cách hiểu: AI bóc tách
Đúng ý bạn chưa? Bấm ✅ OK để thực hiện, ✏️ Sửa lại nếu mình hiểu sai, ❌ Huỷ nếu không làm nữa.
[ ✅ OK ] [ ✏️ Sửa lại ] [ ❌ Huỷ ]
```

AI đọc sai giờ: dòng ⚠️ đối chiếu từ khoá:

```
🤖 Mình hiểu bạn muốn: Đổi giờ bot: tắt 19:00 (giờ bật giữ nguyên)
• Hành động: gio_bot (Giờ bot tự bật / tự tắt, lệnh /giobot)
• Chi tiết đã bóc tách:
   - giờ TẮT bot: 19:00
• Tin bạn nhắn: «tắt bot lúc 6 giờ chiều»
• Cách hiểu: AI bóc tách
⚠️ Đọc theo từ khoá thì ra giờ TẮT bot = 18:00, khác với chi tiết ở trên. Kiểm tra kỹ; sai thì bấm ✏️ Sửa lại.
Đúng ý bạn chưa? Bấm ✅ OK để thực hiện, ✏️ Sửa lại nếu mình hiểu sai, ❌ Huỷ nếu không làm nữa.
[ ✅ OK ] [ ✏️ Sửa lại ] [ ❌ Huỷ ]
```

AI chọn sai action: dòng ⚠️ gợi ý action theo từ khoá:

```
🤖 Mình hiểu bạn muốn: Ghi output (việc đã xong): «làm tiếp job đối soát»
• Hành động: ghi_output (Ghi việc đã xong, lệnh /output)
• Chi tiết đã bóc tách:
   - việc đã xong: làm tiếp job đối soát
• Tin bạn nhắn: «mai làm tiếp job đối soát»
• Cách hiểu: AI bóc tách
⚠️ Theo từ khoá thì tin này lại giống «Ghi việc đầu tiên sáng mai» (lệnh /tmrtask). Nếu ý bạn là việc đó, bấm ✏️ Sửa lại hoặc gõ thẳng lệnh.
Đúng ý bạn chưa? Bấm ✅ OK để thực hiện, ✏️ Sửa lại nếu mình hiểu sai, ❌ Huỷ nếu không làm nữa.
[ ✅ OK ] [ ✏️ Sửa lại ] [ ❌ Huỷ ]
```

Không có AI: hiểu bằng từ khoá, ngày bỏ trống = hôm nay:

```
🤖 Mình hiểu bạn muốn: Ghi nghỉ phép buổi chiều ngày 2026-10-14
• Hành động: nghi_phep (Nghỉ phép (sáng / chiều / cả ngày), lệnh /leave)
• Chi tiết đã bóc tách:
   - buổi nghỉ: buổi chiều
   - ngày nghỉ: hôm nay 2026-10-14 (mặc định)
• Tin bạn nhắn: «chiều nay nghỉ phép»
• Cách hiểu: từ khoá (AI không dùng được)
Đúng ý bạn chưa? Bấm ✅ OK để thực hiện, ✏️ Sửa lại nếu mình hiểu sai, ❌ Huỷ nếu không làm nữa.
[ ✅ OK ] [ ✏️ Sửa lại ] [ ❌ Huỷ ]
```

Action chỉ xem (chạy luôn, không cần OK), ví dụ «hôm nay mình tập trung được bao nhiêu rồi», «tiến độ hôm nay sao rồi»:

```
🔎 Mình hiểu là: Tổng kết hôm nay (xem_hom_nay, lệnh /today)
🔎 Mình hiểu là: Tiến độ hôm nay / cảnh báo tiến độ (canh_bao_tien_do, lệnh /pace)
```

| Dòng trên thẻ | Nghĩa |
|---|---|
| `🤖 Mình hiểu bạn muốn:` | Câu mô tả đầy đủ, đã điền tham số |
| `• Hành động:` | Tên action + tên dễ hiểu + lệnh gạch chéo tương đương |
| `• Chi tiết đã bóc tách:` | Mỗi tham số một dòng. Tham số ngày bỏ trống ghi rõ «hôm nay … (mặc định)» |
| `• Tin bạn nhắn:` | Nguyên văn (cắt 200 ký tự) |
| `• Cách hiểu:` | «AI bóc tách» hoặc «từ khoá (AI không dùng được)» |
| `⚠️ ...` | Chỉ khi AI hiểu: `intent.cross_check()` đọc lại tin bằng từ khoá; **khác action**, hoặc cùng action mà **khác ngày / giờ / buổi / mức** thì in cách đọc theo từ khoá để bạn soát |

### 6.3 Từ khoá dự phòng (khi không có AI / AI lỗi)

| Luật | Ví dụ (đã chạy qua `by_rules`) |
|---|---|
| Chọn từ khoá **dài nhất** khớp; từ khoá yếu (như "hôm nay") chỉ thắng khi không có gì khác | «tiến độ hôm nay sao rồi» → `canh_bao_tien_do` |
| Câu khớp cả action **ghi** lẫn action **xem**: ghi thắng (trừ khi là câu hỏi) | «đã xong báo cáo tuần cho sếp» → ghi output |
| Một từ đệm (mình/em/tôi/anh/chị/sẽ/đã/cứ) được phép nằm giữa từ khoá nhiều chữ | «mai mình xin nghỉ phép» → `bao_nghi`, ngày mai |
| Câu hỏi (tại sao, bao nhiêu, ...?) không phải lệnh ghi → `hoi_ai` | «giá vàng hôm nay bao nhiêu?» → `hoi_ai` |
| Tra từ (bật/tắt, giọng, mức) chọn cụm dài nhất (cả trong lệnh gạch chéo) | `/encourage tất cả` → `both`, không phải «tắt» |
| Tham số đọc từ cả câu | «nhắc nghỉ mỗi 45 phút» → `/break 45` · «bật bot lúc 8 rưỡi» → bật 08:30 · «cho bot chạy từ 8h đến 18h» → 08:00–18:00 · «tắt bot lúc 6 giờ chiều» → tắt 18:00 |
| Nghỉ phép | «mai nghỉ phép cả ngày» → full, mai · «thứ 6 nghỉ buổi chiều» → pm, thứ 6 · «thứ 6 tuần sau nghỉ phép» → `bao_nghi` thứ 6 tuần kế · «huỷ nghỉ chiều nay» → `bao_di_lam` · «nghỉ nửa ngày» → hỏi lại buổi |
| Issue | «VDI chậm quá chờ restart» → issue, cả câu là nội dung |
| Khác | «AS400 vào 8h10 ra 17h35» → giờ AS400 · «nói chuyện kiểu sếp khó tính đi» → giọng `sep_kho_tinh` · «không gửi kinh thánh nữa» → `/encourage quote` · «tắt AI đánh giá» → off · «chỉ nhắc 1 lần mỗi ngày thôi» → `nhe` · «bot tắt lúc mấy giờ?» → xem giờ bot · «mệt quá» → `tro_chuyen` |

Mọi ví dụ nhắn tự nhiên trong `/help` đều có test kiểm tra đi đúng action.

---

## 7. AI: gọi thế nào, gửi gì, prompt mẫu

### 7.1 Nhà cung cấp, model, gọi HTTP

| | Gemini | Claude |
|---|---|---|
| Chọn khi | `ai_provider: "auto"` và có `GEMINI_API_KEY`, hoặc `"gemini"` | `auto` mà chỉ có `ANTHROPIC_API_KEY`, hoặc `"claude"` |
| Gọi | `POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent` bằng `urllib` (không SDK). Key ở header `x-goog-api-key` (không nằm trong URL/log) | `POST https://api.anthropic.com/v1/messages`, header `x-api-key`, `anthropic-version: 2023-06-01` |
| Thân | `contents` (prompt; ảnh `inline_data` image/jpeg nếu có), `systemInstruction`, `generationConfig.maxOutputTokens = 8192`; **không** gửi `thinkingConfig` (dùng mặc định của model, giống bot timesheet); tra web: `tools: [{google_search: {}}]` | `model` = `claude_model` (mặc định `claude-opus-5-5`), `max_tokens 4096`, `system`, ảnh base64 nếu có; tra web: `web_search_20250305`, `max_uses 3` |
| Thời gian chờ | `ai_timeout_seconds` (60) | như Gemini |
| `ai_provider: "off"` | Tắt AI hoàn toàn | |

> ⚠️ **Không gửi tham số «tắt thinking» (`thinkingConfig`) cho Gemini. Tham số này không cần thiết.**
>
> | | |
> |---|---|
> | Bot timesheet | Gọi cùng loại model Gemini Flash Lite **không có** tham số này và chạy ổn; tài liệu của bot đó cũng không nhắc tới thinking. App này làm giống hệt |
> | Tốc độ | Model Flash Lite tự quyết định có "nghĩ" hay không. Câu hỏi của app ngắn nên trả lời vẫn nhanh, không cần ép tắt |
> | Gửi kèm thì hỏng | Trên máy thật ngày 14/10/2026, `gemini-flash-lite-latest` trả lỗi 400 «Request contains an invalid argument» chỉ vì có `thinkingConfig`. Bỏ tham số đi là gọi được ngay |
> | Nếu model có "nghĩ" | Phần suy nghĩ (Google đánh dấu `thought`) bị app bỏ, chỉ giữ câu trả lời. `maxOutputTokens` 8192 đủ chỗ cho cả hai |
> | Giữ cho khỏi bị thêm lại | Test `test_no_thinking_config_is_sent` (`tests/test_ai_client.py`) báo lỗi nếu ai đó thêm `thinkingConfig` vào yêu cầu |

**Chuỗi model Gemini** (`gemini_model: "auto"`; ghim một tên model thì model đó đứng đầu, chết vẫn tự chuyển):

```
[model ghim] → gemini-flash-lite-latest → gemini-2.5-flash-lite → gemini-2.0-flash-lite → (lite khác Google liệt kê)
             → gemini-flash-latest → gemini-2.5-flash → gemini-2.0-flash → (flash khác Google liệt kê)
```

Không dùng model "pro". Thử tối đa 6 model mỗi lần gọi. Danh sách model Google liệt kê (tối đa 8) giữ 30 ngày. Model đã hết quota hôm nay bị bỏ qua.

| Lỗi | Xử lý |
|---|---|
| 404 | Model đã ngừng → model kế |
| 429 theo ngày ("PerDay") | Đánh dấu model hết quota tới 08:00 UTC (Google reset, khoảng 15:00 giờ VN) → model kế |
| 429 theo phút | Model kế |
| 500 / 503 / 504 | Thử lại 3 lần, cách 5 giây → chuyển sang cụm còn lại (lite ↔ flash). Model thứ 2 cũng nghẽn → bỏ cuộc |
| 400 vì tools | Hỏi lại không tra web |
| 400 chung chung (không phải key) | Thử model kế (tối đa 3 model), hết thì báo nguyên lời Google để biết lỗi gì |
| 400 key / 401 / 403 | Lỗi vĩnh viễn (báo kiểm tra key), không thử lại đánh giá |
| Mọi model hết quota ngày | AI "nghỉ" 3 giờ (`offline_until`), bot dùng từ khoá / nội dung có sẵn |
| AI chặn nội dung (SAFETY, RECITATION...), trả rỗng, bị cắt (MAX_TOKENS) | Câu báo tiếng Việt; bị cắt thì vẫn dùng phần đã có |
| Mọi lỗi | Key bị che trước khi ghi log / gửi Telegram; audit `AI_ERROR` |

### 7.2 Khi nào gọi AI

| Lời gọi (`purpose`) | Khi nào | Gửi gì | System prompt | Tra web | Cache |
|---|---|---|---|---|---|
| `intent` | Mỗi tin nhắn tự nhiên cần hiểu (mục 6.1) | Ngày hôm nay, danh sách action (catalog), nguyên tin nhắn | Chung + đoạn "bộ phân tích lệnh" | Không | Không |
| `daily_review` | Tổng kết ngày (17:00, xong `/review`, gửi bù, thử lại mỗi 15 phút) | Số liệu + ghi chú hôm nay, các ngày trước tách riêng (mục 7.4) | Chung | Không | `ai_cache` `review:<ngày>:<băm>` |
| `weekly_review` | Tổng kết tuần, `/week`, gửi bù, thử lại | Tổng hợp tuần, báo cáo từng ngày, ngày nghỉ, tuần trước | Chung | Không | `ai_cache` `week:<tuần>:<băm>` (băm toàn bộ dữ liệu từng ngày) |
| `morning:<kiểu>` | Lời chào đầu ngày | Hôm nay (ngày, thứ, việc đầu tiên, streak, nghỉ phép, lễ sắp tới), ngày làm việc trước (tóm tắt), các câu đã gửi gần đây | Chung | Không | Không (lưu câu đã gửi vào `quotes`) |
| `encourage:<kiểu>` | 14:30, sau nhắc sao nhãng, `/quote`, `/bible`, `/resume`, trò chuyện | Tình huống + số liệu hôm nay 1 dòng, các câu gần đây | Chung | Không | Như trên |
| `ask` | `/ask`, câu hỏi tự nhiên, chế độ hỏi AI | Giờ hiện tại, thứ, số liệu hôm nay 1 dòng, câu hỏi (≤ 3000 ký tự) | Chung | **Có** | Không |
| `as400_photo` | Gửi ảnh | Ảnh + ngày | **Không có** (chỉ prompt) | Không | Không |
| `test` | `ai-test` | 1 câu chào | — | Không | Không |

AI **không** nhận: mẫu thô 5 giây, tiêu đề cửa sổ, tên file, nội dung màn hình.

### 7.3 System prompt (gửi kèm MỌI lời gọi, không ngoại lệ)

AI không nhớ gì giữa các lần gọi nên mỗi lần app gửi lại toàn bộ bối cảnh (`focus/ai_context.py`): app là gì, luật tính tập trung, công việc (`work_context`), giờ làm, mục tiêu, cách nói, cách xưng hô + giọng + thông tin trong `persona.json` (tên, tuổi, nơi sống, mô tả; thiếu tên thì dùng tên Telegram). Bản render thật (persona ví dụ "Minh"):

<details><summary>System prompt</summary>

```
BỐI CẢNH (bạn không có trí nhớ giữa các lần gọi, mọi thông tin cần thiết đều nằm dưới đây):
- Bạn là trợ lý của "Focus Tracker", một app nhỏ chạy trên máy tính của người dùng (laptop), nói chuyện với người dùng qua bot Telegram.
- Người dùng làm việc bên trong máy ảo VDI (Citrix Desktop Viewer). App chỉ đo từ bên ngoài: cửa sổ nào đang ở trước, chuột/bàn phím có dùng không, máy có khoá không. App KHÔNG đọc nội dung màn hình, email hay code.
- Luật tính tập trung: chỉ thời gian cửa sổ VDI ở trước VÀ có thao tác chuột/phím mới tính là làm việc. VDI bị thu nhỏ (minimize), nằm sau app khác, hoặc dùng app ngoài VDI đều tính là KHÔNG tập trung. "Tập trung sâu" là các khối làm liên tục trong VDI từ 20 phút trở lên.
- Sao nhãng, ngồi yên, rời máy CHỈ đo trong giờ làm chính thức (không tính giờ nghỉ trưa). Ngoài giờ (trước / sau giờ làm, thứ Bảy, Chủ nhật, ngày lễ có bật bot) app chỉ cộng thêm thời gian làm trong VDI (làm ngoài giờ / OT, ví dụ làm bù buổi tối), không ghi sao nhãng.

- Công việc của người dùng: Lập trình viên/BA hệ thống lõi bảo hiểm nhân thọ Life Asia (LifeAsia, CSC/DXC) chạy trên IBM i (AS400), viết bằng COBOL (ILE COBOL), CL, DB2 for i; việc hằng ngày gồm sửa và test chương trình, batch job, spooled file, đối soát dữ liệu hợp đồng, xử lý yêu cầu nghiệp vụ (phát hành, thu phí, bồi thường, đáo hạn); làm việc qua máy ảo VDI Citrix.
- Giờ làm 08:00–17:00, nghỉ trưa 11:15–12:30. Mục tiêu tập trung sâu: 4 giờ/ngày.

CÁCH NÓI:
- Viết tiếng Việt, gửi qua Telegram: văn bản thường, không tiêu đề markdown, không bảng, tối đa 1–2 emoji (giọng sếp khó tính thì không emoji).
- Cụ thể, dựa trên số liệu được cung cấp, không bịa số, không lên lớp chung chung.
- Không bịa câu trích dẫn hay nguồn; câu trích dẫn giữ nguyên văn, ghi đúng nguồn.
- Người dùng TẮT Kinh Thánh: TUYỆT ĐỐI không dùng câu Kinh Thánh hay nội dung tôn giáo trong mọi tin nhắn (chào buổi sáng, khích lệ, nhắc nhở, cảnh báo, đánh giá), trừ khi chính người dùng xin câu Kinh Thánh (lệnh /bible). Câu trích dẫn chỉ dùng châm ngôn, câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa (ví dụ Khổng Tử, Mạnh Tử, Lão Tử, Seneca, Marcus Aurelius), ghi đúng tác giả; không chắc tác giả thì chọn câu khác.
- Gọi người dùng là "bạn", tự xưng là "mình". Giọng thân mật, ấm áp như một người bạn thân. Người dùng tên Minh. Tuổi: 35. Sống ở: TP.HCM, Việt Nam. Về người dùng: Dev AS400 5 năm, có 2 con nhỏ.
```

</details>

| Đảm bảo | Cách làm |
|---|---|
| Lần gọi nào cũng có bối cảnh | `ai_client.generate` (cửa duy nhất ra AI) gọi `ai_context.ensure_context`: system chưa có khối «BỐI CẢNH (bạn không có trí nhớ...» thì tự thêm toàn bộ system prompt lên đầu. Đọc ảnh AS400, `ai-test`, hiểu tin nhắn, khích lệ, chào sáng, hỏi AI, đánh giá ngày/tuần đều có. Có test kiểm từng câu của bối cảnh |
| Bạn tự chỉnh được | `work_context`, `work_start`/`work_end`, `lunch_start`/`lunch_end`, `daily_focus_goal_hours`, `min_focus_block_minutes` trong `settings.json`; tên, xưng hô, giọng, sếp, tuổi, công việc trong `persona.json` hoặc `/style`. Đổi xong là lần gọi AI kế tiếp dùng giá trị mới, cho **mọi** loại prompt |
| Câu trích theo nút Kinh Thánh | Dòng cuối khối CÁCH NÓI là `quote_rule`: Kinh Thánh **bật** (bản render trên) thì «dùng câu Kinh Thánh Tin Lành bản Truyền Thống 1926…»; **tắt** (`/kinhthanh off`) thì «TUYỆT ĐỐI không dùng câu Kinh Thánh hay nội dung tôn giáo trong mọi tin nhắn…, chỉ dùng châm ngôn, câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa». Vì nằm trong system prompt nên áp cho **mọi** lời gọi AI: chào sáng, khích lệ, nhắc, đánh giá ngày / tuần, hỏi AI |
| Cache đánh giá | Khoá cache đánh giá ngày/tuần có mã băm của **toàn bộ** system prompt: đổi bất kỳ thông số nào ở trên thì đánh giá được viết lại, không dùng bản cũ |

### 7.4 Dữ liệu gửi AI, tách theo ngày

Mọi số liệu đã được app tính sẵn. Mỗi khối có ngày rõ ràng để AI không lấy số ngày trước làm số hôm nay. Kèm theo là **bảng giải nghĩa** (`GLOSSARY`) chỉ cho những trường có mặt trong dữ liệu.

| Lời gọi | Phần "đang đánh giá" | Phần ngày khác (chỉ để so sánh) |
|---|---|---|
| Đánh giá ngày | `report_date`, `today` (số liệu + ghi chú **chỉ** ngày đó) | `previous_days_context`: `note` («KHÔNG phải số liệu ngày X»), `avg_deep_hours_7d`, `recent_days[{date, weekday, deep_hours, score}]`, `recent_issues[{date, issue}]`, `promised_yesterday{written_on, task}` |
| Chào sáng | `today` {date, weekday, first_task, leave, upcoming_holiday, streak_days} | `previous_workday` {date, summary} (chỉ điểm tốt, có giờ làm ngoài giờ), `pending_from_previous_workday` {date, items} (app tự gửi danh sách này dưới lời chào, AI chỉ nhắc chung, không chép lại) |
| Tổng kết tuần | `week_summary` (không kèm issue; có `total_score_explained`, `off_day_overtime` = làm bù ngày nghỉ), `days[]` (mỗi phần tử đúng 1 ngày có `day`/`weekday`, gồm cả ngày có số liệu mà 0h tập trung sâu; có `ai_daily_review` = lời AI đã gửi hôm đó), `days_off` | `previous_week` |
| Hỏi AI | `luc_nay`, `thu`, `so_lieu_tap_trung_hom_nay` | — |

Trường trong `today` / `days[]`: `goal_hours`, `work_from_to`, `deep_hours`, `vdi_hours`, `outside_vdi_minutes`, `vdi_minimized_minutes`, `idle_minutes`, `away_minutes`, `out_of_vdi_exits`, `short_idle_count_1_5min`, `vdi_not_fullscreen_minutes`, `vdi_closed`, `vdi_minimize_count`, `inactive_over_10min_count`, `away_count`, `overtime_vdi_minutes`, `overtime_deep_minutes`, `score`, `total_score`, `total_score_10`, `total_score_parts`, `interruptions_per_hour`, `gift_robot`, `science_advice` (chỉ khi điểm tổng dưới 50), `streak_days`, `focus_blocks`, `golden_hour`, `top_apps_outside_vdi`, và ghi chú `plan`, `output`, `issues`, `distractions`, `energy`, `as400_*`, `tomorrow`, `leave` (chỉ trường có giá trị).

### 7.5 Prompt mẫu (render từ code bằng dữ liệu giả, không gọi mạng)

Mỗi prompt dưới đây là phần **user prompt**; system prompt là bản ở mục 7.3.

<details><summary>Đánh giá cuối ngày (<code>daily_review</code>)</summary>

```
VIỆC CẦN LÀM: viết tin nhắn đánh giá cuối ngày làm việc 2026-10-14 (Thứ 4) của người dùng, gửi qua Telegram.

CẤU TRÚC SỐ LIỆU (app đã tính sẵn và tách theo ngày, không cần tính lại):
- "report_date": ngày bạn đang đánh giá, 2026-10-14 (Thứ 4). Bạn chỉ đánh giá ĐÚNG ngày này.
- "today": số liệu và ghi chú CHỈ của ngày 2026-10-14. Mọi con số bạn nói về "hôm nay" phải lấy từ phần này.
- "previous_days_context" (nếu có): báo cáo tóm tắt các ngày TRƯỚC 2026-10-14, mỗi mục ghi rõ "date". Phần này CHỈ để so
  sánh xu hướng, tìm issue lặp lại và kiểm tra lời hẹn hôm trước. TUYỆT ĐỐI không lấy số liệu ở đây làm số liệu hôm
  nay, không cộng dồn vào hôm nay. Khi nhắc tới ngày trước, ghi rõ ngày đó (ví dụ "thứ Ba 13/10").
- Trường không có mặt nghĩa là app không ghi nhận hoặc người dùng không ghi: không suy đoán, không bịa.
- "energy" là năng lượng còn lại cuối ngày 1–5 (1 = kiệt sức, 5 = còn rất sung). Có "energy_source": "app_uoc_tinh"
  thì người dùng KHÔNG tự chấm, app ước tính từ số giờ tập trung (càng tập trung sâu lâu càng thấp): đừng nói như thể
  đó là cảm nhận của người dùng.

ĐIỂM TỔNG LÀ GÌ (người dùng KHÔNG biết điểm tổng là gì, bạn phải giải thích lại bằng lời dễ hiểu):
- Điểm tổng 0–100 (thang 10 = chia 10) là con số chính cho biết ngày làm việc tập trung tốt tới đâu. Mức: dưới 30 kém (robot SD), 30–49 chưa tốt (robot HG), 50–69 trung bình (robot RG), 70–84 tốt (robot MG), từ 85 xuất sắc (robot PG).
- Điểm tổng gộp 3 thành phần, mỗi phần 0–100:
  a) Điểm tập trung (60%) = 70 × min(giờ tập trung sâu / mục tiêu, 1) + 30 × (giờ trong VDI / giờ có dùng phím chuột
     trong giờ làm). Tập trung sâu = khối làm liền trong VDI đủ dài (mặc định từ 20 phút).
  b) Ít bị cắt ngang (30%) = 100 × max(0, 1 − số lần bị cắt ngang mỗi giờ / 20). Bị cắt ngang = rời VDI sang app
     khác hoặc thu nhỏ VDI, hoặc ngồi yên 1–5 phút rồi làm tiếp (thường là cầm điện thoại). Mốc 20 lần/giờ lấy từ
     nghiên cứu González và Mark (CHI 2004): nhân viên văn phòng trung bình khoảng 3 phút lại chuyển việc.
  c) Năng lượng tự chấm (10%) = (năng lượng 1–5 − 1) / 4 × 100, chỉ khi người dùng TỰ chấm. Không tự chấm thì điểm
     tổng = 65% điểm tập trung + 35% ít bị cắt ngang. Năng lượng app tự ước tính KHÔNG tính vào điểm tổng.
- Rời máy, ngồi yên lâu không trừ điểm trực tiếp (chỉ làm ít giờ tập trung đi). Làm ngoài giờ (OT) trong VDI được cộng
  vào giờ tập trung sâu, không tính bị cắt ngang.
- Trọng số 60/30/10 là lựa chọn của app, không phải chuẩn khoa học: không nói điểm tổng là "chuẩn khoa học".
- Trường "total_score_explained" đã tính sẵn bằng số thật: meaning (điểm nghĩa là mức gì), formula, parts (từng thành
  phần và nó đến từ số liệu gốc nào), biggest_loss (phần kéo điểm xuống nhiều nhất), how_to_raise (làm gì để tăng
  điểm, tăng khoảng bao nhiêu). Dùng ĐÚNG các con số đó, không tự tính lại, không bịa số khác.

Viết tối đa 19 dòng, đúng thứ tự 7 mục sau (mỗi mục mở đầu bằng emoji và tên mục ngắn do bạn tự đặt, không markdown):
1. Điểm tổng hôm nay (BẮT BUỘC, 3–5 dòng, viết cho người chưa từng nghe tới điểm tổng):
   - Câu đầu: điểm tổng hôm nay là today.total_score/100 (today.total_score_10/10), nghĩa là mức gì (lấy từ
     today.total_score_explained.meaning), kèm robot quà today.gift_robot cho vui.
   - Giải thích vì sao ra số đó: điểm tổng gộp từ các thành phần nào, nêu số từng thành phần và nó đến từ số liệu gốc
     nào (today.total_score_explained.parts), ví dụ "điểm tập trung chỉ 14/100 vì tập trung sâu 0,1h so với mục tiêu
     4h", "ít bị cắt ngang 12/100 vì bị cắt ngang 17,6 lần mỗi giờ".
   - Nói rõ phần nào kéo điểm xuống nhiều nhất (today.total_score_explained.biggest_loss) và muốn tăng điểm thì làm gì,
     tăng khoảng bao nhiêu (today.total_score_explained.how_to_raise).
   - Rồi đánh giá chung tốt / ổn / chưa tốt: deep_hours so với mục tiêu 4h, so với previous_days_context
     (avg_deep_hours_7d, recent_days). Có overtime_vdi_minutes thì ghi nhận việc làm bù ngoài giờ. Nếu today có
     "leave" thì đánh giá theo mục tiêu nửa ngày.
2. Việc pending cho ngày mai: lấy today.pending_carry (app đã tính sẵn: việc kế hoạch và issue của hôm nay và các ngày
   trước chưa thấy ghi xong, cộng dồn, kèm "tồn từ" ngày nào; việc tồn nhiều ngày thì nhắc ưu tiên xử lý hoặc báo bot
   nếu đã xong), thêm việc hẹn ở previous_days_context.promised_yesterday chưa thấy làm hôm nay, và today.tomorrow nếu
   có. Không có dữ liệu thì nhắc ghi /tmrtask.
3. Mất tập trung vì đâu: 1–2 nguyên nhân chiếm nhiều phút / nhiều lần nhất trong today (app ngoài VDI
   outside_vdi_minutes, VDI thu nhỏ vdi_minimized_minutes / vdi_minimize_count, ngồi yên 1–5 phút nhiều lần = điện
   thoại, rời máy away_minutes / away_count, today.vdi_closed = VDI tự ngắt vì bỏ VDI quá lâu, VDI không toàn màn hình,
   distractions người dùng ghi). App ngoài VDI có thể là việc liên quan công việc (ghi chú, tra cứu, công cụ AI, chat
   với đồng nghiệp): nói là "thời gian ngoài VDI", không khẳng định người dùng đang chơi.
4. Cần khắc phục: với từng issue/blocker quan trọng của today (hoặc lặp lại trong previous_days_context.recent_issues,
   ghi rõ đã gặp ngày nào), gợi ý một bước xử lý cụ thể, sát bối cảnh công việc (AS400/COBOL/Life Asia nếu liên quan).
   Không có issue nào thì chỉ viết một dòng ngắn "hôm nay chưa ghi issue nào" và nhắc /issue, không tự nghĩ ra việc
   cần khắc phục chung chung.
5. Ngày mai cải thiện: 1–2 hành động rất cụ thể, làm được, có giờ giấc (ví dụ chặn khung giờ vàng, tắt app nào, để điện thoại ở đâu).
   Nếu today có "science_advice" (điểm tổng dưới 50): thêm đúng một câu dựa trên dữ kiện đó (giữ tên tác giả, năm,
   con số như đã cho), nối với lý do làm việc vì gia đình. Không có trường này thì KHÔNG tự nêu nghiên cứu nào.
6. Một câu khích lệ ngắn hợp giọng văn (là châm ngôn / câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa, ghi đúng tác giả; người dùng đã TẮT Kinh Thánh nên KHÔNG dùng Kinh Thánh). Câu phải nâng đỡ, tích cực, cho thêm sức (kể cả khi ngày kém):
   không chọn câu răn đe, chê trách (ví dụ câu về sự biếng nhác). Câu trích phải đúng nguyên văn; không chắc nguyên
   văn thì chọn câu khác.
7. Dòng cuối: lời chúc buổi tối ấm áp, thư giãn bên gia đình, tự nhiên, hợp giọng văn (sếp khó tính thì chúc ngắn gọn nhưng vẫn chân thành).
Không chép lại toàn bộ số liệu (riêng điểm tổng ở mục 1 thì phải giải thích đủ). Thiếu số liệu ở mục nào thì nói
ngắn gọn rồi bỏ qua, không bịa.

Ý nghĩa các trường số liệu:
- report_date: ngày đang được đánh giá (chỉ đánh giá ngày này)
- today: số liệu và ghi chú CHỈ của ngày đang đánh giá
- previous_days_context: báo cáo tóm tắt các ngày TRƯỚC, mỗi mục có date; chỉ để so sánh, không phải số liệu hôm nay
- day / weekday: ngày của khối số liệu chứa nó
- goal_hours: mục tiêu giờ tập trung sâu mỗi ngày
- work_from_to: giờ dùng máy đầu tiên – cuối cùng
- deep_hours: giờ tập trung sâu (khối làm liên tục trong VDI đủ dài)
- vdi_hours: tổng giờ VDI ở trước và có thao tác
- outside_vdi_minutes: phút dùng chuột/phím ở app ngoài VDI (Chrome, Teams, Zalo...)
- vdi_minimized_minutes: phút VDI bị thu nhỏ (taskbar / Dock), bị ẩn hoặc nằm sau app khác trong lúc vẫn dùng máy
- idle_minutes: phút ngồi yên không chạm phím/chuột (dưới ngưỡng rời máy)
- away_minutes: phút rời máy hoặc khoá máy
- vdi_closed: các khoảng giờ cửa sổ VDI bị đóng trong giờ làm (Citrix tự ngắt khi người dùng không đụng VDI 10–20 phút, hoặc tự đóng): người dùng đã rời VDI quá lâu, khoảng này không tính giờ làm
- out_of_vdi_exits: số lần rời VDI sang app khác
- short_idle_count_1_5min: số lần ngồi yên 1–5 phút trước VDI rồi làm tiếp; cao thường là do cầm điện thoại
- vdi_not_fullscreen_minutes: phút VDI không toàn màn hình (dễ liếc sang app khác)
- score: điểm tập trung 0–100 = 70 × min(tập trung sâu / mục tiêu, 1) + 30 × (giờ VDI / giờ có thao tác)
- total_score / total_score_10: ĐIỂM TỔNG 0–100 (và thang 1–10), chỉ số quan trọng nhất của ngày: 60% điểm tập trung + 30% điểm ít bị cắt ngang + 10% năng lượng tự chấm (chưa tự chấm thì 65/35)
- total_score_parts: điểm thành phần 0–100: focus (điểm tập trung), interruptions (ít bị cắt ngang: 100 khi không bị cắt ngang, 0 khi bị cắt ngang từ 20 lần/giờ trở lên), energy (năng lượng tự chấm)
- interruptions_per_hour: số lần bị cắt ngang mỗi giờ làm (rời VDI / thu nhỏ VDI + ngồi yên ngắn rồi làm tiếp)
- total_score_explained: giải thích điểm tổng đã tính sẵn bằng số thật: meaning (nghĩa là mức gì), formula, parts (từng thành phần + số liệu gốc), biggest_loss (phần kéo điểm xuống nhiều nhất), how_to_raise / avg_parts / by_day (cách tăng điểm, điểm thành phần trung bình, từng ngày)
- gift_robot: robot quà tặng theo điểm tổng: SD (thấp nhất, robot tí hon) -> HG -> RG -> MG -> PG (cao nhất)
- vdi_minimize_count: số lần thu nhỏ VDI trong giờ làm
- inactive_over_10min_count: số lần ngồi yên / rời máy từ 10 phút trở lên trong giờ làm
- away_count: số lần rời máy (ngồi yên quá ngưỡng hoặc khoá máy)
- streak_days: số ngày làm việc liên tiếp đạt mục tiêu
- focus_blocks: các khối tập trung sâu trong ngày
- golden_hour: giờ tập trung tốt nhất trong ngày
- top_apps_outside_vdi: app ngoài VDI dùng nhiều nhất
- avg_deep_hours_7d: trung bình giờ tập trung sâu 7 ngày làm việc trước
- recent_days: giờ tập trung sâu và điểm của từng ngày làm việc TRƯỚC (có date; để so sánh xu hướng)
- plan: kế hoạch người dùng tự ghi đầu ngày
- output: việc người dùng ghi là đã xong
- issues: issue / blocker người dùng ghi trong ngày
- recent_issues: issue của các ngày TRƯỚC, kèm date (để thấy issue lặp lại)
- pending_carry: việc tồn chuyển sang ngày làm việc kế: kế hoạch và issue của ngày này và các ngày trước chưa thấy ghi xong trong output, cộng dồn, ghi ngày bắt đầu tồn
- promised_yesterday: việc người dùng ghi ngày written_on, hẹn làm đầu tiên ở ngày đang đánh giá

SỐ LIỆU (JSON):
{
 "report_date": "2026-10-14 (Thứ 4)",
 "today": {
  "day": "2026-10-14",
  "weekday": "Thứ 4",
  "goal_hours": 4,
  "work_from_to": "09:00–10:35",
  "deep_hours": 1.6,
  "vdi_hours": 1.6,
  "outside_vdi_minutes": 0,
  "vdi_minimized_minutes": 0,
  "idle_minutes": 0,
  "away_minutes": 0,
  "out_of_vdi_exits": 0,
  "short_idle_count_1_5min": 0,
  "vdi_not_fullscreen_minutes": 0,
  "vdi_closed": [],
  "score": 58,
  "streak_days": 0,
  "focus_blocks": [
   "09:00–10:35"
  ],
  "golden_hour": "09:00–10:00",
  "top_apps_outside_vdi": [],
  "vdi_minimize_count": 0,
  "inactive_over_10min_count": 0,
  "away_count": 0,
  "total_score": 73,
  "total_score_explained": {
   "meaning": "73/100 (7,3/10) = mức tốt, robot MG Vanguard. Thang: dưới 30 kém (robot SD), 30–49 chưa tốt (robot HG), 50–69 trung bình (robot RG), 70–84 tốt (robot MG), từ 85 xuất sắc (robot PG)",
   "formula": "65% × điểm tập trung 58 + 35% × ít bị cắt ngang 100 = 73",
   "parts": [
    "Điểm tập trung 58/100 (trọng số 65%, góp 37,7 điểm tổng): phần giờ tập trung sâu = 70 × min(1,58h / mục tiêu 4h, 1) = 27,7/70; phần ở trong VDI = 30 × (giờ trong VDI 1,58h / giờ có dùng phím chuột 1,58h = 100%) = 30/30",
    "Ít bị cắt ngang 100/100 (trọng số 35%, góp 35 điểm tổng): bị cắt ngang 0 lần (rời VDI / thu nhỏ VDI 0 lần + ngồi yên 1–5 phút rồi làm tiếp 0 lần) trong 1,58 giờ làm = 0 lần/giờ; 0 lần/giờ = 100 điểm, từ 20 lần/giờ trở lên = 0 điểm",
    "Năng lượng: người dùng chưa tự chấm nên không tính; trọng số dồn sang 65% điểm tập trung + 35% ít bị cắt ngang"
   ],
   "biggest_loss": "điểm tập trung làm mất nhiều điểm nhất (27,3 điểm tổng), chủ yếu do thiếu giờ tập trung sâu",
   "how_to_raise": [
    "thêm 2,4h tập trung sâu (khối làm liền trong VDI từ 20 phút) cho đủ mục tiêu: điểm tổng tăng khoảng 27"
   ]
  },
  "total_score_10": 7.3,
  "total_score_parts": {
   "focus": 58,
   "interruptions": 100
  },
  "interruptions_per_hour": 0.0,
  "gift_robot": "MG Vanguard (robot tiên phong giáp nhiều lớp, có cánh đẩy)",
  "plan": "fix job đối soát\nviết spec API",
  "output": "- fix job đối soát (10:30)",
  "issues": "- VDI chậm sáng nay (09:05)",
  "pending_carry": [
   "issue: VDI chậm buổi sáng (tồn từ T2 05/10)",
   "issue: thiếu quyền thư viện PRDLIB (tồn từ T3 06/10)",
   "issue: VDI chậm (tồn từ T5 08/10)",
   "review batch (tồn từ T6 09/10)",
   "viết spec API (tồn từ T4 14/10)",
   "issue: VDI chậm sáng nay (tồn từ T4 14/10)"
  ]
 },
 "previous_days_context": {
  "note": "Báo cáo các ngày TRƯỚC 2026-10-14, chỉ để so sánh. KHÔNG phải số liệu ngày 2026-10-14.",
  "avg_deep_hours_7d": 2.8,
  "recent_days": [
   {
    "date": "2026-10-13",
    "weekday": "Thứ 3",
    "deep_hours": 2.8,
    "score": 78
   },
   {
    "date": "2026-10-12",
    "weekday": "Thứ 2",
    "deep_hours": 2.8,
    "score": 78
   },
   {
    "date": "2026-10-09",
    "weekday": "Thứ 6",
    "deep_hours": 3.1,
    "score": 81
   },
   {
    "date": "2026-10-08",
    "weekday": "Thứ 5",
    "deep_hours": 2.8,
    "score": 74
   },
   {
    "date": "2026-10-07",
    "weekday": "Thứ 4",
    "deep_hours": 2.8,
    "score": 77
   }
  ],
  "recent_issues": [
   {
    "date": "2026-10-13",
    "issue": "VDI chậm"
   },
   {
    "date": "2026-10-08",
    "issue": "VDI chậm (09:30)"
   }
  ],
  "promised_yesterday": {
   "written_on": "2026-10-13",
   "task": "fix job đối soát"
  }
 }
}
```

</details>

<details><summary>Tổng kết tuần (<code>weekly_review</code>)</summary>

```
VIỆC CẦN LÀM: tổng kết tuần 2026-W41 (2026-10-05 → 2026-10-09) cho người dùng.
Bạn KHÔNG nhớ gì về các ngày trong tuần, nên dưới đây là TOÀN BỘ báo cáo của tuần, app đã tính sẵn và tách theo ngày:
- "week_summary": tổng hợp cả tuần (giờ tập trung sâu, điểm trung bình, điểm tổng trung bình avg_total_score, ngày
  tốt/kém nhất, giờ vàng). "week_summary.total_score_explained" đã tính sẵn: meaning (điểm tổng trung bình nghĩa là
  mức gì), avg_parts (điểm thành phần trung bình), by_day (điểm tổng và thành phần từng ngày), best_day, worst_day,
  biggest_loss (phần kéo điểm cả tuần xuống nhiều nhất). Issue nằm trong từng ngày ở "days".
- "days": báo cáo đầy đủ TỪNG ngày làm việc theo thứ tự thời gian: số liệu tập trung, khối tập trung, app ngoài VDI,
  kế hoạch đầu ngày (plan), việc đã xong (output), issue, điều làm mất tập trung, năng lượng 1–5 (có
  "energy_source": "app_uoc_tinh" là app tự ước tính vì người dùng không chấm, không phải cảm nhận), giờ AS400, việc hẹn
  làm đầu tiên sáng hôm sau (tomorrow), và "ai_daily_review" là lời đánh giá AI đã gửi cuối ngày đó (nếu có).
- "days_off": ngày nghỉ trong tuần và lý do. "previous_week": số liệu tuần trước, CHỈ để so sánh (nếu có).
Mỗi phần tử trong "days" là báo cáo của ĐÚNG MỘT ngày (trường "day" / "weekday"): số liệu ngày nào chỉ thuộc ngày đó,
không trộn hay chuyển số giữa các ngày; khi nêu số liệu luôn kèm ngày. "ai_daily_review" là lời nhận xét đã gửi hôm
đó, không phải số liệu. Số tổng của tuần lấy từ "week_summary", không tự cộng lại.

Cách đọc trước khi viết (không cần viết ra các bước này):
- So plan với output từng ngày: việc nào xong, việc nào kéo dài qua nhiều ngày, việc nào chưa thấy xong tới cuối tuần.
- So "tomorrow" của ngày này với plan/output của ngày làm việc kế tiếp: có giữ lời hẹn không.
- Gom issue giống nhau qua các ngày (cùng hệ thống, cùng nguyên nhân) và đếm số lần lặp.
- Xem lời khuyên trong ai_daily_review các ngày trước có được làm theo không (số liệu ngày sau có tốt lên không).
- Tìm quy luật: ngày/giờ nào tập trung tốt, năng lượng thấp đi cùng số liệu nào, ngoài VDI / thu nhỏ VDI / ngồi yên 1–5 phút (thường là điện thoại) tăng vào lúc nào.

ĐIỂM TỔNG LÀ GÌ (người dùng KHÔNG biết điểm tổng là gì, bạn phải giải thích lại bằng lời dễ hiểu):
- Điểm tổng 0–100 (thang 10 = chia 10) là con số chính cho biết ngày làm việc tập trung tốt tới đâu. Mức: dưới 30 kém (robot SD), 30–49 chưa tốt (robot HG), 50–69 trung bình (robot RG), 70–84 tốt (robot MG), từ 85 xuất sắc (robot PG).
- Điểm tổng gộp 3 thành phần, mỗi phần 0–100:
  a) Điểm tập trung (60%) = 70 × min(giờ tập trung sâu / mục tiêu, 1) + 30 × (giờ trong VDI / giờ có dùng phím chuột
     trong giờ làm). Tập trung sâu = khối làm liền trong VDI đủ dài (mặc định từ 20 phút).
  b) Ít bị cắt ngang (30%) = 100 × max(0, 1 − số lần bị cắt ngang mỗi giờ / 20). Bị cắt ngang = rời VDI sang app
     khác hoặc thu nhỏ VDI, hoặc ngồi yên 1–5 phút rồi làm tiếp (thường là cầm điện thoại). Mốc 20 lần/giờ lấy từ
     nghiên cứu González và Mark (CHI 2004): nhân viên văn phòng trung bình khoảng 3 phút lại chuyển việc.
  c) Năng lượng tự chấm (10%) = (năng lượng 1–5 − 1) / 4 × 100, chỉ khi người dùng TỰ chấm. Không tự chấm thì điểm
     tổng = 65% điểm tập trung + 35% ít bị cắt ngang. Năng lượng app tự ước tính KHÔNG tính vào điểm tổng.
- Rời máy, ngồi yên lâu không trừ điểm trực tiếp (chỉ làm ít giờ tập trung đi). Làm ngoài giờ (OT) trong VDI được cộng
  vào giờ tập trung sâu, không tính bị cắt ngang.
- Trọng số 60/30/10 là lựa chọn của app, không phải chuẩn khoa học: không nói điểm tổng là "chuẩn khoa học".
- Trường "total_score_explained" đã tính sẵn bằng số thật: meaning (điểm nghĩa là mức gì), formula, parts (từng thành
  phần và nó đến từ số liệu gốc nào), biggest_loss (phần kéo điểm xuống nhiều nhất), how_to_raise (làm gì để tăng
  điểm, tăng khoảng bao nhiêu). Dùng ĐÚNG các con số đó, không tự tính lại, không bịa số khác.

Viết tin nhắn Telegram tối đa 24 dòng, theo thứ tự (mỗi mục mở đầu bằng emoji và tên mục ngắn do bạn tự đặt, không markdown):
1. Điểm tổng của tuần (BẮT BUỘC, 3–5 dòng, viết cho người chưa từng nghe tới điểm tổng): điểm tổng trung bình
   week_summary.avg_total_score/100 nghĩa là mức gì (total_score_explained.meaning); điểm tổng gộp từ những thành phần
   nào và trung bình mỗi phần bao nhiêu (avg_parts); ngày điểm cao nhất, thấp nhất và vì sao, dựa trên thành phần của
   chính ngày đó (by_day); phần nào kéo điểm cả tuần xuống nhiều nhất (biggest_loss) và tuần sau cải thiện gì để tăng
   điểm. So với tuần trước nếu có.
2. Đánh giá chung: tuần tốt/ổn/chưa tốt, số ngày đạt mục tiêu, giờ tập trung sâu, xu hướng trong tuần.
3. Ngày tốt nhất và kém nhất: nguyên nhân dựa trên số liệu và ghi chú của chính ngày đó (gộp với mục 1 nếu đã nói).
4. Việc đã xong và việc còn pending sang tuần sau: dựa trên plan/output/tomorrow/issue, nêu tên việc cụ thể.
5. Issue lặp lại: mỗi nhóm 1 dòng kèm số lần và một bước khắc phục cụ thể sát bối cảnh công việc.
6. Mất tập trung: quy luật chính của tuần và cách giảm.
7. Mục tiêu tuần sau: 1–2 mục tiêu nhỏ, đo được, có ngày giờ cụ thể (ví dụ giữ giờ vàng cho việc gì).
8. Một câu khích lệ ngắn hợp giọng văn (là châm ngôn / câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa, ghi đúng tác giả; người dùng đã TẮT Kinh Thánh nên KHÔNG dùng Kinh Thánh): nâng đỡ, tích cực, không răn đe chê trách; câu trích đúng
   nguyên văn.
9. Dòng cuối: lời chúc cuối tuần vui vẻ, nghỉ ngơi trọn vẹn bên gia đình, ấm áp, tự nhiên, hợp giọng văn (sếp khó tính thì chúc ngắn gọn nhưng vẫn chân thành).
Chỉ dùng số liệu và ghi chú được cung cấp; thiếu thì nói ngắn rồi bỏ qua, không bịa.

Ý nghĩa các trường số liệu:
- day / weekday: ngày của khối số liệu chứa nó
- work_from_to: giờ dùng máy đầu tiên – cuối cùng
- deep_hours: giờ tập trung sâu (khối làm liên tục trong VDI đủ dài)
- vdi_hours: tổng giờ VDI ở trước và có thao tác
- outside_vdi_minutes: phút dùng chuột/phím ở app ngoài VDI (Chrome, Teams, Zalo...)
- vdi_minimized_minutes: phút VDI bị thu nhỏ (taskbar / Dock), bị ẩn hoặc nằm sau app khác trong lúc vẫn dùng máy
- idle_minutes: phút ngồi yên không chạm phím/chuột (dưới ngưỡng rời máy)
- away_minutes: phút rời máy hoặc khoá máy
- vdi_closed: các khoảng giờ cửa sổ VDI bị đóng trong giờ làm (Citrix tự ngắt khi người dùng không đụng VDI 10–20 phút, hoặc tự đóng): người dùng đã rời VDI quá lâu, khoảng này không tính giờ làm
- out_of_vdi_exits: số lần rời VDI sang app khác
- short_idle_count_1_5min: số lần ngồi yên 1–5 phút trước VDI rồi làm tiếp; cao thường là do cầm điện thoại
- vdi_not_fullscreen_minutes: phút VDI không toàn màn hình (dễ liếc sang app khác)
- score: điểm tập trung 0–100 = 70 × min(tập trung sâu / mục tiêu, 1) + 30 × (giờ VDI / giờ có thao tác)
- total_score / total_score_10: ĐIỂM TỔNG 0–100 (và thang 1–10), chỉ số quan trọng nhất của ngày: 60% điểm tập trung + 30% điểm ít bị cắt ngang + 10% năng lượng tự chấm (chưa tự chấm thì 65/35)
- total_score_parts: điểm thành phần 0–100: focus (điểm tập trung), interruptions (ít bị cắt ngang: 100 khi không bị cắt ngang, 0 khi bị cắt ngang từ 20 lần/giờ trở lên), energy (năng lượng tự chấm)
- interruptions_per_hour: số lần bị cắt ngang mỗi giờ làm (rời VDI / thu nhỏ VDI + ngồi yên ngắn rồi làm tiếp)
- total_score_explained: giải thích điểm tổng đã tính sẵn bằng số thật: meaning (nghĩa là mức gì), formula, parts (từng thành phần + số liệu gốc), biggest_loss (phần kéo điểm xuống nhiều nhất), how_to_raise / avg_parts / by_day (cách tăng điểm, điểm thành phần trung bình, từng ngày)
- gift_robot: robot quà tặng theo điểm tổng: SD (thấp nhất, robot tí hon) -> HG -> RG -> MG -> PG (cao nhất)
- vdi_minimize_count: số lần thu nhỏ VDI trong giờ làm
- inactive_over_10min_count: số lần ngồi yên / rời máy từ 10 phút trở lên trong giờ làm
- away_count: số lần rời máy (ngồi yên quá ngưỡng hoặc khoá máy)
- streak_days: số ngày làm việc liên tiếp đạt mục tiêu
- focus_blocks: các khối tập trung sâu trong ngày
- golden_hour: giờ tập trung tốt nhất trong ngày
- top_apps_outside_vdi: app ngoài VDI dùng nhiều nhất
- plan: kế hoạch người dùng tự ghi đầu ngày
- output: việc người dùng ghi là đã xong
- issues: issue / blocker người dùng ghi trong ngày
- distractions: điều làm mất tập trung người dùng tự ghi
- energy: mức năng lượng tự chấm 1–5
- tomorrow: việc đầu tiên sáng mai người dùng đã ghi
- pending_carry: việc tồn chuyển sang ngày làm việc kế: kế hoạch và issue của ngày này và các ngày trước chưa thấy ghi xong trong output, cộng dồn, ghi ngày bắt đầu tồn
- as400: giờ vào/ra AS400 hôm nay
- per_day / best_day / worst_day / golden_hours: số liệu từng ngày trong tuần, ngày tốt nhất/kém nhất, giờ vàng của tuần
- deep_hours_total / deep_hours_avg / avg_score / days_reached_goal / work_days: tổng / trung bình giờ tập trung sâu của tuần, điểm trung bình, số ngày đạt mục tiêu, số ngày làm việc
- avg_total_score / overtime_hours: điểm tổng trung bình của tuần, tổng giờ làm trong VDI ngoài giờ (OT)
- ai_daily_review: lời đánh giá AI đã gửi người dùng cuối ngày đó (để xem lời khuyên có được làm theo không)
- previous_week: số liệu tổng của tuần trước để so sánh

SỐ LIỆU (JSON):
{
 "week_summary": {
  "week": "2026-W41",
  "from": "2026-10-05",
  "to": "2026-10-09",
  "goal_hours_per_day": 4,
  "work_days": 5,
  "streak_days": 0,
  "deep_hours_total": 14.1,
  "deep_hours_avg": 2.8,
  "avg_score": 78,
  "avg_total_score": 82,
  "overtime_hours": 0.0,
  "days_reached_goal": 0,
  "best_day": "Thứ 6 10-09 (3.1h)",
  "worst_day": "Thứ 2 10-05 (2.8h)",
  "golden_hours": [
   "09:00–10:00",
   "10:00–11:00"
  ],
  "per_day": [
   "10-05 2.8h điểm 78 điểm tổng 82",
   "10-06 2.8h điểm 78 điểm tổng 84",
   "10-07 2.8h điểm 77 điểm tổng 83",
   "10-08 2.8h điểm 74 điểm tổng 76",
   "10-09 3.1h điểm 81 điểm tổng 86"
  ],
  "total_score_explained": {
   "meaning": "Điểm tổng trung bình tuần 82/100 = mức tốt. Thang: dưới 30 kém (robot SD), 30–49 chưa tốt (robot HG), 50–69 trung bình (robot RG), 70–84 tốt (robot MG), từ 85 xuất sắc (robot PG)",
   "avg_parts": {
    "điểm tập trung": 78,
    "ít bị cắt ngang": 99,
    "năng lượng tự chấm": 60
   },
   "by_day": [
    "Thứ 2 05/10: 82 (điểm tập trung 78, ít bị cắt ngang 100, năng lượng tự chấm 50)",
    "Thứ 3 06/10: 84 (điểm tập trung 78, ít bị cắt ngang 100, năng lượng tự chấm 75)",
    "Thứ 4 07/10: 83 (điểm tập trung 77, ít bị cắt ngang 98, năng lượng tự chấm 75)",
    "Thứ 5 08/10: 76 (điểm tập trung 74, ít bị cắt ngang 98, năng lượng tự chấm 25)",
    "Thứ 6 09/10: 86 (điểm tập trung 81, ít bị cắt ngang 99, năng lượng tự chấm 75)"
   ],
   "best_day": "Thứ 6 09/10 (86)",
   "worst_day": "Thứ 5 08/10 (76)",
   "biggest_loss": "điểm tập trung làm mất nhiều điểm nhất, trung bình 13,4 điểm tổng mỗi ngày"
  }
 },
 "days": [
  {
   "day": "2026-10-05",
   "weekday": "Thứ 2",
   "work_from_to": "08:30–11:15",
   "deep_hours": 2.8,
   "vdi_hours": 2.8,
   "outside_vdi_minutes": 0,
   "vdi_minimized_minutes": 0,
   "idle_minutes": 0,
   "away_minutes": 0,
   "out_of_vdi_exits": 0,
   "short_idle_count_1_5min": 0,
   "vdi_not_fullscreen_minutes": 0,
   "vdi_closed": [],
   "score": 78,
   "focus_blocks": [
    "08:30–11:15"
   ],
   "golden_hour": "09:00–10:00",
   "top_apps_outside_vdi": [],
   "vdi_minimize_count": 0,
   "inactive_over_10min_count": 0,
   "away_count": 0,
   "total_score": 82,
   "total_score_10": 8.2,
   "total_score_parts": {
    "focus": 78,
    "interruptions": 100,
    "energy": 50
   },
   "interruptions_per_hour": 0.0,
   "gift_robot": "MG Vanguard (robot tiên phong giáp nhiều lớp, có cánh đẩy)",
   "plan": "fix job đối soát\nviết spec API",
   "output": "- fix job đối soát (16:40)",
   "issues": "- VDI chậm buổi sáng (09:10)",
   "energy": 3,
   "tomorrow": "viết spec API",
   "pending_carry": [
    "viết spec API (tồn từ T2 05/10)",
    "issue: VDI chậm buổi sáng (tồn từ T2 05/10)"
   ]
  },
  {
   "day": "2026-10-06",
   "weekday": "Thứ 3",
   "work_from_to": "08:30–11:15",
   "deep_hours": 2.8,
   "vdi_hours": 2.8,
   "outside_vdi_minutes": 0,
   "vdi_minimized_minutes": 0,
   "idle_minutes": 0,
   "away_minutes": 0,
   "out_of_vdi_exits": 0,
   "short_idle_count_1_5min": 0,
   "vdi_not_fullscreen_minutes": 0,
   "vdi_closed": [],
   "score": 78,
   "focus_blocks": [
    "08:30–11:15"
   ],
   "golden_hour": "09:00–10:00",
   "top_apps_outside_vdi": [],
   "vdi_minimize_count": 0,
   "inactive_over_10min_count": 0,
   "away_count": 0,
   "total_score": 84,
   "total_score_10": 8.4,
   "total_score_parts": {
    "focus": 78,
    "interruptions": 100,
    "energy": 75
   },
   "interruptions_per_hour": 0.0,
   "gift_robot": "MG Vanguard (robot tiên phong giáp nhiều lớp, có cánh đẩy)",
   "plan": "viết spec API",
   "output": "- xong spec API bản nháp (15:20)",
   "issues": "- thiếu quyền thư viện PRDLIB (10:05)",
   "energy": 4,
   "tomorrow": "test CL0123",
   "pending_carry": [
    "issue: VDI chậm buổi sáng (tồn từ T2 05/10)",
    "issue: thiếu quyền thư viện PRDLIB (tồn từ T3 06/10)"
   ]
  },
  {
   "day": "2026-10-07",
   "weekday": "Thứ 4",
   "work_from_to": "08:30–12:39",
   "deep_hours": 2.8,
   "vdi_hours": 2.8,
   "outside_vdi_minutes": 9,
   "vdi_minimized_minutes": 9,
   "idle_minutes": 0,
   "away_minutes": 0,
   "out_of_vdi_exits": 1,
   "short_idle_count_1_5min": 0,
   "vdi_not_fullscreen_minutes": 0,
   "vdi_closed": [],
   "score": 77,
   "focus_blocks": [
    "08:30–11:15"
   ],
   "golden_hour": "09:00–10:00",
   "top_apps_outside_vdi": [
    "zalo.exe 9m"
   ],
   "vdi_minimize_count": 1,
   "inactive_over_10min_count": 0,
   "away_count": 0,
   "total_score": 83,
   "total_score_10": 8.3,
   "total_score_parts": {
    "focus": 77,
    "interruptions": 98,
    "energy": 75
   },
   "interruptions_per_hour": 0.3,
   "gift_robot": "MG Vanguard (robot tiên phong giáp nhiều lớp, có cánh đẩy)",
   "plan": "test CL0123",
   "output": "- test CL0123 (14:00)",
   "distractions": "- Zalo nhóm",
   "energy": 4,
   "tomorrow": "deploy UAT",
   "pending_carry": [
    "issue: VDI chậm buổi sáng (tồn từ T2 05/10)",
    "issue: thiếu quyền thư viện PRDLIB (tồn từ T3 06/10)"
   ]
  },
  {
   "day": "2026-10-08",
   "weekday": "Thứ 5",
   "work_from_to": "08:30–12:56",
   "deep_hours": 2.8,
   "vdi_hours": 2.8,
   "outside_vdi_minutes": 26,
   "vdi_minimized_minutes": 10,
   "idle_minutes": 0,
   "away_minutes": 0,
   "out_of_vdi_exits": 1,
   "short_idle_count_1_5min": 0,
   "vdi_not_fullscreen_minutes": 0,
   "vdi_closed": [],
   "score": 74,
   "focus_blocks": [
    "08:30–11:15"
   ],
   "golden_hour": "09:00–10:00",
   "top_apps_outside_vdi": [
    "chrome.exe 16m",
    "zalo.exe 10m"
   ],
   "vdi_minimize_count": 1,
   "inactive_over_10min_count": 0,
   "away_count": 0,
   "total_score": 76,
   "total_score_10": 7.6,
   "total_score_parts": {
    "focus": 74,
    "interruptions": 98,
    "energy": 25
   },
   "interruptions_per_hour": 0.3,
   "gift_robot": "MG Vanguard (robot tiên phong giáp nhiều lớp, có cánh đẩy)",
   "plan": "deploy UAT",
   "issues": "- VDI chậm (09:30)",
   "energy": 2,
   "tomorrow": "deploy UAT",
   "pending_carry": [
    "issue: VDI chậm buổi sáng (tồn từ T2 05/10)",
    "issue: thiếu quyền thư viện PRDLIB (tồn từ T3 06/10)",
    "deploy UAT (tồn từ T5 08/10)",
    "issue: VDI chậm (tồn từ T5 08/10)"
   ],
   "ai_daily_review": "🧭 Hôm nay ổn... (đánh giá AI đã gửi ngày 08/10, rút gọn)"
  },
  {
   "day": "2026-10-09",
   "weekday": "Thứ 6",
   "work_from_to": "08:30–13:13",
   "deep_hours": 3.1,
   "vdi_hours": 3.1,
   "outside_vdi_minutes": 23,
   "vdi_minimized_minutes": 10,
   "idle_minutes": 0,
   "away_minutes": 0,
   "out_of_vdi_exits": 1,
   "short_idle_count_1_5min": 0,
   "vdi_not_fullscreen_minutes": 0,
   "vdi_closed": [],
   "score": 81,
   "focus_blocks": [
    "08:30–11:15",
    "12:30–12:50"
   ],
   "golden_hour": "09:00–10:00",
   "top_apps_outside_vdi": [
    "chrome.exe 13m",
    "zalo.exe 10m"
   ],
   "vdi_minimize_count": 1,
   "inactive_over_10min_count": 0,
   "away_count": 0,
   "total_score": 86,
   "total_score_10": 8.6,
   "total_score_parts": {
    "focus": 81,
    "interruptions": 99,
    "energy": 75
   },
   "interruptions_per_hour": 0.3,
   "gift_robot": "PG Celestial (robot thiên giới hoàn chỉnh, cánh sáng, vũ khí đầy đủ)",
   "plan": "deploy UAT\nreview batch",
   "output": "- deploy UAT xong (11:00)",
   "energy": 4,
   "pending_carry": [
    "issue: VDI chậm buổi sáng (tồn từ T2 05/10)",
    "issue: thiếu quyền thư viện PRDLIB (tồn từ T3 06/10)",
    "issue: VDI chậm (tồn từ T5 08/10)",
    "review batch (tồn từ T6 09/10)"
   ],
   "as400": "08:10–17:35"
  }
 ],
 "previous_week": {
  "week": "2026-W40",
  "work_days": 5,
  "deep_hours_total": 13.4,
  "deep_hours_avg": 2.7,
  "avg_score": 76,
  "avg_total_score": 84,
  "days_reached_goal": 0
 }
}
```

</details>

<details><summary>Chào buổi sáng, kiểu Kinh Thánh (<code>morning:bible</code>)</summary>

```
VIỆC CẦN LÀM: viết tin nhắn chào buổi sáng, gửi tự động qua Telegram lúc người dùng bắt đầu ngày làm việc.
Chọn MỘT câu Kinh Thánh của Tin Lành (Cơ Đốc giáo Tin Lành) về đừng bỏ cuộc, đừng nản lòng, sức mới, phó thác, bình an, hoặc làm việc hết lòng. Chỉ dùng 66 sách Kinh Thánh Tin Lành, KHÔNG dùng các sách Thứ Kinh/Đệ Nhị Kinh (Tô-bi-a, Giu-đi-tha, Khôn Ngoan, Huấn Ca, Ma-ca-bê, Ba-rúc) và không dùng tên sách theo bản Công giáo. Trích nguyên văn theo bản dịch Truyền Thống 1926 (bản Hội Thánh Tin Lành Việt Nam dùng), ghi đúng sách chương câu (ví dụ Ga-la-ti 6:9). Không chắc chữ chính xác thì chọn câu quen thuộc khác.
Lời khích lệ LUÔN tích cực, ấm áp, đầy hy vọng: không chê trách, không nhắc thất bại, không so sánh tiêu cực, không doạ nạt (kể cả giọng sếp khó tính: nghiêm nhưng vẫn khích lệ).

THÔNG TIN (JSON, app đã tách sẵn theo ngày):
- "today": thông tin của hôm nay 2026-10-14. Ngày làm việc mới bắt đầu nên CHƯA có số liệu tập trung hôm nay.
- "previous_workday" (nếu có): báo cáo ngắn của ngày làm việc trước, có ghi rõ ngày. Đó là chuyện đã qua,
  không phải số liệu hôm nay; nhắc tới thì nói rõ là hôm đó (ví dụ "hôm qua" hoặc "thứ Sáu tuần trước").
{
 "today": {
  "date": "2026-10-14",
  "weekday": "thứ Tư",
  "first_task": "fix job đối soát",
  "streak_days": 2
 },
 "previous_workday": {
  "date": "2026-10-13",
  "summary": "tập trung sâu 3h 20m"
 }
}

Viết 3–5 dòng, văn bản thường:
1. Một câu chào buổi sáng ngắn, đúng giọng văn và cách xưng hô.
2. Câu trích (nguyên văn, kèm nguồn) trên một dòng riêng.
3. Một câu nối ý câu trích với hôm nay: nếu today có first_task thì khích lệ bắt đầu ngay bằng việc đó; nếu có
   previous_workday thì chỉ nhắc điểm tốt của ngày đó (không nhắc điểm yếu).
4. Nếu today có pending_from_previous_workday (việc trong kế hoạch và issue các ngày trước chưa thấy ghi xong, cộng
   dồn, việc tồn lâu có ghi "tồn từ ..."):
   app sẽ TỰ gửi nguyên danh sách ngay dưới tin nhắn của bạn, nên bạn KHÔNG chép lại danh sách; chỉ thêm một câu nhẹ
   nhàng khích lệ xử lý dứt điểm các việc còn tồn (có thể nêu tên 1 việc quan trọng nhất), không trách móc.
Không chèn số liệu khô khan, không lên lớp.
```

</details>

<details><summary>Câu khích lệ (<code>encourage:motivation</code>)</summary>

```
VIỆC CẦN LÀM: viết một lời khích lệ gửi qua Telegram.
Chọn MỘT châm ngôn / câu nói có thật của người thành đạt hoặc danh nhân, nhà hiền triết thời xưa (ví dụ Khổng Tử, Mạnh Tử, Lão Tử, Seneca, Marcus Aurelius, Edison) về kiên trì, không bỏ cuộc, tập trung. Ghi đúng tác giả; câu nước ngoài thì dịch sang tiếng Việt tự nhiên. Không chắc tác giả thì chọn câu khác. KHÔNG dùng Kinh Thánh.
Lời khích lệ LUÔN tích cực, ấm áp, đầy hy vọng: không chê trách, không nhắc thất bại, không so sánh tiêu cực, không doạ nạt (kể cả giọng sếp khó tính: nghiêm nhưng vẫn khích lệ).

Tình huống lúc này: buổi chiều, đang giữ nhịp tốt; đã tập trung sâu 2h 10m / mục tiêu 4h, ngoài VDI 12m, bây giờ là 14:30

Trả lời đúng 2 dòng: dòng 1 là câu trích (kèm nguồn), dòng 2 là một câu ngắn gắn với tình huống, gợi ý một bước nhỏ làm ngay.

Đừng lặp lại các câu đã gửi hôm nay và hôm qua (nguyên văn):
- "Đường tuy ngắn, không đi không bao giờ đến; việc tuy nhỏ, không làm chẳng bao giờ nên." — Tuân Tử
```

</details>

<details><summary>Hỏi AI (<code>ask</code>, có tra web)</summary>

```
VIỆC CẦN LÀM: người dùng đang ở chế độ "hỏi AI" của bot và gửi câu hỏi dưới đây. Câu hỏi có thể về
bất kỳ chủ đề nào (tập trung, công việc, AS400/COBOL/Life Asia, sức khoẻ, tài chính, kiếm thêm thu nhập, gia đình...).
- Mỗi câu hỏi độc lập: bạn KHÔNG thấy các câu hỏi trước. Nếu câu hỏi nhắc tới "câu trước", nói ngắn rằng bạn không xem
  được câu trước và nhờ người dùng hỏi lại đầy đủ.
- Trả lời thẳng vào câu hỏi, cụ thể, làm được; ưu tiên bước hành động. Tối đa khoảng 250 từ trừ khi câu hỏi cần dài hơn.
- Câu hỏi cần thông tin mới nhất (giá vàng, tỷ giá, giá xăng, tin tức, thời tiết, lịch sự kiện...): dùng công cụ tìm
  kiếm web nếu có, ưu tiên nơi người dùng sống, ghi rõ nguồn và thời điểm của số liệu. Không tra được thì nói thẳng là
  không có số liệu thời gian thực và gợi ý nơi xem (ví dụ trang SJC, PNJ, ngân hàng); TUYỆT ĐỐI không bịa số.
- Dùng thông tin về người dùng (tên, tuổi, nơi sống, công việc, hệ thống đang làm, số liệu hôm nay) khi liên quan để
  trả lời sát hoàn cảnh; không liên quan thì bỏ qua.
- Việc nhạy cảm (y tế, pháp lý, đầu tư): đưa thông tin chung và khuyên hỏi chuyên gia; không hứa lợi nhuận.
- Giữ đúng cách xưng hô và giọng văn đã dặn.

Thông tin lúc này (JSON): {"luc_nay": "2026-10-14 10:35 (+08, UTC+0800)", "thu": "thứ Tư", "so_lieu_tap_trung_hom_nay": "đã tập trung sâu 1h 35m / mục tiêu 4h, ngoài VDI 0m, bây giờ là 10:35"}

Câu hỏi của người dùng: """giá vàng SJC hôm nay bao nhiêu?"""
```

</details>

<details><summary>Hiểu tin nhắn (<code>intent</code>): phần thêm vào system prompt + prompt</summary>

```
(system prompt chung, rồi:)
Bạn là bộ phân tích lệnh cho bot Telegram theo dõi tập trung của một người làm việc trong máy ảo VDI.
Nhiệm vụ: đọc tin nhắn tiếng Việt và chọn ĐÚNG MỘT action trong danh sách, kèm tham số.
Chỉ trả về JSON một dòng, không giải thích, không markdown.

Hôm nay là 2026-10-14 (thứ Tư). Danh sách action:
[{"action": "xem_hom_nay", "mo_ta": "Xem số liệu tập trung, điểm, chuỗi ngày, kế hoạch đầu ngày, năng lượng, output, issue của hôm nay hoặc một ngày đã qua", "tham_so": {"day": "pastdate: ngày đã qua muốn xem lại (bỏ trống = hôm nay) (không bắt buộc)"}}, {"action": "gui_bao_cao", "mo_ta": "Gửi file báo cáo HTML chi tiết của hôm nay hoặc một ngày đã qua", "tham_so": {"day": "pastdate: ngày đã qua muốn xem lại (bỏ trống = hôm nay) (không bắt buộc)"}}, {"action": "xem_tuan", "mo_ta": "Tổng kết tuần: giờ vàng, ngày tốt/kém nhất, issue lặp lại", "tham_so": {}}, {"action": "xem_gio_vang", "mo_ta": "Xem khung giờ tập trung tốt nhất 14 ngày gần nhất", "tham_so": {}}, {"action": "xem_trang_thai", "mo_ta": "Lúc này đang trong VDI hay ngoài, idle bao lâu", "tham_so": {}}, {"action": "ghi_ke_hoach", "mo_ta": "Ghi kế hoạch / 3 việc quan trọng hôm nay (không có nội dung thì bot hỏi từng câu)", "tham_so": {"text": "text: nội dung kế hoạch (không bắt buộc)"}}, {"action": "ghi_output", "mo_ta": "Ghi nhanh một việc vừa làm xong (output)", "tham_so": {"text": "text: việc đã xong"}}, {"action": "ghi_issue", "mo_ta": "Ghi ngay một issue, blocker, việc bị chặn (VDI chậm, thiếu quyền, chờ người khác)", "tham_so": {"text": "text: nội dung issue"}}, {"action": "ghi_phan_tam", "mo_ta": "Ghi điều làm mất tập trung hoặc lý do vừa bị gián đoạn hôm nay (con khóc, việc nhà, họp đột xuất, người hỏi chuyện, điện thoại...)", "tham_so": {"text": "text: điều làm mất tập trung"}}, {"action": "ghi_viec_ngay_mai", "mo_ta": "Ghi việc đầu tiên sẽ làm sáng mai (sáng mai bot nhắc lại)", "tham_so": {"text": "text: nội dung"}}, {"action": "ghi_nang_luong", "mo_ta": "Ghi mức năng lượng hôm nay từ 1 đến 5", "tham_so": {"energy": "energy: mức năng lượng 1–5"}}, {"action": "ghi_gio_as400", "mo_ta": "Ghi giờ vào và ra AS400 hôm nay (HH:MM). Có thể gửi ảnh spooled file thay vì gõ", "tham_so": {"start": "HH:MM giờ vào", "end": "HH:MM giờ ra (không bắt buộc)"}}, {"action": "tong_ket_ngay", "mo_ta": "Bắt đầu hỏi tổng kết cuối ngày từng câu (output, issue, AS400, việc mai, năng lượng)", "tham_so": {}}, {"action": "bao_nghi", "mo_ta": "Báo một ngày nghỉ (hôm nay hoặc ngày khác) để bot không nhắc gì ngày đó", "tham_so": {"day": "date: ngày nghỉ (không bắt buộc)", "reason": "text: lý do (không bắt buộc)"}}, {"action": "nghi_phep", "mo_ta": "Báo nghỉ phép nửa ngày buổi sáng, nửa ngày buổi chiều, hoặc cả ngày (hôm nay hoặc ngày khác): bot không theo dõi, không nhắc trong phần nghỉ; nghỉ nửa ngày thì mục tiêu còn một nửa", "tham_so": {"part": "leavepart: buổi nghỉ: am (buổi sáng) | pm (buổi chiều) | full (cả ngày, mặc định) (không bắt buộc)", "day": "date: ngày nghỉ (mặc định hôm nay) (không bắt buộc)", "reason": "text: lý do (không bắt buộc)"}}, {"action": "bao_di_lam", "mo_ta": "Huỷ ngày nghỉ hoặc nghỉ phép (cả ngày hay nửa ngày) đã báo, làm việc lại bình thường", "tham_so": {"day": "date: ngày (không bắt buộc)"}}, {"action": "tam_dung", "mo_ta": "Tạm dừng theo dõi (ví dụ việc riêng)", "tham_so": {}}, {"action": "tiep_tuc", "mo_ta": "Theo dõi lại sau khi tạm dừng", "tham_so": {}}, {"action": "xin_cau_dong_luc", "mo_ta": "Xin một câu nói truyền động lực", "tham_so": {}}, {"action": "xin_cau_kinh_thanh", "mo_ta": "Xin một câu Kinh Thánh khích lệ", "tham_so": {}}, {"action": "xem_ai", "mo_ta": "Xem AI đang dùng model nào, đã gọi bao nhiêu lần", "tham_so": {}}, {"action": "xoa_cache_ai", "mo_ta": "Xoá cache model AI và các nhận xét AI đã lưu", "tham_so": {}}, {"action": "xem_hieu_nang", "mo_ta": "Xem tracker tốn bao nhiêu CPU/RAM", "tham_so": {}}, {"action": "bat_tat_ai_danh_gia", "mo_ta": "Bật hoặc tắt việc AI tự đọc báo cáo và nhắn đánh giá cuối ngày, cuối tuần; không kèm on/off thì xem trạng thái", "tham_so": {"state": "onoff: on (bật) / off (tắt) (không bắt buộc)"}}, {"action": "hoi_ai", "mo_ta": "Hỏi AI bất kỳ câu gì (tập trung, công việc, AS400, sức khoẻ, thu nhập...) và nhận câu trả lời; hoặc bật/tắt chế độ hỏi AI (text = on / off); không kèm gì thì xem trạng thái", "tham_so": {"text": "text: câu hỏi, hoặc on / off (không bắt buộc)"}}, {"action": "cai_khich_le", "mo_ta": "Bật/tắt tự gửi lời khích lệ đầu ngày, buổi chiều; chọn chỉ danh ngôn (không Kinh Thánh), chỉ Kinh Thánh, hoặc cả hai; không kèm lựa chọn thì xem cài đặt hiện tại", "tham_so": {"mode": "encmode: on | off | quote | bible | both (không bắt buộc)"}}, {"action": "bat_tat_kinh_thanh", "mo_ta": "Nút gạt Kinh Thánh: on = lời chào buổi sáng và lời khích lệ dùng Kinh Thánh, off (mặc định khi cài lần đầu) = mọi tin chỉ dùng châm ngôn người thành đạt, danh nhân xưa (cho người không theo đạo); không kèm gì thì đảo trạng thái hiện tại", "tham_so": {"state": "onoff: on (Kinh Thánh) / off (danh ngôn) (không bắt buộc)"}}, {"action": "doi_giong", "mo_ta": "Đổi giọng nói của bot và AI: than_mat, vui_tuoi, hai_huoc, sep_kho_tinh; không kèm giọng thì xem giọng hiện tại", "tham_so": {"tone": "tone: giọng: than_mat | vui_tuoi | hai_huoc | sep_kho_tinh (không bắt buộc)"}}, {"action": "doi_muc_nhac", "mo_ta": "Đổi mức nhắc khi sao nhãng (ra ngoài VDI, thu nhỏ VDI): off (tắt hẳn), nhe (1 lần/ngày), vua (1 lần mỗi lần sao nhãng), nghiem (nhắc lặp, gắt hơn); không kèm mức thì xem mức hiện tại", "tham_so": {"level": "nudgelevel: mức: off | nhe | vua | nghiem | mac_dinh (không bắt buộc)"}}, {"action": "canh_bao_tien_do", "mo_ta": "Xem tiến độ hôm nay (giờ làm thật trong VDI so với nhịp cần để đạt mục tiêu và về đúng giờ); on/off bật tắt cảnh báo tiến độ tự động ở các mốc trong ngày", "tham_so": {"state": "onoff: on (bật) / off (tắt) (không bắt buộc)"}}, {"action": "tu_tinh_nang_luong", "mo_ta": "Xem / bật / tắt việc bot tự tính năng lượng 1–5 lúc tổng kết cuối ngày khi bạn chưa chấm, dựa trên số liệu tập trung (càng tập trung sâu lâu càng cạn)", "tham_so": {"state": "onoff: on (bật) / off (tắt) (không bắt buộc)"}}, {"action": "nhac_nghi_ngoi", "mo_ta": "Bật/tắt nhắc đứng dậy đi lại, vươn vai, tập mắt (chống cận) khi ngồi làm liên tục lâu, hoặc đổi số phút; không kèm gì thì xem cài đặt", "tham_so": {"every": "health: on | off | số phút (ví dụ 45) | mac_dinh (không bắt buộc)"}}, {"action": "nhac_uong_nuoc", "mo_ta": "Bật/tắt nhắc uống nước trong giờ làm, hoặc đổi số phút; không kèm gì thì xem cài đặt", "tham_so": {"every": "health: on | off | số phút (ví dụ 45) | mac_dinh (không bắt buộc)"}}, {"action": "gio_bot", "mo_ta": "Xem hoặc đổi giờ bot (tracker) tự bật và tự tắt mỗi ngày làm việc thứ 2 – thứ 6: start = giờ bật HH:MM, stop = giờ tắt HH:MM, reset = true để về giờ trong settings.json; không kèm gì thì xem giờ hiện tại", "tham_so": {"start": "clock: giờ BẬT bot HH:MM (24h) (không bắt buộc)", "stop": "clock: giờ TẮT bot HH:MM (24h) (không bắt buộc)", "time": "clock: giờ HH:MM khi câu không nói rõ là bật hay tắt (không bắt buộc)", "reset": "flag: true = về giờ trong settings.json (không bắt buộc)"}}, {"action": "huy", "mo_ta": "Huỷ thao tác đang chờ xác nhận hoặc đang hỏi dở", "tham_so": {}}, {"action": "tro_giup", "mo_ta": "Xem danh sách lệnh", "tham_so": {}}, {"action": "tro_chuyen", "mo_ta": "Tâm sự, than mệt, chán, cần động viên, hoặc tin nhắn không thuộc thao tác nào ở trên", "tham_so": {"text": "text: tin nhắn (không bắt buộc)"}}]

Tin nhắn của người dùng: """mai làm tiếp job đối soát"""

Quy tắc:
- Chọn action khớp nhất. Câu HỎI cần được trả lời (kiến thức, lời khuyên, giá vàng, tỷ giá, cách làm...) -> "hoi_ai"
  với text là nguyên câu hỏi. Tin nhắn tâm sự, than mệt/chán hoặc không thuộc action nào -> "tro_chuyen".
- Kể lý do vừa bị gián đoạn, bận việc khác, bị kéo khỏi việc ("nãy giờ bận trông em bé khóc", "bị sếp gọi đi họp gấp",
  "hàng xóm khoan tường ồn quá") -> "ghi_phan_tam" với text là nguyên câu, KHÔNG phải "tro_chuyen".
- Tham số text: giữ nguyên ý và từ ngữ của người dùng, bỏ phần dẫn như "ghi giúp", "việc ngày mai là".
- Ngày dạng YYYY-MM-DD (tự tính "mai", "thứ 6 này"...). Giờ dạng HH:MM 24h.
- Không đoán bừa tham số bắt buộc; thiếu thì vẫn chọn action và để trống.
- Nghỉ phép / nghỉ nửa ngày ("chiều nay nghỉ phép", "mai nghỉ buổi sáng") -> "nghi_phep" với part = am (sáng) |
  pm (chiều) | full (cả ngày); "sáng mai"/"chiều mai" = buổi đó của NGÀY MAI. Huỷ nghỉ -> "bao_di_lam".
- Giờ bot (tracker) tự bật / tự tắt ("bật bot lúc 8 rưỡi", "cho bot chạy từ 8h đến 18h") -> "gio_bot" với start / stop
  HH:MM 24h ("6 giờ chiều" = 18:00); hỏi bot chạy mấy giờ -> "gio_bot" không tham số.
Trả về: {"action": "<tên>", "args": {...}}
```

AI trả `{"action": "ghi_viec_ngay_mai", "args": {"text": "làm tiếp job đối soát"}}` → app kiểm tra action có thật, tham số hợp lệ, rồi mới làm thẻ xác nhận.

</details>

<details><summary>Đọc ảnh AS400 (<code>as400_photo</code>, không có system prompt)</summary>

```
Ảnh này là màn hình AS400 (ví dụ danh sách spooled file / job log) của ngày 2026-10-14.
Tìm thời điểm SỚM NHẤT và MUỘN NHẤT của ngày 2026-10-14 xuất hiện trong ảnh (giờ:phút).
Chỉ trả về JSON một dòng, không giải thích:
{"start": "HH:MM" hoặc null, "end": "HH:MM" hoặc null, "note": "ghi chú ngắn nếu ảnh mờ/không rõ"}
```

</details>

### 7.6 Quota, đếm lượt, đếm từ

| | |
|---|---|
| Đếm từ | `words_in` = số từ (tách theo khoảng trắng) của prompt + system; `words_out` = số từ câu trả lời. Đếm từ cho nhẹ, không đếm token |
| `data/ai_usage.json` | Theo tháng: số lượt, từ gửi / nhận; theo ngày (31 ngày): số lượt, từ, dùng cho việc gì; theo model: lượt gọi **thô** mỗi ngày (7 ngày, tính cả lần thử lại) |
| `data/ai_model.json` | `model` (gần nhất), `candidates` (model Google liệt kê), `resolved_at`, `cache_date`, `quota_exhausted` [{model, date, at}], `offline_until`, `rule_parser_mode` |
| Quota còn lại | Google không báo nên app ước tính: `gemini_free_calls_per_model` (20) − lượt thô hôm nay của model đó. Hạn mức tự đặt: `ai_daily_call_budget`. **Chỉ để báo cáo, không bao giờ chặn AI**: vượt số ước tính app vẫn gọi bình thường. App chỉ bỏ qua một model khi chính Google trả lỗi 429 hết quota ngày; mọi model đều bị Google từ chối thì nghỉ 3 tiếng rồi tự thử lại |
| Xem | `/status`, `/aistatus` |
| Xoá | `/clearcache` hoặc `python focus_tracker.py clearcache`: xoá cache model và mọi nhận xét AI đã lưu, lần gọi sau dò model lại từ đầu |
| Nhật ký | Mỗi lời gọi: `focus.log` dòng `AI ok provider=... model=... purpose=... in=... out=... ms` hoặc `AI fail ...`; audit `AI_CALL` / `AI_ERROR` |
| Prompt đã gửi | `data/logs/ai-prompts-YYYY-MM-DD.log`: **nguyên văn** SYSTEM + PROMPT sau khi điền số liệu, rồi TRẢ LỜI (hoặc LỖI), kèm giờ, purpose, model, ms. AI trả lời lạ thì mở file này xem AI đã nhận gì. Không ghi key, không lưu ảnh (chỉ ghi số byte). Giữ `ai_prompt_log_days` (14) ngày rồi housekeeping tự xoá; `0` = không ghi |

---

## 8. Dữ liệu lưu ở đâu

Mọi thứ nằm trong thư mục app, trên máy bạn (`data_dir` = `data`, `report_dir` = `reports`, tương đối so với thư mục app).

| Đường dẫn | Nội dung | Giữ |
|---|---|---|
| `data/focus.db` (+ `-wal`, `-shm`) | SQLite (WAL, `synchronous=NORMAL`): mọi bảng dưới đây | Xem mục 10 |
| `data/audit.log` | Nhật ký sự kiện hôm nay (mục 9) | Qua ngày chuyển vào `data/logs/` |
| `data/logs/` | `focus.log*`, `audit-YYYY-MM-DD.log`, `config-error.txt`, `launcher-error.txt`, `launchd.err.log` | Mục 9, 10 |
| `data/backup/focus-YYYY-MM-DD.db.zip` | Bản sao DB nén mỗi ngày | `keep_db_backups` (3) bản |
| `data/ai_model.json`, `data/ai_usage.json` | Model đang dùng, quota, lượt và số từ đã dùng | Mục 7.6 |
| `data/holidays_<năm>.json`, `data/holiday_fetch.json` | Lịch lễ đã tải từ MOM, lần tải gần nhất | 2 năm trước |
| `data/housekeeping_last_run.txt` | Ngày dọn gần nhất | — |
| `data/demo/` | Dữ liệu giả của lệnh `demo` | — |
| `reports/focus-YYYY-MM-DD.html`, `reports/focus-week-YYYY-Www.html` | Báo cáo HTML ngày, tuần | `keep_reports_days` (30) |
| `config/settings.json(.bak)`, `config/persona.json`, `config/secrets.env` | Cấu hình. `.bak` do `/giobot` tạo | Bạn giữ. **secrets.env không chia sẻ** |
| `config/python_path.txt`, `config/python_path.cmd` | (Windows) Python mà script cài tìm được | — |

**Các bảng trong `focus.db`**

| Bảng | Cột chính | Ghi |
|---|---|---|
| `samples` | `ts`, `dur`, `idle`, `locked`, `vdi_state`, `fg_proc`, `fg_title` (rỗng trừ khi `store_window_titles`), `vdi_full` | Mẫu 5 giây, gom 12 mẫu ghi 1 lần (mỗi phút). DB bận / đầy thì giữ tối đa 2000 mẫu trong RAM |
| `notes` | `day`, `plan`, `output`, `issues`, `distractions`, `energy`, `tomorrow`, `as400_start`, `as400_end`, `day_off`, `leave_part` (`am`/`pm`), `energy_source` (`auto` = bot tự tính lúc tổng kết, trống = bạn tự chấm), `updated` | Ghi chú theo ngày. Ghi bằng `BEGIN IMMEDIATE` (an toàn khi bot và tracker cùng ghi) |
| `daily_stats` | `day`, `data` (JSON số liệu ngày, có `v` = phiên bản cách tính, giờ làm ngoài giờ `ot` và các khoảng giờ `ot_ranges`, số lần thu nhỏ / ngồi yên / rời máy, điểm tổng `total`), `updated` | Chốt số liệu ngày, giữ mãi (mẫu thô bị xoá sau 35 ngày nhưng số liệu ngày còn). Bản ghi cách tính cũ mà mẫu thô còn thì app tự tính lại; sáng hôm sau app chốt lại ngày làm việc trước để có phần làm ngoài giờ |
| `ai_cache` | `key` (`review:<ngày>:<băm>`, `week:<tuần>:<băm>`), `created`, `text` | Lời AI đánh giá |
| `quotes` | `ts`, `style`, `text` | Câu khích lệ đã gửi: chỉ lưu câu trích (nguyên văn), để không lặp trong 2 ngày |
| `sent_log` | `day`, `kind`, `ts` | Việc đã làm hôm nay, để mỗi việc chỉ 1 lần/ngày kể cả khi tracker khởi động lại |
| `prefs` | `key`, `value`, `updated` | Tuỳ chọn đổi qua Telegram (đè lên file cấu hình) |

| `sent_log.kind` | Nghĩa |
|---|---|
| `morning`, `plan`, `review`, `summary`, `boost` | Chào sáng, hỏi kế hoạch, hỏi tổng kết, tổng kết ngày, khích lệ chiều |
| `weekly` (khoá = mã tuần) | Tổng kết tuần |
| `pace_HHMM`, `pace_praise` | Mốc tiến độ, lời khen tiến độ |
| `not_fullscreen`, `nudge_light` | Gợi ý phóng to, nhắc mức nhẹ (1 lần/ngày) |
| `leave_notice`, `off_notice` | Đã báo nghỉ phép / ngày nghỉ |
| `holiday_warn` (khoá `YYYY-12`) | Đã nhắc thiếu lịch lễ năm sau |

| `prefs.key` | Đặt bằng |
|---|---|
| `ai_review_enabled` | `/aireview` |
| `giong` | `/style` |
| `encouragement_enabled`, `encouragement_styles` | `/encourage`, `/kinhthanh` |
| `ask_mode` | `/ask on/off` |
| `tg_name` | Tên Telegram của bạn (AI gọi tên này nếu persona chưa có `ten`) |
| `nudge_level` | `/nudge` |
| `pace_check_enabled` | `/pace on/off` |
| `energy_auto_enabled` | `/autoenergy on/off` |
| `break_enabled`, `break_minutes`, `water_enabled`, `water_minutes` | `/break`, `/water` |
| `auto_start_at`, `auto_stop_at`, `hours_orig` | `/giobot` (`hours_orig` = giờ trong settings.json trước lần đổi đầu, để `mac_dinh` trả lại) |
| `ai_review_retry` | Đánh giá AI đang chờ gửi lại |

Đổi qua Telegram rồi muốn về giá trị trong file: `/style mac_dinh`, `/aireview mac_dinh`, `/encourage mac_dinh`, `/nudge mac_dinh`, `/pace mac_dinh`, `/break mac_dinh`, `/water mac_dinh`, `/giobot mac_dinh`.

---

## 9. Log

| File | Gì | Định dạng | Giữ |
|---|---|---|---|
| `data/logs/focus.log` | Log **kỹ thuật** đầy đủ (mức DEBUG): mọi tin nhắn nhận, lệnh, cách hiểu tin nhắn, mỗi lần gọi AI (model, purpose, số từ, ms), cảnh báo, việc chạy nền, đổi trạng thái VDI / khoá máy, hiệu năng mỗi 10 phút, mọi lỗi kể cả lỗi nhỏ đã tự xử lý (kèm traceback). Lỗi không ai bắt ở mọi luồng cũng được ghi (excepthook) | `2026-10-14 09:31:05,123 INFO    MainThread tracker: ...` | Xoay lúc nửa đêm thành `focus.log.YYYY-MM-DD`, giữ 30 bản |
| `data/audit.log` | Nhật ký **sự kiện** dễ đọc, 1 sự kiện 1 dòng (cũng chép vào focus.log) | `2026-10-14T09:31:05 \| ALERT_OUT_OF_VDI \| {...}` | Sang ngày chuyển thành `data/logs/audit-YYYY-MM-DD.log` |
| `data/logs/ai-prompts-YYYY-MM-DD.log` | Nguyên văn mọi prompt gửi AI + câu trả lời / lỗi (mục 7.6) | `===== 2026-10-14 17:00:03 · purpose=daily_review · model=... =====` rồi `--- SYSTEM ---`, `--- PROMPT ---`, `--- TRẢ LỜI ---` | `ai_prompt_log_days` (14) ngày |
| `data/logs/config-error.txt` | Lỗi cấu hình lúc khởi động | Chữ | 30 ngày |
| `data/logs/launcher-error.txt` | (Windows) `start_tracker.vbs` không chạy được Python | Chữ | Mục 10 |
| `data/logs/launchd.err.log` | (Mac) stderr của launchd | Chữ | Mục 10 |

Lỗi lặp lại mỗi 5 giây (ví dụ không đọc được cửa sổ) chỉ ghi lần đầu rồi tối đa 1 lần / 10 phút. Key / token không bao giờ được ghi ra log.

**Sự kiện audit**

| Nhóm | Sự kiện |
|---|---|
| Vòng đời | `START`, `STOP`, `CRASH`, `WAKE`, `NEW_DAY`, `OUTSIDE_WINDOW`, `AUTO_STOP`, `OFF_DAY`, `OFF_NOTICE`, `LEAVE_PAUSE`, `LEAVE_RESUME`, `PAUSE`, `RESUME`, `HOUSEKEEPING` |
| Cảnh báo | `ALERT_OUT_OF_VDI`, `ALERT_AWAY`, `ALERT_BACK`, `ALERT_BREAK`, `ALERT_WATER`, `ALERT_PHONE`, `ALERT_NOT_FULLSCREEN`, `PACE`, `PACE_CHECK` |
| Việc theo giờ | `JOB_MORNING`, `JOB_PLAN`, `JOB_REVIEW`, `JOB_SUMMARY`, `JOB_WEEKLY`, `JOB_BOOST`, `JOB_PACE_HHMM`, `MORNING_SENT`, `DAILY_SUMMARY_SENT`, `WEEKLY_SENT`, `CATCH_UP`, `ENCOURAGE` |
| Ghi chú | `NOTE_<TRƯỜNG>`, `PLAN_SAVED`, `REVIEW_SAVED`, `TOMORROW_SAVED`, `AS400_TIMES`, `DAY_OFF`, `DAY_ON`, `LEAVE` |
| Telegram | `PARSED` (mọi tin nhắn tự nhiên: nguồn ai/rule, action, tham số), `CONFIRMED`, `REJECT_STRANGER`, `BOT_ERROR`, `TELEGRAM_SEND_FAIL`, `TELEGRAM_BAD_TOKEN` |
| Cài đặt | `NUDGE_LEVEL`, `STYLE`, `AI_REVIEW`, `ASK_MODE`, `BOT_HOURS`, `BOT_HOURS_REJECT`, `AUTOSTART_UPDATE`, `SETTINGS_WRITE`, `CLEAR_CACHE` |
| AI | `AI_CALL`, `AI_ERROR`, `AI_QUOTA_EXHAUSTED`, `ASK_AI` |
| Lịch lễ | `HOLIDAYS_FETCHED`, `HOLIDAYS_FETCH_FAIL`, `HOLIDAYS_REJECTED`, `HOLIDAYS_MISSING` |

`/status` đếm số lần đã nhắc hôm nay từ các dòng `ALERT_*` trong `audit.log`.

---

## 10. Tự dọn dẹp (housekeeping), sao lưu, khôi phục

Chạy ở nền **mỗi ngày một lần** (lúc tracker khởi động, và khi sang ngày mới), cờ `data/housekeeping_last_run.txt`. Mỗi bước chạy riêng: một bước lỗi không chặn bước khác, không chặn việc đo. Chạy tay: `python focus_tracker.py housekeeping`.

| Thứ | Giữ / làm |
|---|---|
| Sao lưu DB | `data/backup/focus-YYYY-MM-DD.db.zip` (nén khoảng 3 lần), giữ `keep_db_backups` (3) bản mới nhất |
| `samples` (mẫu 5 giây, khoảng 0,55 MB/ngày làm việc) | `keep_samples_days` (35, tối thiểu 8) ngày. Trước khi xoá, chốt số liệu ngày vào `daily_stats` |
| `daily_stats`, `notes`, `prefs` | Giữ mãi (rất nhỏ) |
| `ai_cache` / `quotes` / `sent_log` | 60 / 90 / 30 ngày |
| `reports/focus-*.html` | `keep_reports_days` (30) ngày |
| `audit.log` | Quá 20.000 dòng thì cắt còn 5.000 dòng cuối |
| `logs/focus.log.*` | Tự xoay mỗi đêm, giữ 30 bản |
| `logs/config-error.txt` | Xoá sau 30 ngày |
| `logs/` file khác (`audit-*.log`, `launcher-error.txt`, `launchd.err.log`...) | Quá 1 MB thì cắt còn khoảng 200 KB cuối (giữ mã hoá UTF-16/UTF-8); `audit-YYYY-MM-DD.log` cũ hơn 30 ngày thì xoá; file `.txt`/`.log` khác không ghi 60 ngày thì xoá |
| `holidays_<năm>.json` | Giữ 2 năm trước |
| `*.tmp` (file ghi dở do tắt máy ngang) | Xoá khi cũ hơn 1 ngày |
| `focus/__pycache__`, `tests/__pycache__` | Xoá `.pyc` mồ côi (module đã xoá khi cập nhật, bản Python cũ) |
| `focus.db` | `VACUUM` ngày 1 hằng tháng hoặc khi chỗ trống > 25%; sau đó `wal_checkpoint(TRUNCATE)` |

Dùng hằng ngày, cả thư mục `data` thường vài chục MB. `/status` hiện dung lượng app đang dùng (DB, backup, log).

**Khôi phục từ bản sao lưu**

```
1. Tắt tracker (Windows: nhấp đúp go_tu_khoi_dong.bat; Mac: nhấp đúp go_tu_khoi_dong.command)
2. Giải nén data/backup/focus-YYYY-MM-DD.db.zip  (bên trong là focus.db)
3. Chép đè lên data/focus.db
4. Xoá data/focus.db-wal và data/focus.db-shm nếu có
5. Bật lại tracker (nhấp đúp cai_tu_khoi_dong.bat / cai_tu_khoi_dong.command)
```

---

## 11. Cấu hình

### 11.1 `config/settings.json`

Không bắt buộc. Chỉ cần ghi dòng muốn đổi; dòng không có dùng mặc định trong `focus/config.py`. File mẫu `config/settings.example.json` có mọi khoá dưới đây (trừ `data_dir`, `report_dir`) với giá trị mặc định, chỉ để tra: đừng chép nguyên thành `settings.json`. Khi nào cần tạo, cách tạo: mục 2.4 bước 7. Mọi khoá:

**Giờ giấc, mục tiêu**

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `work_start`, `work_end` | `"08:00"`, `"17:00"` | Giờ làm. Chỉ cảnh báo trong khung này |
| `lunch_start`, `lunch_end` | `"11:15"`, `"12:30"` | Nghỉ trưa: không cảnh báo |
| `auto_start_at`, `auto_stop_at` | `"08:00"`, `"23:59"` | Khung chạy của tracker (thứ 2 – thứ 6). Đổi nhanh `/giobot`. `auto_stop_at` phải sau `daily_summary_at`, `weekly_report_at`, `review_prompt_at`, `plan_prompt_after` |
| `plan_prompt_after` | `"08:00"` | Sau giờ này, lần đầu dùng máy: chào sáng + hỏi kế hoạch |
| `review_prompt_at` | `"16:45"` | Hỏi tổng kết cuối ngày |
| `daily_summary_at` | `"17:00"` | Tổng kết ngày + AI đánh giá |
| `afternoon_boost_at` | `"14:30"` | Câu khích lệ buổi chiều (`""` = tắt) |
| `weekly_report_day`, `weekly_report_at` | `"fri"`, `"16:50"` | Ngày (`mon`…`sun`) và giờ tổng kết tuần |
| `daily_focus_goal_hours` | `4` | Mục tiêu giờ tập trung sâu mỗi ngày (> 0) |
| `run_on_off_days` | `false` | `true` = vẫn chạy và ghi số liệu cuối tuần / lễ / ngày nghỉ (không nhắc) |
| `extra_off_days` | `[]` | Ngày nghỉ thêm, ví dụ `["2026-12-24"]` |

**Đo đạc, nhận VDI**

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `platform` | `"auto"` | `auto`, `windows` hoặc `mac` (nhận cả `win11`, `macos`...). Đặt sai với máy thật thì báo lỗi rõ |
| `sample_seconds` | `5` | Chu kỳ lấy mẫu (1–60 giây) |
| `idle_threshold_seconds` | `60` | Không chạm lâu hơn = ngồi yên |
| `away_threshold_seconds` | `300` | Ngồi yên lâu hơn (hoặc khoá máy) = rời máy |
| `focus_gap_seconds` | `120` | Hai đoạn VDI cách nhau không quá mức này vẫn cùng một khối |
| `min_focus_block_minutes` | `20` | Khối tập trung sâu tối thiểu |
| `vdi_processes` | `["citrix.desktopviewer.app.exe", "cdviewer.exe", "wfica32.exe", "msrdc.exe", "mstsc.exe", "citrix viewer", "windows app", "microsoft remote desktop"]` | Process / app của **khung** VDI. Ghi trong `settings.json` là thay cả danh sách: chép đủ tên mặc định rồi thêm tên mới |
| `vdi_session_processes` | `["citrix.engineui.app.exe"]` | Process của cửa sổ **mặt phiên** Citrix (tool window nhận phím khi gõ trong VDI, phủ khung Desktop Viewer). Đang hiện thật, đủ lớn và khung không thu nhỏ thì tính là cửa sổ VDI. Đã có sẵn trong app, **không cần** thêm vào `settings.json`; chỉ thêm khi Citrix đổi tên (mục 4.2) |
| `vdi_title_keywords` | `["Desktop Viewer"]` | Từ khoá tiêu đề. Dùng cho app Citrix tên lạ (Citrix đổi tên file khung) và khi không đọc được tên process |
| `vdi_browser_title_keywords` | `["AZ-WIN11-SGLIFE"]` | Citrix trong trình duyệt: từ khoá tiêu đề tab VDI (phần đầu tên máy ảo công ty). Máy ảo tên khác thì sửa, `[]` = tắt (mục 4.2) |
| `browser_processes` | `["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "google chrome", "microsoft edge", "safari", "firefox", "arc", "brave browser"]` | Trình duyệt được xét khi bật dòng trên |
| `extra_focus_processes` | `[]` | App trên máy thật cũng tính là làm việc, ví dụ `["code.exe"]` |
| `store_window_titles` | `false` | Lưu tiêu đề cửa sổ vào DB (mặc định chỉ lưu tên process) |

**Nhắc nhở**

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `nudge_level` | `"vua"` | `off` / `nhe` / `vua` / `nghiem` (mục 4.3). Đổi nhanh `/nudge` |
| `nudge_out_of_vdi_minutes` | `15` | Ngưỡng mức vừa (0 = mức vừa không nhắc) |
| `nudge_light_minutes` | `15` | Ngưỡng mức nhẹ (số nguyên) |
| `nudge_strict_minutes` | `5` | Mức nghiêm: nhắc sau N phút, lặp mỗi N phút (số nguyên) |
| `golden_hours` | `"auto"` | `"auto"`, `["09:00-11:00"]`, hoặc `[]` = tắt |
| `golden_nudge_minutes` | `5` | Ngưỡng nhắc trong giờ vàng (mức vừa / nghiêm) |
| `away_alert_minutes` | `15` | Rời máy quá N phút thì nhắc (0 = tắt) |
| `vdi_closed_alert` | `true` | Cửa sổ VDI biến mất trong giờ làm (Citrix tự ngắt) thì báo ngay (mục 4.4) |
| `phone_pattern_count` | `3` | Số lần ngồi yên 1–5 phút trong 30 phút để nhắc cất điện thoại (0 = tắt) |
| `fullscreen_tip_minutes` | `15` | Dùng VDI không toàn màn hình cộng dồn N phút (chỉ lúc VDI ở trước) thì gợi ý, 1 lần/ngày (0 = tắt) |
| `break_reminder_enabled`, `break_reminder_minutes` | `true`, `60` | Nhắc đứng dậy (0 phút = tắt). Đổi nhanh `/break` |
| `water_reminder_enabled`, `water_reminder_minutes` | `false`, `60` | Nhắc uống nước, **mặc định tắt** khi cài lần đầu (0 phút cũng = tắt). Bật nhanh `/water on` |
| `pace_check_enabled` | `true` | Cảnh báo tiến độ. Đổi nhanh `/pace` |
| `pace_target_vdi_hours` | `6` | Mục tiêu giờ làm thật trong VDI (0 < h ≤ 24) |
| `pace_checkpoints` | `["10:30", "14:00", "15:30"]` | Mốc kiểm tra (trong giờ làm, ngoài giờ trưa) |
| `pace_behind_ratio` | `0.4` | Chậm hơn mức cần quá tỉ lệ này thì nhắc (0 < r < 1) |
| `energy_auto_enabled` | `true` | Tới giờ tổng kết mà chưa chấm năng lượng thì bot tự tính và báo (mục 4.10). Đổi nhanh `/autoenergy` |
| `energy_capacity_hours` | `4` | Số giờ tập trung sâu một ngày thì coi là cạn sức (1–12) |

**AI, khích lệ, AS400**

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `ai_provider` | `"auto"` | `auto` / `gemini` / `claude` / `off` |
| `gemini_model` | `"auto"` | `auto` hoặc tên model ghim |
| `claude_model` | `"claude-opus-5-5"` | Model Claude |
| `ai_timeout_seconds` | `60` | Chờ tối đa mỗi lần gọi |
| `ai_daily_call_budget` | `0` | Hạn mức lượt/ngày tự đặt, chỉ để `/status` hiện còn bao nhiêu (0 = không đặt) |
| `gemini_free_calls_per_model` | `20` | Quota free mỗi model mỗi ngày, chỉ để ước tính còn lại (không chặn AI) |
| `ai_prompt_log_days` | `14` | Giữ log nguyên văn prompt AI bao nhiêu ngày (0 = không ghi) |
| `ai_review_enabled` | `true` | AI tự đánh giá ngày / tuần. Đổi nhanh `/aireview` |
| `work_context` | (Lập trình viên/BA Life Asia trên IBM i (AS400), COBOL, CL, DB2 for i; làm qua VDI Citrix) | Công việc của bạn, gửi kèm **mọi** lần gọi AI. **Sửa cho đúng việc của bạn** |
| `encouragement_enabled` | `true` | Tự gửi lời khích lệ. Đổi nhanh `/encourage` |
| `encouragement_styles` | `["motivation", "family"]` (Kinh Thánh tắt) | `motivation`, `bible`, `family`. Bật Kinh Thánh: `["bible"]` hoặc `/kinhthanh on` |
| `as400_enabled` | `true` | Hỏi giờ vào/ra AS400 trong `/review` |
| `as400_photo_ai` | `true` | Cho phép gửi ảnh AS400 lên AI (cảnh báo mục 1) |

**Lịch lễ, báo cáo, dọn dẹp, thư mục**

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `timesheet_data_dir` | `""` | Thư mục có `sg_holidays_<năm>.json` của app khác |
| `holiday_fetch_enabled` | `true` | Tự tải lịch lễ từ trang MOM |
| `mom_holidays_url` | `"https://www.mom.gov.sg/employment-practices/public-holidays"` | Trang lịch lễ (phải là `https://`) |
| `report_refresh_minutes` | `0` | Làm mới file báo cáo HTML mỗi N phút (0 = chỉ khi cần) |
| `keep_samples_days` | `35` | Giữ mẫu thô (≥ 8) |
| `keep_reports_days` | `30` | Giữ báo cáo HTML |
| `keep_db_backups` | `3` | Số bản backup (≥ 1) |
| `data_dir` | `"data"` | Thư mục dữ liệu (tương đối với thư mục app, hoặc đường dẫn tuyệt đối) |
| `report_dir` | `"reports"` | Thư mục báo cáo |

Khoá bắt đầu bằng `_` (ví dụ `"_ghi_chu"`) được bỏ qua. Khoá lạ: bỏ qua và nhắn báo.

### 11.2 `config/secrets.env`

| Khoá trong file | Khoá cấu hình | Kiểm tra |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `telegram_bot_token` | Dạng `123456789:AAH...` (≥ 20 ký tự sau dấu `:`) |
| `TELEGRAM_CHAT_ID` | `telegram_chat_id` | Một con số (nhóm thì có dấu `-`) |
| `GEMINI_API_KEY` | `gemini_api_key` | — |
| `ANTHROPIC_API_KEY` | `anthropic_api_key` | — |

Thiếu trong file thì đọc biến môi trường cùng tên. Ghi chú cuối dòng (`TOKEN=abc   # bot của tôi`), dấu cách thừa và dấu nháy được bỏ. Dòng bắt đầu bằng `#` bị bỏ qua cả dòng (lỗi hay gặp: điền key vào dòng `# ANTHROPIC_API_KEY=`). Cách tạo file và điền: mục 2.1, 2.4.

### 11.3 `config/persona.json`

Bắt buộc khi cài (mục 2.4 bước 6: cách điền từng dòng, quy tắc viết JSON, cách kiểm tra). App chỉ đọc file này lúc khởi động; `/style` đổi giọng lưu trong CSDL. Phần `check` của `kiem_tra_may` (`focus/persona.py`, hàm `check_lines`) báo ✗ khi thiếu file hoặc sai cú pháp JSON (kèm dòng, cột và lỗi bằng tiếng Việt), báo `!` khi gõ sai tên khoá, gõ sai giọng, hoặc còn trống `ten`, `tuoi`, `noi_song`, `mo_ta`. File sai cú pháp thì app bỏ qua cả file, dùng mặc định và ghi cảnh báo vào `focus.log`.

```json
{
  "ten": "Minh",
  "tuoi": "35",
  "noi_song": "TP.HCM, Việt Nam",
  "goi_nguoi_dung": "bro",
  "bot_xung": "tui",
  "ten_sep": "anh Tuấn",
  "giong": "hai_huoc",
  "mo_ta": "Dev AS400 5 năm, có 2 con nhỏ."
}
```

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `ten` | `""` | Tên bạn. Trống thì AI dùng tên Telegram |
| `tuoi` | `""` | Tuổi, để AI khuyên hợp hoàn cảnh |
| `noi_song` | `""` | Nơi sống (giá vàng, tỷ giá, thời tiết đúng nơi) |
| `goi_nguoi_dung` | `"bạn"` | Bot gọi bạn là gì: `bạn`, `bro`, `anh`, `chị`, `em`, tên... |
| `bot_xung` | `"mình"` | Bot tự xưng: `mình`, `tui`, `em`, `tôi`... |
| `ten_sep` | `""` | Tên sếp để "doạ nhẹ" trong nhắc lặp lại. Trống = không |
| `giong` | `"than_mat"` | `than_mat`, `vui_tuoi`, `hai_huoc`, `sep_kho_tinh` (mục 4.19) |
| `mo_ta` | `""` | Vài dòng về bạn, gửi kèm mọi lần gọi AI |

---

## 12. Lỗi thường gặp

Mọi lỗi gửi cho bạn đều được dịch thành câu tiếng Việt (`focus/errors.py`), không hiện mã lỗi thô; `focus.log` vẫn giữ traceback đầy đủ.

| Triệu chứng / câu bot báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bot không trả lời gì | Tracker chưa chạy (ngoài giờ, ngày nghỉ), token sai, mạng công ty chặn Telegram | `kiem_tra_may.bat check` (Mac `.command`); chạy `start_tracker.bat` / `start_tracker.command` xem log. Token sai (401/404): bot dừng phần Telegram nhưng **tracker vẫn đo**; sửa `TELEGRAM_BOT_TOKEN` rồi chạy lại |
| «Chat ID của bạn là ...» | Chưa điền `TELEGRAM_CHAT_ID` | Điền số đó vào `secrets.env`, lưu, chạy lại `start_tracker.bat` (mục 2.4 bước 5) |
| `start_tracker` báo «Hết 10 phút mà chưa thấy tin nhắn nào gửi cho bot» | Nhắn nhầm bot khác, hoặc chưa bấm gửi | Tìm đúng tên bot in trong khung, chạy lại `start_tracker` |
| `start_tracker` báo «Có chương trình khác đang đọc tin nhắn của bot này» | Tracker đang chạy ẩn, hoặc bot khác dùng chung token | Tắt tracker ẩn (mục 2.8), chạy lại |
| «...đang có một bản bot khác cùng token chạy ở máy khác» (409) | 2 máy cùng một bot | Tắt bản kia; mỗi người một bot |
| Luôn báo ngoài VDI dù đang trong VDI | Tên process VDI chưa có trong `vdi_processes` / `vdi_session_processes` (Citrix đổi tên sau khi cập nhật) | `kiem_tra_may.bat vdi`, làm theo mục 4.2 «Citrix đổi tên app ở bản sau». Citrix trong trình duyệt: `vdi_browser_title_keywords` (Mac: cấp Screen Recording) |
| `/status` báo «Không đọc được tên tiến trình của cửa sổ VDI (Citrix chạy quyền Admin?)» | Process VDI chạy quyền cao hơn | App tự chuyển sang nhận theo tiêu đề (`vdi_title_keywords`); kiểm tra từ khoá đúng tiêu đề |
| «Thấy app "..." nhưng không có trong "vdi_processes"» (Mac) | App Citrix tên khác | Thêm tên (chữ thường) vào `vdi_processes` |
| `/status` báo «Cửa sổ Citrix "....exe" phủ lên VDI, đang tạm tính là VDI...» (Windows) | Citrix cập nhật, đổi tên file mặt phiên. App vẫn đo đúng | Thêm tên đó vào `vdi_session_processes` (mục 4.2) |
| `/status` báo «Thấy cửa sổ Citrix lạ "....exe" ở trước nhưng chưa tính là VDI...» (Windows) | Citrix đổi tên file mặt phiên, đang ở Full screen hoặc chưa đối chiếu được với khung | Nếu lúc đó đang gõ trong VDI: thêm tên vào `vdi_session_processes`, chạy `kiem_tra_may.bat vdi` |
| «Chưa có API key AI nên mình chưa trả lời được» | Chưa điền key | Mục 2.3 |
| «Gemini từ chối: khoá bí mật ... sai hoặc đã bị thu hồi» | Key sai / bị khoá | Tạo key mới, `ai-test` |
| «Các model Gemini đều hết quota hôm nay ... quota tự reset khoảng 14–15h chiều giờ VN» | Hết gói free | Chờ; bot tự dùng từ khoá / nội dung có sẵn, 3 giờ sau thử lại; đánh giá AI tự gửi lại |
| «Server Gemini đang quá tải...» | 503 liên tục | Tự thử lại sau |
| «AI chưa đánh giá được hôm nay (...)» | AI lỗi lúc 17:00 | Không cần làm gì: thử lại mỗi 15 phút |
| «lỗi chứng chỉ bảo mật khi kết nối (thường do proxy/tường lửa công ty...)» | Proxy kiểm tra HTTPS | Mạng khác, hoặc nhờ IT mở `api.telegram.org`, `generativelanguage.googleapis.com` |
| «không có mạng hoặc không phân giải được tên máy chủ» / «mạng chậm» | Mất mạng, VPN, DNS | Kiểm tra mạng; tin sẽ gửi khi có mạng (hàng đợi 100 việc) |
| «dữ liệu đang bận (một chương trình khác đang mở file focus.db)» | DB bị khoá (mở bằng tool khác, OneDrive) | Đóng tool đó; không để app trong OneDrive |
| «file dữ liệu focus.db bị hỏng...» | DB hỏng | Khôi phục từ `data/backup` (mục 10) |
| «ổ đĩa đầy» | Hết chỗ | Xoá bớt file; `housekeeping` |
| «không có quyền ghi file ...» | File đang mở / antivirus / OneDrive khoá | Đóng file, chuyển app ra khỏi thư mục đồng bộ |
| `"work_start" phải có dạng HH:MM...` (và các câu `"<khoá>" phải ...`) | settings.json sai | Xem `data/logs/config-error.txt`, sửa đúng khoá được nêu |
| `TELEGRAM_BOT_TOKEN trong config/secrets.env không đúng dạng` | Token có dấu cách / ghi chú dính vào | Chép lại từ @BotFather |
| Bot gọi bạn «bạn», không đúng như `persona.json` | Thiếu file, đặt tên sai (`persona.json.txt`), sai cú pháp JSON, hoặc chưa khởi động lại tracker sau khi sửa | `kiem_tra_may.bat check` (Mac `.command`): dòng `✗ config/persona.json ...` nói rõ lỗi ở dòng, cột nào. Sửa xong khởi động lại tracker (mục 2.8) |
| `✗ config/persona.json không lưu dạng UTF-8` | Notepad lưu kiểu `ANSI` | Notepad: *File > Save As* > *Encoding* `UTF-8` > *Save* |
| `! Khoá lạ (gõ sai tên?), app bỏ qua: ...` | Gõ sai tên khoá trong `persona.json` | Sửa đúng tên như mục 2.4 bước 6 |
| Không tự chạy buổi sáng (Windows) | Task chưa cài / Python đổi chỗ | Task Scheduler > FocusTracker > History; xem `launcher-error.txt`; chạy lại `cai_tu_khoi_dong.bat` |
| Chuột phải `.ps1` > Run with PowerShell hỏi «Execution Policy Change» | Windows hỏi xác nhận trước khi chạy script | Gõ `Y` + Enter (chỉ trong cửa sổ đó), hoặc nhấp đúp `cai_tu_khoi_dong.bat` để khỏi bị hỏi |
| Không tự chạy (Mac) | launchd chưa nạp; hoặc thư mục app nằm trong Documents / Desktop / Downloads / iCloud (macOS chặn chạy nền đọc, `launchd.err.log` có «Operation not permitted»); hoặc Python bị tắt trong *Login Items > Allow in the Background* | `kiem_tra_may.command autostart` báo nguyên nhân. Chuyển thư mục ra `~/focus-tracker` hoặc bật lại Python, rồi nhấp đúp lại `cai_tu_khoi_dong.command` |
| Mac báo lỗi chứng chỉ (CERTIFICATE_VERIFY_FAILED) | Python từ python.org chưa có chứng chỉ gốc và không tìm thấy `/etc/ssl/cert.pem` | *Applications > Python 3.x* > nhấp đúp `Install Certificates.command` |
| `start_tracker.bat` chờ khoảng 2 phút rồi báo «Tracker khác vẫn đang chạy sau khi chờ, bản này thoát.» | Đã có bản chạy ẩn (khoá một bản) | Tắt bản ẩn trước (mục 2.8) |
| «Mình chưa hiểu tin nhắn này (AI không dùng được lúc này và không khớp từ khoá nào)» | AI lỗi và không có từ khoá | Dùng lệnh gạch chéo |
| «Yêu cầu này đã hết hạn hoặc đã xử lý. Nhắn lại nhé.» | Bấm OK sau 30 phút | Nhắn lại |
| «Chưa đọc được ảnh: ...» / ảnh quá lớn | Ảnh mờ, > 10 MB, AI lỗi | Gõ `/as400 08:10 17:35` |
| «⚠️ Không làm được «...»: ...» | Một việc chạy nền lỗi | Đọc lý do sau dấu hai chấm; chi tiết trong `focus.log` |
| Họp chỉ nghe bị tính rời máy | Không chạm phím/chuột | `/pause` khi họp lâu |
| Hỏi AI giá vàng, tin tức: AI nói «lần này không tra được web» | Hết lượt tra Google của gói Gemini free (tính riêng, rất ít; Gemini 3.x: 0 lượt) | Không cần làm gì: app tự hỏi lại không tra web. Muốn số liệu mới thì xem trang web trực tiếp (mục 4.17) |
| Nhắn lý do bị gián đoạn («nãy giờ bận trông em bé khóc») mà bot chỉ trò chuyện | Bản cũ (trước 2.3.0) | Cập nhật app; hoặc gõ `/distraction nội dung` |
| Sáng bị báo «Cửa sổ VDI đã đóng» dù chưa làm gì | Bản cũ (trước 2.3.0): mở VDI sớm, Citrix tự ngắt trước giờ làm | Cập nhật app. Từ 2.3.0 chỉ báo khi hôm đó đã làm trong VDI (mục 4.4) |
| `GEMINI_API_KEY trong config/secrets.env có dấu cách ở giữa` | Chép key bị đứt, xuống dòng | Chép lại nguyên key (mục 2.3, bảng lỗi hay gặp) |
| `TELEGRAM_CHAT_ID ... phải là một con số` | Gõ username bot hay chữ vào chat ID | Lấy lại số ở mục 2.4 bước 5 |

---

## 13. Giới hạn và việc cần kiểm tra trên máy thật

| Giới hạn | Ghi chú |
|---|---|
| Không biết bạn làm gì bên trong VDI | Mở VDI rồi đọc báo trong VDI vẫn tính là làm việc |
| Họp chỉ nghe | Bị tính rời máy; dùng `/pause` |
| Chỉ rê chuột qua VDI | Chưa tính là trong VDI |
| Lịch lễ có sẵn | Chỉ Singapore; nơi khác dùng `extra_off_days` / `/off`. Lễ thứ Bảy không tự nghỉ bù |
| Citrix trong trình duyệt | Phụ thuộc tiêu đề tab; Mac cần Screen Recording |
| Quota AI | Gói free có hạn; quota còn lại chỉ là **ước tính** |
| AI | Có thể hiểu sai: luôn đọc thẻ xác nhận (có dòng ⚠️ đối chiếu từ khoá) trước khi bấm OK |

| Cần kiểm tra trên máy thật | Vì sao |
|---|---|
| Windows: `probe` với Citrix Desktop Viewer thật (phóng to / vừa / thu nhỏ, 2 màn hình, DPI cao) | Test tự động dùng Win32 giả; `tests/test_windows_live.py` mở cửa sổ thật nhưng chỉ chạy trên Windows (trên máy khác tự bỏ qua) |
| Mac: `probe` với Citrix Viewer thật (Dock, Cmd+H, Space khác, toàn màn hình, màn hình ngoài, bấm ra desktop Finder) | Phần Mac (CoreGraphics, `NSWorkspace` qua libobjc) mới kiểm bằng giả lập |
| Tải lịch lễ từ trang MOM trên laptop công ty | Proxy / tường lửa có thể chặn; trang MOM có thể đổi cấu trúc. Xem `/status` và audit `HOLIDAYS_*` |
| `cai_tu_khoi_dong.ps1`, `go_tu_khoi_dong.ps1` trên Windows PowerShell 5.1 | Cài đã chạy được trên một laptop Windows thật (14/10/2026); gỡ và `/giobot` (sửa task qua PowerShell COM / `schtasks`) chưa thử trên máy thật |
| `cai_tu_khoi_dong_mac.sh` và mọi file `.command` trên macOS thật | Chưa có Mac để thử: `launchctl bootstrap` (thử lại 5 lần), Gatekeeper chặn file `.command` lần đầu |

---

## 14. Cho lập trình viên

### 14.1 Cấu trúc code

| Module (`focus/`) | Việc |
|---|---|
| `config` | Mặc định (`DEFAULTS`), đọc + kiểm tra `settings.json`, `secrets.env` |
| `probe` | Đọc trạng thái máy: Win32 qua ctypes; Mac qua CoreGraphics (dự phòng AppleScript/JXA) |
| `storage` | SQLite, ghi mẫu theo lô, ghi chú ngày (an toàn nhiều luồng), `sent_log`, `prefs` |
| `analysis` | Mẫu thô → số liệu ngày (cắt theo giờ làm chính thức, bỏ giờ trưa, phần ngoài giờ thành `ot` + `ot_ranges`), khối tập trung, điểm tập trung, streak, tuần, giờ vàng |
| `scoring` | Điểm tổng, hạng robot, công thức hiển thị, các câu nghiên cứu đã kiểm chứng (`SCIENCE`), lời khuyên khi điểm thấp |
| `robots` | Vẽ robot quà tặng 5 hạng bằng SVG (không dùng hình có bản quyền) |
| `report` + `report_html` | `report`: gom số liệu báo cáo ngày / tuần, OT 14 ngày (`ot_history`), ghi file; `report_html`: vẽ trang HTML (bảng màu Pop Art, dòng thời gian, robot, OT 14 ngày), không dùng thư viện ngoài |
| `pending` | Việc còn tồn cộng dồn qua các ngày làm việc (kế hoạch chưa thấy trong output + issue, tối đa 10 ngày làm việc), cho lời chào sáng, báo cáo HTML, đánh giá AI |
| `alerts` + `messages` | Máy trạng thái cảnh báo (lớp thuần) + câu chữ cảnh báo |
| `pace` | Tính tiến độ, mốc kiểm tra |
| `energy` | Tự tính năng lượng 1–5 lúc tổng kết khi bạn chưa chấm (công thức ở mục 4.10) |
| `schedule` | Khung chạy, giờ làm, trưa, nghỉ phép nửa ngày, việc theo giờ (hàm thuần) |
| `tracker` | Vòng lấy mẫu chính, khoá một bản, gửi việc vào hàng đợi |
| `notifier` | Hàng đợi nền (tối đa 100 việc) cho mọi việc mạng |
| `telegram_bot` | Long-poll Telegram, định tuyến tin nhắn, hỏi từng câu, thẻ xác nhận, tổng kết, gửi bù |
| `actions` + `intent` | Danh sách thao tác (lệnh, tham số, ví dụ, từ khoá), hiểu tin nhắn bằng AI / từ khoá, đối chiếu |
| `ai_client` + `ai_context` + `motivation` | Gọi AI, system prompt + giải nghĩa, prompt đánh giá / khích lệ / hỏi AI / đọc ảnh. **Không gửi `thinkingConfig`** cho Gemini (mục 7.1: không cần, và có model từ chối cả yêu cầu) |
| `persona` + `prefs` | Xưng hô, giọng; tuỳ chọn đổi qua Telegram |
| `holidays` | Lịch lễ Singapore (file, MOM, bảng có sẵn) |
| `net` | HTTPS dùng chung (Telegram, AI, MOM): một SSL context; Python chưa có chứng chỉ gốc (python.org trên Mac) thì dùng `/etc/ssl/cert.pem` của hệ điều hành |
| `autostart` | Sửa giờ Task Scheduler / plist khi `/giobot` |
| `housekeeping`, `demo`, `cli`, `logs`, `errors` | Dọn dẹp, dữ liệu giả, lệnh máy, log, dịch lỗi |

Thêm một thao tác Telegram: viết `_ten(bot, args)` trong `focus/actions.py`, thêm `Action(...)` vào `ACTIONS` (tên, lệnh, tiêu đề, mô tả, tham số, có ghi không, từ khoá dự phòng), thêm vào `HELP_GROUPS` / `EXAMPLES`. Bot, menu lệnh, catalog cho AI, từ khoá và bảng ở mục 5 (sinh từ code) tự nhận.

### 14.2 Vòng chạy của tracker

```
Task Scheduler (Windows) / launchd (Mac) gọi: focus_tracker.py run
  |
  v
Đã có một bản tracker khác đang chạy?
  |-- CÓ --> chờ tối đa 120 giây, bản kia vẫn chạy thì bản này thoát. HẾT
  |
  v (không)
Hạ ưu tiên CPU (Windows: BELOW_NORMAL + EcoQoS, Mac: nice 5) để không làm chậm máy
  |
  v
Giờ hiện tại nằm trong auto_start_at – auto_stop_at (08:00 – 23:59)?
  |-- KHÔNG --> thoát im lặng (audit OUTSIDE_WINDOW). HẾT
  |
  v (có)
Mở DB. Năm nay chưa có lịch lễ? --> tải trang MOM (tối đa 20 giây)
  |
  v
Hôm nay là ngày nghỉ (cuối tuần, lễ, nghỉ phép cả ngày, /off)?
  |-- CÓ --> nhắn 1 câu (trừ cuối tuần), thoát. HẾT
  |
  v (không)
Mở bot Telegram. Chạy nền: dọn dẹp, kiểm lịch lễ, gửi bù tổng kết bị lỡ
  |
  v
VÒNG LẶP mỗi 5 giây:
  |  1. Đọc trạng thái máy: cửa sổ VDI (phóng to / vừa / thu nhỏ / sau app khác / đã đóng),
  |     app đang ở trước, số giây không chạm phím/chuột, máy có khoá không
  |  2. Có cảnh báo tức thời (ngoài VDI, rời máy, VDI đã đóng, nhắc nghỉ...)? --> đưa vào hàng đợi gửi
  |  3. Mỗi 30 giây: tới giờ việc nào chưa (chào sáng, mốc tiến độ, hỏi tổng kết,
  |     tổng kết ngày 17:00, tổng kết tuần thứ Sáu 16:50)? --> làm việc đó (mỗi việc 1 lần/ngày)
  |  4. Mỗi 12 mẫu (1 phút): ghi số liệu vào DB
  |  5. Hai lần đo cách nhau > 120 giây? --> máy vừa ngủ dậy: audit WAKE, xoá đồng hồ cảnh báo
  |  6. Kiểm tra giờ:
  |       |-- quá auto_stop_at hoặc /off hôm nay --> chốt số liệu, thoát. HẾT
  |       |-- sang ngày mới --> chốt ngày cũ, bỏ /pause hôm trước, dọn dẹp, kiểm lịch lễ
  |       |                       |-- ngày mới là ngày nghỉ --> thoát. HẾT
  |       |                       |-- ngày làm việc --> chạy tiếp
  |       |-- còn lại --> chạy tiếp
  |
  +--> quay lại đầu VÒNG LẶP
```

| Chi tiết | |
|---|---|
| Đọc trạng thái lỗi | Bỏ qua tới 720 lần liên tiếp (khoảng 1 giờ) rồi mới dừng hẳn (audit `CRASH`) |
| Mạng | Mọi việc mạng (Telegram, AI) chạy trong hàng đợi nền: mạng chậm không làm lỡ mẫu. Hàng đợi đầy (mất mạng lâu) thì bỏ việc mới tới, không ăn RAM |
| Telegram | `getUpdates` long-poll 50 giây, lỗi thì chờ tăng dần 5 → 300 giây. Tin dài cắt mỗi 4000 ký tự, gửi thử 2 lần |
| `/off`, `/leave` hôm nay | Bot báo tracker đọc lại ngay ở vòng kế (sự kiện `recheck`) |
| Hiệu năng | Đo mỗi 10 phút (`/perf`) |

### 14.3 Chạy test

```
python focus_tracker.py selftest
# hoặc
python -m unittest discover -s tests -t .
```

| Kết quả lần chạy gần nhất (Linux, Python 3) | |
|---|---|
| Số test | 841, OK, 9 bỏ qua (`tests/test_windows_live.py` chỉ chạy trên Windows). Chạy được trên Python 3.9, 3.10, 3.13 |
| Thời gian | khoảng 50 giây |
| Dòng `[perf]` của `tests/test_tracker.py` (mô phỏng cả ngày làm việc) | `7919 vòng: 0.285 ms/vòng, CPU tương đương 0.0052% (1 nhân), RSS đỉnh 57.8 MB` |

RSS đỉnh là của **cả tiến trình chạy test** (nạp mọi module test), không phải riêng tracker; trên máy thật xem `/perf` hoặc `xem_cpu_ram.bat` (mục 4.18).

Test gồm: nhận diện VDI (kể cả VDI thu nhỏ mà Windows vẫn báo là cửa sổ đang chọn, thu nhỏ/phóng to liên tiếp), Mac giả lập, cảnh báo trong/ngoài giờ làm và giờ trưa, 4 mức nhắc, tiến độ, nhắc sức khoẻ, nghỉ phép, lịch lễ (trang MOM nhiều năm), mô phỏng cả ngày, bot (lệnh, nhắn tự nhiên, thẻ xác nhận, đối chiếu từ khoá, người lạ, tin cũ), `/giobot`, AI (lỗi mạng, hết quota, key sai, xoay model), ghi đồng thời nhiều luồng, dọn dẹp, dịch lỗi. Test không bao giờ gọi `schtasks` / `launchctl` thật.

### 14.4 Quản lý mã nguồn bằng Git / GitHub

| Việc | Cách làm |
|---|---|
| File không đưa lên | `.gitignore` đã chặn sẵn `config/secrets.env`, `config/settings.json`, `config/persona.json`, `config/python_path.*`, `data/`, `reports/`, `__pycache__/`. Người tải code về tự tạo các file này theo mục 2 |
| Kiểu xuống dòng | `.gitattributes` giữ `.bat`, `.ps1`, `.vbs` dạng CRLF và `.command`, `.sh` dạng LF trên mọi máy (test `LauncherFilesTest` kiểm tra) |
| Quyền chạy trên Mac | Git trên Windows không lưu quyền chạy: Mac tải code về thì chạy `chmod +x *.command *.sh` một lần (mục 2.5) |
| Repo | Để **Private**: README và test có tên máy ảo, môi trường làm việc thật |
| Phiên bản | `__version__` trong `focus/__init__.py` (hiện `2.5.1`), dạng `x.y.z`: sửa lỗi tăng `z`, thêm tính năng tăng `y`, đổi lớn (dữ liệu / cài đặt cũ không dùng được nữa) tăng `x`. Gắn tag `vx.y.z` cho bản chạy ổn. `/status` hiện số phiên bản đang chạy |
| Lỡ đưa `secrets.env` lên | Xoá file trên GitHub **chưa đủ** (lịch sử vẫn còn): đổi token bot (BotFather `/revoke`) và tạo key AI mới ngay |

Góp ý, báo lỗi: liên hệ người tạo dự án.
