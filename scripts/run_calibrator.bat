@echo off
REM scripts/run_calibrator.bat
REM 一键构建并运行 ROI 标定工具（Windows）

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "REQ_FILE=%PROJECT_ROOT%\experiments\desk_eval\requirements.txt"
set "TARGET_DIR=%PROJECT_ROOT%\experiments\desk_eval"

REM 检查 uv
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
)

REM 安装/更新依赖
echo [setup] 安装/更新依赖...
uv pip install -r "%REQ_FILE%"

REM 运行标定工具
cd /d "%TARGET_DIR%"
echo [run] 启动 ROI 标定工具（画 3 个圈，按 's' 保存，'q' 退出）...
uv run python roi_calibrator.py

pause
