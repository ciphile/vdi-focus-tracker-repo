#!/bin/bash
# Mac: chạy Focus Tracker có cửa sổ Terminal để xem log (dùng khi kiểm tra lỗi).
# Bình thường tracker tự chạy ẩn qua launchd (xem cai_tu_khoi_dong_mac.sh).
# Bạn tự bật (--manual): ngày nghỉ vẫn chạy để ghi giờ làm bù trong VDI, không nhắc nhở.
cd "$(dirname "$0")" || exit 1

py_ok() {
  [ -n "$1" ] && [ -x "$1" ] || return 1
  if [ "$1" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then return 1; fi
  "$1" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1
}

# Thứ tự: config/python_path.txt > python.org (bản mới nhất) > Homebrew > python3 trên PATH.
PY=""
CFG="$(head -n 1 config/python_path.txt 2>/dev/null | tr -d '\r')"
if py_ok "$CFG"; then PY="$CFG"; fi
if [ -z "$PY" ]; then
  for v in $(ls -d /Library/Frameworks/Python.framework/Versions/[0-9]*.[0-9]* 2>/dev/null \
             | sed 's#.*/##' | sort -t. -k1,1nr -k2,2nr); do
    c="/Library/Frameworks/Python.framework/Versions/$v/bin/python3"
    if py_ok "$c"; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 2>/dev/null)"; do
    if py_ok "$c"; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "Không tìm thấy Python 3.9 trở lên."
  echo "Cách sửa: cài Python từ https://www.python.org/downloads/macos/ rồi mở lại file này."
  read -r -p "Enter để đóng"
  exit 1
fi
"$PY" focus_tracker.py run --manual
read -r -p "Enter để đóng"
