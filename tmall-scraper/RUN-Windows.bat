@echo off
title 天猫罗技旗舰店数据采集
cd /d "%~dp0"

echo ============================================
echo   天猫罗技旗舰店数据采集 - 一键运行
echo ============================================
echo.

rem 检测是否在压缩包临时目录里运行（没解压就双击）
echo %~dp0 | findstr /i "\\Temp\\" >nul && (
    echo [提示] 你好像没有解压，直接在压缩包里运行了！
    echo        请先右键 zip 压缩包 - 全部解压缩，
    echo        再进入解压出来的文件夹双击本文件。
    pause
    exit /b
)

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
    python --version >nul 2>nul && set "PY=python"
)

if not defined PY (
    echo [提示] 你的电脑还没有安装 Python。
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
echo [第1步/共4步] 正在安装基础依赖（第一次要几分钟，别关窗口）...
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

echo [第2步/共4步] 正在安装价格识别组件（可选，失败也不影响其它字段）...
%PY% -m pip install ddddocr -q >nul 2>nul || %PY% -m pip install ddddocr -q -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>nul

echo [第3步/共4步] 正在下载浏览器（约150MB，请耐心等待）...
%PY% -m playwright install chromium
if errorlevel 1 (
    echo [失败] 浏览器下载失败，请把本窗口截图发给助手。
    pause
    exit /b
)

echo [第4步/共4步] 开始采集！稍后会弹出浏览器窗口，
echo   请用手机淘宝扫码登录，然后回到本窗口按回车继续。
echo.
%PY% scrape_tmall_store.py

echo.
echo ============================================
echo 运行结束！成果表格就在本文件夹里（会自动弹出并选中），
echo 文件名：罗技官方旗舰店_商品数据_日期.xlsx
echo ============================================
pause
