@echo off
REM Lam bu ngoai gio: bat Focus Tracker chay an, che do ban tu bat (--manual).
REM Dung khi lam bu cuoi tuan, ngay le, ngay /off, hoac muon bat truoc gio tu bat.
REM Ngay nghi va ngoai gio lam: bot chi ghi gio lam trong VDI (co go phim / re chuot),
REM khong nhac nho, khong tinh sao nhang / ngoi yen / thu nho VDI.
REM Tracker tu tat luc auto_stop_at (mac dinh 23:59), hoac khi tat may. Ban Mac: lam_bu_ngoai_gio.command.
cd /d "%~dp0"
wscript.exe "%~dp0start_tracker.vbs" --manual
echo.
echo Da bat Focus Tracker (chay an) de ghi gio lam bu trong VDI.
echo - Ngay nghi / ngoai gio: chi ghi gio lam trong VDI, khong nhac nho, khong tinh sao nhang.
echo - Neu tracker dang chay roi thi ban moi tu thoat, khong sao.
echo - Tracker tu tat luc 23:59 hoac khi tat may. Tat som: xem README muc 2.8.
echo.
pause
