# -*- coding: utf-8 -*-

import requests
import json
import base64
import os
import argparse
import sys
from loguru import logger
import asyncio
import time
from typing import Optional, Dict, Any, List, Union, Tuple


class LightX2VClient:
    """
    LightX2V 服务客户端
    
    支持多种任务类型：
    - s2v (speech-to-video): 图片 + 音频 + 提示词
    - i2v (image-to-video): 图片 + 提示词
    - t2v (text-to-video): 提示词
    - i2i (image-to-image): 图片(可多图) + 提示词
    - t2i (text-to-image): 提示词
    - flf2v (first-last-frame-to-video): 首帧图片 + 尾帧图片
    - animate: 图片 + 视频
    """
    
    def __init__(self, base_url: str = None, access_token: str = None):
        """
        初始化客户端
        
        Args:
            base_url: 服务基础URL，默认从环境变量 LIGHTX2V_BASE_URL 获取
            access_token: 访问令牌，默认从环境变量 LIGHTX2V_ACCESS_TOKEN 获取
        """
        self.base_url = base_url or os.getenv("LIGHTX2V_BASE_URL", "http://localhost:8080")
        self.access_token = access_token or os.getenv("LIGHTX2V_ACCESS_TOKEN", "")
        self.session = requests.Session()

        self.session.headers.update({
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        })
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}"
            })

        print(self.session.headers)
    
    async def check_response(self, response, prefix):
        """检查响应状态"""
        logger.info(f"{prefix}: status_code: {response.status_code}")
        if response.status_code not in [200, 201]:
            try:
                error_data = response.json()
                logger.warning(f"{prefix}: HTTP error response: {response.status_code}, {error_data}")
            except:
                logger.warning(f"{prefix}: HTTP error response: {response.status_code}, {response.text}")
            return False
        return True
    
    def _encode_image(self, image_path: str) -> Dict[str, str]:
        """
        将图片文件编码为 base64
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            包含 type 和 data 的字典
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        return {
            "type": "base64",
            "data": image_data
        }
    
    def _encode_audio(self, audio_path: str) -> Dict[str, str]:
        """
        将音频文件编码为 base64
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            包含 type 和 data 的字典
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        with open(audio_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode('utf-8')
        
        return {
            "type": "base64",
            "data": audio_data
        }
    
    def _encode_video(self, video_path: str) -> Dict[str, str]:
        """
        将视频文件编码为 base64
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            包含 type 和 data 的字典
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        with open(video_path, "rb") as f:
            video_data = base64.b64encode(f.read()).decode('utf-8')
        
        return {
            "type": "base64",
            "data": video_data
        }
    
    def _encode_images(self, image_paths: List[str]) -> Dict[str, Any]:
        """
        将多张图片编码为目录格式（用于 i2i 任务）
        
        Args:
            image_paths: 图片文件路径列表
            
        Returns:
            包含 type 和 data 的字典（目录格式）
        """
        if not image_paths:
            raise ValueError("Image paths list is empty")
        
        data = {}
        for image_path in image_paths:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            filename = os.path.basename(image_path)
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            data[filename] = image_data
        
        return {
            "type": "directory",
            "data": data
        }
    
    async def submit_task(
        self,
        task: str = "s2v",
        model_cls: str = "SekoTalk",
        stage: str = "single_stage",
        prompt: str = "",
        seed: Optional[int] = None,
        # 图片输入（单图或多图）
        input_image: Optional[Dict[str, Any]] = None,
        input_image_path: Optional[Union[str, List[str]]] = None,
        # 音频输入
        input_audio: Optional[Dict[str, str]] = None,
        input_audio_path: Optional[str] = None,
        # 视频输入
        input_video: Optional[Dict[str, str]] = None,
        input_video_path: Optional[str] = None,
        # 尾帧图片（用于 flf2v）
        last_frame: Optional[Dict[str, str]] = None,
        last_frame_path: Optional[str] = None,
        # 尺寸和宽高比参数
        custom_shape: Optional[List[int]] = None,  # [height, width]
        aspect_ratio: Optional[str] = None,  # 宽高比，如 "16:9", "9:16", "1:1"
        # 其他参数
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        提交任务到 LightX2V 服务
        
        支持的任务类型：
        - s2v: 需要 input_image, input_audio, prompt
        - i2v: 需要 input_image, prompt
        - t2v: 需要 prompt
        - i2i: 需要 input_image (可多图), prompt
        - t2i: 需要 prompt
        - flf2v: 需要 input_image (首帧), last_frame (尾帧)
        - animate: 需要 input_image, input_video
        
        Args:
            task: 任务类型 (s2v, i2v, t2v, i2i, t2i, flf2v, animate)
            model_cls: 模型类别，默认 "SekoTalk"
            stage: 处理阶段，默认 "single_stage"
            prompt: 提示文本（某些任务类型不需要，如 flf2v, animate）
            seed: 随机种子
            input_image: 输入图片（base64编码的字典或目录格式）
            input_image_path: 输入图片文件路径（单图字符串或多图列表）
            input_audio: 输入音频（base64编码的字典）
            input_audio_path: 输入音频文件路径
            input_video: 输入视频（base64编码的字典）
            input_video_path: 输入视频文件路径
            last_frame: 尾帧图片（base64编码的字典，用于 flf2v）
            last_frame_path: 尾帧图片文件路径（用于 flf2v）
            custom_shape: 自定义尺寸，格式为 [height, width]，例如 [720, 1280]
            aspect_ratio: 宽高比，例如 "16:9", "9:16", "1:1", "4:3" 等
            negative_prompt: 负面提示文本
            **kwargs: 其他参数（如 cfg_scale, steps, guidance_scale, num_inference_steps 等，取决于具体模型）
            
        Returns:
            包含 task_id, workers, params, wait_time 的字典
            
        Note:
            - custom_shape 和 aspect_ratio 可以同时使用，但 custom_shape 优先级更高
            - custom_shape 格式为 [height, width]，例如 [720, 1280] 表示高度720，宽度1280
            - 对于 t2v 任务，custom_shape 需要在合理范围内（256-1280）
        """
        # 验证任务类型
        valid_tasks = ["s2v", "i2v", "t2v", "i2i", "t2i", "flf2v", "animate"]
        if task not in valid_tasks:
            raise ValueError(f"Invalid task type: {task}. Valid types: {valid_tasks}")
        
        # 构建请求参数
        params = {
            "task": task,
            "model_cls": model_cls,
            "stage": stage
        }
        
        # 根据任务类型验证必需参数
        if task == "t2v" or task == "t2i":
            # t2v 和 t2i 只需要 prompt
            if not prompt:
                raise ValueError(f"{task} task requires prompt")
            params["prompt"] = prompt
        elif task == "flf2v":
            # flf2v 不需要 prompt，需要首帧和尾帧
            if not input_image_path and not input_image:
                raise ValueError("flf2v task requires input_image (first frame)")
            if not last_frame_path and not last_frame:
                raise ValueError("flf2v task requires last_frame (last frame)")
            # prompt 可选
            if prompt:
                params["prompt"] = prompt
        elif task == "animate":
            # animate 不需要 prompt，需要图片和视频
            if not input_image_path and not input_image:
                raise ValueError("animate task requires input_image")
            if not input_video_path and not input_video:
                raise ValueError("animate task requires input_video")
            # prompt 可选，默认使用 "视频中的人在做动作"
            params["prompt"] = prompt if prompt else "视频中的人在做动作"
        else:
            # s2v, i2v, i2i 需要 prompt
            if not prompt:
                raise ValueError(f"{task} task requires prompt")
            params["prompt"] = prompt
        
        # 处理输入图片
        if input_image_path:
            if isinstance(input_image_path, list):
                # 多图模式（用于 i2i）
                if task != "i2i":
                    raise ValueError("Multiple images only supported for i2i task")
                params["input_image"] = self._encode_images(input_image_path)
            else:
                # 单图模式
                params["input_image"] = self._encode_image(input_image_path)
        elif input_image:
            params["input_image"] = input_image
        
        # 处理输入音频（s2v 需要）
        if input_audio_path:
            params["input_audio"] = self._encode_audio(input_audio_path)
        elif input_audio:
            params["input_audio"] = input_audio
        
        # 处理输入视频（animate 需要）
        if input_video_path:
            params["input_video"] = self._encode_video(input_video_path)
        elif input_video:
            params["input_video"] = input_video
        
        # 处理尾帧图片（flf2v 需要）
        if last_frame_path:
            params["last_frame"] = self._encode_image(last_frame_path)
        elif last_frame:
            params["last_frame"] = last_frame
        
        # 添加可选参数
        if seed is not None:
            params["seed"] = seed
        if negative_prompt:
            params["negative_prompt"] = negative_prompt
        
        # 添加尺寸和宽高比参数
        if custom_shape is not None:
            if not isinstance(custom_shape, list) or len(custom_shape) != 2:
                raise ValueError("custom_shape must be a list of 2 integers [height, width]")
            params["custom_shape"] = custom_shape
        
        if aspect_ratio is not None:
            params["aspect_ratio"] = aspect_ratio
        
        # 添加其他参数（如 cfg_scale, steps, guidance_scale 等）
        params.update(kwargs)
        
        # 发送请求
        url = f"{self.base_url}/api/v1/task/submit"
        logger.info(f"Submitting task to: {url}")
        logger.info(f"Task params: task={task}, model_cls={model_cls}, stage={stage}")
        
        try:
            payload = json.dumps(params, ensure_ascii=False).encode("utf-8")
            response = self.session.post(url, data=payload)
            
            if not await self.check_response(response, "LightX2VClient submit_task"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            logger.info(f"Task submitted successfully: task_id={result.get('task_id')}, task={task}")
            return {"success": True, **result}
            
        except Exception as e:
            logger.error(f"LightX2VClient submit_task failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def query_task(self, task_id: str) -> Dict[str, Any]:
        """
        查询任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务信息字典
        """
        url = f"{self.base_url}/api/v1/task/query"
        params = {"task_id": task_id}
        
        logger.info(f"Querying task: {task_id}")
        
        try:
            response = self.session.get(url, params=params)
            
            if not await self.check_response(response, "LightX2VClient query_task"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            return {"success": True, **result}
            
        except Exception as e:
            logger.error(f"LightX2VClient query_task failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def wait_for_task(
        self,
        task_id: str,
        poll_interval: int = 5,
        timeout: int = 3600,
        check_status: bool = True
    ) -> Dict[str, Any]:
        """
        等待任务完成
        
        Args:
            task_id: 任务ID
            poll_interval: 轮询间隔（秒）
            timeout: 超时时间（秒）
            check_status: 是否检查任务状态
            
        Returns:
            最终任务信息
        """
        start_time = time.time()
        logger.info(f"Waiting for task {task_id} to complete...")
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Task {task_id} timeout after {timeout}s")
                return {"success": False, "error": "Timeout", "task_id": task_id}
            
            result = await self.query_task(task_id)
            if not result.get("success"):
                return result
            
            task = result
            status = task.get("status", "UNKNOWN")
            logger.info(f"Task {task_id} status: {status} (elapsed: {elapsed:.1f}s)")
            
            if check_status:
                if status in ["SUCCEED", "FAILED", "CANCELLED"]:
                    logger.info(f"Task {task_id} finished with status: {status}")
                    return {"success": True, **task}
            
            await asyncio.sleep(poll_interval)
    
    async def get_result_url(self, task_id: str, name: str = None) -> Optional[str]:
        """
        获取任务结果URL
        
        Args:
            task_id: 任务ID
            name: 输出名称
                - 视频任务 (s2v, i2v, t2v, flf2v, animate): 默认 "output_video"
                - 图片任务 (i2i, t2i): 默认 "output_image"
            
        Returns:
            结果文件URL
        """
        if name is None:
            # 根据任务类型自动选择默认输出名称
            task_info = await self.query_task(task_id)
            if task_info.get("success"):
                task_type = task_info.get("task_type", "")
                if task_type in ["i2i", "t2i"]:
                    name = "output_image"
                else:
                    name = "output_video"
            else:
                name = "output_video"  # 默认值
        
        url = f"{self.base_url}/api/v1/task/result_url"
        params = {"task_id": task_id, "name": name}
        
        logger.info(f"Getting result URL for task {task_id}, output: {name}")
        
        try:
            response = self.session.get(url, params=params)
            
            if not await self.check_response(response, "LightX2VClient get_result_url"):
                return None
            
            result = response.json()
            return result.get("url")
            
        except Exception as e:
            logger.error(f"LightX2VClient get_result_url failed: {e}")
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功
        """
        url = f"{self.base_url}/api/v1/task/cancel"
        params = {"task_id": task_id}
        
        logger.info(f"Cancelling task: {task_id}")
        
        try:
            # LightX2V 服务端 cancel 接口是 GET，不是 POST
            response = self.session.get(url, params=params)
            
            if not await self.check_response(response, "LightX2VClient cancel_task"):
                return False
            
            result = response.json()
            return result.get("msg") == "Task cancelled successfully"
            
        except Exception as e:
            logger.error(f"LightX2VClient cancel_task failed: {e}")
            return False

    async def resume_task(self, task_id: str) -> Tuple[bool, Optional[str]]:
        """
        恢复/重试任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            (是否成功, 失败时的错误信息)
        """
        url = f"{self.base_url}/api/v1/task/resume"
        params = {"task_id": task_id}
        
        logger.info(f"Resuming task: {task_id}")
        
        try:
            response = self.session.get(url, params=params)
            try:
                result = response.json()
            except Exception:
                result = {}

            if response.status_code not in [200, 201]:
                err_msg = result.get("detail") or result.get("error") or result.get("msg") or response.text or f"HTTP {response.status_code}"
                logger.warning(f"LightX2VClient resume_task: HTTP {response.status_code}, {err_msg}")
                return (False, err_msg)

            if result.get("msg") == "ok":
                return (True, None)
            err_msg = result.get("detail") or result.get("error") or result.get("msg") or str(result)
            logger.warning(f"LightX2VClient resume_task: API returned not ok: {err_msg}")
            return (False, err_msg)

        except Exception as e:
            err_msg = str(e)
            logger.error(f"LightX2VClient resume_task failed: {e}")
            return (False, err_msg)
    
    def close(self):
        """关闭会话"""
        self.session.close()


async def test(args):
    """
    测试函数
    
    Args:
        args: 命令行参数列表
    """
    parser = argparse.ArgumentParser(description="LightX2V Client Test")
    parser.add_argument("--base_url", type=str, default=None, help="Service base URL")
    parser.add_argument("--token", type=str, default=None, help="Access token")
    parser.add_argument("--task", type=str, default="s2v", 
                       choices=["s2v", "i2v", "t2v", "i2i", "t2i", "flf2v", "animate"],
                       help="Task type")
    parser.add_argument("--model", type=str, default="SekoTalk", help="Model class")
    parser.add_argument("--stage", type=str, default="single_stage", help="Stage")
    parser.add_argument("--prompt", type=str, default="", help="Prompt text")
    parser.add_argument("--image", type=str, nargs="+", default=None, 
                       help="Input image path(s) - single or multiple for i2i")
    parser.add_argument("--audio", type=str, default=None, help="Input audio path (for s2v)")
    parser.add_argument("--video", type=str, default=None, help="Input video path (for animate)")
    parser.add_argument("--last_frame", type=str, default=None, 
                       help="Last frame image path (for flf2v)")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--custom_shape", type=str, default=None,
                       help="Custom shape as 'height,width' (e.g., '720,1280')")
    parser.add_argument("--aspect_ratio", type=str, default=None,
                       help="Aspect ratio (e.g., '16:9', '9:16', '1:1')")
    parser.add_argument("--negative_prompt", type=str, default=None,
                       help="Negative prompt text")
    parser.add_argument("--wait", action="store_true", help="Wait for task completion")
    parser.add_argument("--poll_interval", type=int, default=5, help="Poll interval in seconds")
    parser.add_argument("--timeout", type=int, default=3600, help="Timeout in seconds")
    
    parsed_args = parser.parse_args(args) if args else parser.parse_args()
    
    client = LightX2VClient(
        base_url=parsed_args.base_url,
        access_token=parsed_args.token
    )
    
    try:
        # 构建提交参数
        submit_kwargs = {
            "task": parsed_args.task,
            "model_cls": parsed_args.model,
            "stage": parsed_args.stage,
            "prompt": parsed_args.prompt,
        }
        
        if parsed_args.seed is not None:
            submit_kwargs["seed"] = parsed_args.seed
        
        if parsed_args.custom_shape:
            try:
                # 解析 "height,width" 格式
                shape_parts = parsed_args.custom_shape.split(",")
                if len(shape_parts) == 2:
                    submit_kwargs["custom_shape"] = [int(shape_parts[0].strip()), int(shape_parts[1].strip())]
                else:
                    raise ValueError("custom_shape must be in format 'height,width'")
            except ValueError as e:
                logger.error(f"Invalid custom_shape format: {e}")
                return
        
        if parsed_args.aspect_ratio:
            submit_kwargs["aspect_ratio"] = parsed_args.aspect_ratio
        
        if parsed_args.negative_prompt:
            submit_kwargs["negative_prompt"] = parsed_args.negative_prompt
        
        if parsed_args.image:
            if len(parsed_args.image) == 1:
                submit_kwargs["input_image_path"] = parsed_args.image[0]
            else:
                submit_kwargs["input_image_path"] = parsed_args.image
        
        if parsed_args.audio:
            submit_kwargs["input_audio_path"] = parsed_args.audio
        
        if parsed_args.video:
            submit_kwargs["input_video_path"] = parsed_args.video
        
        if parsed_args.last_frame:
            submit_kwargs["last_frame_path"] = parsed_args.last_frame
        
        # 提交任务
        result = await client.submit_task(**submit_kwargs)
        
        if not result.get("success"):
            logger.error(f"Task submission failed: {result.get('error')}")
            return
        
        task_id = result.get("task_id")
        logger.info(f"Task submitted successfully: task_id={task_id}, task={parsed_args.task}")
        
        # 如果需要等待完成
        if parsed_args.wait:
            final_result = await client.wait_for_task(
                task_id,
                poll_interval=parsed_args.poll_interval,
                timeout=parsed_args.timeout
            )
            
            if final_result.get("success"):
                status = final_result.get("status")
                logger.info(f"Task completed with status: {status}")
                
                if status == "SUCCEED":
                    result_url = await client.get_result_url(task_id)
                    if result_url:
                        logger.info(f"Result URL: {result_url}")
            else:
                logger.error(f"Task failed: {final_result.get('error')}")
        else:
            logger.info(f"Task ID: {task_id}, use --wait to monitor completion")
    
    finally:
        client.close()


# 为了向后兼容，保留 S2VClient 作为别名
S2VClient = LightX2VClient


if __name__ == "__main__":
    asyncio.run(test(sys.argv[1:]))



