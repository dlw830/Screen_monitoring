@echo off
chcp 65001 >nul 2>&1
title LanScreenMonitor 一键打包

echo ============================================
echo   LanScreenMonitor - 一键打包脚本
echo ============================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检查 Python 是否可用
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 检查 PyInstaller 是否已安装
python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] PyInstaller 未安装，正在自动安装...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [错误] PyInstaller 安装失败，请手动执行: pip install pyinstaller
        pause
        exit /b 1
    )
)

:: 检查依赖是否已安装
echo [1/3] 检查并安装依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 开始打包（-y 自动覆盖旧输出）
echo [2/3] 开始打包...
echo.
python -m PyInstaller --noconfirm LanScreenMonitor.spec
if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo [3/3] 打包完成！
echo ============================================
echo   输出目录: dist\LanScreenMonitor\
echo   可执行文件: dist\LanScreenMonitor\LanScreenMonitor.exe
echo ============================================
echo.
pause
