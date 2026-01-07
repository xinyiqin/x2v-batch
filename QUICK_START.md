# 快速启动指南

## 一键启动（推荐）

```bash
./start.sh
```

这将同时启动后端（端口 8000）和前端（端口 3000）。

## 分步启动

### 1. 启动后端

```bash
# 在项目根目录
python -m server.main
```

后端将在 `http://localhost:8000` 启动

### 2. 启动前端（新终端）

```bash
cd frontend
npm run dev
```

前端将在 `http://localhost:3000` 启动

## 测试连接

启动后端后，运行测试脚本：

```bash
python test_connection.py
```

## 访问地址

- **前端界面**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

## 登录账户

- **管理员**: `admin` / `admin8888`
- **普通用户**: `user1` / `lightx2v9999`

## 常见问题

### 端口被占用

如果端口被占用，可以修改：

- **后端端口**: 修改 `server/main.py` 中的 `port=8000`
- **前端端口**: 修改 `frontend/vite.config.ts` 中的 `port: 3000`

### CORS 错误

后端已配置允许所有来源，如果仍有问题，检查：
1. 后端是否正常运行
2. 前端 API_BASE 配置是否正确（`frontend/api.ts`）

### 无法登录

1. 检查后端日志
2. 确认 `data/users.json` 文件存在
3. 运行 `python test_connection.py` 测试连接

