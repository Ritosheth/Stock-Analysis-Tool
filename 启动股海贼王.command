#!/bin/zsh

cd "$(dirname "$0")" || exit 1

echo "正在启动股海贼王工作台..."
echo "如果浏览器没有自动打开，请查看终端中的本地地址。"
echo

pkill -f "[g]hzw.gui" 2>/dev/null || true

PYTHONPATH=src python3 -m ghzw.gui

echo
echo "股海贼王工作台已停止。"
read -r "?按回车键关闭窗口。"
