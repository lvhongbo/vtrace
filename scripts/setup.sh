#!/bin/bash
set -e

# scripts/setup.sh
# 项目通用构建脚本：使用 uv 创建虚拟环境并安装 desk_eval 依赖

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQ_FILE="$PROJECT_ROOT/experiments/desk_eval/requirements.txt"

# 检查 uv 是否已安装
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
else
    echo "[setup] 虚拟环境已存在，跳过创建"
fi

# 安装依赖
echo "[setup] 安装 desk_eval 依赖..."
uv pip install -r "$REQ_FILE"

echo "[setup] 完成。你可以运行以下命令启动程序："
echo "  ./scripts/run_desk_eval.sh"
echo "  ./scripts/run_calibrator.sh"
