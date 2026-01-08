#!/bin/bash

# 本地启动前后端服务脚本
set -e

echo "🚀 启动本地开发环境..."

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 注意：S3_CONFIG 应该从环境变量或 .env 文件读取，不要硬编码在脚本中
# 如果需要使用 S3，请在运行脚本前设置环境变量：
# export STORAGE_TYPE="s3"
# export S3_CONFIG='{"aws_access_key_id":"...","aws_secret_access_key":"...",...}'

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误: 未安装 Python3${NC}"
    exit 1
fi

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ 错误: 未安装 Node.js${NC}"
    exit 1
fi

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ 错误: 未安装 npm${NC}"
    exit 1
fi

# 检查端口是否被占用
check_port() {
    local port=$1
    local pid=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pid" ]; then
        echo -e "${YELLOW}⚠️  警告: 端口 $port 已被占用 (PID: $pid)${NC}"
        echo "   正在尝试清理占用该端口的进程..."
        
        # 尝试优雅地停止进程
        kill -TERM $pid 2>/dev/null || true
        sleep 1
        
        # 检查进程是否还在运行
        if kill -0 $pid 2>/dev/null; then
            # 如果还在运行，强制杀掉
            echo "   强制停止进程 $pid..."
            kill -9 $pid 2>/dev/null || true
            sleep 1
        fi
        
        # 再次检查端口是否被释放
        if lsof -ti:$port >/dev/null 2>&1; then
            echo -e "${RED}❌ 无法释放端口 $port，请手动停止占用该端口的服务${NC}"
            return 1
        else
            echo -e "${GREEN}✅ 端口 $port 已释放${NC}"
            return 0
        fi
    fi
    return 0
}

echo -e "${GREEN}🔍 检查端口...${NC}"
if ! check_port 8000; then
    exit 1
fi
if ! check_port 3000; then
    exit 1
fi

# 设置环境变量（如果未设置）
if [ -z "$STORAGE_TYPE" ]; then
    export STORAGE_TYPE="local"
    echo -e "${YELLOW}⚠️  STORAGE_TYPE 未设置，使用默认值: local${NC}"
fi

# 如果使用 S3，检查 S3_CONFIG
if [ "$STORAGE_TYPE" = "s3" ] && [ -z "$S3_CONFIG" ]; then
    echo -e "${YELLOW}⚠️  警告: STORAGE_TYPE=s3 但 S3_CONFIG 未设置${NC}"
    echo "   将回退到本地存储"
    export STORAGE_TYPE="local"
fi

# 设置默认环境变量
export LIGHTX2V_BASE_URL="${LIGHTX2V_BASE_URL:-https://x2v.light-ai.top}"
# 注意：LIGHTX2V_ACCESS_TOKEN 应该从环境变量或 .env 文件读取，不要硬编码在脚本中
# 如果需要，请在运行脚本前设置：export LIGHTX2V_ACCESS_TOKEN="your_token"
export DATA_DIR="${DATA_DIR:-./data}"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# 检查后端依赖
echo -e "${GREEN}📦 检查后端依赖...${NC}"
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  后端依赖未安装，正在安装...${NC}"
    pip install -q fastapi uvicorn loguru aioboto3
fi

# 检查前端依赖
echo -e "${GREEN}📦 检查前端依赖...${NC}"
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}⚠️  前端依赖未安装，正在安装...${NC}"
    cd frontend
    npm install
    cd ..
fi

# 创建数据目录
mkdir -p "$DATA_DIR"/{images,audios,videos,batches}

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}🛑 正在停止服务...${NC}"
    
    # 杀掉后端进程及其子进程
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo "   正在停止后端服务 (PID: $BACKEND_PID)..."
        # 先尝试优雅退出
        kill -TERM $BACKEND_PID 2>/dev/null || true
        # 等待进程退出
        sleep 2
        # 如果还在运行，强制杀掉进程及其子进程
        if kill -0 $BACKEND_PID 2>/dev/null; then
            # 获取进程组 ID 并杀掉整个进程组
            PGID=$(ps -o pgid= -p $BACKEND_PID 2>/dev/null | tr -d ' ')
            if [ ! -z "$PGID" ]; then
                kill -TERM -$PGID 2>/dev/null || true
                sleep 1
                kill -9 -$PGID 2>/dev/null || true
            else
                kill -9 $BACKEND_PID 2>/dev/null || true
            fi
        fi
    fi
    
    # 杀掉前端进程及其子进程
    if [ ! -z "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "   正在停止前端服务 (PID: $FRONTEND_PID)..."
        # 先尝试优雅退出
        kill -TERM $FRONTEND_PID 2>/dev/null || true
        # 等待进程退出
        sleep 2
        # 如果还在运行，强制杀掉进程及其子进程
        if kill -0 $FRONTEND_PID 2>/dev/null; then
            # 获取进程组 ID 并杀掉整个进程组
            PGID=$(ps -o pgid= -p $FRONTEND_PID 2>/dev/null | tr -d ' ')
            if [ ! -z "$PGID" ]; then
                kill -TERM -$PGID 2>/dev/null || true
                sleep 1
                kill -9 -$PGID 2>/dev/null || true
            else
                kill -9 $FRONTEND_PID 2>/dev/null || true
            fi
        fi
    fi
    
    # 额外清理：杀掉可能残留的 uvicorn 进程（通过端口或进程名）
    echo "   清理残留的后端进程..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    pkill -f "uvicorn server.main:app" 2>/dev/null || true
    
    # 额外清理：杀掉可能残留的 vite 进程（通过端口或进程名）
    echo "   清理残留的前端进程..."
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    
    echo -e "${GREEN}✅ 服务已停止${NC}"
    exit 0
}

# 注册清理函数
trap cleanup SIGINT SIGTERM

# 启动后端服务
echo -e "${GREEN}🔧 启动后端服务 (端口 8000)...${NC}"
cd "$SCRIPT_DIR"
# 使用 nohup 或直接后台运行（macOS 可能没有 setsid）
if command -v setsid &> /dev/null; then
    setsid python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload > server.log 2>&1 &
else
    # macOS 上没有 setsid，使用 nohup 或直接后台运行
    python3 -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload > server.log 2>&1 &
fi
BACKEND_PID=$!
echo "   后端服务 PID: $BACKEND_PID"

# 等待后端启动
echo -e "${YELLOW}⏳ 等待后端服务启动...${NC}"
sleep 3

# 检查后端是否启动成功
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${RED}❌ 后端服务启动失败，请查看 server.log${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 后端服务启动成功${NC}"

# 启动前端服务
echo -e "${GREEN}🎨 启动前端服务...${NC}"
cd "$SCRIPT_DIR/frontend"

# 设置前端 API 地址
export VITE_API_BASE="http://localhost:8000"

# 使用 nohup 或直接后台运行（macOS 可能没有 setsid）
if command -v setsid &> /dev/null; then
    setsid npm run dev > ../frontend.log 2>&1 &
else
    # macOS 上没有 setsid，使用 nohup 或直接后台运行
    npm run dev > ../frontend.log 2>&1 &
fi
FRONTEND_PID=$!
echo "   前端服务 PID: $FRONTEND_PID"

# 等待前端启动
echo -e "${YELLOW}⏳ 等待前端服务启动...${NC}"
sleep 5

echo ""
echo -e "${GREEN}✅✅✅ 服务启动完成！${NC}"
echo ""
echo -e "${GREEN}服务地址:${NC}"
echo -e "  - ${GREEN}前端:${NC} http://localhost:3000"
echo -e "  - ${GREEN}后端 API:${NC} http://localhost:8000"
echo -e "  - ${GREEN}API 文档:${NC} http://localhost:8000/docs"
echo -e "  - ${GREEN}健康检查:${NC} http://localhost:8000/health"
echo ""
echo -e "${YELLOW}查看日志:${NC}"
echo "  - 后端日志: tail -f server.log"
echo "  - 前端日志: tail -f frontend.log"
echo ""
echo -e "${YELLOW}停止服务:${NC} 按 Ctrl+C"
echo ""

# 等待用户中断
wait

