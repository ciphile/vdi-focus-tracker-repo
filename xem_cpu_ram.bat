@echo off
REM Xem Focus Tracker dang ton bao nhieu CPU va RAM (do 10 giay). Nhap dup file nay.
REM Cung lenh nay go thang vao cmd duoc (xem README muc 4.18).
echo Dang do CPU/RAM cua tracker trong 10 giay...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*focus_tracker.py*run*' }); if ($ps.Count -eq 0) { 'Tracker chua chay.' } else { foreach ($w in $ps) { $p = Get-Process -Id $w.ProcessId; $c1 = $p.CPU; Start-Sleep -Seconds 10; $p.Refresh(); $cpu = ($p.CPU - $c1) / 10 / [Environment]::ProcessorCount * 100; 'PID {0} | RAM {1:N1} MB | CPU {2:N3} phan tram ca may (trung binh 10 giay) | tong CPU {3:N1} giay | chay tu {4}' -f $p.Id, ($p.WorkingSet64 / 1MB), $cpu, $p.CPU, $p.StartTime } }"
echo.
pause
