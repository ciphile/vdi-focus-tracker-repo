@echo off
REM Tao bao cao hom nay (file HTML trong thu muc reports) va mo bang trinh duyet. Tim Python giong start_tracker.bat.
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
"%PY%" focus_tracker.py report --open
goto done
:run_py
py -3 focus_tracker.py report --open
goto done
:run_python
python focus_tracker.py report --open
:done
if errorlevel 1 pause
