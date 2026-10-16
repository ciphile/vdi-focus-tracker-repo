# Go bo tu chay va dung tracker dang chay.
# Chay: nhap dup go_tu_khoi_dong.bat (khong bi hoi Execution Policy), hoac chuot phai file nay > "Run with PowerShell"
$ErrorActionPreference = "Continue"
$taskName = "FocusTracker"
$hadError = $false

# 1. Go task trong Task Scheduler (neu co).
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Khong thay task '$taskName' (co the da go truoc do). Bo qua buoc nay." -ForegroundColor Yellow
} else {
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-Host "Da go task '$taskName'." -ForegroundColor Green
    } catch {
        $hadError = $true
        Write-Host "Khong go duoc task '$taskName'. Hay mo Task Scheduler, tim FocusTracker, chuot phai > Delete." -ForegroundColor Red
        Write-Host ("Chi tiet ky thuat: " + $_.Exception.Message) -ForegroundColor Red
    }
}

# 2. Dung tracker dang chay (neu co).
try {
    $procs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like "*focus_tracker.py*run*" })
    if ($procs.Count -eq 0) {
        Write-Host "Khong co tracker nao dang chay."
    }
    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host "Da dung tracker (PID $($p.ProcessId))." -ForegroundColor Green
        } catch {
            # Tien trinh co the da tu thoat (vd py.exe dung kem python.exe con).
            if (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue) {
                $hadError = $true
                Write-Host "Khong dung duoc tracker PID $($p.ProcessId). Hay khoi dong lai may." -ForegroundColor Red
            }
        }
    }
} catch {
    $hadError = $true
    Write-Host "Khong kiem tra duoc tracker dang chay. Neu can, khoi dong lai may de dung han." -ForegroundColor Red
    Write-Host ("Chi tiet ky thuat: " + $_.Exception.Message) -ForegroundColor Red
}

Write-Host ""
if ($hadError) {
    Write-Host "Da xong nhung co buoc bi loi (xem dong mau do o tren)." -ForegroundColor Yellow
} else {
    Write-Host "Da go xong tu khoi dong Focus Tracker. Du lieu trong thu muc data\ van duoc giu nguyen." -ForegroundColor Green
}
Read-Host "Nhan Enter de dong cua so" | Out-Null
