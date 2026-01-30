"""
批次处理器 - 负责处理批次任务，调用 S2V API
"""
import asyncio
from datetime import datetime
from typing import Dict, Any
from loguru import logger

from tools.s2v_client import S2VClient
from server.task_manager import TaskManager, VideoItemStatus, BatchStatus
from server.data_manager import LocalDataManager
from server.auth import AuthManager


class BatchProcessor:
    """批次处理器"""
    
    def __init__(
        self,
        task_manager: TaskManager,
        data_manager: LocalDataManager,
        auth_manager: AuthManager,
        base_url: str,
        access_token: str,
    ):
        """
        初始化批次处理器
        
        Args:
            task_manager: 任务管理器
            data_manager: 数据管理器
            base_url: S2V API 基础 URL
            access_token: S2V API 访问令牌
        """
        self.task_manager = task_manager
        self.data_manager = data_manager
        self.auth_manager = auth_manager
        self.base_url = base_url
        self.access_token = access_token
        self.client = S2VClient(base_url=base_url, access_token=access_token)
    
    def update_token(self, new_token: str):
        """
        更新访问令牌
        
        Args:
            new_token: 新的访问令牌
        """
        self.access_token = new_token
        # 重新创建客户端以使用新 token
        self.client = S2VClient(base_url=self.base_url, access_token=new_token)
        logger.info("S2V API access token updated successfully")
    
    async def process_batch(self, batch_id: str):
        """
        处理批次中的所有子任务
        
        Args:
            batch_id: 批次ID
        """
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            logger.error(f"Batch {batch_id} not found")
            return
        
        logger.info(f"Processing batch {batch_id} with {len(batch.items)} items")
        
        # 更新批次状态
        batch.status = BatchStatus.PROCESSING
        await self.task_manager._save_batch(batch)
        
        # 加载音频文件
        audio_data = await self.data_manager.load_bytes(batch.audio_filename, "audios")
        
        # 并发处理所有子任务（限制并发数）
        semaphore = asyncio.Semaphore(3)  # 最多3个并发任务
        
        async def process_item(item):
            async with semaphore:
                await self._process_video_item(batch, item, audio_data)
        
        tasks = [process_item(item) for item in batch.items]
        await asyncio.gather(*tasks)
        
        # 更新批次最终状态
        batch = self.task_manager.get_batch(batch_id)
        if batch:
            batch.update_status()
            await self.task_manager._save_batch(batch)
            await self._charge_completed_batch(batch.id)
        
        logger.info(f"Batch {batch_id} processing completed")
    
    async def _process_video_item(
        self,
        batch: Any,
        item: Any,
        audio_data: bytes,
    ):
        """
        处理单个视频子项
        
        Args:
            batch: 批次对象
            item: 视频子项
            audio_data: 音频数据（字节）
        """
        try:
            current_item = self.task_manager.get_video_item(batch.id, item.id)
            if current_item and current_item.status == VideoItemStatus.CANCELLED:
                return

            # 更新状态为处理中，设置估算时间（默认60秒，可根据实际情况调整）
            await self.task_manager.update_video_item(
                batch_id=batch.id,
                item_id=item.id,
                status=VideoItemStatus.PROCESSING,
                estimated_duration=60,  # 默认估算60秒
            )
            
            # 加载图片数据
            image_data = await self.data_manager.load_bytes(item.source_image_filename, "images")
            
            # 创建临时文件用于 API 调用
            import tempfile
            import os
            
            # 确保文件扩展名正确
            img_ext = os.path.splitext(item.source_image_filename)[1] or ".png"
            audio_ext = os.path.splitext(batch.audio_filename)[1] or ".wav"
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=img_ext) as img_file:
                img_file.write(image_data)
                img_path = img_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=audio_ext) as audio_file:
                audio_file.write(audio_data)
                audio_path = audio_file.name
            
            try:
                # 提交任务到 S2V API
                submit_result = await self.client.submit_task(
                    task="s2v",
                    model_cls="SekoTalk",
                    stage="single_stage",
                    prompt=batch.prompt or "根据音频生成对应视频",
                    negative_prompt="色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
                    cfg_scale=5,
                    duration=7,
                    input_image_path=img_path,
                    input_audio_path=audio_path,
                )
                
                if not submit_result.get("success"):
                    error_msg = submit_result.get("error", "Unknown error")
                    logger.error(f"Failed to submit task for item {item.id}: {error_msg}")
                    await self.task_manager.update_video_item(
                        batch_id=batch.id,
                        item_id=item.id,
                        status=VideoItemStatus.FAILED,
                        error_msg=error_msg,
                    )
                    return
                
                api_task_id = submit_result["task_id"]
                await self.task_manager.update_video_item(
                    batch_id=batch.id,
                    item_id=item.id,
                    api_task_id=api_task_id,
                )
                
                # 等待任务完成
                final_result = await self.client.wait_for_task(
                    api_task_id,
                    poll_interval=5,
                    timeout=3600,
                )

                current_item = self.task_manager.get_video_item(batch.id, item.id)
                if current_item and current_item.status == VideoItemStatus.CANCELLED:
                    return
                
                if not final_result.get("success"):
                    error_msg = final_result.get("error", "Unknown error")
                    logger.error(f"Task failed for item {item.id}: {error_msg}")
                    await self.task_manager.update_video_item(
                        batch_id=batch.id,
                        item_id=item.id,
                        status=VideoItemStatus.FAILED,
                        error_msg=error_msg,
                    )
                    return
                
                status = final_result.get("status", "UNKNOWN")
                if status == "SUCCEED":
                    # 获取结果 URL
                    result_url = await self.client.get_result_url(api_task_id, name="output_video")
                    
                    if result_url:
                        # 保存视频 URL
                        await self.task_manager.update_video_item(
                            batch_id=batch.id,
                            item_id=item.id,
                            status=VideoItemStatus.COMPLETED,
                            video_url=result_url,
                        )
                        logger.info(f"Item {item.id} completed, video URL: {result_url}")
                    else:
                        logger.warning(f"Item {item.id} succeeded but no result URL")
                        await self.task_manager.update_video_item(
                            batch_id=batch.id,
                            item_id=item.id,
                            status=VideoItemStatus.FAILED,
                            error_msg="No result URL returned",
                        )
                else:
                    error_msg = f"Task status: {status}"
                    logger.error(f"Task failed for item {item.id}: {error_msg}")
                    await self.task_manager.update_video_item(
                        batch_id=batch.id,
                        item_id=item.id,
                        status=VideoItemStatus.FAILED,
                        error_msg=error_msg,
                    )
            
            finally:
                # 清理临时文件
                try:
                    if os.path.exists(img_path):
                        os.unlink(img_path)
                    if os.path.exists(audio_path):
                        os.unlink(audio_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp files: {e}")
        
        except Exception as e:
            logger.exception(f"Error processing item {item.id}: {e}")
            await self.task_manager.update_video_item(
                batch_id=batch.id,
                item_id=item.id,
                status=VideoItemStatus.FAILED,
                error_msg=str(e),
            )

    async def cancel_item(self, batch_id: str, item_id: str) -> bool:
        """取消单个子任务"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return False

        item = self.task_manager.get_video_item(batch_id, item_id)
        if not item:
            return False

        if item.status in [VideoItemStatus.COMPLETED, VideoItemStatus.FAILED, VideoItemStatus.CANCELLED]:
            return False

        if item.api_task_id:
            await self.client.cancel_task(item.api_task_id)

        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.CANCELLED,
            error_msg="Cancelled by user",
        )
        await self._charge_completed_batch(batch_id)
        return True

    async def resume_item(self, batch_id: str, item_id: str) -> bool:
        """重试单个失败子任务"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return False

        item = self.task_manager.get_video_item(batch_id, item_id)
        if not item or item.status != VideoItemStatus.FAILED:
            return False

        if not item.api_task_id:
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg="Missing task id for resume",
            )
            await self._charge_completed_batch(batch_id)
            return False

        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.PROCESSING,
            error_msg=None,
            estimated_duration=60,
        )

        success, resume_error = await self.client.resume_task(item.api_task_id)
        if not success:
            error_msg = resume_error or "Resume failed"
            logger.warning(f"Resume task failed for item {item_id}: {error_msg}")
            # 后端任务可能已成功（例如取消未生效、任务在后台跑完），尝试同步结果
            if resume_error and "Succeed task cannot be resumed" in (resume_error or ""):
                task_info = await self.client.query_task(item.api_task_id)
                st = task_info.get("status")
                is_succeed = st == "SUCCEED" or st == 4
                if task_info.get("success") and is_succeed:
                    result_url = await self.client.get_result_url(item.api_task_id, name="output_video")
                    if result_url:
                        logger.info(f"Task {item.api_task_id} already succeeded, syncing result for item {item_id}")
                        await self.task_manager.update_video_item(
                            batch_id=batch_id,
                            item_id=item_id,
                            status=VideoItemStatus.COMPLETED,
                            video_url=result_url,
                        )
                        await self._charge_completed_batch(batch_id)
                        return True
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg=error_msg,
            )
            await self._charge_completed_batch(batch_id)
            return False

        final_result = await self.client.wait_for_task(
            item.api_task_id,
            poll_interval=5,
            timeout=3600,
        )

        current_item = self.task_manager.get_video_item(batch_id, item_id)
        if current_item and current_item.status == VideoItemStatus.CANCELLED:
            return True

        if not final_result.get("success"):
            error_msg = final_result.get("error", "Unknown error")
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg=error_msg,
            )
            return False

        status = final_result.get("status", "UNKNOWN")
        if status == "SUCCEED":
            result_url = await self.client.get_result_url(item.api_task_id, name="output_video")
            if result_url:
                await self.task_manager.update_video_item(
                    batch_id=batch_id,
                    item_id=item_id,
                    status=VideoItemStatus.COMPLETED,
                    video_url=result_url,
                )
                await self._charge_completed_batch(batch_id)
                return True
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg="No result URL returned",
            )
            await self._charge_completed_batch(batch_id)
            return False

        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.FAILED,
            error_msg=f"Task status: {status}",
        )
        await self._charge_completed_batch(batch_id)
        return False

    async def reprocess_item(self, batch_id: str, item_id: str) -> bool:
        """重新处理已取消的子任务（置为 PENDING 后重新走一遍流程）"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return False

        item = self.task_manager.get_video_item(batch_id, item_id)
        if not item or item.status != VideoItemStatus.CANCELLED:
            return False

        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.PENDING,
            error_msg=None,
        )
        audio_data = await self.data_manager.load_bytes(batch.audio_filename, "audios")
        batch = self.task_manager.get_batch(batch_id)
        item = self.task_manager.get_video_item(batch_id, item_id) if batch else None
        if not batch or not item:
            return False
        await self._process_video_item(batch, item, audio_data)
        await self._charge_completed_batch(batch_id)
        return True

    async def resume_failed_items(self, batch_id: str) -> int:
        """批量重试失败或已取消的子任务：失败走 resume，已取消走 reprocess"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return 0

        failed_items = [item for item in batch.items if item.status == VideoItemStatus.FAILED]
        cancelled_items = [item for item in batch.items if item.status == VideoItemStatus.CANCELLED]
        to_retry = failed_items + cancelled_items
        if not to_retry:
            return 0

        semaphore = asyncio.Semaphore(3)

        async def do_retry(item):
            async with semaphore:
                if item.status == VideoItemStatus.FAILED:
                    await self.resume_item(batch_id, item.id)
                else:
                    await self.reprocess_item(batch_id, item.id)

        await asyncio.gather(*[do_retry(item) for item in to_retry])
        return len(to_retry)

    async def _charge_completed_batch(self, batch_id: str):
        """按已完成任务数扣除积分（支持首次完成与重试成功后增量扣费，规则与正常任务一致）"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return

        credits_per_video = getattr(batch, "credits_per_video", 0)
        if credits_per_video <= 0:
            return

        completed_count = sum(1 for item in batch.items if item.status == VideoItemStatus.COMPLETED)
        # 已扣费对应的完成数（向下取整，与扣费规则一致）
        already_charged_count = batch.credits_used // credits_per_video
        delta = completed_count - already_charged_count

        if delta <= 0:
            if batch.status == BatchStatus.COMPLETED:
                batch.credits_charged = True
                batch.updated_at = datetime.now()
                await self.task_manager._save_batch(batch)
            return

        credits_to_charge = credits_per_video * delta
        if not await self.auth_manager.deduct_credits(batch.user_id, credits_to_charge):
            logger.warning(
                f"Failed to deduct {credits_to_charge} credits for user {batch.user_id} on batch {batch_id}"
            )
            return

        batch.credits_used = batch.credits_used + credits_to_charge
        batch.updated_at = datetime.now()
        if batch.status == BatchStatus.COMPLETED:
            batch.credits_charged = True
        await self.task_manager._save_batch(batch)
