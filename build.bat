@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 构建 MCLite 单文件 exe ===
python -m PyInstaller mclite.spec --noconfirm --clean
if errorlevel 1 (
    echo 构建失败
    pause
    exit /b 1
)
echo.
echo 完成： %~dp0dist\MCLite.exe
dir /b dist\MCLite.exe
pause
