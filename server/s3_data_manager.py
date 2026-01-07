"""
S3 数据管理器 - 使用 S3 兼容的对象存储服务
支持 AWS S3、阿里云 OSS、腾讯云 COS 等
"""
import os
import json
import hashlib
import asyncio
from typing import Optional, List
from loguru import logger

try:
    import aioboto3
    from botocore.client import Config
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    # 不在这里显示警告，只在真正使用时显示


class S3DataManager:
    """S3 对象存储数据管理器"""
    
    def __init__(self, config_string: str):
        """
        初始化 S3 数据管理器
        
        Args:
            config_string: JSON 格式的配置字符串，包含：
                - aws_access_key_id: AWS Access Key ID
                - aws_secret_access_key: AWS Secret Access Key
                - endpoint_url: S3 端点 URL
                - bucket_name: 存储桶名称
                - base_path: 基础路径前缀
                - region: 区域（可选）
                - cdn_url: CDN URL（可选，用于直接访问）
                - connect_timeout: 连接超时（默认 60 秒）
                - read_timeout: 读取超时（默认 60 秒）
                - write_timeout: 写入超时（默认 10 秒）
        """
        if not S3_AVAILABLE:
            raise ImportError("aioboto3 is required for S3 support. Install it with: pip install aioboto3")
        
        self.config = json.loads(config_string)
        self.bucket_name = self.config["bucket_name"]
        self.aws_access_key_id = self.config["aws_access_key_id"]
        self.aws_secret_access_key = self.config["aws_secret_access_key"]
        self.endpoint_url = self.config["endpoint_url"]
        self.base_path = self.config.get("base_path", "")
        self.region = self.config.get("region", None)
        self.cdn_url = self.config.get("cdn_url", "")
        self.connect_timeout = self.config.get("connect_timeout", 60)
        self.read_timeout = self.config.get("read_timeout", 60)
        self.write_timeout = self.config.get("write_timeout", 10)
        
        self.session = None
        self.s3_client = None
        self._initialized = False
        
        logger.info(f"S3DataManager initialized with bucket: {self.bucket_name}, base_path: {self.base_path}")
    
    async def init(self):
        """初始化 S3 客户端并检查存储桶"""
        if self._initialized:
            return
        
        try:
            logger.info(f"Initializing S3 client for bucket: {self.bucket_name}")
            
            s3_config = {"payload_signing_enabled": True}
            self.session = aioboto3.Session()
            self.s3_client = await self.session.client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                config=Config(
                    signature_version="s3v4",
                    s3=s3_config,
                    connect_timeout=self.connect_timeout,
                    read_timeout=self.read_timeout,
                    parameter_validation=False,
                    max_pool_connections=50,
                ),
            ).__aenter__()
            
            # 检查存储桶是否存在，不存在则创建
            try:
                await self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info(f"Bucket {self.bucket_name} exists")
            except Exception as e:
                logger.info(f"Bucket {self.bucket_name} does not exist, creating...")
                try:
                    if self.region:
                        await self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    else:
                        await self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket: {self.bucket_name}")
                except Exception as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise
            
            self._initialized = True
            logger.info(f"S3DataManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise
    
    async def close(self):
        """关闭 S3 客户端"""
        if self.s3_client:
            try:
                await self.s3_client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing S3 client: {e}")
        self.session = None
        self._initialized = False
    
    def _get_key(self, filename: str, subdir: Optional[str] = None) -> str:
        """获取 S3 对象键（路径）"""
        parts = []
        if self.base_path:
            parts.append(self.base_path.rstrip('/'))
        if subdir:
            parts.append(subdir)
        parts.append(filename)
        key = '/'.join(parts)
        # 确保 key 不以 / 开头
        return key.lstrip('/')
    
    async def save_bytes(self, bytes_data: bytes, filename: str, subdir: Optional[str] = None) -> str:
        """
        保存字节数据到 S3
        
        Args:
            bytes_data: 字节数据
            filename: 文件名
            subdir: 子目录（images, audios, videos, batches）
            
        Returns:
            S3 对象键
        """
        if not self._initialized:
            await self.init()
        
        key = self._get_key(filename, subdir)
        content_sha256 = hashlib.sha256(bytes_data).hexdigest()
        
        try:
            await self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=bytes_data,
                ContentType="application/octet-stream",
            )
            logger.debug(f"Saved bytes to S3: {key}")
            return key
        except Exception as e:
            logger.error(f"Failed to save bytes to S3: {e}")
            raise
    
    async def load_bytes(self, filename: str, subdir: Optional[str] = None) -> bytes:
        """
        从 S3 加载字节数据
        
        Args:
            filename: 文件名或 S3 键
            subdir: 子目录
            
        Returns:
            字节数据
        """
        if not self._initialized:
            await self.init()
        
        # 如果 filename 已经是完整的 key，直接使用
        if '/' in filename and not subdir:
            key = filename
        else:
            key = self._get_key(filename, subdir)
        
        try:
            response = await self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            data = await response["Body"].read()
            logger.debug(f"Loaded bytes from S3: {key}")
            return data
        except Exception as e:
            logger.error(f"Failed to load bytes from S3: {e}")
            raise FileNotFoundError(f"File not found in S3: {key}")
    
    async def delete_bytes(self, filename: str, subdir: Optional[str] = None) -> bool:
        """
        从 S3 删除文件
        
        Args:
            filename: 文件名
            subdir: 子目录
            
        Returns:
            是否成功
        """
        if not self._initialized:
            await self.init()
        
        key = self._get_key(filename, subdir)
        
        try:
            await self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.debug(f"Deleted file from S3: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file from S3: {e}")
            return False
    
    async def file_exists(self, filename: str, subdir: Optional[str] = None) -> bool:
        """
        检查文件是否存在
        
        Args:
            filename: 文件名
            subdir: 子目录
            
        Returns:
            是否存在
        """
        if not self._initialized:
            await self.init()
        
        key = self._get_key(filename, subdir)
        
        try:
            await self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False
    
    async def get_url(self, filename: str, subdir: Optional[str] = None) -> str:
        """
        获取文件访问 URL
        
        Args:
            filename: 文件名
            subdir: 子目录
            
        Returns:
            文件 URL
        """
        # 如果已经提供 CDN URL，直接使用
        if self.cdn_url:
            key = self._get_key(filename, subdir)
            return f"{self.cdn_url.rstrip('/')}/{key}"
        
        # 否则生成预签名 URL（24小时有效）
        if not self._initialized:
            await self.init()
        
        key = self._get_key(filename, subdir)
        
        try:
            # 生成预签名 URL，有效期 24 小时
            url = await self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=86400  # 24 小时
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            # 如果生成失败，返回相对路径
            return f"/api/files/{subdir}/{filename}" if subdir else f"/api/files/{filename}"
    
    async def save_image(self, image_data: bytes, filename: str) -> str:
        """保存图片"""
        return await self.save_bytes(image_data, filename, "images")
    
    async def save_audio(self, audio_data: bytes, filename: str) -> str:
        """保存音频"""
        return await self.save_bytes(audio_data, filename, "audios")
    
    async def save_video(self, video_data: bytes, filename: str) -> str:
        """保存视频"""
        return await self.save_bytes(video_data, filename, "videos")
    
    async def list_files(self, subdir: Optional[str] = None) -> List[str]:
        """
        列出目录下的所有文件
        
        Args:
            subdir: 子目录
            
        Returns:
            文件名列表
        """
        if not self._initialized:
            await self.init()
        
        prefix = self._get_key("", subdir)
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        
        files = []
        continuation_token = None
        
        try:
            while True:
                list_kwargs = {
                    "Bucket": self.bucket_name,
                    "Prefix": prefix,
                    "MaxKeys": 1000
                }
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token
                
                response = await self.s3_client.list_objects_v2(**list_kwargs)
                
                if "Contents" in response:
                    for obj in response["Contents"]:
                        key = obj["Key"]
                        # 移除前缀，只保留文件名
                        if key.startswith(prefix):
                            filename = key[len(prefix):]
                            if filename:  # 跳过空文件名（目录本身）
                                files.append(filename)
                
                # 检查是否有更多页面
                if response.get("IsTruncated", False):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break
            
            return files
        except Exception as e:
            logger.error(f"Failed to list files from S3: {e}")
            return []

