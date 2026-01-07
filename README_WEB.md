# S2V 批量任务 Web 服务

基于 FastAPI 的批量 S2V API 调用 Web 服务，提供友好的 Web 界面来管理和提交任务。

## 功能特性

- ✅ 通过 Web 界面提交单个任务
- ✅ 支持图片和音频文件上传
- ✅ 实时任务状态查询
- ✅ 自动轮询任务状态
- ✅ 任务结果 URL 展示
- ✅ 任务取消功能
- ✅ 批量任务管理（通过多次提交）

## 安装依赖

```bash
pip install -r requirements_web.txt
```

## 配置环境变量

在运行服务前，需要设置 API 访问令牌：

```bash
export LIGHTX2V_ACCESS_TOKEN="your_access_token_here"
export LIGHTX2V_BASE_URL="https://x2v.light-ai.top"  # 可选，默认值
```

或者创建 `.env` 文件：

```
LIGHTX2V_ACCESS_TOKEN=your_access_token_here
LIGHTX2V_BASE_URL=https://x2v.light-ai.top
```

## 启动服务

### 方式 1: 直接运行

```bash
python web_backend.py
```

### 方式 2: 使用 uvicorn

```bash
uvicorn web_backend:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后：
- API 文档: http://localhost:8000/docs
- Web 界面: 打开 `web_frontend.html` 文件（需要修改其中的 `API_BASE` 地址）

## 使用说明

### Web 界面使用

1. 打开 `web_frontend.html` 文件
2. 填写任务参数：
   - 提示词（必填）
   - 负面提示词（可选）
   - CFG Scale、时长、随机种子等参数
   - 上传图片和音频文件
3. 选择是否等待任务完成
4. 点击"提交任务"
5. 在任务列表中查看任务状态和结果

### API 使用

#### 提交任务

```bash
curl -X POST "http://localhost:8000/api/submit" \
  -F "prompt=根据音频生成对应视频" \
  -F "negative_prompt=色调艳丽，过曝" \
  -F "cfg_scale=5" \
  -F "duration=7" \
  -F "image=@/path/to/image.png" \
  -F "audio=@/path/to/audio.wav" \
  -F "wait_for_completion=false"
```

#### 查询任务状态

```bash
curl "http://localhost:8000/api/task/{task_id}"
```

#### 列出所有任务

```bash
curl "http://localhost:8000/api/tasks?limit=50&offset=0"
```

#### 取消任务

```bash
curl -X DELETE "http://localhost:8000/api/task/{task_id}"
```

## 注意事项

1. **安全性**: 生产环境应该：
   - 限制 CORS 来源
   - 使用环境变量或密钥管理服务存储 token
   - 添加身份验证
   - 使用数据库存储任务状态（而不是内存）

2. **文件存储**: 当前使用临时目录存储上传的文件，生产环境应该：
   - 使用对象存储服务（如 S3、OSS）
   - 定期清理临时文件

3. **性能**: 对于大量并发任务，考虑：
   - 使用任务队列（如 Celery、RQ）
   - 添加限流机制
   - 使用数据库而不是内存存储

## 架构说明

### 为什么需要后端？

1. **安全性**: API token 不能暴露在前端代码中
2. **文件处理**: 需要接收和处理用户上传的文件
3. **任务管理**: 需要管理任务队列和状态跟踪
4. **长时间轮询**: 任务可能需要很长时间完成，需要后端持续轮询
5. **CORS 限制**: 外部 API 可能不支持跨域请求

### 技术栈

- **后端**: FastAPI (异步 Python Web 框架)
- **前端**: 纯 HTML/CSS/JavaScript (无需构建工具)
- **API 客户端**: 基于现有的 `S2VClient`

