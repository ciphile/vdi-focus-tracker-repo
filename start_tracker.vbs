' Chay Focus Tracker an (khong cua so). Task Scheduler goi file nay.
' Dung python.exe chay an thay vi pythonw (bai hoc tu app timesheet: pythonw hay chet im lang).
' Khong hien hop thoai loi: neu khong tim thay Python thi ghi vao data\logs\launcher-error.txt.
Option Explicit
On Error Resume Next

Dim fso, sh, here, cfgPy, py, runCmd, p, cand, dirs, d, dd, lad
Dim sub1, best, bestNum, n
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
cfgPy = here & "\config\python_path.txt"
py = ""
runCmd = ""

' Doc 1 dong tu file; fmt = -1 (UTF-16, file moi) hoac 0 (ANSI, file cu).
Function ReadFirstLine(path, fmt)
    On Error Resume Next
    Dim f, s
    ReadFirstLine = ""
    s = ""
    Err.Clear
    Set f = fso.OpenTextFile(path, 1, False, fmt)
    If Err.Number = 0 Then
        If Not f.AtEndOfStream Then s = f.ReadLine
        f.Close
    End If
    Err.Clear
    s = Replace(Replace(Replace(s, vbCr, ""), vbLf, ""), Chr(34), "")
    ReadFirstLine = Trim(s)
End Function

Function IsGoodFile(path)
    On Error Resume Next
    IsGoodFile = False
    If path = "" Then Exit Function
    If InStr(1, path, "\WindowsApps\", vbTextCompare) > 0 Then Exit Function
    If fso.FileExists(path) Then IsGoodFile = True
End Function

Sub LogError(msg)
    On Error Resume Next
    Dim logDir, f
    Err.Clear
    If Not fso.FolderExists(here & "\data") Then fso.CreateFolder here & "\data"
    logDir = here & "\data\logs"
    If Not fso.FolderExists(logDir) Then fso.CreateFolder logDir
    Set f = fso.OpenTextFile(logDir & "\launcher-error.txt", 8, True, -1)
    If Err.Number = 0 Then
        f.WriteLine Now & "  " & msg
        f.Close
    End If
    Err.Clear
End Sub

' 1. Duong dan do cai_tu_khoi_dong.ps1 ghi lai.
If fso.FileExists(cfgPy) Then
    p = ReadFirstLine(cfgPy, -1)
    If Not IsGoodFile(p) Then p = ReadFirstLine(cfgPy, 0)
    If IsGoodFile(p) Then py = p
End If

' 2. python.exe tren PATH (bo ban gia WindowsApps).
If py = "" Then
    dirs = Split(sh.ExpandEnvironmentStrings("%PATH%"), ";")
    For Each d In dirs
        dd = Trim(Replace(d, Chr(34), ""))
        If dd <> "" Then
            cand = dd
            If Right(cand, 1) <> "\" Then cand = cand & "\"
            cand = cand & "python.exe"
            If py = "" And IsGoodFile(cand) Then py = cand
        End If
    Next
End If

' 3. Thu muc cai mac dinh cua python.org (cho tung user), chon ban moi nhat.
If py = "" Then
    lad = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python"
    If fso.FolderExists(lad) Then
        best = "" : bestNum = 0
        For Each sub1 In fso.GetFolder(lad).SubFolders
            If LCase(Left(sub1.Name, 7)) = "python3" Then
                n = 0
                If IsNumeric(Mid(sub1.Name, 8, 2)) Then
                    n = CInt(Mid(sub1.Name, 8, 2))
                ElseIf IsNumeric(Mid(sub1.Name, 8, 1)) Then
                    n = CInt(Mid(sub1.Name, 8, 1))
                End If
                If n >= 9 And n > bestNum And fso.FileExists(sub1.Path & "\python.exe") Then
                    best = sub1.Path & "\python.exe" : bestNum = n
                End If
            End If
        Next
        If best <> "" Then py = best
    End If
End If

If py <> "" Then
    runCmd = """" & py & """ """ & here & "\focus_tracker.py"" run"
Else
    ' 4. py launcher (python.org cai vao C:\Windows hoac LOCALAPPDATA).
    For Each cand In Array(sh.ExpandEnvironmentStrings("%SystemRoot%") & "\py.exe", _
                           sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\py.exe")
        If runCmd = "" And fso.FileExists(cand) Then runCmd = """" & cand & """ -3 """ & here & "\focus_tracker.py"" run"
    Next
End If

If runCmd = "" Then
    LogError "Khong tim thay Python 3.9+. Hay chay lai cai_tu_khoi_dong.ps1 (chuot phai > Run with PowerShell). File python_path.txt: " & cfgPy
    WScript.Quit 1
End If

' lam_bu_ngoai_gio.bat goi file nay kem --manual: ngay nghi van chay de ghi gio lam bu trong VDI.
If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "--manual" Then runCmd = runCmd & " --manual"
End If

Err.Clear
sh.CurrentDirectory = here
sh.Run runCmd, 0, False
If Err.Number <> 0 Then
    LogError "Khong chay duoc lenh: " & runCmd & "  (loi " & Err.Number & ": " & Err.Description & ")"
    WScript.Quit 1
End If
