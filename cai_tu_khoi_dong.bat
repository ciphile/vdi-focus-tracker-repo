@echo off
REM Cai Focus Tracker tu chay luc 08:00 thu 2-thu 6 (Task Scheduler, khong can quyen Admin).
REM Nhap dup file nay (khong bi hoi "Execution Policy"): chay cai_tu_khoi_dong.ps1 voi -ExecutionPolicy Bypass, chi cho lan chay nay.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cai_tu_khoi_dong.ps1"
if errorlevel 1 (
    echo.
    echo Co loi. Doc dong mau do o tren, hoac gui anh chup man hinh cho Claude.
    pause
)
