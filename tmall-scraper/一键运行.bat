@echo off
title 天猫罗技旗舰店数据采集
cd /d "%~dp0"

echo ============================================
echo   天猫罗技旗舰店数据采集 - 一键运行
echo ============================================
echo.

rem 优先用 py 启动器（python.org 安装包自带，即使没勾选 PATH 也能用）
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
    python --version >nul 2>nul && set "PY=python"
)

if not defined PY (
    echo [提示] 你的电脑还没有安装好 Python。
    echo.
    echo   即将为你打开 Python 官网下载页面，请点击黄色的
    echo   "Download Python 3.x.x" 按钮，下载后双击安装。
    echo   安装界面勾选底部 "Add python.exe to PATH" 最好，
    echo   忘了勾也没关系，本脚本能自动找到它。
    echo.
    echo   Python 安装完成后，重新双击本文件即可继续。
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b
)

echo [OK] 已找到 Python：%PY%
echo.
echo [第1步/共3步] 正在安装依赖（第一次要几分钟，别关本窗口）...
%PY% -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [提示] 安装失败，改用国内镜像重试...
    %PY% -m pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [失败] 依赖安装失败，请把本窗口截图发给助手。
        pause
        exit /b
    )
)

echo [第2步/共3步] 正在下载浏览器组件（约150MB，请耐心等待）...
%PY% -m playwright install chromium
if errorlevel 1 (
    echo [失败] 浏览器组件下载失败，请把本窗口截图发给助手。
    pause
    exit /b
)

echo [第3步/共3步] 开始采集！稍后会弹出浏览器窗口，
echo   请用手机淘宝扫码登录，然后回到本窗口按回车。
echo.
%PY% scrape_tmall_store.py

echo.
echo ============================================
echo 运行结束。Excel 表格在本文件夹的 data 目录里。
echo ============================================
pause
