#!/bin/bash
# Mac: làm bù ngoài giờ. Bật Focus Tracker chạy nền, chế độ bạn tự bật (--manual).
# Dùng khi làm bù cuối tuần, ngày lễ, ngày /off, hoặc muốn bật trước giờ tự bật.
# Ngày nghỉ và ngoài giờ làm: bot chỉ ghi giờ làm trong VDI (có gõ phím / rê chuột), không nhắc nhở,
# không tính sao nhãng / ngồi yên / thu nhỏ VDI. Tracker tự tắt lúc auto_stop_at (mặc định 23:59).
# Bản Windows: lam_bu_ngoai_gio.bat.
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
nohup "$PY" focus_tracker.py run --manual >/dev/null 2>&1 &
disown
echo "Đã bật Focus Tracker (chạy nền) để ghi giờ làm bù trong VDI."
echo "- Ngày nghỉ / ngoài giờ: chỉ ghi giờ làm trong VDI, không nhắc nhở, không tính sao nhãng."
echo "- Nếu tracker đang chạy rồi thì bản mới tự thoát, không sao."
echo "- Tracker tự tắt lúc 23:59. Tắt sớm: xem README mục 2.8. Đóng cửa sổ này không làm tắt tracker."
read -r -p "Enter để đóng"
