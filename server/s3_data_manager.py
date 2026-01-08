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
        self.addressing_style = self.config.get("addressing_style", None)
        self.connect_timeout = self.config.get("connect_timeout", 60)
        self.read_timeout = self.config.get("read_timeout", 60)
        self.write_timeout = self.config.get("write_timeout", 10)
        
        self.session = None
        self.s3_client = None
        self._initialized = False
        # 存储每个事件循环的客户端，避免事件循环冲突
        self._loop_clients = {}
        
        logger.info(f"S3DataManager initialized with bucket: {self.bucket_name}, base_path: {self.base_path}")
    
    async def init(self):
        """初始化 S3 客户端并检查存储桶"""
        # 获取当前事件循环
        loop = asyncio.get_event_loop()
        
        # 如果当前事件循环已经有客户端，直接返回
        if loop in self._loop_clients:
            self.s3_client = self._loop_clients[loop]
            self._initialized = True
            return
        
        if self._initialized:
            # 检查当前事件循环是否与已初始化的客户端匹配
            if self.s3_client and hasattr(self.s3_client, '_client_config'):
                # 如果客户端存在但事件循环不匹配，需要重新创建
                try:
                    # 尝试使用现有客户端，如果失败则重新创建
                    pass
                except RuntimeError:
                    self._initialized = False
                    self.s3_client = None
        
        if self._initialized:
            return
        
        try:
            logger.info(f"Initializing S3 client for bucket: {self.bucket_name} (loop: {id(loop)})")
            
            s3_config = {"payload_signing_enabled": True}
            # 火山引擎 TOS 需要 addressing_style
            if self.addressing_style:
                s3_config["addressing_style"] = self.addressing_style
                logger.debug(f"Using addressing_style: {self.addressing_style}")
            
            # 为当前事件循环创建新的会话和客户端
            session = aioboto3.Session()
            s3_client = await session.client(
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
            
            # 存储会话和客户端
            self.session = session
            self.s3_client = s3_client
            self._loop_clients[loop] = s3_client
            
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
        # 关闭所有事件循环的客户端
        for loop, client in list(self._loop_clients.items()):
            try:
                await client.__aexit__(None, None, None)
                logger.debug(f"Closed S3 client for loop: {id(loop)}")
            except Exception as e:
                logger.warning(f"Error closing S3 client for loop {id(loop)}: {e}")
            finally:
                del self._loop_clients[loop]
        
        # 关闭主客户端（如果存在）
        if self.s3_client:
            try:
                await self.s3_client.__aexit__(None, None, None)
                logger.info("S3 client closed")
            except Exception as e:
                logger.warning(f"Error closing S3 client: {e}")
        
        self.session = None
        self.s3_client = None
        self._initialized = False
        self._loop_clients.clear()
    
    def _get_key(self, filename: str, subdir: Optional[str] = None) -> str:
        """获取 S3 对象键（路径）"""
        parts = []
        if self.base_path:
            # 移除 base_path 前后的斜杠
            base = self.base_path.strip('/')
            if base:
                parts.append(base)
        if subdir:
            # 移除 subdir 前后的斜杠
            sub = subdir.strip('/')
            if sub:
                parts.append(sub)
        # 移除 filename 前后的斜杠
        name = filename.strip('/')
        if name:
            parts.append(name)
        # 使用 / 连接，确保没有双斜杠
        key = '/'.join(parts)
        # 确保 key 不以 / 开头，并且规范化路径
        key = key.lstrip('/')
        # 移除空字符串部分
        key = '/'.join([p for p in key.split('/') if p])
        return key
    
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
        # 确保 key 不为空
        if not key:
            raise ValueError(f"Invalid key generated for filename: {filename}, subdir: {subdir}")
        
        content_sha256 = hashlib.sha256(bytes_data).hexdigest()
        
        # 获取当前事件循环
        loop = asyncio.get_event_loop()
        
        # 确保当前事件循环有客户端
        if loop not in self._loop_clients:
            await self.init()
        
        # 使用当前事件循环的客户端
        s3_client = self._loop_clients.get(loop, self.s3_client)
        if not s3_client:
            await self.init()
            s3_client = self._loop_clients.get(loop, self.s3_client)
        
        try:
            logger.debug(f"Attempting to save bytes to S3: bucket={self.bucket_name}, key={key}, size={len(bytes_data)}")
            await s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=bytes_data,
                ContentType="application/octet-stream",
            )
            logger.debug(f"Saved bytes to S3: {key}")
            return key
        except Exception as e:
            logger.error(f"Failed to save bytes to S3: bucket={self.bucket_name}, key={key}, error={e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
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
        
        # 构建前缀路径
        parts = []
        if self.base_path:
            base = self.base_path.strip('/')
            if base:
                parts.append(base)
        if subdir:
            sub = subdir.strip('/')
            if sub:
                parts.append(sub)
        
        prefix = '/'.join(parts)
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        elif not prefix:
            prefix = ""
        
        logger.debug(f"Listing files with prefix: '{prefix}'")
        
        files = []
        continuation_token = None
        
        try:
            while True:
                list_kwargs = {
                    "Bucket": self.bucket_name,
                    "MaxKeys": 1000
                }
                if prefix:
                    list_kwargs["Prefix"] = prefix
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token
                
                response = await self.s3_client.list_objects_v2(**list_kwargs)
                
                if "Contents" in response:
                    for obj in response["Contents"]:
                        key = obj["Key"]
                        # 移除前缀，只保留文件名
                        if prefix and key.startswith(prefix):
                            filename = key[len(prefix):]
                            if filename:  # 跳过空文件名（目录本身）
                                files.append(filename)
                        elif not prefix:
                            # 如果没有前缀，直接使用文件名
                            if key and not key.endswith('/'):
                                # 提取文件名（最后一个部分）
                                filename = key.split('/')[-1]
                                if filename:
                                    files.append(filename)
                
                # 检查是否有更多页面
                if response.get("IsTruncated", False):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break
            
            return files
        except Exception as e:
            logger.error(f"Failed to list files from S3: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []

