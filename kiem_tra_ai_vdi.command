#!/bin/bash
# Mac: chạy lại hai phần AI (Gemini) và nhận diện cửa sổ VDI. Windows dùng kiem_tra_ai_vdi.bat.
cd "$(dirname "$0")" || exit 1
exec bash kiem_tra_may.command ai vdi
