#!/bin/bash
# 天猫罗技旗舰店数据采集 - Mac 一键运行
cd "$(dirname "$0")"

echo "============================================"
echo "  天猫罗技旗舰店数据采集 - 一键运行"
echo "============================================"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] 你的电脑还没有安装 Python，即将打开官网下载页面。"
    echo "    安装完成后重新双击本文件即可。"
    open "https://www.python.org/downloads/"
    read -r -p "按回车退出"
    exit 1
fi

echo "[1/3] 正在安装依赖（第一次运行需要几分钟）..."
python3 -m pip install -r requirements.txt -q || \
python3 -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "[2/3] 正在安装价格识别组件（可选，失败不影响其它字段）..."
python3 -m pip install ddddocr -q >/dev/null 2>&1 || python3 -m pip install ddddocr -q -i https://pypi.tuna.tsinghua.edu.cn/simple >/dev/null 2>&1

echo "[2.5/3] 正在准备浏览器（第一次运行需要下载，请耐心等待）..."
python3 -m playwright install chromium

echo "[3/3] 开始采集！稍后会弹出浏览器窗口，"
echo "      请按提示用手机淘宝扫码登录，然后回到本窗口按回车。"
python3 scrape_tmall_store.py

echo "运行结束。Excel 表格在本文件夹的 data 目录里。"
read -r -p "按回车关闭窗口"
