"""
任务管理器 - 负责批次和子任务的管理
支持 batch（批次）和 video_item（子任务）的层级结构
"""
import uuid
import json
import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path
from loguru import logger
import concurrent.futures


class VideoItemStatus(Enum):
    """视频子项状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchStatus(Enum):
    """批次状态"""
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoItem:
    """视频子项"""
    def __init__(
        self,
        item_id: str,
        batch_id: str,
        source_image_filename: str,
        status: VideoItemStatus = VideoItemStatus.PENDING,
        video_filename: Optional[str] = None,
        video_url: Optional[str] = None,
        error_msg: Optional[str] = None,
        api_task_id: Optional[str] = None,
    ):
        self.id = item_id
        self.batch_id = batch_id
        self.source_image_filename = source_image_filename
        self.status = status
        self.video_filename = video_filename
        self.video_url = video_url
        self.error_msg = error_msg
        self.api_task_id = api_task_id
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        # 估算的处理时间（秒），用于进度计算
        self.estimated_duration: Optional[int] = None
    
    def get_progress(self) -> int:
        """
        获取当前进度百分比 (0-100)
        
        Returns:
            进度百分比
        """
        if self.status == VideoItemStatus.COMPLETED:
            return 100
        elif self.status in [VideoItemStatus.FAILED, VideoItemStatus.CANCELLED]:
            return 0
        elif self.status == VideoItemStatus.PENDING:
            return 0
        elif self.status == VideoItemStatus.PROCESSING:
            if self.started_at and self.estimated_duration:
                # 基于已运行时间计算进度
                elapsed = (datetime.now() - self.started_at).total_seconds()
                progress = min((elapsed / self.estimated_duration) * 100, 95)  # 最多95%
                return int(progress)
            else:
                # 如果没有时间信息，返回默认进度
                return 50
        return 0
    
    def get_elapsed_time(self) -> float:
        """获取已运行时间（秒）"""
        if self.started_at:
            if self.completed_at:
                return (self.completed_at - self.started_at).total_seconds()
            else:
                return (datetime.now() - self.started_at).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "sourceImage": self.source_image_filename,
            "videoUrl": self.video_url or "",
            "status": self.status.value,
            "error_msg": self.error_msg,
            "api_task_id": self.api_task_id,
            "progress": self.get_progress(),
            "elapsed_time": self.get_elapsed_time(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoItem":
        """从字典创建"""
        # 兼容旧数据格式：sourceImage 可能是字段名
        source_image = data.get("source_image_filename") or data.get("sourceImage", "")
        video_url = data.get("video_url") or data.get("videoUrl", "")
        
        item = cls(
            item_id=data["id"],
            batch_id=data.get("batch_id", ""),
            source_image_filename=source_image,
            status=VideoItemStatus(data.get("status", "pending")),
            video_filename=data.get("video_filename"),
            video_url=video_url,
            error_msg=data.get("error_msg"),
            api_task_id=data.get("api_task_id"),
        )
        if "created_at" in data and data["created_at"]:
            try:
                item.created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                item.created_at = datetime.now()
        if "updated_at" in data and data["updated_at"]:
            try:
                item.updated_at = datetime.fromisoformat(data["updated_at"])
            except (ValueError, TypeError):
                item.updated_at = datetime.now()
        if "started_at" in data and data["started_at"]:
            try:
                item.started_at = datetime.fromisoformat(data["started_at"])
            except (ValueError, TypeError):
                item.started_at = None
        if "completed_at" in data and data["completed_at"]:
            try:
                item.completed_at = datetime.fromisoformat(data["completed_at"])
            except (ValueError, TypeError):
                item.completed_at = None
        if "estimated_duration" in data:
            item.estimated_duration = data["estimated_duration"]
        return item


class Batch:
    """批次"""
    def __init__(
        self,
        batch_id: str,
        user_id: str,
        user_name: str,
        name: str,
        prompt: str,
        audio_filename: str,
        image_count: int,
        items: Optional[List[VideoItem]] = None,
        status: BatchStatus = BatchStatus.CREATED,
        credits_used: int = 0,
        credits_per_video: int = 0,
        credits_charged: bool = False,
    ):
        self.id = batch_id
        self.user_id = user_id
        self.user_name = user_name
        self.name = name
        self.prompt = prompt
        self.audio_filename = audio_filename
        self.image_count = image_count
        self.items = items or []
        self.status = status
        self.credits_used = credits_used  # 批次消耗的灵感值
        self.credits_per_video = credits_per_video
        self.credits_charged = credits_charged
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def get_overall_progress(self) -> int:
        """
        获取批次总体进度百分比 (0-100)
        
        Returns:
            总体进度百分比
        """
        if not self.items:
            return 0
        
        completed_count = sum(1 for item in self.items if item.status == VideoItemStatus.COMPLETED)
        return int((completed_count / len(self.items)) * 100)
    
    def get_progress_info(self) -> Dict[str, Any]:
        """
        获取进度详细信息
        
        Returns:
            包含进度信息的字典
        """
        if not self.items:
            return {
                "overall_progress": 0,
                "total": 0,
                "completed": 0,
                "processing": 0,
                "pending": 0,
                "failed": 0,
                "cancelled": 0,
            }
        
        total = len(self.items)
        completed = sum(1 for item in self.items if item.status == VideoItemStatus.COMPLETED)
        processing = sum(1 for item in self.items if item.status == VideoItemStatus.PROCESSING)
        pending = sum(1 for item in self.items if item.status == VideoItemStatus.PENDING)
        failed = sum(1 for item in self.items if item.status == VideoItemStatus.FAILED)
        cancelled = sum(1 for item in self.items if item.status == VideoItemStatus.CANCELLED)
        
        return {
            "overall_progress": self.get_overall_progress(),
            "total": total,
            "completed": completed,
            "processing": processing,
            "pending": pending,
            "failed": failed,
            "cancelled": cancelled,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        progress_info = self.get_progress_info()
        return {
            "id": self.id,
            "userId": self.user_id,
            "userName": self.user_name,
            "name": self.name,
            "timestamp": int(self.created_at.timestamp() * 1000),
            "prompt": self.prompt,
            "audioName": self.audio_filename,
            "imageCount": self.image_count,
            "status": self.status.value,
            "progress": progress_info,
            "items": [item.to_dict() for item in self.items],
            "creditsUsed": self.credits_used,  # 批次消耗的灵感值
            "creditsPerVideo": self.credits_per_video,
            "creditsCharged": self.credits_charged,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Batch":
        """从字典创建"""
        batch = cls(
            batch_id=data["id"],
            user_id=data["userId"],
            user_name=data["userName"],
            name=data["name"],
            prompt=data["prompt"],
            audio_filename=data["audioName"],
            image_count=data["imageCount"],
            status=BatchStatus(data.get("status", "created")),
            credits_used=data.get("creditsUsed", 0),  # 兼容旧数据，默认为0
            credits_per_video=data.get("creditsPerVideo", 0),
            credits_charged=data.get("creditsCharged", False),
        )
        if "items" in data:
            batch.items = []
            for item_data in data["items"]:
                # 确保 batch_id 被设置
                item_data["batch_id"] = batch.id
                try:
                    item = VideoItem.from_dict(item_data)
                    batch.items.append(item)
                except Exception as e:
                    logger.error(f"Failed to load item from batch {batch.id}: {e}, item_data: {item_data}")
                    # 继续处理其他 items
        if "created_at" in data:
            try:
                batch.created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                # 兼容时间戳格式
                if isinstance(data["created_at"], (int, float)):
                    batch.created_at = datetime.fromtimestamp(data["created_at"] / 1000 if data["created_at"] > 1e10 else data["created_at"])
                else:
                    batch.created_at = datetime.now()
        if "updated_at" in data:
            try:
                batch.updated_at = datetime.fromisoformat(data["updated_at"])
            except (ValueError, TypeError):
                if isinstance(data["updated_at"], (int, float)):
                    batch.updated_at = datetime.fromtimestamp(data["updated_at"] / 1000 if data["updated_at"] > 1e10 else data["updated_at"])
                else:
                    batch.updated_at = datetime.now()
        return batch
    
    def update_status(self):
        """根据子任务状态更新批次状态"""
        if not self.items:
            return
        
        statuses = [item.status for item in self.items]
        
        if all(s == VideoItemStatus.COMPLETED for s in statuses):
            self.status = BatchStatus.COMPLETED
        elif any(s in [VideoItemStatus.FAILED, VideoItemStatus.CANCELLED] for s in statuses):
            if all(s in [VideoItemStatus.COMPLETED, VideoItemStatus.FAILED, VideoItemStatus.CANCELLED] for s in statuses):
                self.status = BatchStatus.COMPLETED  # 部分失败也算完成
            else:
                self.status = BatchStatus.PROCESSING
        elif any(s == VideoItemStatus.PROCESSING for s in statuses):
            self.status = BatchStatus.PROCESSING
        elif any(s == VideoItemStatus.PENDING for s in statuses):
            self.status = BatchStatus.PROCESSING
        
        self.updated_at = datetime.now()


class TaskManager:
    """任务管理器"""
    
    def __init__(self, storage_dir: str = "./data/batches", task_storage_manager=None, data_manager=None):
        """
        初始化任务管理器
        
        Args:
            storage_dir: 批次数据存储目录（当不使用 task_storage_manager 时）
            task_storage_manager: 任务存储管理器（可选，用于存储批次 JSON 文件，独立于 data_manager）
            data_manager: 数据管理器（可选，用于存储实际文件数据，如图片、音频、视频等）
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # task_storage_manager 用于存储任务相关的 JSON 数据（batches/*.json）
        self.task_storage_manager = task_storage_manager
        # data_manager 用于存储实际文件数据（图片、音频、视频等）
        self.data_manager = data_manager
        self._batches_loaded = False
        
        # 内存中的批次缓存
        self._batches: Dict[str, Batch] = {}
        
        # 加载已存在的批次（如果是本地存储，立即加载；如果是 S3，延迟到异步上下文）
        # 检查是否是 S3DataManager（通过检查是否有 init 方法来判断）
        is_s3_storage = self.task_storage_manager and hasattr(self.task_storage_manager, 'init') and callable(getattr(self.task_storage_manager, 'init', None))
        
        if not is_s3_storage:
            # 本地存储，可以同步加载
            self._load_batches()
            logger.info(f"TaskManager initialized with {len(self._batches)} batches (task storage: local)")
        else:
            # S3 存储，延迟加载
            logger.info("TaskManager initialized (task storage: S3, will load batches asynchronously)")
    
    async def ensure_batches_loaded(self):
        """确保批次数据已加载（用于 S3 存储的异步加载）"""
        if self._batches_loaded:
            return
        
        if self.task_storage_manager:
            # 异步加载批次数据
            try:
                files = await self._load_batches_async()
                
                # 加载每个批次
                for filename in files:
                    if filename.endswith('.json'):
                        batch_id = filename[:-5]  # 移除 .json 后缀
                        # 跳过 users.json（用户数据文件，不是批次文件）
                        if batch_id == 'users':
                            continue
                        try:
                            data_bytes = await self._load_batch_async(batch_id)
                            if data_bytes:
                                data = json.loads(data_bytes.decode('utf-8'))
                                batch = Batch.from_dict(data)
                                self._batches[batch.id] = batch
                        except Exception as e:
                            logger.error(f"Failed to load batch {batch_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to load batches from S3: {e}")
        
        self._batches_loaded = True
        logger.info(f"TaskManager loaded {len(self._batches)} batches (task storage: S3)")
    
    def _get_batch_file(self, batch_id: str) -> Path:
        """获取批次文件路径"""
        return self.storage_dir / f"{batch_id}.json"
    
    def _load_batches(self):
        """从存储加载所有批次（支持本地文件或 S3）"""
        # 检查是否是 S3DataManager
        is_s3_storage = self.task_storage_manager and hasattr(self.task_storage_manager, 'init') and callable(getattr(self.task_storage_manager, 'init', None))
        
        if is_s3_storage:
            # 使用 S3DataManager（异步）
            try:
                # 列出所有批次文件
                # 为每个线程创建独立的事件循环，避免事件循环关闭问题
                def run_list_async():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(self._load_batches_async())
                        # 确保所有任务都完成
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        return result
                    finally:
                        # 确保所有任务完成后再关闭
                        try:
                            pending = asyncio.all_tasks(loop)
                            if pending:
                                for task in pending:
                                    task.cancel()
                                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        except Exception:
                            pass
                        finally:
                            loop.close()
                
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_list_async)
                    files = future.result()
                
                # 加载每个批次
                for filename in files:
                    if filename.endswith('.json'):
                        batch_id = filename[:-5]  # 移除 .json 后缀
                        # 跳过 users.json（用户数据文件，不是批次文件）
                        if batch_id == 'users':
                            continue
                        try:
                            def run_load_async():
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    result = loop.run_until_complete(self._load_batch_async(batch_id))
                                    # 确保所有任务都完成
                                    pending = asyncio.all_tasks(loop)
                                    if pending:
                                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                                    return result
                                finally:
                                    # 确保所有任务完成后再关闭
                                    try:
                                        pending = asyncio.all_tasks(loop)
                                        if pending:
                                            for task in pending:
                                                task.cancel()
                                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                                    except Exception:
                                        pass
                                    finally:
                                        loop.close()
                            
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(run_load_async)
                                data_bytes = future.result()
                            
                            if data_bytes:
                                data = json.loads(data_bytes.decode('utf-8'))
                                batch = Batch.from_dict(data)
                                self._batches[batch.id] = batch
                        except Exception as e:
                            logger.error(f"Failed to load batch {batch_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to load batches from data_manager: {e}")
        else:
            # 使用本地文件
            for batch_file in self.storage_dir.glob("*.json"):
                # 跳过 users.json（用户数据文件，不是批次文件）
                if batch_file.name == "users.json":
                    continue
                try:
                    with open(batch_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        batch = Batch.from_dict(data)
                        self._batches[batch.id] = batch
                except Exception as e:
                    logger.error(f"Failed to load batch {batch_file}: {e}")
    
    async def _load_batches_async(self) -> List[str]:
        """异步列出所有批次文件"""
        try:
            return await self.task_storage_manager.list_files("batches")
        except Exception as e:
            logger.error(f"Failed to list batches from S3: {e}")
            return []
    
    async def _load_batch_async(self, batch_id: str) -> bytes:
        """异步加载单个批次"""
        try:
            filename = f"{batch_id}.json"
            return await self.task_storage_manager.load_bytes(filename, "batches")
        except Exception as e:
            logger.error(f"Failed to load batch {batch_id} from S3: {e}")
            return None
    
    def _batch_is_terminal(self, batch: Batch) -> bool:
        """批次是否已终态：所有 item 均为 COMPLETED/FAILED/CANCELLED。"""
        if not batch or not batch.items:
            return False
        return all(
            item.status in (VideoItemStatus.COMPLETED, VideoItemStatus.FAILED, VideoItemStatus.CANCELLED)
            for item in batch.items
        )

    async def save_batch(self, batch_id: str) -> bool:
        """主动将批次持久化到存储（供 create_batch 等调用）。"""
        batch = self._batches.get(batch_id)
        if not batch:
            return False
        await self._save_batch(batch)
        return True

    async def save_batch_if_terminal(self, batch_id: str) -> bool:
        """仅当批次已终态时持久化，减少 S3 写入次数。"""
        batch = self._batches.get(batch_id)
        if not batch or not self._batch_is_terminal(batch):
            return False
        await self._save_batch(batch)
        return True

    async def _save_batch(self, batch: Batch):
        """保存批次到存储（支持本地文件或 S3）- 异步版本"""
        # 检查是否是 S3DataManager
        is_s3_storage = self.task_storage_manager and hasattr(self.task_storage_manager, 'init') and callable(getattr(self.task_storage_manager, 'init', None))
        
        if is_s3_storage:
            # 使用 S3DataManager（异步）
            try:
                data = json.dumps(batch.to_dict(), ensure_ascii=False, indent=2).encode('utf-8')
                filename = f"{batch.id}.json"
                await self.task_storage_manager.save_bytes(data, filename, "batches")
            except Exception as e:
                logger.error(f"Failed to save batch to task_storage_manager: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
                raise
        else:
            # 使用本地文件（同步操作，但在异步上下文中执行）
            batch_file = self._get_batch_file(batch.id)
            # 使用 asyncio.to_thread 在后台线程中执行文件 I/O
            import asyncio
            def write_file():
                with open(batch_file, "w", encoding="utf-8") as f:
                    json.dump(batch.to_dict(), f, ensure_ascii=False, indent=2)
            await asyncio.to_thread(write_file)
    
    async def create_batch(
        self,
        user_id: str,
        user_name: str,
        name: str,
        prompt: str,
        audio_filename: str,
        image_filenames: List[str],
        credits_used: int = 0,
        credits_per_video: int = 0,
    ) -> Batch:
        """
        创建新批次（异步）
        
        Args:
            user_id: 用户ID
            user_name: 用户名
            name: 批次名称
            prompt: 提示词
            audio_filename: 音频文件名
            image_filenames: 图片文件名列表
            credits_used: 批次消耗的灵感值
            
        Returns:
            创建的批次对象
        """
        batch_id = str(uuid.uuid4())
        
        # 创建子任务
        items = [
            VideoItem(
                item_id=str(uuid.uuid4()),
                batch_id=batch_id,
                source_image_filename=img_filename,
            )
            for img_filename in image_filenames
        ]
        
        batch = Batch(
            batch_id=batch_id,
            user_id=user_id,
            user_name=user_name,
            name=name,
            prompt=prompt,
            audio_filename=audio_filename,
            image_count=len(image_filenames),
            items=items,
            status=BatchStatus.CREATED,
            credits_used=credits_used,
            credits_per_video=credits_per_video,
        )
        
        self._batches[batch.id] = batch
        # 不在此处持久化，由 main.create_batch 在设置完所有 api_task_id 后统一 save_batch 一次
        logger.info(f"Created batch {batch_id} with {len(items)} items, credits used: {credits_used}")
        return batch
    
    def get_batch(self, batch_id: str) -> Optional[Batch]:
        """获取批次"""
        return self._batches.get(batch_id)
    
    def get_user_batches(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Batch]:
        """获取用户的所有批次"""
        user_batches = [
            batch for batch in self._batches.values()
            if batch.user_id == user_id
        ]
        # 按创建时间倒序
        user_batches.sort(key=lambda b: b.created_at, reverse=True)
        return user_batches[offset:offset + limit]
    
    def get_all_batches(self, limit: int = 100, offset: int = 0) -> List[Batch]:
        """获取所有批次"""
        all_batches = list(self._batches.values())
        all_batches.sort(key=lambda b: b.created_at, reverse=True)
        return all_batches[offset:offset + limit]
    
    async def update_video_item(
        self,
        batch_id: str,
        item_id: str,
        status: Optional[VideoItemStatus] = None,
        video_filename: Optional[str] = None,
        video_url: Optional[str] = None,
        error_msg: Optional[str] = None,
        api_task_id: Optional[str] = None,
        estimated_duration: Optional[int] = None,
        persist: bool = True,
    ) -> bool:
        """
        更新视频子项（异步）。persist=False 时只更新内存，不写 S3，由调用方在适当时机 save_batch/save_batch_if_terminal。
        """
        batch = self._batches.get(batch_id)
        if not batch:
            return False

        item = next((item for item in batch.items if item.id == item_id), None)
        if not item:
            return False

        if status is not None:
            old_status = item.status
            item.status = status
            if status == VideoItemStatus.PROCESSING and old_status != VideoItemStatus.PROCESSING:
                item.started_at = datetime.now()
            elif status in [VideoItemStatus.COMPLETED, VideoItemStatus.FAILED, VideoItemStatus.CANCELLED]:
                item.completed_at = datetime.now()

        if video_filename is not None:
            item.video_filename = video_filename
        if video_url is not None:
            item.video_url = video_url
        if error_msg is not None:
            item.error_msg = error_msg
        if api_task_id is not None:
            item.api_task_id = api_task_id
        if estimated_duration is not None:
            item.estimated_duration = estimated_duration

        item.updated_at = datetime.now()
        batch.update_status()
        if persist:
            await self._save_batch(batch)
        return True
    
    def get_video_item(self, batch_id: str, item_id: str) -> Optional[VideoItem]:
        """获取视频子项"""
        batch = self._batches.get(batch_id)
        if not batch:
            return None
        return next((item for item in batch.items if item.id == item_id), None)

