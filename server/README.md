# AI Vision Batch Service - 后端服务

基于 FastAPI 的批量视频生成服务后端。

## 功能特性

- ✅ 用户认证和授权（JWT）
- ✅ 用户点数管理
- ✅ 批次任务管理（Batch + VideoItem 层级结构）
- ✅ 文件存储管理（本地文件系统）
- ✅ 异步批量处理（调用 S2V API）
- ✅ 任务状态跟踪和轮询
- ✅ 管理员功能

## 目录结构

```
server/
├── __init__.py
├── main.py              # FastAPI 主应用
├── auth.py              # 认证管理
├── data_manager.py      # 数据存储管理
├── task_manager.py      # 任务管理（Batch + VideoItem）
├── batch_processor.py   # 批次处理器（调用 S2V API）
└── requirements.txt     # Python 依赖
```

## 安装和运行

### 1. 安装依赖

```bash
cd server
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
export LIGHTX2V_BASE_URL="https://x2v.light-ai.top"
export LIGHTX2V_ACCESS_TOKEN="your_access_token_here"
```

### 3. 运行服务

```bash
python -m server.main
# 或
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后：
- API 文档: http://localhost:8000/docs
- API 基础路径: http://localhost:8000/api

## API 接口

### 认证接口

- `POST /api/auth/login` - 用户登录

### 用户接口

- `GET /api/user/profile` - 获取当前用户信息

### 视频生成接口

- `POST /api/video/batch` - 创建批次任务
- `GET /api/video/batches` - 获取用户批次列表
- `GET /api/video/batches/{batch_id}` - 获取批次详情

### 管理员接口

- `GET /api/admin/users` - 获取所有用户
- `PATCH /api/admin/users/{user_id}/credits` - 更新用户点数
- `GET /api/admin/batches` - 获取所有批次

### 文件服务

- `GET /api/files/{subdir}/{filename}` - 获取文件

## 数据存储

### 文件存储结构

```
data/
├── images/          # 用户上传的图片
├── audios/          # 用户上传的音频
├── videos/          # 生成的视频（可选，当前使用外部 URL）
├── batches/         # 批次元数据 JSON 文件
└── users.json       # 用户数据
```

### 批次数据结构

每个批次存储为独立的 JSON 文件：`data/batches/{batch_id}.json`

```json
{
  "id": "batch-uuid",
  "userId": "u-1",
  "userName": "admin",
  "name": "批次 admin 1234567890",
  "timestamp": 1234567890000,
  "prompt": "根据音频生成对应视频",
  "audioName": "audio.wav",
  "imageCount": 5,
  "status": "processing",
  "items": [
    {
      "id": "item-uuid",
      "sourceImage": "user_image.png",
      "videoUrl": "https://...",
      "status": "completed",
      "api_task_id": "s2v-task-id"
    }
  ]
}
```

## 任务处理流程

1. **用户提交批次**
   - 上传图片和音频文件
   - 创建 Batch 和多个 VideoItem
   - 扣除用户点数

2. **异步处理**
   - BatchProcessor 并发处理所有 VideoItem
   - 每个 VideoItem 调用 S2V API
   - 更新任务状态

3. **状态跟踪**
   - 前端轮询批次状态
   - 实时更新 VideoItem 状态
   - 批次状态根据子任务自动更新

## 注意事项

1. **默认管理员账户**: `admin` / `admin` (首次启动自动创建)
2. **点数消耗**: 每个图片消耗 1 点
3. **并发限制**: 默认最多 3 个并发任务（可在 `batch_processor.py` 中调整）
4. **文件清理**: 临时文件会自动清理，但用户上传的文件会保留
5. **生产环境**: 建议使用数据库替代 JSON 文件存储，使用对象存储替代本地文件系统

