# 前后端启动指南

## 快速启动

### 方式 1: 使用启动脚本（推荐）

```bash
chmod +x start.sh
./start.sh
```

### 方式 2: 手动启动

#### 1. 启动后端服务

```bash
cd /Users/qinxinyi/Documents/code/agent

# 设置环境变量（可选，但推荐）
export LIGHTX2V_ACCESS_TOKEN="your_token_here"

# 启动后端
python -m server.main
```

后端服务将在 `http://localhost:8000` 启动

#### 2. 启动前端服务

打开新的终端窗口：

```bash
cd /Users/qinxinyi/Documents/code/agent/frontend

# 安装依赖（首次运行）
npm install

# 启动前端开发服务器
npm run dev
```

前端服务将在 `http://localhost:3000` 启动

## 访问地址

- **前端界面**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

## 默认账户

- **管理员账户**:
  - 用户名: `admin`
  - 密码: `admin8888`
  - 点数: 9999

- **普通用户**:
  - 用户名: `user1`
  - 密码: `lightx2v9999`
  - 点数: 10

## 配置说明

### 前端 API 配置

前端 API 基础地址在 `frontend/api.ts` 中配置：

```typescript
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
```

可以通过环境变量 `VITE_API_BASE` 自定义 API 地址。

### 后端 CORS 配置

后端已配置允许所有来源的跨域请求（开发环境）。生产环境建议限制具体域名。

### 环境变量

- `LIGHTX2V_ACCESS_TOKEN`: S2V API 访问令牌（必需，用于批次处理）
- `LIGHTX2V_BASE_URL`: S2V API 基础 URL（可选，默认: https://x2v.light-ai.top）

## 故障排查

### 1. 前端无法连接后端

- 检查后端是否正在运行（访问 http://localhost:8000/docs）
- 检查浏览器控制台是否有 CORS 错误
- 确认前端 API_BASE 配置正确

### 2. 登录失败

- 检查后端日志
- 确认用户数据文件 `data/users.json` 存在
- 验证密码是否正确

### 3. 文件上传失败

- 检查 `data/images` 和 `data/audios` 目录权限
- 确认磁盘空间充足

### 4. 批次处理失败

- 检查 `LIGHTX2V_ACCESS_TOKEN` 是否设置
- 检查后端日志中的错误信息
- 验证 S2V API 是否可访问

## 开发模式

### 后端热重载

后端已配置自动重载，修改代码后会自动重启。

### 前端热重载

前端使用 Vite，修改代码后会自动刷新浏览器。

## 生产部署

生产环境部署时：

1. 修改前端 `api.ts` 中的 API_BASE 为生产地址
2. 修改后端 CORS 配置，限制允许的来源
3. 使用环境变量管理敏感信息
4. 配置 HTTPS
5. 使用进程管理器（如 PM2）管理服务

