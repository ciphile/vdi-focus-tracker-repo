#!/bin/bash
# Mac: cài Focus Tracker tự chạy bằng launchd (không cần quyền admin).
# Chạy trong Terminal:  bash cai_tu_khoi_dong_mac.sh
# Tracker được bật: lúc đăng nhập và thứ 2 – thứ 6 lúc auto_start_at (mặc định 08:00; máy ngủ lúc đó thì chạy khi thức dậy).
# Đổi giờ bật/tắt: nhắn /giobot cho bot (bot ghi giờ mới vào settings.json và file plist; macOS áp dụng từ lần đăng nhập
# lại tới, hoặc chạy lại file này để áp dụng ngay — tracker đang chạy sẽ khởi động lại).
# Gỡ: bash cai_tu_khoi_dong_mac.sh --go
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.focustracker.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "$1" = "--go" ]; then
  launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Đã gỡ tự khởi động. Dữ liệu trong thư mục data/ vẫn được giữ nguyên."
  exit 0
fi

# Trả về 0 nếu $1 là Python 3.9+ chạy được.
py_ok() {
  [ -n "$1" ] && [ -x "$1" ] || return 1
  # /usr/bin/python3 là bản giả của Apple khi chưa cài Command Line Tools (gọi vào sẽ bật hộp thoại cài đặt).
  if [ "$1" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then return 1; fi
  "$1" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1
}

# Tìm Python 3.9+: python.org (bản mới nhất) > Homebrew > python3 trên PATH.
find_python() {
  local c
  for c in $(ls -d /Library/Frameworks/Python.framework/Versions/[0-9]*.[0-9]* 2>/dev/null \
             | sed 's#.*/##' | sort -t. -k1,1nr -k2,2nr); do
    if py_ok "/Library/Frameworks/Python.framework/Versions/$c/bin/python3"; then
      echo "/Library/Frameworks/Python.framework/Versions/$c/bin/python3"; return 0
    fi
  done
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null || true)"; do
    if py_ok "$c"; then echo "$c"; return 0; fi
  done
  return 1
}

# Escape ký tự đặc biệt khi đưa vào file plist (XML).
xml_esc() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

# macOS (từ 10.15) không cho chương trình chạy nền do launchd bật đọc Documents, Desktop, Downloads và thư mục iCloud
# nếu chưa được cấp quyền: tracker tự chạy sẽ không mở được file của chính nó, dù chạy tay bằng Terminal vẫn được.
case "$HERE/" in
  "$HOME/Documents/"*|"$HOME/Desktop/"*|"$HOME/Downloads/"*|"$HOME/Library/Mobile Documents/"*|"$HOME/Library/CloudStorage/"*)
    echo "CẢNH BÁO: thư mục app đang nằm trong Documents / Desktop / Downloads / iCloud:"
    echo "  $HERE"
    echo "macOS chặn tracker tự chạy nền đọc các thư mục này, nên tự khởi động có thể không chạy (dù bấm tay vẫn chạy)."
    echo "Cách sửa: Finder > Go > Home, kéo cả thư mục app vào đó (ví dụ ~/focus-tracker),"
    echo "  rồi nhấp đúp cai_tu_khoi_dong.command trong thư mục mới."
    ANS=""
    if [ -t 0 ]; then read -r -p "Vẫn cài ở chỗ hiện tại? Gõ c rồi Enter để cài, chỉ Enter để dừng: " ANS || true; fi
    if [ "$ANS" != "c" ] && [ "$ANS" != "C" ]; then
      echo "Đã dừng, chưa cài gì."
      exit 1
    fi
    ;;
esac

PY="$(find_python || true)"
if [ -z "$PY" ]; then
  echo "Không tìm thấy Python 3.9 trở lên."
  echo "Cách sửa: cài Python từ https://www.python.org/downloads/macos/ rồi chạy lại lệnh này."
  exit 1
fi
echo "Python: $PY"
mkdir -p "$HERE/config" "$HERE/data/logs" "$HOME/Library/LaunchAgents"
printf '%s\n' "$PY" > "$HERE/config/python_path.txt"

# Đọc auto_start_at và chuẩn hoá về HH:MM ("7:00" -> 08:00, "24:00" -> 23:59, sai -> 08:00).
START="$("$PY" - "$HERE" <<'PYEOF'
import json, os, re, sys
v = "08:00"
try:
    with open(os.path.join(sys.argv[1], "config", "settings.json"), encoding="utf-8-sig") as f:
        v = str(json.load(f).get("auto_start_at", "08:00"))
except Exception:
    pass
m = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", v.strip())
if not m:
    print("08:00")
else:
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h == 24 and mi == 0:
        print("23:59")
    elif h > 23 or mi > 59:
        print("08:00")
    else:
        print("%02d:%02d" % (h, mi))
PYEOF
)"
H="${START%%:*}"; M="${START##*:}"

X_PY="$(xml_esc "$PY")"
X_HERE="$(xml_esc "$HERE")"

cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$X_PY</string><string>$X_HERE/focus_tracker.py</string><string>run</string></array>
  <key>WorkingDirectory</key><string>$X_HERE</string>
  <key>RunAtLoad</key><true/>
  <key>StartCalendarInterval</key>
  <array>$(for d in 1 2 3 4 5; do printf '<dict><key>Weekday</key><integer>%s</integer><key>Hour</key><integer>%s</integer><key>Minute</key><integer>%s</integer></dict>' "$d" "$((10#$H))" "$((10#$M))"; done)</array>
  <key>ProcessType</key><string>Standard</string>
  <key>ExitTimeOut</key><integer>40</integer>
  <key>LowPriorityIO</key><true/>
  <key>Nice</key><integer>10</integer>
  <key>StandardErrorPath</key><string>$X_HERE/data/logs/launchd.err.log</string>
</dict>
</plist>
PL

if command -v plutil >/dev/null 2>&1 && ! plutil -lint "$PLIST" >/dev/null 2>&1; then
  echo "Lỗi: file $PLIST không hợp lệ. Hãy chụp màn hình này gửi người hỗ trợ."
  plutil -lint "$PLIST" || true
  exit 1
fi

# bootout chạy bất đồng bộ: thử bootstrap lại tối đa 5 lần, mỗi lần cách 1 giây.
launchctl bootout "$DOMAIN" "$PLIST" 2>/dev/null || true
OK=0
ERR=""
for i in 1 2 3 4 5; do
  if ERR="$(launchctl bootstrap "$DOMAIN" "$PLIST" 2>&1)"; then OK=1; break; fi
  sleep 1
done
if [ "$OK" != 1 ]; then
  echo "Lỗi: không bật được tự khởi động (launchctl bootstrap thất bại)."
  echo "Chi tiết: $ERR"
  echo "Cách sửa: đăng xuất rồi đăng nhập lại macOS, sau đó chạy lại: bash cai_tu_khoi_dong_mac.sh"
  exit 1
fi

echo "Đã cài. Tracker chạy lúc đăng nhập và mỗi ngày lúc $START."
echo "Kiểm tra: launchctl print $DOMAIN/$LABEL   |   Log: $HERE/data/logs/"
echo "Ghi chú: app đọc cửa sổ bằng CoreGraphics/NSWorkspace, KHÔNG cần cấp quyền. Chỉ khi dùng Citrix qua trình duyệt"
echo "  (vdi_browser_title_keywords): macOS sẽ hỏi quyền Screen Recording cho Python, bấm cho phép rồi chạy lại tracker."
echo "macOS 13 trở lên có thể báo «Background Items Added»: để nguyên. Đừng tắt Python / python3 trong"
echo "  System Settings > General > Login Items > Allow in the Background, nếu không tracker không tự chạy."
