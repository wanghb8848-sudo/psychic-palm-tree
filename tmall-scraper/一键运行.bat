@echo off
chcp 65001 >nul
title 天猫罗技旗舰店数据采集
cd /d "%~dp0"

echo ============================================
echo   天猫罗技旗舰店数据采集 - 一键运行
echo ============================================
echo.

rem 优先用 py 启动器（python.org 安装包默认自带，即使没勾选 PATH 也能用）
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
    python --version >nul 2>nul && set "PY=python"
)

if not defined PY (
    echo [!] 你的电脑还没有安装好 Python。
    echo.
    echo     即将为你打开 Python 官网下载页面，请点击黄色的
    echo     "Download Python 3.x.x" 按钮下载并安装。
    echo     安装时勾选底部的 "Add python.exe to PATH" 最好，
    echo     忘了勾也没关系，本脚本能自动找到它。
    echo.
    echo     安装完成后，重新双击本文件即可。
    start https://www.python.org/downloads/
    pause
    exit /b
)

echo [√] 已找到 Python：%PY%
echo.
echo [1/3] 正在安装依赖（第一次运行需要几分钟，请勿关闭本窗口）...
%PY% -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [!] 安装失败，改用国内镜像重试...
    %PY% -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [X] 依赖安装失败，请把本窗口截图发给助手。
        pause
        exit /b
    )
)

echo [2/3] 正在准备浏览器（第一次运行要下载约 150MB，请耐心等待）...
%PY% -m playwright install chromium
if errorlevel 1 (
    echo [X] 浏览器组件下载失败，请把本窗口截图发给助手。
    pause
    exit /b
)

echo [3/3] 开始采集！稍后会弹出浏览器窗口，
echo       请按提示用手机淘宝扫码登录，然后回到本窗口按回车。
echo.
%PY% scrape_tmall_store.py

echo.
echo ============================================
echo 运行结束。Excel 表格在本文件夹的 data 目录里。
echo ============================================
pause
