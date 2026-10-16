@echo off
REM Go tu khoi dong Focus Tracker va tat tracker dang chay.
REM Nhap dup file nay (khong bi hoi "Execution Policy"): chay go_tu_khoi_dong.ps1 voi -ExecutionPolicy Bypass, chi cho lan chay nay.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0go_tu_khoi_dong.ps1"
if errorlevel 1 (
    echo.
    echo Co loi. Doc dong mau do o tren, hoac gui anh chup man hinh cho Claude.
    pause
)
