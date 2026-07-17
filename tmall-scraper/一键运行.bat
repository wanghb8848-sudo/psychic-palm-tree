@echo off
chcp 65001 >nul
title 天猫罗技旗舰店数据采集
cd /d "%~dp0"

echo ============================================
echo   天猫罗技旗舰店数据采集 - 一键运行
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [!] 你的电脑还没有安装 Python。
    echo     即将为你打开 Python 官网下载页面。
    echo     安装时务必勾选底部的 "Add python.exe to PATH"！
    echo     安装完成后，重新双击本文件即可。
    start https://www.python.org/downloads/
    pause
    exit /b
)

echo [1/3] 正在安装依赖（第一次运行需要几分钟）...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [!] 依赖安装失败，尝试使用国内镜像重试...
    python -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo [2/3] 正在准备浏览器（第一次运行需要下载，请耐心等待）...
python -m playwright install chromium

echo [3/3] 开始采集！稍后会弹出浏览器窗口，
echo       请按提示用手机淘宝扫码登录，然后回到本窗口按回车。
echo.
python scrape_tmall_store.py

echo.
echo ============================================
echo 运行结束。Excel 表格在本文件夹的 data 目录里。
echo ============================================
pause
