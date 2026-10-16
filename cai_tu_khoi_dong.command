#!/bin/bash
# Mac: cài Focus Tracker tự chạy lúc đăng nhập và giờ tự bật (mặc định 08:00) thứ 2 - thứ 6 (launchd, không cần
# quyền admin). Nhấp đúp file này.
# File này CHỈ cho Mac; Windows dùng cai_tu_khoi_dong.bat. Gỡ: nhấp đúp go_tu_khoi_dong.command.
cd "$(dirname "$0")" || exit 1
if bash cai_tu_khoi_dong_mac.sh; then
  echo
  echo "ĐÃ CÀI XONG. Tracker sẽ tự chạy lần đăng nhập tới và theo giờ tự bật ở dòng trên (thứ 2 - thứ 6)."
else
  echo
  echo "Có lỗi. Đọc dòng ở trên, hoặc chụp màn hình gửi người hỗ trợ."
fi
read -r -p "Enter để đóng"
