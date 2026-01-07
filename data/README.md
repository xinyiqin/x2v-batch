# 数据目录说明

## 目录结构

- `users.json` - 用户数据（包含密码哈希，**不要提交到 Git**）
- `batches/` - 批次任务数据（JSON 文件）
- `images/` - 上传的图片文件
- `audios/` - 上传的音频文件
- `videos/` - 生成的视频文件

## 部署说明

### Railway 部署

1. **使用 Railway Volume（推荐）**
   - 在 Railway 项目设置中添加 Volume
   - 挂载到 `/app/data` 目录
   - 数据会持久化保存

2. **初始化数据**
   - 首次部署时，`init_data.py` 会自动创建初始用户
   - 默认用户：
     - admin / admin8888 (管理员，9999 点数)
     - user1 / lightx2v9999 (普通用户，10 点数)

### 本地开发

数据会自动保存在 `./data` 目录。

## 注意事项

⚠️ **不要将以下内容提交到 Git：**
- `users.json` - 包含密码哈希
- `images/` - 用户上传的图片
- `audios/` - 用户上传的音频
- `videos/` - 生成的视频
- `batches/*.json` - 包含用户数据

✅ **可以提交：**
- `data/.gitkeep` - 保持目录结构
- `data/init_data.py` - 初始化脚本
- `data/README.md` - 说明文档

