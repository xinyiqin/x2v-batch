"""
数据管理器 - 负责文件存储和读取
支持本地文件系统存储
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Optional, List
from loguru import logger


class LocalDataManager:
    """本地文件数据管理器"""
    
    def __init__(self, base_dir: str = "./data"):
        """
        初始化数据管理器
        
        Args:
            base_dir: 基础存储目录
        """
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        self.images_dir = self.base_dir / "images"
        self.audios_dir = self.base_dir / "audios"
        self.videos_dir = self.base_dir / "videos"
        self.batches_dir = self.base_dir / "batches"
        
        for dir_path in [self.images_dir, self.audios_dir, self.videos_dir, self.batches_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"DataManager initialized with base_dir: {self.base_dir}")
    
    def _get_path(self, filename: str, subdir: Optional[str] = None) -> Path:
        """获取文件完整路径"""
        if subdir:
            return self.base_dir / subdir / filename
        return self.base_dir / filename
    
    async def save_bytes(self, bytes_data: bytes, filename: str, subdir: Optional[str] = None) -> str:
        """
        保存字节数据到文件
        
        Args:
            bytes_data: 字节数据
            filename: 文件名
            subdir: 子目录（images, audios, videos, batches）
            
        Returns:
            保存的文件路径
        """
        file_path = self._get_path(filename, subdir)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(bytes_data)
        
        logger.debug(f"Saved bytes to: {file_path}")
        return str(file_path)
    
    async def load_bytes(self, filename: str, subdir: Optional[str] = None) -> bytes:
        """
        从文件加载字节数据
        
        Args:
            filename: 文件名
            subdir: 子目录
            
        Returns:
            字节数据
        """
        file_path = self._get_path(filename, subdir)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, "rb") as f:
            return f.read()
    
    async def delete_bytes(self, filename: str, subdir: Optional[str] = None) -> bool:
        """
        删除文件
        
        Args:
            filename: 文件名
            subdir: 子目录
            
        Returns:
            是否成功
        """
        file_path = self._get_path(filename, subdir)
        
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted file: {file_path}")
            return True
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
        file_path = self._get_path(filename, subdir)
        return file_path.exists()
    
    async def get_url(self, filename: str, subdir: Optional[str] = None) -> str:
        """
        获取文件访问 URL（返回相对路径，前端需要拼接 API_BASE）
        
        Args:
            filename: 文件名
            subdir: 子目录
            
        Returns:
            文件 URL（相对路径）
        """
        # 如果已经是完整 URL，直接返回
        if filename.startswith('http://') or filename.startswith('https://'):
            return filename
        
        # 返回相对于 API 的路径
        if subdir:
            return f"/api/files/{subdir}/{filename}"
        return f"/api/files/{filename}"
    
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
        dir_path = self._get_path("", subdir) if subdir else self.base_dir
        if not dir_path.exists():
            return []
        
        return [f.name for f in dir_path.iterdir() if f.is_file()]

