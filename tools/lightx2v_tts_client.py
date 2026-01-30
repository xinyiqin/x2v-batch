# -*- coding: utf-8 -*-
"""
LightX2V TTS 客户端工具

用于调用 LightX2V 服务器的 TTS (文本转语音) 服务
"""

import os
import json
import requests
import argparse
import sys
import tempfile
from typing import Optional, Dict, Any
from loguru import logger
import asyncio
import aiohttp


class LightX2VTTSClient:
    """
    LightX2V TTS 客户端
    
    用于调用 LightX2V 服务器的 TTS 服务
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
        
        logger.info(f"LightX2VTTSClient initialized with base_url: {self.base_url}")
    
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
    
    async def generate(
        self,
        text: str,
        voice_type: str,
        context_texts: str = "",
        emotion: str = "",
        emotion_scale: int = 3,
        speech_rate: int = 0,
        pitch: int = 0,
        loudness_rate: int = 0,
        resource_id: str = "seed-tts-1.0",
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成 TTS 音频
        
        Args:
            text: 要转换的文本
            voice_type: 音色类型（必需）
            context_texts: 上下文文本，用于优化发音，默认 ""
            emotion: 情感类型，默认 ""
            emotion_scale: 情感强度 (1-5)，默认 3
            speech_rate: 语速 (-50~100，0为正常语速)，默认 0
            pitch: 音调 (-12~12，0为正常音调)，默认 0
            loudness_rate: 音量 (-50~100，0为正常音量)，默认 0
            resource_id: 资源ID，默认 "seed-tts-1.0"
            save_path: 保存音频文件的路径，如果为 None 则不保存，默认 None
            
        Returns:
            包含 success, audio_path (如果 save_path 不为 None), audio_data (bytes) 的字典
        """
        url = f"{self.base_url}/api/v1/tts/generate"
        
        # 构建请求参数
        payload = {
            "text": text,
            "voice_type": voice_type,
            "context_texts": context_texts,
            "emotion": emotion,
            "emotion_scale": emotion_scale,
            "speech_rate": speech_rate,
            "pitch": pitch,
            "loudness_rate": loudness_rate,
            "resource_id": resource_id
        }
        
        logger.info(f"Generating TTS: text={text[:50]}..., voice_type={voice_type}")
        
        try:
            response = self.session.post(url, json=payload)
            
            if not await self.check_response(response, "LightX2VTTSClient generate"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            # 检查响应内容类型
            content_type = response.headers.get("Content-Type", "")
            if "audio" in content_type or "application/octet-stream" in content_type:
                # 返回的是音频文件
                audio_data = response.content
                
                result = {
                    "success": True,
                    "audio_data": audio_data,
                    "content_type": content_type,
                    "size": len(audio_data)
                }
                
                # 如果指定了保存路径，保存文件
                if save_path:
                    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(audio_data)
                    result["audio_path"] = save_path
                    logger.info(f"Audio saved to: {save_path}")
                
                return result
            else:
                # 返回的是 JSON 错误信息
                try:
                    error_data = response.json()
                    return {"success": False, "error": error_data.get("error", "Unknown error")}
                except:
                    return {"success": False, "error": response.text}
            
        except Exception as e:
            logger.error(f"LightX2VTTSClient generate failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_voice_list(self) -> Dict[str, Any]:
        """
        获取可用的音色列表
        
        Returns:
            包含音色列表的字典
        """
        url = f"{self.base_url}/api/v1/voices/list"
        
        logger.info("Fetching voice list")
        
        try:
            response = self.session.get(url)
            
            if not await self.check_response(response, "LightX2VTTSClient get_voice_list"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            return {"success": True, **result}
            
        except Exception as e:
            logger.error(f"LightX2VTTSClient get_voice_list failed: {e}")
            return {"success": False, "error": str(e)}
    
    def close(self):
        """关闭会话"""
        self.session.close()


async def test(args):
    """测试函数"""
    parser = argparse.ArgumentParser(description="LightX2V TTS Client Test")
    parser.add_argument("--base_url", type=str, default=None, help="Service base URL")
    parser.add_argument("--token", type=str, default=None, help="Access token")
    parser.add_argument("--text", type=str, required=True, help="Text to convert")
    parser.add_argument("--voice_type", type=str, required=True, help="Voice type")
    parser.add_argument("--context_texts", type=str, default="", help="Context texts")
    parser.add_argument("--emotion", type=str, default="", help="Emotion type")
    parser.add_argument("--emotion_scale", type=int, default=3, help="Emotion scale (1-5)")
    parser.add_argument("--speech_rate", type=int, default=0, help="Speech rate (-50~100)")
    parser.add_argument("--pitch", type=int, default=0, help="Pitch (-12~12)")
    parser.add_argument("--loudness_rate", type=int, default=0, help="Loudness rate (-50~100)")
    parser.add_argument("--resource_id", type=str, default="seed-tts-1.0", help="Resource ID")
    parser.add_argument("--output", type=str, default=None, help="Output audio file path")
    parser.add_argument("--list_voices", action="store_true", help="List available voices")
    
    parsed_args = parser.parse_args(args) if args else parser.parse_args()
    
    client = LightX2VTTSClient(
        base_url=parsed_args.base_url,
        access_token=parsed_args.token
    )
    
    try:
        if parsed_args.list_voices:
            # 列出音色
            result = await client.get_voice_list()
            if result.get("success"):
                voices = result.get("voices", [])
                print(f"Available voices ({len(voices)}):")
                for voice in voices[:20]:  # 显示前20个
                    print(f"  - {voice.get('name', 'N/A')} ({voice.get('voice_type', 'N/A')})")
            else:
                print(f"Failed to get voice list: {result.get('error')}")
        else:
            # 生成 TTS
            result = await client.generate(
                text=parsed_args.text,
                voice_type=parsed_args.voice_type,
                context_texts=parsed_args.context_texts,
                emotion=parsed_args.emotion,
                emotion_scale=parsed_args.emotion_scale,
                speech_rate=parsed_args.speech_rate,
                pitch=parsed_args.pitch,
                loudness_rate=parsed_args.loudness_rate,
                resource_id=parsed_args.resource_id,
                save_path=parsed_args.output
            )
            
            if result.get("success"):
                print(f"TTS generated successfully!")
                if result.get("audio_path"):
                    print(f"Audio saved to: {result['audio_path']}")
                print(f"Audio size: {result.get('size', 0) / 1024:.2f} KB")
            else:
                print(f"TTS generation failed: {result.get('error')}")
    
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test(sys.argv[1:]))



