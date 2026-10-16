@echo off
REM KIEM TRA FOCUS TRACKER TREN MAY THAT (nhap dup file nay).
REM Lam theo huong dan tren man hinh (khoang 3 phut). Ket qua ghi vao data\logs\kiem_tra-*.txt
REM Can mo san cua so VDI (Citrix Desktop Viewer) truoc khi chay.
REM Chi chay mot phan: mo cmd trong thu muc nay roi go  kiem_tra_may.bat vdi   (hoac ai, mom, autostart, tests, check).
REM File nay CHI cho Windows. Mac dung kiem_tra_may.command.
REM Tim Python theo thu tu: config\python_path.cmd (do cai_tu_khoi_dong.ps1 tao), py -3, python.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
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
"%PY%" -X utf8 focus_tracker.py verify %*
goto done
:run_py
py -3 -X utf8 focus_tracker.py verify %*
goto done
:run_python
python -X utf8 focus_tracker.py verify %*
:done
echo.
echo Xong. Nhan tin cho Claude trong thread de Claude doc file ket qua.
pause
