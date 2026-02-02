"""
批次处理器 - 调用 LightX2V HTTP API（/api/v1/task/*），不存 CDN URL，按需用 result_url/input_url 取。
"""
import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from server import lightx2v_api
from server.task_manager import TaskManager, VideoItemStatus, BatchStatus


class BatchProcessor:
    """批次处理器（直接调 API，不用 S2VClient）"""

    def __init__(
        self,
        task_manager: TaskManager,
        data_manager: Any,
        auth_manager: Any,
        base_url: str,
        access_token: str,
    ):
        self.task_manager = task_manager
        self.data_manager = data_manager
        self.auth_manager = auth_manager
        self.base_url = base_url
        self.access_token = access_token

    def update_token(self, new_token: str):
        self.access_token = new_token
        logger.info("LightX2V API token updated")

    async def process_batch(self, batch_id: str):
        """只轮询每个 item 的 task 状态并更新，不取/不存 result_url。"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            logger.error(f"Batch {batch_id} not found")
            return

        logger.info(f"Processing batch {batch_id} (poll only), {len(batch.items)} items")
        batch.status = BatchStatus.PROCESSING

        semaphore = asyncio.Semaphore(3)

        async def poll_item(item):
            async with semaphore:
                await self._poll_video_item(batch_id, item)

        tasks = [poll_item(item) for item in batch.items if item.api_task_id]
        await asyncio.gather(*tasks)

        batch = self.task_manager.get_batch(batch_id)
        if batch:
            batch.update_status()
            await self.task_manager.save_batch_if_terminal(batch_id)
            await self._charge_completed_batch(batch.id)
        logger.info(f"Batch {batch_id} processing (poll) completed")

    async def _poll_video_item(self, batch_id: str, item: Any):
        """轮询单个任务的 query 直到终态，只更新 status，不存 result_url。"""
        if not item.api_task_id:
            return
        current = self.task_manager.get_video_item(batch_id, item.id)
        if current and current.status == VideoItemStatus.CANCELLED:
            return

        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item.id,
            status=VideoItemStatus.PROCESSING,
            estimated_duration=60,
            persist=False,
        )

        result = await lightx2v_api.wait_for_task(
            self.base_url,
            self.access_token,
            item.api_task_id,
            poll_interval=5,
            timeout=3600,
        )

        current = self.task_manager.get_video_item(batch_id, item.id)
        if current and current.status == VideoItemStatus.CANCELLED:
            return

        if not result.get("success"):
            err = result.get("error", "Unknown error")
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item.id,
                status=VideoItemStatus.FAILED,
                error_msg=err,
                persist=False,
            )
            await self.task_manager.save_batch_if_terminal(batch_id)
            return

        status = (result.get("status") or "UNKNOWN").upper()
        if status == "SUCCEED":
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item.id,
                status=VideoItemStatus.COMPLETED,
                error_msg=None,
                persist=False,
            )
            logger.info(f"Item {item.id} completed (use result_url API for URL)")
        elif status == "CANCELLED":
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item.id,
                status=VideoItemStatus.CANCELLED,
                error_msg="Cancelled",
                persist=False,
            )
        else:
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item.id,
                status=VideoItemStatus.FAILED,
                error_msg=f"Task status: {status}",
                persist=False,
            )
        await self.task_manager.save_batch_if_terminal(batch_id)

    async def cancel_item(self, batch_id: str, item_id: str) -> bool:
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return False
        item = self.task_manager.get_video_item(batch_id, item_id)
        if not item or item.status in (
            VideoItemStatus.COMPLETED,
            VideoItemStatus.FAILED,
            VideoItemStatus.CANCELLED,
        ):
            return False
        if item.api_task_id:
            await lightx2v_api.cancel_task(
                self.base_url,
                self.access_token,
                item.api_task_id,
            )
        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.CANCELLED,
            error_msg="Cancelled by user",
            persist=False,
        )
        await self.task_manager.save_batch_if_terminal(batch_id)
        await self._charge_completed_batch(batch_id)
        return True

    async def resume_item(self, batch_id: str, item_id: str) -> bool:
        """调用 LightX2V /api/v1/task/resume 重试失败任务，再轮询状态。"""
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
        ok, err = await lightx2v_api.resume_task(
            self.base_url,
            self.access_token,
            item.api_task_id,
        )
        if not ok:
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg=err or "Resume failed",
            )
            await self._charge_completed_batch(batch_id)
            return False

        result = await lightx2v_api.wait_for_task(
            self.base_url,
            self.access_token,
            item.api_task_id,
            poll_interval=5,
            timeout=3600,
        )
        current = self.task_manager.get_video_item(batch_id, item_id)
        if current and current.status == VideoItemStatus.CANCELLED:
            return True
        if not result.get("success"):
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg=result.get("error", "Unknown error"),
            )
            await self._charge_completed_batch(batch_id)
            return False
        status = (result.get("status") or "UNKNOWN").upper()
        if status == "SUCCEED":
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.COMPLETED,
                error_msg=None,
            )
            await self._charge_completed_batch(batch_id)
            return True
        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.FAILED,
            error_msg=f"Task status: {status}",
        )
        await self._charge_completed_batch(batch_id)
        return False

    async def reprocess_item(self, batch_id: str, item_id: str) -> bool:
        """已取消任务：直接调 LightX2V /api/v1/task/resume，与失败项重试一致。"""
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return False
        item = self.task_manager.get_video_item(batch_id, item_id)
        if not item or item.status != VideoItemStatus.CANCELLED:
            return False
        if not item.api_task_id:
            logger.warning("reprocess_item: no api_task_id for cancelled item")
            return False

        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.PROCESSING,
            error_msg=None,
            estimated_duration=60,
        )
        ok, err = await lightx2v_api.resume_task(
            self.base_url,
            self.access_token,
            item.api_task_id,
        )
        if not ok:
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.CANCELLED,
                error_msg=err or "Resume failed",
            )
            await self._charge_completed_batch(batch_id)
            return False

        result = await lightx2v_api.wait_for_task(
            self.base_url,
            self.access_token,
            item.api_task_id,
            poll_interval=5,
            timeout=3600,
        )
        current = self.task_manager.get_video_item(batch_id, item_id)
        if current and current.status == VideoItemStatus.CANCELLED:
            return True
        if not result.get("success"):
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.FAILED,
                error_msg=result.get("error", "Unknown error"),
            )
            await self._charge_completed_batch(batch_id)
            return False
        status = (result.get("status") or "UNKNOWN").upper()
        if status == "SUCCEED":
            await self.task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item_id,
                status=VideoItemStatus.COMPLETED,
                error_msg=None,
            )
            await self._charge_completed_batch(batch_id)
            return True
        await self.task_manager.update_video_item(
            batch_id=batch_id,
            item_id=item_id,
            status=VideoItemStatus.FAILED,
            error_msg=f"Task status: {status}",
        )
        await self._charge_completed_batch(batch_id)
        return False

    async def resume_failed_items(self, batch_id: str) -> int:
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return 0
        failed = [i for i in batch.items if i.status == VideoItemStatus.FAILED]
        cancelled = [i for i in batch.items if i.status == VideoItemStatus.CANCELLED]
        to_retry = failed + cancelled
        if not to_retry:
            return 0
        semaphore = asyncio.Semaphore(3)

        async def do_retry(it):
            async with semaphore:
                if it.status == VideoItemStatus.FAILED:
                    await self.resume_item(batch_id, it.id)
                else:
                    await self.reprocess_item(batch_id, it.id)

        await asyncio.gather(*[do_retry(it) for it in to_retry])
        return len(to_retry)

    async def _charge_completed_batch(self, batch_id: str):
        batch = self.task_manager.get_batch(batch_id)
        if not batch:
            return
        credits_per_video = getattr(batch, "credits_per_video", 0)
        if credits_per_video <= 0:
            return
        completed_count = sum(
            1 for item in batch.items if item.status == VideoItemStatus.COMPLETED
        )
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
