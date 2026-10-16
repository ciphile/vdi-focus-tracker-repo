#!/bin/bash
# Mac: gỡ tự khởi động Focus Tracker (launchd) và tắt tracker đang chạy. Dữ liệu trong data/ được giữ nguyên.
# Nhấp đúp file này. File này CHỈ cho Mac; Windows dùng go_tu_khoi_dong.bat.
cd "$(dirname "$0")" || exit 1
bash cai_tu_khoi_dong_mac.sh --go
if pkill -f 'focus_tracker.py run' 2>/dev/null; then echo "Đã tắt tracker đang chạy."; fi
read -r -p "Enter để đóng"
