# -*- coding: utf-8 -*-
"""
LightX2V 音色克隆客户端工具

用于调用 LightX2V 服务器的音色克隆服务
包括：创建音色克隆、使用克隆音色进行TTS、保存、列表、删除等功能
"""

import os
import json
import requests
import argparse
import sys
import base64
import tempfile
from typing import Optional, Dict, Any, List
from loguru import logger
import asyncio
import aiohttp


class LightX2VVoiceCloneClient:
    """
    LightX2V 音色克隆客户端
    
    用于调用 LightX2V 服务器的音色克隆服务
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
            "Accept": "application/json"
        })
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}"
            })
        
        logger.info(f"LightX2VVoiceCloneClient initialized with base_url: {self.base_url}")
    
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
    
    def _encode_audio(self, audio_path: str) -> str:
        """
        将音频文件编码为 base64
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            base64 编码的字符串
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        with open(audio_path, "rb") as f:
            audio_data = base64.b64encode(f.read()).decode('utf-8')
        
        return audio_data
    
    async def clone_voice(
        self,
        audio_path: str,
        text: Optional[str] = None,
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建音色克隆
        
        Args:
            audio_path: 音频文件路径（用于克隆的参考音频）
            text: 音频对应的文本（可选，如果不提供会自动进行 ASR 识别）
            save_path: 保存返回的音频文本到文件（可选），默认 None
            
        Returns:
            包含 success, speaker_id, text, message 的字典
        """
        url = f"{self.base_url}/api/v1/voice/clone"
        
        logger.info(f"Cloning voice from: {audio_path}, text={text if text else 'auto ASR'}")
        
        try:
            # 准备文件数据
            headers = {}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            data = {}
            if text:
                data["text"] = text
            
            with open(audio_path, "rb") as f:
                files = {"file": (os.path.basename(audio_path), f, "audio/*")}
                response = requests.post(url, files=files, data=data, headers=headers)
            
            if not await self.check_response(response, "LightX2VVoiceCloneClient clone_voice"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            
            if "speaker_id" in result:
                # 成功
                ret = {
                    "success": True,
                    "speaker_id": result["speaker_id"],
                    "text": result.get("text", ""),
                    "message": result.get("message", "Voice clone successful")
                }
                
                # 如果指定了保存路径，保存文本信息
                if save_path:
                    os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(ret, f, indent=2, ensure_ascii=False)
                    logger.info(f"Clone info saved to: {save_path}")
                
                logger.info(f"Voice clone successful: speaker_id={ret['speaker_id']}")
                return ret
            else:
                # 失败
                return {"success": False, "error": result.get("error", "Unknown error")}
            
        except Exception as e:
            logger.error(f"LightX2VVoiceCloneClient clone_voice failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def tts_with_clone(
        self,
        text: str,
        speaker_id: str,
        style: str = "正常",
        speed: float = 1.0,
        volume: float = 0,
        pitch: float = 0,
        language: str = "ZH_CN",
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        使用克隆的音色进行 TTS
        
        Args:
            text: 要转换的文本
            speaker_id: 克隆的音色 ID（必需）
            style: 说话风格，默认 "正常"
            speed: 语速 (0.5~2.0，1.0为正常语速)，默认 1.0
            volume: 音量 (-12~12 dB，0为正常音量)，默认 0
            pitch: 音调 (-24~24 halftone，0为正常音调)，默认 0
            language: 语言，默认 "ZH_CN" (可选: "ZH_CN", "EN_US", "ZH_CN_SICHUAN", "ZH_CN_HK")
            save_path: 保存音频文件的路径，如果为 None 则不保存，默认 None
            
        Returns:
            包含 success, audio_path (如果 save_path 不为 None), audio_data (bytes) 的字典
        """
        url = f"{self.base_url}/api/v1/voice/clone/tts"
        
        # 构建请求参数
        payload = {
            "text": text,
            "speaker_id": speaker_id,
            "style": style,
            "speed": speed,
            "volume": volume,
            "pitch": pitch,
            "language": language
        }
        
        logger.info(f"Generating TTS with cloned voice: text={text[:50]}..., speaker_id={speaker_id}")
        
        try:
            response = self.session.post(url, json=payload)
            
            if not await self.check_response(response, "LightX2VVoiceCloneClient tts_with_clone"):
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
            logger.error(f"LightX2VVoiceCloneClient tts_with_clone failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def save_voice_clone(
        self,
        speaker_id: str,
        name: str
    ) -> Dict[str, Any]:
        """
        保存克隆的音色到用户收藏
        
        Args:
            speaker_id: 克隆的音色 ID
            name: 音色名称（用于用户标识）
            
        Returns:
            包含 success, message, speaker_id, name 的字典
        """
        url = f"{self.base_url}/api/v1/voice/clone/save"
        
        payload = {
            "speaker_id": speaker_id,
            "name": name
        }
        
        logger.info(f"Saving voice clone: speaker_id={speaker_id}, name={name}")
        
        try:
            response = self.session.post(url, json=payload)
            
            if not await self.check_response(response, "LightX2VVoiceCloneClient save_voice_clone"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            
            if "message" in result and "success" in result.get("message", "").lower():
                return {
                    "success": True,
                    "message": result["message"],
                    "speaker_id": result.get("speaker_id", speaker_id),
                    "name": result.get("name", name)
                }
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
            
        except Exception as e:
            logger.error(f"LightX2VVoiceCloneClient save_voice_clone failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def list_voice_clones(self) -> Dict[str, Any]:
        """
        列出用户的音色克隆列表
        
        Returns:
            包含 success, voice_clones 的字典
        """
        url = f"{self.base_url}/api/v1/voice/clone/list"
        
        logger.info("Listing voice clones")
        
        try:
            response = self.session.get(url)
            
            if not await self.check_response(response, "LightX2VVoiceCloneClient list_voice_clones"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            
            if "voice_clones" in result:
                return {
                    "success": True,
                    "voice_clones": result["voice_clones"]
                }
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
            
        except Exception as e:
            logger.error(f"LightX2VVoiceCloneClient list_voice_clones failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_voice_clone(
        self,
        speaker_id: str
    ) -> Dict[str, Any]:
        """
        删除音色克隆
        
        Args:
            speaker_id: 要删除的音色克隆 ID
            
        Returns:
            包含 success, message 的字典
        """
        url = f"{self.base_url}/api/v1/voice/clone/{speaker_id}"
        
        logger.info(f"Deleting voice clone: speaker_id={speaker_id}")
        
        try:
            response = self.session.delete(url)
            
            if not await self.check_response(response, "LightX2VVoiceCloneClient delete_voice_clone"):
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            result = response.json()
            
            if "message" in result and "success" in result.get("message", "").lower():
                return {
                    "success": True,
                    "message": result["message"]
                }
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
            
        except Exception as e:
            logger.error(f"LightX2VVoiceCloneClient delete_voice_clone failed: {e}")
            return {"success": False, "error": str(e)}
    
    def close(self):
        """关闭会话"""
        self.session.close()


async def test(args):
    """测试函数"""
    parser = argparse.ArgumentParser(description="LightX2V Voice Clone Client Test")
    parser.add_argument("--base_url", type=str, default=None, help="Service base URL")
    parser.add_argument("--token", type=str, default=None, help="Access token")
    parser.add_argument("--action", type=str, required=True,
                       choices=["clone", "tts", "save", "list", "delete"],
                       help="Action to perform")
    
    # clone 参数
    parser.add_argument("--audio", type=str, default=None, help="Audio file path (for clone)")
    parser.add_argument("--text", type=str, default=None, help="Audio text (optional for clone)")
    
    # tts 参数
    parser.add_argument("--speaker_id", type=str, default=None, help="Speaker ID (for tts, save, delete)")
    parser.add_argument("--tts_text", type=str, default=None, help="Text for TTS (for tts)")
    parser.add_argument("--style", type=str, default="正常", help="Style (for tts)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed (0.5~2.0, for tts)")
    parser.add_argument("--volume", type=float, default=0, help="Volume (-12~12, for tts)")
    parser.add_argument("--pitch", type=float, default=0, help="Pitch (-24~24, for tts)")
    parser.add_argument("--language", type=str, default="ZH_CN", help="Language (for tts)")
    
    # save 参数
    parser.add_argument("--name", type=str, default=None, help="Voice name (for save)")
    
    # 输出参数
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    
    parsed_args = parser.parse_args(args) if args else parser.parse_args()
    
    client = LightX2VVoiceCloneClient(
        base_url=parsed_args.base_url,
        access_token=parsed_args.token
    )
    
    try:
        if parsed_args.action == "clone":
            if not parsed_args.audio:
                print("Error: --audio is required for clone action")
                return
            
            result = await client.clone_voice(
                audio_path=parsed_args.audio,
                text=parsed_args.text,
                save_path=parsed_args.output
            )
            
            if result.get("success"):
                print(f"Voice clone successful!")
                print(f"Speaker ID: {result['speaker_id']}")
                print(f"Recognized text: {result['text']}")
            else:
                print(f"Voice clone failed: {result.get('error')}")
        
        elif parsed_args.action == "tts":
            if not parsed_args.speaker_id or not parsed_args.tts_text:
                print("Error: --speaker_id and --tts_text are required for tts action")
                return
            
            result = await client.tts_with_clone(
                text=parsed_args.tts_text,
                speaker_id=parsed_args.speaker_id,
                style=parsed_args.style,
                speed=parsed_args.speed,
                volume=parsed_args.volume,
                pitch=parsed_args.pitch,
                language=parsed_args.language,
                save_path=parsed_args.output
            )
            
            if result.get("success"):
                print(f"TTS with cloned voice successful!")
                if result.get("audio_path"):
                    print(f"Audio saved to: {result['audio_path']}")
                print(f"Audio size: {result.get('size', 0) / 1024:.2f} KB")
            else:
                print(f"TTS failed: {result.get('error')}")
        
        elif parsed_args.action == "save":
            if not parsed_args.speaker_id or not parsed_args.name:
                print("Error: --speaker_id and --name are required for save action")
                return
            
            result = await client.save_voice_clone(
                speaker_id=parsed_args.speaker_id,
                name=parsed_args.name
            )
            
            if result.get("success"):
                print(f"Voice clone saved successfully!")
                print(f"Speaker ID: {result['speaker_id']}")
                print(f"Name: {result['name']}")
            else:
                print(f"Save failed: {result.get('error')}")
        
        elif parsed_args.action == "list":
            result = await client.list_voice_clones()
            
            if result.get("success"):
                voice_clones = result.get("voice_clones", [])
                print(f"Voice clones ({len(voice_clones)}):")
                for clone in voice_clones:
                    print(f"  - {clone.get('name', 'N/A')} (ID: {clone.get('speaker_id', 'N/A')})")
            else:
                print(f"List failed: {result.get('error')}")
        
        elif parsed_args.action == "delete":
            if not parsed_args.speaker_id:
                print("Error: --speaker_id is required for delete action")
                return
            
            result = await client.delete_voice_clone(speaker_id=parsed_args.speaker_id)
            
            if result.get("success"):
                print(f"Voice clone deleted successfully!")
            else:
                print(f"Delete failed: {result.get('error')}")
    
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test(sys.argv[1:]))

