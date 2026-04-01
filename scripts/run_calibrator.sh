#!/bin/bash
set -e

# scripts/run_calibrator.sh
# 一键构建并运行 ROI 标定工具（Linux / macOS）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQ_FILE="$PROJECT_ROOT/experiments/desk_eval/requirements.txt"
TARGET_DIR="$PROJECT_ROOT/experiments/desk_eval"

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "[错误] 未找到 uv，请先安装: https://docs.astral.sh/uv/getting-started/installation/"
    echo "快速安装 (Linux/macOS): curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

cd "$PROJECT_ROOT"

# 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
    echo "[setup] 创建 uv 虚拟环境 (.venv)..."
    uv venv
fi

# 安装/更新依赖
echo "[setup] 安装/更新依赖..."
uv pip install -r "$REQ_FILE"

# 运行标定工具
cd "$TARGET_DIR"
echo "[run] 启动 ROI 标定工具（画 3 个圈，按 's' 保存，'q' 退出）..."
uv run python roi_calibrator.py
