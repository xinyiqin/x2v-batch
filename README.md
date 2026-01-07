# X2V Batch Service

批量 S2V (Speech to Video) API 调用服务，提供 Web 界面来管理和提交视频生成任务。

## 功能特性

- ✅ 用户认证和授权（JWT）
- ✅ 用户点数管理
- ✅ 批次任务管理
- ✅ 文件上传和管理
- ✅ 异步批量处理（调用 S2V API）
- ✅ 任务状态跟踪和轮询
- ✅ 管理员功能
- ✅ 现代化的 Web 界面

## 项目结构

```
.
├── server/          # 后端服务 (FastAPI)
├── frontend/        # 前端应用 (React + Vite)
├── tools/           # 工具函数
├── data/            # 数据存储目录
└── main.py          # 测试脚本
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Docker (可选)

### 本地开发

#### 后端

```bash
cd server
pip install -r requirements.txt
uvicorn server.main:app --reload
```

#### 前端

```bash
cd frontend
npm install
npm run dev
```

### 环境变量

创建 `.env` 文件（参考 `env.example`）：

```bash
LIGHTX2V_BASE_URL=https://x2v.light-ai.top
LIGHTX2V_ACCESS_TOKEN=your_access_token_here
```

## 部署

### Railway 部署

1. 连接 GitHub 仓库到 Railway
2. 设置环境变量 `LIGHTX2V_ACCESS_TOKEN`
3. Railway 会自动检测并部署

### Docker 部署

```bash
docker-compose up -d
```

## 文档

- [快速开始指南](./README_START.md)
- [Web 服务文档](./README_WEB.md)

## License

MIT

