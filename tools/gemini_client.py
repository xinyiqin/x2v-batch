# -*- coding: utf-8 -*-
"""
Google Gemini 3 Pro 客户端工具

用于调用 Google Gemini 3 Pro API 的工具类
支持文本、图片等多模态输入
"""

import os
import json
import base64
import asyncio
import argparse
import sys
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from loguru import logger

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai is not installed. Install it with: pip install google-generativeai")


class GeminiClient:
    """
    Google Gemini 3 Pro 客户端
    
    用于调用 Gemini 3 Pro API 的工具类
    """
    
    def __init__(self, api_key: str = None, model_name: str = "gemini-3.0-pro"):
        """
        初始化客户端
        
        Args:
            api_key: Google API Key，默认从环境变量 GEMINI_API_KEY 获取
            model_name: 模型名称，默认为 "gemini-3.0-pro"
                       可选值: "gemini-3.0-pro", "gemini-2.0-pro", "gemini-1.5-pro" 等
        """
        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai is required for Gemini support. "
                "Install it with: pip install google-generativeai"
            )
        
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. "
                "Set it as environment variable or pass it to __init__"
            )
        
        self.model_name = model_name
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
        
        logger.info(f"GeminiClient initialized with model: {self.model_name}")
    
    def _encode_image(self, image_path: str) -> Dict[str, Any]:
        """
        编码图片为 base64
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            包含图片数据的字典
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # 读取图片文件
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # 获取文件扩展名
        ext = image_path.suffix.lower()
        mime_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_type_map.get(ext, "image/jpeg")
        
        return {
            "mime_type": mime_type,
            "data": image_data
        }
    
    def _prepare_content(
        self, 
        text: str = None, 
        images: List[str] = None
    ) -> List[Union[str, Dict[str, Any]]]:
        """
        准备消息内容（支持文本和图片）
        
        Args:
            text: 文本内容
            images: 图片文件路径列表
            
        Returns:
            内容列表
        """
        content = []
        
        # 添加图片
        if images:
            for image_path in images:
                image_data = self._encode_image(image_path)
                content.append(image_data)
        
        # 添加文本
        if text:
            content.append(text)
        
        if not content:
            raise ValueError("At least one of text or images must be provided")
        
        return content
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        images: List[str] = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        top_p: float = None,
        top_k: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送聊天消息
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            images: 图片文件路径列表（可选）
            temperature: 温度参数，控制随机性 (0.0-1.0)
            max_tokens: 最大生成 token 数
            top_p: 核采样参数
            top_k: Top-K 采样参数
            **kwargs: 其他参数
            
        Returns:
            包含响应内容的字典
        """
        try:
            # 构建生成配置
            generation_config = {}
            if temperature is not None:
                generation_config["temperature"] = temperature
            if max_tokens is not None:
                generation_config["max_output_tokens"] = max_tokens
            if top_p is not None:
                generation_config["top_p"] = top_p
            if top_k is not None:
                generation_config["top_k"] = top_k
            
            # 处理消息历史
            # Gemini API 使用不同的消息格式
            # 如果只有一条用户消息且没有历史，直接生成
            if len(messages) == 1 and messages[0].get("role") == "user":
                # 单条消息，直接生成
                if images:
                    content = self._prepare_content(
                        text=messages[0].get("content", ""),
                        images=images
                    )
                else:
                    content = [messages[0].get("content", "")]
                
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    content,
                    generation_config=generation_config if generation_config else None,
                    **kwargs
                )
            else:
                # 多条消息，需要构建聊天历史
                chat_history = []
                
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        # 用户消息：只在第一条消息时包含图片
                        if images and len(chat_history) == 0:
                            user_content = self._prepare_content(
                                text=content,
                                images=images
                            )
                        else:
                            user_content = [content] if content else []
                        
                        if user_content:
                            chat_history.append({
                                "role": "user",
                                "parts": user_content
                            })
                    elif role == "assistant":
                        # 助手回复
                        if content:
                            chat_history.append({
                                "role": "model",
                                "parts": [content]
                            })
                
                # 使用聊天历史
                if len(chat_history) > 1:
                    # 有历史记录，使用 start_chat
                    chat = self.model.start_chat(history=chat_history[:-1])
                    last_message = chat_history[-1]
                    response = await asyncio.to_thread(
                        chat.send_message,
                        last_message["parts"],
                        generation_config=generation_config if generation_config else None,
                        **kwargs
                    )
                else:
                    # 只有一条消息，直接生成
                    content = chat_history[0]["parts"] if chat_history else []
                    response = await asyncio.to_thread(
                        self.model.generate_content,
                        content,
                        generation_config=generation_config if generation_config else None,
                        **kwargs
                    )
            
            # 提取响应文本
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            # 构建返回结果
            result = {
                "success": True,
                "content": response_text,
                "model": self.model_name,
                "usage": {}
            }
            
            # 尝试获取使用统计
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                result["usage"] = {
                    "prompt_tokens": getattr(usage, 'prompt_token_count', 0),
                    "completion_tokens": getattr(usage, 'completion_token_count', 0),
                    "total_tokens": getattr(usage, 'total_token_count', 0)
                }
            
            logger.info(f"Gemini chat completed: {len(response_text)} characters")
            return result
            
        except Exception as e:
            logger.error(f"Gemini chat failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "content": None
            }
    
    async def generate_text(
        self,
        prompt: str,
        images: List[str] = None,
        temperature: float = 0.7,
        max_tokens: int = None,
        **kwargs
    ) -> str:
        """
        生成文本（简化接口）
        
        Args:
            prompt: 提示词
            images: 图片文件路径列表（可选）
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            **kwargs: 其他参数
            
        Returns:
            生成的文本
        """
        messages = [{"role": "user", "content": prompt}]
        result = await self.chat(
            messages=messages,
            images=images,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        if result.get("success"):
            return result.get("content", "")
        else:
            raise Exception(f"Generation failed: {result.get('error')}")
    
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        images: List[str] = None,
        temperature: float = 0.7,
        **kwargs
    ):
        """
        流式聊天（生成器）
        
        Args:
            messages: 消息列表
            images: 图片文件路径列表（可选）
            temperature: 温度参数
            **kwargs: 其他参数
            
        Yields:
            文本块
        """
        try:
            # 准备内容
            if images and messages:
                content = self._prepare_content(
                    text=messages[-1].get("content", ""),
                    images=images
                )
            else:
                content = [messages[-1].get("content", "")] if messages else []
            
            # 生成配置
            generation_config = {"temperature": temperature} if temperature is not None else {}
            
            # 流式生成
            response = await asyncio.to_thread(
                self.model.generate_content,
                content,
                generation_config=generation_config,
                stream=True,
                **kwargs
            )
            
            for chunk in response:
                if hasattr(chunk, 'text'):
                    yield chunk.text
                else:
                    yield str(chunk)
                    
        except Exception as e:
            logger.error(f"Stream chat failed: {str(e)}")
            yield f"Error: {str(e)}"
    
    def list_models(self) -> List[str]:
        """
        列出可用的模型
        
        Returns:
            模型名称列表
        """
        try:
            models = genai.list_models()
            model_names = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            return model_names
        except Exception as e:
            logger.error(f"Failed to list models: {str(e)}")
            return []
    
    def close(self):
        """关闭客户端（清理资源）"""
        # Gemini 客户端不需要显式关闭
        pass


async def test(args):
    """测试函数"""
    parser = argparse.ArgumentParser(description="Test Gemini 3 Pro Client")
    parser.add_argument("--api_key", type=str, default=None, help="Gemini API Key")
    parser.add_argument("--model", type=str, default="gemini-3.0-pro", help="Model name")
    parser.add_argument("--prompt", type=str, default="Hello, how are you?", help="Prompt text")
    parser.add_argument("--images", type=str, nargs="+", default=None, help="Image file paths")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature")
    parser.add_argument("--max_tokens", type=int, default=None, help="Max tokens")
    parser.add_argument("--list_models", action="store_true", help="List available models")
    parser.add_argument("--stream", action="store_true", help="Use streaming mode")
    
    parsed_args = parser.parse_args(args)
    
    try:
        client = GeminiClient(api_key=parsed_args.api_key, model_name=parsed_args.model)
        
        if parsed_args.list_models:
            models = client.list_models()
            print("Available models:")
            for model in models:
                print(f"  - {model}")
            return
        
        if parsed_args.stream:
            print("Streaming response:")
            print("-" * 50)
            async for chunk in client.stream_chat(
                messages=[{"role": "user", "content": parsed_args.prompt}],
                images=parsed_args.images,
                temperature=parsed_args.temperature
            ):
                print(chunk, end="", flush=True)
            print("\n" + "-" * 50)
        else:
            result = await client.chat(
                messages=[{"role": "user", "content": parsed_args.prompt}],
                images=parsed_args.images,
                temperature=parsed_args.temperature,
                max_tokens=parsed_args.max_tokens
            )
            
            if result.get("success"):
                print("Response:")
                print("-" * 50)
                print(result.get("content", ""))
                print("-" * 50)
                if result.get("usage"):
                    print(f"Usage: {result['usage']}")
            else:
                print(f"Error: {result.get('error')}")
    
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test(sys.argv[1:]))

