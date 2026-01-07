# Railway 数据存储配置指南

## 方案一：使用 Railway Volume（推荐）

### 优点
- ✅ 数据持久化，不会丢失
- ✅ 简单易用
- ✅ 适合小规模使用

### 配置步骤

1. **在 Railway 项目设置中添加 Volume**
   - 进入你的 Railway 项目
   - 点击 "Settings" → "Volumes"
   - 点击 "New Volume"
   - 设置：
     - **Name**: `data-volume`
     - **Mount Path**: `/app/data`
     - **Size**: 1GB（根据需求调整）

2. **设置环境变量**
   - 在 Railway 服务设置中添加：
     - `DATA_DIR=/app/data`

3. **重新部署**
   - Railway 会自动将 Volume 挂载到 `/app/data`
   - 数据会持久化保存

## 方案二：使用外部对象存储（适合生产环境）

### 优点
- ✅ 可扩展性强
- ✅ 支持 CDN 加速
- ✅ 数据备份方便

### 推荐服务
- AWS S3
- 阿里云 OSS
- 腾讯云 COS
- Cloudflare R2（便宜）

### 实现方式
需要修改 `data_manager.py`，添加 S3/OSS 支持。

## 方案三：初始化数据到 Repo（仅限少量用户）

### 适用场景
- 只有几个固定用户
- 不需要持久化存储
- 可以接受数据在重新部署时重置

### 步骤

1. **创建初始数据文件**
   ```bash
   # 将 users.json 复制到 data/ 目录
   # 注意：密码需要重新生成哈希
   ```

2. **修改 .gitignore**
   - 允许提交 `data/users.json`（但要注意安全）

3. **在启动时复制数据**
   - 在 `init_data.py` 中从 repo 复制初始数据

⚠️ **注意：** 这种方式不推荐，因为：
- 密码哈希会暴露在代码仓库中
- 数据无法持久化
- 不适合生产环境

## 当前推荐方案

**对于少量用户，推荐使用 Railway Volume：**

1. 成本低（Railway 提供免费额度）
2. 数据持久化
3. 配置简单
4. 适合小规模使用

## 数据迁移

如果需要从本地迁移数据到 Railway：

1. **导出本地数据**
   ```bash
   # 压缩 data 目录
   tar -czf data-backup.tar.gz data/
   ```

2. **上传到 Railway Volume**
   - 可以通过 Railway CLI 或临时服务上传
   - 或者使用 `init_data.py` 重新初始化

## 备份建议

定期备份重要数据：
- `users.json` - 用户账户
- `batches/*.json` - 任务记录

可以使用 Railway 的备份功能或手动导出。

