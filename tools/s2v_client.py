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
from typing import Optional, Dict, Any


class S2VClient:
    """
    LightX2V 服务客户端
    
    用于调用 s2v (speech-to-video) 服务的工具类
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

        # 设置默认请求头
        self.session.headers.update({
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        })
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}"
            })
    
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
    
    async def submit_task(
        self,
        task: str = "s2v",
        model_cls: str = "SekoTalk",
        stage: str = "single_stage",
        prompt: str = "",
        seed: Optional[int] = None,
        input_image: Optional[Dict[str, str]] = None,
        input_audio: Optional[Dict[str, str]] = None,
        input_image_path: Optional[str] = None,
        input_audio_path: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        提交任务到 s2v 服务
        
        Args:
            task: 任务类型，默认 "s2v"
            model_cls: 模型类别，默认 "SekoTalk"
            stage: 处理阶段，默认 "single_stage"
            prompt: 提示文本
            seed: 随机种子
            input_image: 输入图片（base64编码的字典，格式: {"type": "base64", "data": "..."}）
            input_audio: 输入音频（base64编码的字典，格式: {"type": "base64", "data": "..."}）
            input_image_path: 输入图片文件路径（如果提供，会自动编码）
            input_audio_path: 输入音频文件路径（如果提供，会自动编码）
            negative_prompt: 负面提示文本
            **kwargs: 其他参数（如 cfg_scale, steps 等）
            
        Returns:
            包含 task_id, workers, params, wait_time 的字典
        """
        # 构建请求参数
        params = {
            "task": task,
            "model_cls": model_cls,
            "stage": stage,
            "prompt": prompt
        }
        
        # 添加可选参数
        if seed is not None:
            params["seed"] = seed
        if negative_prompt:
            params["negative_prompt"] = negative_prompt
        
        # 处理输入图片
        if input_image_path:
            params["input_image"] = self._encode_image(input_image_path)
        elif input_image:
            params["input_image"] = input_image
        
        # 处理输入音频
        if input_audio_path:
            params["input_audio"] = self._encode_audio(input_audio_path)
        elif input_audio:
            params["input_audio"] = input_audio
        
        # 添加其他参数
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
            logger.info(f"Task submitted successfully: task_id={result.get('task_id')}")
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
    
    async def get_result_url(self, task_id: str, name: str = "output_video") -> str:
        """
        获取任务结果URL
        
        Args:
            task_id: 任务ID
            name: 输出名称，默认 "output_video"
            
        Returns:
            结果文件URL
        """
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
            response = self.session.post(url, params=params)
            
            if not await self.check_response(response, "LightX2VClient cancel_task"):
                return False
            
            result = response.json()
            return result.get("msg") == "Task cancelled successfully"
            
        except Exception as e:
            logger.error(f"LightX2VClient cancel_task failed: {e}")
            return False
    
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
    parser.add_argument("--task", type=str, default="s2v", help="Task type")
    parser.add_argument("--model", type=str, default="SekoTalk", help="Model class")
    parser.add_argument("--stage", type=str, default="single_stage", help="Stage")
    parser.add_argument("--prompt", type=str, required=True, help="Prompt text")
    parser.add_argument("--image", type=str, required=True, help="Input image path")
    parser.add_argument("--audio", type=str, required=True, help="Input audio path")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("--wait", action="store_true", help="Wait for task completion")
    parser.add_argument("--poll_interval", type=int, default=5, help="Poll interval in seconds")
    parser.add_argument("--timeout", type=int, default=3600, help="Timeout in seconds")
    
    parsed_args = parser.parse_args(args) if args else parser.parse_args()
    
    client = S2VClient(
        base_url=parsed_args.base_url,
        access_token=parsed_args.token
    )
    
    try:
        # 提交任务
        result = await client.submit_task(
            task=parsed_args.task,
            model_cls=parsed_args.model,
            stage=parsed_args.stage,
            prompt=parsed_args.prompt,
            seed=parsed_args.seed,
            input_image_path=parsed_args.image,
            input_audio_path=parsed_args.audio
        )
        
        if not result.get("success"):
            logger.error(f"Task submission failed: {result.get('error')}")
            return
        
        task_id = result.get("task_id")
        logger.info(f"Task submitted successfully: {task_id}")
        
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


if __name__ == "__main__":
    asyncio.run(test(sys.argv[1:]))



