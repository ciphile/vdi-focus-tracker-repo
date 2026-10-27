# Khoi dong lai Focus Tracker (Windows). Goi tu khoi_dong_lai.bat.
# 1. Tao file data\khoi_dong_lai.flag: tracker thay trong vong 1 phut, ghi nop so lieu vao DB roi tu thoat
#    (khong mat so lan sao nhang / cau nhac da dung nhu khi End task).
# 2. Cho toi da 90 giay. Ban cu khong tu thoat (vd. phien ban truoc v2.10.8) thi tat han.
# 3. Bat lai chay an bang start_tracker.vbs (dang o che do lam bu --manual thi giu --manual).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

function Get-Trackers {
    @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'" |
        Where-Object { $_.CommandLine -like "*focus_tracker.py*run*" })
}

try {
    $procs = Get-Trackers
} catch {
    Write-Host "Khong kiem tra duoc tracker dang chay: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
$manual = @($procs | Where-Object { $_.CommandLine -like "*--manual*" }).Count -gt 0
$flag = Join-Path $here "data\khoi_dong_lai.flag"

if ($procs.Count -eq 0) {
    Write-Host "Khong co tracker nao dang chay, bat moi luon."
} else {
    Write-Host "Dang yeu cau tracker ghi nop so lieu va tu tat (toi da 90 giay)..."
    if (-not (Test-Path (Join-Path $here "data"))) { New-Item -ItemType Directory -Path (Join-Path $here "data") | Out-Null }
    Set-Content -Path $flag -Value "restart" -Encoding ASCII
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Trackers).Count -gt 0 -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    $left = Get-Trackers
    if ($left.Count -eq 0) {
        Write-Host "Tracker da tu tat, so lieu da ghi du." -ForegroundColor Green
    } else {
        Write-Host "Tracker khong tu tat kip, tat han (giong End task)." -ForegroundColor Yellow
        foreach ($p in $left) {
            try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
        }
        Start-Sleep -Seconds 2
        if ((Get-Trackers).Count -gt 0) {
            Write-Host "Khong tat duoc tracker. Hay khoi dong lai may." -ForegroundColor Red
            exit 1
        }
    }
    Remove-Item -Path $flag -ErrorAction SilentlyContinue
}

$vbs = Join-Path $here "start_tracker.vbs"
if ($manual) {
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbs`" --manual"
    Write-Host "Da bat lai tracker (che do lam bu ngoai gio)." -ForegroundColor Green
} else {
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbs`""
    Write-Host "Da bat lai tracker (chay an). Bot se doc lai settings.json, persona.json." -ForegroundColor Green
}
Write-Host "Ngoai khung gio chay hoac ngay nghi thi tracker tu thoat ngay, binh thuong."
exit 0
