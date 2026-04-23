@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo   PUBG 宏识别工具
echo ============================================
echo.

:: 检查 GHUB DLL 是否存在
if not exist "_internal\ghub_device_GHUB.dll" (
    echo [错误] 未找到 ghub_device_GHUB.dll
    echo 请确保 _internal 目录中包含此文件。
    echo.
    pause
    exit /b 1
)

:: 检查配置文件
if not exist "Config\config.json" (
    echo [提示] 首次运行，正在生成默认配置...
    if not exist "Config" mkdir Config
)

echo 正在启动程序...
start "" "PUBG宏识别工具.exe"
