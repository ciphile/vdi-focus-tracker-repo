#!/bin/bash
# Mac: xem Focus Tracker đang tốn bao nhiêu CPU và RAM (đo 10 giây). Nhấp đúp file này khi tracker ĐANG CHẠY.
# File này CHỈ cho Mac; Windows dùng xem_cpu_ram.bat.
cd "$(dirname "$0")" || exit 1

to_sec() {  # thời gian CPU của ps ("1:02:03.45" hoặc "2:03.45") -> giây
  echo "$1" | awk -F: '{s = 0; for (i = 1; i <= NF; i++) s = s * 60 + $i; print s}'
}

PIDS="$(pgrep -f '[Pp]ython.*focus_tracker[.]py run')"  # chỉ tiến trình Python, không tính cửa sổ Terminal bọc ngoài
if [ -z "$PIDS" ]; then
  echo "Tracker chưa chạy."
else
  echo "Đang đo CPU/RAM của tracker trong 10 giây..."
  CORES="$(sysctl -n hw.ncpu 2>/dev/null || echo 1)"
  for P in $PIDS; do
    T1="$(to_sec "$(ps -p "$P" -o time= | tr -d ' ')")"
    sleep 10
    T2="$(ps -p "$P" -o time= | tr -d ' ')"
    if [ -z "$T2" ]; then echo "PID $P đã dừng trong lúc đo."; continue; fi
    T2="$(to_sec "$T2")"
    RSS="$(ps -p "$P" -o rss= | tr -d ' ')"
    SINCE="$(ps -p "$P" -o lstart=)"
    awk -v p="$P" -v r="$RSS" -v a="$T1" -v b="$T2" -v c="$CORES" -v s="$SINCE" 'BEGIN {
      printf "PID %s | RAM %.1f MB | CPU %.3f phần trăm cả máy (trung bình 10 giây) | tổng CPU %.1f giây | chạy từ %s\n",
             p, r / 1024, (b - a) / 10 / c * 100, b, s }'
  done
fi
echo
read -r -p "Enter để đóng"
