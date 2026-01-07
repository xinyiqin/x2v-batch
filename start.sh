#!/bin/bash

# 启动脚本 - 同时启动前后端服务

echo "🚀 启动 AI Vision Batch Service..."

# 检查后端依赖
if [ ! -d "server" ]; then
    echo "❌ 错误: server 目录不存在"
    exit 1
fi

# 检查前端依赖
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 安装前端依赖..."
    cd frontend && npm install && cd ..
fi

# 设置环境变量（如果未设置）
if [ -z "$LIGHTX2V_ACCESS_TOKEN" ]; then
    echo "⚠️  警告: LIGHTX2V_ACCESS_TOKEN 未设置，批次处理功能将不可用"
    echo "   可以通过以下命令设置:"
    echo "   export LIGHTX2V_ACCESS_TOKEN='your_token_here'"
fi

# 启动后端服务（后台运行）
echo "🔧 启动后端服务 (端口 8000)..."
cd "$(dirname "$0")"
python -m server.main > server.log 2>&1 &
BACKEND_PID=$!
echo "   后端服务 PID: $BACKEND_PID"

# 等待后端启动
sleep 3

# 启动前端服务（前台运行）
echo "🎨 启动前端服务 (端口 3000)..."
cd frontend
npm run dev

# 清理：当脚本退出时停止后端
trap "kill $BACKEND_PID 2>/dev/null" EXIT

