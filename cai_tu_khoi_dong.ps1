# Cai Focus Tracker tu chay (Task Scheduler), khong can quyen Admin.
# Chay: nhap dup cai_tu_khoi_dong.bat (khong bi hoi Execution Policy), hoac chuot phai file nay > "Run with PowerShell"
#   hoac: powershell -ExecutionPolicy Bypass -File cai_tu_khoi_dong.ps1
# Tracker duoc bat khi: gio auto_start_at thu 2 - thu 6 (mac dinh 08:00; thu 7, CN, ngay le tracker tu thoat ngay), khi dang nhap Windows, va khi may thuc day sau sleep.
# Tracker tu thoat luc auto_stop_at (mac dinh 23:59), ngoai khung gio, va vao ngay nghi (cuoi tuan, le, /off).
# Doi gio bat/tat: nhan /giobot cho bot Telegram (bot tu sua task nay va ghi gio moi vao config\settings.json).
# Chay lai file nay bat cu luc nao: gio bat lay tu auto_start_at trong config\settings.json.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = "FocusTracker"

# Dung cua so lai de nguoi dung kip doc thong bao.
function Wait-Close {
    Read-Host "Nhan Enter de dong cua so" | Out-Null
}

# In loi mau do (kem giai thich tieng Viet), dung cua so, roi thoat.
function Stop-WithError([string]$message, $err) {
    Write-Host ""
    Write-Host $message -ForegroundColor Red
    if ($err) { Write-Host ("Chi tiet ky thuat: " + $err) -ForegroundColor Red }
    Write-Host ""
    Wait-Close
    exit 1
}

# Chay python, doc ket qua dang UTF-8: duong dan co dau (vd C:\Users\Nguyen... co dau) khong lam Python loi
# UnicodeEncodeError khi in ra pipe (mac dinh Python in theo bang ma ANSI cp1252). -X utf8 + doi OutputEncoding tam thoi.
# Tra ve @{ Out = cac dong in ra; Code = ma thoat }.
function Invoke-PyUtf8([string]$exe, [string[]]$pyArgs) {
    $oldEnc = $null
    try {
        $oldEnc = [Console]::OutputEncoding
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    } catch { $oldEnc = $null }
    $out = $null
    $code = 1
    try {
        $out = & $exe @pyArgs 2>$null
        $code = $LASTEXITCODE
    } finally {
        if ($oldEnc) { try { [Console]::OutputEncoding = $oldEnc } catch { } }
    }
    return @{ Out = @($out); Code = $code }
}

# Chay python o duong dan $exe, tra ve @{Path; Version} neu la Python 3.9+; nguoc lai tra ve $null.
function Test-Python([string]$exe) {
    if (-not $exe) { return $null }
    $exe = $exe.Trim().Trim('"')
    if (-not $exe -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) { return $null }
    if ($exe -like "*\WindowsApps\*") { return $null }
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $res = Invoke-PyUtf8 $exe @("-X", "utf8", "-c", "import sys;print('%d.%d' % sys.version_info[:2]);print(sys.executable)")
        $out = $res.Out | Where-Object { $_ -ne $null }
        if ($res.Code -ne 0 -or -not $out) { return $null }
        $lines = @($out)
        $ver = [version]($lines[0].Trim())
        if ($ver -lt [version]"3.9") { return $null }
        $real = $exe
        if ($lines.Count -ge 2 -and $lines[1].Trim() -and (Test-Path -LiteralPath $lines[1].Trim() -PathType Leaf)) { $real = $lines[1].Trim() }
        return @{ Path = $real; Version = $ver }
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $oldPref
    }
}

# Tim Python 3.9+: (1) python.exe tren PATH (bo ban gia WindowsApps), (2) py -3, (3) registry PythonCore (ban moi nhat).
function Find-Python {
    # 1. python.exe tren PATH
    foreach ($c in @(Get-Command python.exe -All -CommandType Application -ErrorAction SilentlyContinue)) {
        if ($c.Source -and $c.Source -notlike "*\WindowsApps\*") {
            $r = Test-Python $c.Source
            if ($r) { return $r }
        }
    }
    # 2. py launcher
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $oldPref = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $res = Invoke-PyUtf8 "py.exe" @("-3", "-X", "utf8", "-c", "import sys;print(sys.executable)")
            $p = $res.Out | Where-Object { $_ -ne $null }
            if ($res.Code -eq 0 -and $p) {
                $p = (@($p)[0]).Trim()
                $r = Test-Python $p
                if ($r) { return $r }
            }
        } catch { } finally { $ErrorActionPreference = $oldPref }
    }
    # 3. registry (python.org ghi vao day ke ca khi khong them vao PATH)
    $found = @()
    foreach ($root in @("HKCU:\Software\Python\PythonCore", "HKLM:\Software\Python\PythonCore", "HKLM:\Software\WOW6432Node\Python\PythonCore")) {
        foreach ($k in @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
            if ($k.PSChildName -notmatch '^(\d+)\.(\d+)') { continue }
            $ver = [version]("{0}.{1}" -f $Matches[1], $Matches[2])
            if ($ver -lt [version]"3.9") { continue }
            $ip = Get-ItemProperty -LiteralPath (Join-Path $k.PSPath "InstallPath") -ErrorAction SilentlyContinue
            if (-not $ip) { continue }
            $exe = $null
            if ($ip.PSObject.Properties["ExecutablePath"] -and $ip.ExecutablePath) { $exe = $ip.ExecutablePath }
            elseif ($ip.PSObject.Properties["(default)"] -and $ip."(default)") { $exe = Join-Path $ip."(default)" "python.exe" }
            if ($exe) { $found += New-Object PSObject -Property @{ Ver = $ver; Exe = $exe } }
        }
    }
    foreach ($f in @($found | Sort-Object Ver -Descending)) {
        $r = Test-Python $f.Exe
        if ($r) { return $r }
    }
    return $null
}

# Chuan hoa gio "7:00", " 08:00", "24:00" -> HH:MM. 24:00 -> 23:59; sai dinh dang -> 08:00.
function Format-StartTime($value) {
    $t = ("" + $value).Trim()
    if ($t -notmatch '^(\d{1,2})(?::(\d{1,2}))?$') { return "08:00" }
    $h = [int]$Matches[1]
    $m = 0
    if ($Matches[2]) { $m = [int]$Matches[2] }
    if ($h -eq 24 -and $m -eq 0) { return "23:59" }
    if ($h -gt 23 -or $m -gt 59) { return "08:00" }
    return ("{0:D2}:{1:D2}" -f $h, $m)
}

# Ghi config\python_path.cmd cho file .bat (cmd doc file .bat theo bang ma OEM).
# Neu duong dan co ky tu khong ghi duoc theo OEM thi thu ten ngan 8.3; khong duoc thi bo qua (file .bat se dung py -3 / python).
function Write-PythonCmd([string]$py, [string]$cmdFile) {
    try {
        $oem = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
        $cands = @($py)
        try { $cands += (New-Object -ComObject Scripting.FileSystemObject).GetFile($py).ShortPath } catch { }
        foreach ($c in $cands) {
            if (-not $c) { continue }
            $line = 'set "PY=' + $c + '"'
            $bytes = $oem.GetBytes($line + "`r`n")
            if ($oem.GetString($bytes) -eq ($line + "`r`n")) {
                [IO.File]::WriteAllBytes($cmdFile, $bytes)
                return $true
            }
        }
        Remove-Item -LiteralPath $cmdFile -Force -ErrorAction SilentlyContinue
    } catch { }
    return $false
}

Write-Host "Dang cai Focus Tracker tu khoi dong..." -ForegroundColor Cyan

# --- Tim Python ---
$pyInfo = Find-Python
if (-not $pyInfo) {
    Stop-WithError ("Khong tim thay Python 3.9 tro len tren may nay.`n" +
        "Cach sua: tai Python tu https://www.python.org/downloads/windows/ , cai dat (nen tick 'Add python.exe to PATH'), roi chay lai file nay.`n" +
        "Luu y: ban 'python' cua Microsoft Store (WindowsApps) khong dung duoc.") $null
}
$py = $pyInfo.Path
Write-Host ("Python: {0} (phien ban {1})" -f $py, $pyInfo.Version)

try {
    New-Item -ItemType Directory -Force -Path (Join-Path $here "config") | Out-Null
    # UTF-16LE co BOM de giu dung ten thu muc co dau (vd C:\Users\Nguyen...).
    Set-Content -LiteralPath (Join-Path $here "config\python_path.txt") -Value $py -Encoding Unicode
    if (-not (Write-PythonCmd $py (Join-Path $here "config\python_path.cmd"))) {
        Write-Host "Ghi chu: khong tao duoc config\python_path.cmd (duong dan co ky tu dac biet); file .bat se tu tim Python." -ForegroundColor Yellow
    }
} catch {
    Stop-WithError ("Khong ghi duoc file cau hinh trong thu muc '" + $here + "\config'.`n" +
        "Cach sua: chep thu muc app ra noi ban co quyen ghi (vd Documents) roi chay lai.") $_.Exception.Message
}

# --- Doc gio bat tu settings.json ---
$startAt = "08:00"
$settingsFile = Join-Path $here "config\settings.json"
if (Test-Path -LiteralPath $settingsFile) {
    try {
        $settings = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($settings -and $settings.auto_start_at) { $startAt = Format-StartTime $settings.auto_start_at }
    } catch {
        Write-Host "Canh bao: khong doc duoc config\settings.json (sai dinh dang JSON?). Dung gio mac dinh 08:00." -ForegroundColor Yellow
    }
}

try {
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
} catch {
    $user = "$env:USERDOMAIN\$env:USERNAME"
}
$vbs = Join-Path $here "start_tracker.vbs"
$today = Get-Date -Format "yyyy-MM-dd"
$resumeQuery = "&lt;QueryList&gt;&lt;Query Id='0' Path='System'&gt;&lt;Select Path='System'&gt;*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;"

# Escape cac gia tri dua vao XML (duong dan co the chua &, <, >, ').
$xUser = [Security.SecurityElement]::Escape($user)
$xVbs = [Security.SecurityElement]::Escape($vbs)
$xHere = [Security.SecurityElement]::Escape($here)

$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Focus Tracker: theo doi thoi gian tap trung (tu thoat luc auto_stop_at va ngay nghi; doi gio: /giobot)</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>${today}T${startAt}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek><WeeksInterval>1</WeeksInterval><DaysOfWeek><Monday /><Tuesday /><Wednesday /><Thursday /><Friday /></DaysOfWeek></ScheduleByWeek>
    </CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><UserId>$xUser</UserId><Delay>PT1M</Delay></LogonTrigger>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>$resumeQuery</Subscription>
      <Delay>PT30S</Delay>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>$xUser</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>wscript.exe</Command><Arguments>"$xVbs"</Arguments><WorkingDirectory>$xHere</WorkingDirectory></Exec>
  </Actions>
</Task>
"@

try {
    Register-ScheduledTask -TaskName $taskName -Xml $xml -Force | Out-Null
} catch {
    Stop-WithError ("Khong cai duoc task '" + $taskName + "' vao Task Scheduler.`n" +
        "Nguyen nhan thuong gap: may cong ty chan Task Scheduler, hoac tai khoan khong duoc phep tao task.`n" +
        "Cach sua: chup man hinh nay gui nguoi ho tro; tam thoi co the chay tay bang start_tracker.bat.") $_.Exception.Message
}

Write-Host ""
Write-Host "DA CAI XONG." -ForegroundColor Green
Write-Host ("- Task '{0}' cho tai khoan {1}" -f $taskName, $user)
Write-Host ("- Tracker tu bat: luc {0} thu 2 - thu 6, 1 phut sau khi dang nhap, va 30 giay sau khi may thuc day (som hon {0} thi tu thoat, cho toi {0})." -f $startAt)
Write-Host "- Doi gio bat/tat: nhan /giobot cho bot Telegram."
Write-Host ("- Python dung: {0}" -f $py)
Write-Host "- Kiem tra: mo Start > go 'Task Scheduler' > Task Scheduler Library > FocusTracker."
Write-Host ("- Log: {0}\data\logs\focus.log" -f $here)
Write-Host "- Go bo: nhap dup go_tu_khoi_dong.bat."
Write-Host ""
$ans = Read-Host "Chay tracker ngay bay gio? (y/n)"
if ($ans -match '^\s*[yYcC]') {
    try {
        Start-ScheduledTask -TaskName $taskName
        Write-Host "Da chay. Xem log: $here\data\logs\focus.log" -ForegroundColor Green
    } catch {
        Write-Host "Khong chay duoc task ngay (se tu chay lan dang nhap sau). Chi tiet: $($_.Exception.Message)" -ForegroundColor Red
    }
}
Wait-Close
