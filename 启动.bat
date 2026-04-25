@echo off
chcp 65001 >nul 2>&1
set "ROOT=%~dp0"
set "RT=%ROOT%runtime"
set "EXE=%RT%\PUBG宏识别工具.exe"

echo ============================================
echo   PUBG 宏识别工具
echo ============================================
echo.

if not exist "%EXE%" (
    echo [错误] 未找到运行库: %EXE%
    echo 请保持本 bat 与 runtime 文件夹的相对位置不变。
    echo.
    pause
    exit /b 1
)

if not exist "%RT%\_internal\ghub_device_GHUB.dll" (
    echo [错误] 未找到 G HUB 驱动库: runtime\_internal\ghub_device_GHUB.dll
    echo.
    pause
    exit /b 1
)

:: 用户目录（Config / logs）在 runtime 内，与 exe 同级
if not exist "%RT%\Config" mkdir "%RT%\Config" 2>nul
if not exist "%RT%\logs" mkdir "%RT%\logs" 2>nul

if not exist "%RT%\Config\config.json" (
    echo [提示] 首次运行将生成默认配置于 runtime\Config\config.json
)

echo 正在从 runtime 启动程序...
:: 工作目录设为本目录，供路径解析为「发布根」
start "" /D "%ROOT%" "%EXE%"
