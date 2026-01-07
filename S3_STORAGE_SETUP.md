# S3 存储配置指南

## 概述

项目支持两种存储方式：
1. **本地存储**（LocalDataManager）- 默认方式，适合小规模使用
2. **S3 对象存储**（S3DataManager）- 适合大规模使用，可扩展性强

## 为什么使用 S3？

- ✅ **可扩展性**：不受 Railway Volume 大小限制
- ✅ **成本效益**：按使用量付费，比固定存储更便宜
- ✅ **可靠性**：对象存储服务通常有高可用性保证
- ✅ **CDN 支持**：可以配置 CDN 加速访问
- ✅ **备份方便**：自动备份，数据安全

## 支持的 S3 兼容服务

- AWS S3
- 阿里云 OSS
- 腾讯云 COS
- Cloudflare R2（推荐，便宜）
- MinIO（自建）
- 其他 S3 兼容服务

## 配置步骤

### 1. 创建存储桶

在您选择的对象存储服务中创建存储桶（Bucket）。

### 2. 获取访问凭证

获取以下信息：
- Access Key ID
- Secret Access Key
- Endpoint URL（端点地址）
- Region（区域，可选）

### 3. 配置环境变量

在 Railway 项目设置中添加以下环境变量：

#### 必需变量

```bash
STORAGE_TYPE=s3
S3_CONFIG='{
  "aws_access_key_id": "your_access_key_id",
  "aws_secret_access_key": "your_secret_access_key",
  "endpoint_url": "https://s3.amazonaws.com",
  "bucket_name": "your-bucket-name",
  "base_path": "x2v-batch",
  "region": "us-east-1"
}'
```

#### 可选变量

```bash
# CDN URL（如果配置了 CDN）
S3_CONFIG='{
  ...
  "cdn_url": "https://cdn.example.com",
  "connect_timeout": 60,
  "read_timeout": 60,
  "write_timeout": 10
}'
```

### 4. S3_CONFIG JSON 格式说明

```json
{
  "aws_access_key_id": "访问密钥 ID",
  "aws_secret_access_key": "访问密钥 Secret",
  "endpoint_url": "S3 端点 URL",
  "bucket_name": "存储桶名称",
  "base_path": "基础路径前缀（可选，用于区分不同环境）",
  "region": "区域（可选）",
  "cdn_url": "CDN URL（可选，用于直接访问文件）",
  "connect_timeout": 60,
  "read_timeout": 60,
  "write_timeout": 10
}
```

## 各服务商配置示例

### AWS S3

```json
{
  "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
  "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "endpoint_url": "https://s3.amazonaws.com",
  "bucket_name": "my-x2v-bucket",
  "base_path": "x2v-batch",
  "region": "us-east-1"
}
```

### 阿里云 OSS

```json
{
  "aws_access_key_id": "your_access_key_id",
  "aws_secret_access_key": "your_secret_access_key",
  "endpoint_url": "https://oss-cn-hangzhou.aliyuncs.com",
  "bucket_name": "my-x2v-bucket",
  "base_path": "x2v-batch",
  "region": "cn-hangzhou"
}
```

### 腾讯云 COS

```json
{
  "aws_access_key_id": "your_secret_id",
  "aws_secret_access_key": "your_secret_key",
  "endpoint_url": "https://cos.ap-beijing.myqcloud.com",
  "bucket_name": "my-x2v-bucket-1234567890",
  "base_path": "x2v-batch",
  "region": "ap-beijing"
}
```

### Cloudflare R2（推荐，便宜）

```json
{
  "aws_access_key_id": "your_r2_access_key_id",
  "aws_secret_access_key": "your_r2_secret_access_key",
  "endpoint_url": "https://your-account-id.r2.cloudflarestorage.com",
  "bucket_name": "my-x2v-bucket",
  "base_path": "x2v-batch"
}
```

**注意**：Cloudflare R2 不需要 region。

## 切换存储方式

### 从本地切换到 S3

1. 在 Railway 中添加 `STORAGE_TYPE=s3` 和 `S3_CONFIG`
2. 重新部署服务
3. 数据会自动保存到 S3

### 从 S3 切换回本地

1. 删除或修改 `STORAGE_TYPE` 环境变量（设为 `local` 或不设置）
2. 重新部署服务
3. 数据会保存到本地（Railway Volume）

## 数据迁移

### 从本地迁移到 S3

如果需要将现有数据迁移到 S3，可以：

1. **手动迁移**：使用 S3 管理工具上传文件
2. **脚本迁移**：编写脚本批量上传（可以参考 `tools/` 目录）

### 从 S3 迁移回本地

使用 S3 管理工具下载文件到本地目录。

## 成本对比

### Railway Volume
- 固定费用：根据大小收费
- 适合：小规模使用（< 10GB）

### S3 对象存储
- **AWS S3**: ~$0.023/GB/月
- **Cloudflare R2**: ~$0.015/GB/月（更便宜）
- **阿里云 OSS**: ~¥0.12/GB/月
- 适合：大规模使用，按需付费

## 注意事项

1. **安全性**：不要将 `S3_CONFIG` 提交到 Git，使用环境变量
2. **权限**：确保 Access Key 有足够的权限（读写、删除）
3. **CDN**：如果配置了 CDN，文件访问会更快
4. **备份**：定期备份重要数据
5. **成本监控**：设置使用量告警，避免意外费用

## 故障排查

### 问题：无法连接到 S3

- 检查 `endpoint_url` 是否正确
- 检查网络连接
- 检查 Access Key 权限

### 问题：文件上传失败

- 检查存储桶是否存在
- 检查 Access Key 权限
- 检查存储桶空间是否充足

### 问题：文件访问 URL 无效

- 检查是否配置了 CDN
- 检查预签名 URL 是否过期（默认 24 小时）
- 检查存储桶的访问策略

## 推荐方案

**对于少量用户**：
- 使用本地存储（Railway Volume）
- 成本低，配置简单

**对于中等规模**：
- 使用 Cloudflare R2
- 成本低，性能好

**对于大规模**：
- 使用 AWS S3 或阿里云 OSS
- 功能完善，可靠性高

