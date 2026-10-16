@echo off
REM Chay Focus Tracker CO cua so console de xem log (dung khi kiem tra loi).
REM Ban tu bat (--manual): ngay nghi van chay de ghi gio lam bu trong VDI, khong nhac nho.
REM Binh thuong tracker tu chay an qua Task Scheduler (xem cai_tu_khoi_dong.ps1).
REM Tim Python theo thu tu: config\python_path.cmd (do cai_tu_khoi_dong.ps1 tao), py -3, python.
setlocal
cd /d "%~dp0"
set "PY="
if exist "config\python_path.cmd" call "config\python_path.cmd"
if defined PY if not exist "%PY%" set "PY="
if defined PY goto run_path
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 goto run_python
echo.
echo KHONG TIM THAY PYTHON 3.9 tro len tren may nay.
echo Cach sua: cai Python tu https://www.python.org/downloads/windows/
echo           roi chuot phai cai_tu_khoi_dong.ps1 ^> Run with PowerShell.
echo.
pause
exit /b 1

:run_path
"%PY%" focus_tracker.py run --manual
goto done
:run_py
py -3 focus_tracker.py run --manual
goto done
:run_python
python focus_tracker.py run --manual
:done
pause
