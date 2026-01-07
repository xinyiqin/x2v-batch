# -*- coding: utf-8 -*-

import asyncio
import json
import os
import sys

import aiohttp
from loguru import logger


class MD2CardClient:
    """
    MD2Card客户端 - 将Markdown转换为卡片图片或生成封面
    
    卡片生成参数说明:
        - theme: 主题样式 (如 "business", "default" 等)
        - themeMode: 主题模式
        - width: 卡片宽度 (默认440)
        - height: 卡片高度 (默认586)
        - splitMode: 分割模式 (如 "autoSplit")
        - overHiddenMode: 是否启用溢出隐藏
        - mdxMode: 是否启用MDX模式
        - weChatMode: 是否启用微信模式
        - background: 背景设置
    
    封面生成参数说明:
        - text: 封面文本内容
        - keywords: 关键词
        - count: 生成封面数量 (默认3)
    """

    def __init__(self):
        self.base_url = "https://md2card.cn/api"
        self.api_key = os.getenv("MD2CARD_API_KEY")
        if not self.api_key:
            raise ValueError("MD2CARD_API_KEY is not set")

    async def generate_card(
        self,
        markdown: str,
        theme: str = "business",
        themeMode: str = "",
        overHiddenMode: bool = False,
        mdxMode: bool = False,
        width: int = 440,
        height: int = 586,
        splitMode: str = "autoSplit",
        background: str = "",
        weChatMode: bool = False,
    ):
        """
        将Markdown转换为卡片图片

        Args:
            markdown: Markdown文本内容
            theme: 主题样式
            themeMode: 主题模式
            overHiddenMode: 是否启用溢出隐藏
            mdxMode: 是否启用MDX模式
            width: 卡片宽度
            height: 卡片高度
            splitMode: 分割模式
            background: 背景设置
            weChatMode: 是否启用微信模式

        Returns:
            dict: 包含success, previewUrl, images, cost等信息的结果字典
        """
        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "markdown": markdown,
                "themeMode": themeMode,
                "theme": theme,
                "overHiddenMode": overHiddenMode,
                "mdxMode": mdxMode,
                "width": width,
                "height": height,
                "splitMode": splitMode,
                "background": background,
                "weChatMode": weChatMode,
            }

            logger.info(f"md2card generate request: theme={theme}, width={width}, height={height}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/generate",
                    json=payload,
                    headers=headers,
                    proxy=self.proxy,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

                    if result.get("success"):
                        logger.info(f"md2card generate success: previewUrl={result.get('previewUrl')}, cost={result.get('cost')}")
                        logger.info(f"md2card generated {len(result.get('images', []))} images")
                    else:
                        logger.warning(f"md2card generate failed: {result}")

                    return result

        except aiohttp.ClientError as e:
            logger.error(f"md2card request failed (ClientError): {e}")
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except asyncio.TimeoutError as e:
            logger.error(f"md2card request timeout: {e}")
            return {"success": False, "error": f"Request timeout: {str(e)}"}
        except Exception as e:
            logger.error(f"md2card generate failed: {e}")
            return {"success": False, "error": str(e)}

    async def generate_cover(
        self,
        text: str,
        keywords: str = "",
        count: int = 3,
    ):
        """
        生成封面图片

        Args:
            text: 封面文本内容
            keywords: 关键词
            count: 生成封面数量 (默认3)

        Returns:
            dict: 包含success等信息的结果字典
        """
        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "text": text,
                "keywords": keywords,
                "count": count,
            }

            logger.info(f"md2card generate cover request: text={text[:50]}..., keywords={keywords}, count={count}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/generate/cover",
                    json=payload,
                    headers=headers,
                    proxy=self.proxy,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response.raise_for_status()
                    result = await response.json()

                    if result.get("success"):
                        logger.info(f"md2card generate cover success: count={count}")
                    else:
                        logger.warning(f"md2card generate cover failed: {result}")

                    return result

        except aiohttp.ClientError as e:
            logger.error(f"md2card cover request failed (ClientError): {e}")
            return {"success": False, "error": f"Request failed: {str(e)}"}
        except asyncio.TimeoutError as e:
            logger.error(f"md2card cover request timeout: {e}")
            return {"success": False, "error": f"Request timeout: {str(e)}"}
        except Exception as e:
            logger.error(f"md2card generate cover failed: {e}")
            return {"success": False, "error": str(e)}


async def test(args):
    """
    MD2Card测试函数

    Args:
        args: list, 第一个参数为模式: "card" 或 "cover"
        
        生成卡片模式:
            [mode, markdown, theme, themeMode, overHiddenMode, mdxMode, width, height, splitMode, background, weChatMode]
            示例: python md2card.py card "# 标题\\n\\n内容" business "" false false 440 586 autoSplit "" false
        
        生成封面模式:
            [mode, text, keywords, count]
            示例: python md2card.py cover "分享一个免费的小红书封面工具\\nMD2Card" "免费" 3
    """
    if not args:
        print("Usage:")
        print("  Generate card: python md2card.py card <markdown> [theme] [themeMode] ...")
        print("  Generate cover: python md2card.py cover <text> [keywords] [count]")
        return
    
    client = MD2CardClient()
    mode = args[0].lower()
    
    if mode == "cover":
        # 封面生成模式
        params = {
            "text": "分享一个免费的小红书封面工具\nMD2Card",
            "keywords": "",
            "count": 3,
        }
        
        keys = list(params.keys())
        
        # 覆盖默认参数 (跳过第一个参数mode)
        for i, arg in enumerate(args[1:]):
            if i >= len(keys):
                break
            
            key = keys[i]
            if key == "count":
                params[key] = int(arg) if arg else params[key]
            else:
                params[key] = arg if arg else params[key]
        
        result = await client.generate_cover(
            params["text"],
            params["keywords"],
            params["count"],
        )
    else:
        # 卡片生成模式 (默认)
        params = {
            "markdown": "# 示例标题\n\n这是示例内容",
            "theme": "business",
            "themeMode": "",
            "overHiddenMode": False,
            "mdxMode": False,
            "width": 440,
            "height": 586,
            "splitMode": "autoSplit",
            "background": "",
            "weChatMode": False,
        }
        
        keys = list(params.keys())
        
        # 覆盖默认参数 (如果第一个参数是mode且不是card，则跳过)
        start_idx = 1 if mode == "card" else 0
        
        for i, arg in enumerate(args[start_idx:], start_idx):
            if i - start_idx >= len(keys):
                break
                
            key = keys[i - start_idx]
            # 类型转换
            if key in ["overHiddenMode", "mdxMode", "weChatMode"]:
                params[key] = str(arg).lower() in ("1", "true", "yes", "on")
            elif key in ["width", "height"]:
                params[key] = int(arg) if arg else params[key]
            else:
                params[key] = arg if arg else params[key]
        
        result = await client.generate_card(
            params["markdown"],
            params["theme"],
            params["themeMode"],
            params["overHiddenMode"],
            params["mdxMode"],
            params["width"],
            params["height"],
            params["splitMode"],
            params["background"],
            params["weChatMode"],
        )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


if __name__ == "__main__":
    asyncio.run(test(sys.argv[1:]))
