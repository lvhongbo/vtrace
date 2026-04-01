@echo off
REM scripts/setup.bat
REM 项目通用构建脚本：使用 uv 创建虚拟环境并安装 desk_eval 依赖 (Windows)

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "REQ_FILE=%PROJECT_ROOT%\experiments\desk_eval\requirements.txt"

REM 检查 uv 是否已安装
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 uv，请先安装: https://docs.astral.sh/uv/getting-started/installation/
    echo 快速安装 (Windows): powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)

cd /d "%PROJECT_ROOT%"

REM 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo [setup] 创建 uv 虚拟环境 (.venv)...
    uv venv
) else (
    echo [setup] 虚拟环境已存在，跳过创建
)

REM 安装依赖
echo [setup] 安装 desk_eval 依赖...
uv pip install -r "%REQ_FILE%"

echo [setup] 完成。你可以运行以下命令启动程序：
echo   scripts\run_desk_eval.bat
echo   scripts\run_calibrator.bat

pause
