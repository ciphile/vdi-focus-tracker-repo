#!/bin/bash
# Mac: khởi động lại Focus Tracker (thay cho tắt tay rồi bật lại). Bản Windows: khoi_dong_lai.bat.
# pkill gửi tín hiệu tắt bình thường (SIGTERM): tracker ghi nốt số liệu vào DB rồi mới thoát.
# Đang ở chế độ làm bù (--manual) thì bật lại vẫn giữ --manual.
cd "$(dirname "$0")" || exit 1

MANUAL=""
if pgrep -f 'focus_tracker.py run' >/dev/null 2>&1; then
  if pgrep -f 'focus_tracker.py run --manual' >/dev/null 2>&1; then MANUAL="--manual"; fi
  echo "Đang yêu cầu tracker ghi nốt số liệu và tự tắt (tối đa 60 giây)..."
  pkill -f 'focus_tracker.py run'
  for _ in $(seq 1 30); do
    pgrep -f 'focus_tracker.py run' >/dev/null 2>&1 || break
    sleep 2
  done
  if pgrep -f 'focus_tracker.py run' >/dev/null 2>&1; then
    echo "Tracker không tự tắt kịp, tắt hẳn."
    pkill -9 -f 'focus_tracker.py run'
    sleep 1
  fi
else
  echo "Không có tracker nào đang chạy, bật mới luôn."
fi

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
nohup "$PY" focus_tracker.py run $MANUAL >/dev/null 2>&1 &
disown
echo "Đã bật lại tracker (chạy nền). Bot sẽ đọc lại settings.json, persona.json."
echo "Ngoài khung giờ chạy hoặc ngày nghỉ thì tracker tự thoát ngay, bình thường. Đóng cửa sổ này không làm tắt tracker."
read -r -p "Enter để đóng"
