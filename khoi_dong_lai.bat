@echo off
REM Khoi dong lai Focus Tracker: thay cho End task python.exe roi bat lai start_tracker.vbs.
REM Dung sau khi sua settings.json / persona.json, hoac sau khi Pull ban moi.
REM Tracker ghi nop so lieu vao DB truoc khi tat nen khong mat so dem trong ngay. Ban Mac: khoi_dong_lai.command.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0khoi_dong_lai.ps1"
echo.
if errorlevel 1 echo Co loi. Doc dong mau do o tren, hoac gui anh chup man hinh cho Claude.
pause
