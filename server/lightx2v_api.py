"""
LightX2V 后端 HTTP API 客户端（直接调用 /api/v1/task/* 接口，不使用 S2VClient）
用于 batch：提交后读入内存立即提交、用 result_url/input_url 按需取结果和输入，不存 CDN URL。
"""
import asyncio
import json
import os
from typing import Any, Dict, Optional, Tuple

import aiohttp
from loguru import logger

# 默认从环境变量读取
DEFAULT_BASE_URL = os.getenv("LIGHTX2V_BASE_URL", "https://x2v.light-ai.top")
DEFAULT_ACCESS_TOKEN = os.getenv("LIGHTX2V_ACCESS_TOKEN", "")


async def _request(
    method: str,
    path: str,
    base_url: str,
    access_token: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """发起请求，返回解析后的 JSON 或错误信息。"""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json", "Content-Type": "application/json; charset=utf-8"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    try:
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers, params=params) as resp:
                    text = await resp.text()
                    if resp.status not in (200, 201):
                        logger.warning(f"LightX2V API {method} {path}: {resp.status} {text}")
                        return {"success": False, "error": f"HTTP {resp.status}", "raw": text}
                    try:
                        return {"success": True, **json.loads(text)}
                    except json.JSONDecodeError:
                        return {"success": True, "raw": text}
            else:
                body = json.dumps(json_body, ensure_ascii=False) if json_body else None
                async with session.post(url, headers=headers, data=body) as resp:
                    text = await resp.text()
                    if resp.status not in (200, 201):
                        logger.warning(f"LightX2V API {method} {path}: {resp.status} {text}")
                        return {"success": False, "error": f"HTTP {resp.status}", "raw": text}
                    try:
                        return {"success": True, **json.loads(text)}
                    except json.JSONDecodeError:
                        return {"success": True, "raw": text}
    except Exception as e:
        logger.error(f"LightX2V API request failed: {e}")
        return {"success": False, "error": str(e)}


async def submit_task(
    base_url: str,
    access_token: str,
    task: str = "s2v",
    model_cls: str = "SekoTalk",
    stage: str = "single_stage",
    prompt: str = "",
    negative_prompt: Optional[str] = None,
    cfg_scale: int = 5,
    duration: int = 7,
    seed: Optional[int] = None,
    input_image: Optional[Dict[str, Any]] = None,
    input_audio: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """POST /api/v1/task/submit，返回 { success, task_id?, error? }。"""
    payload = {
        "task": task,
        "model_cls": model_cls,
        "stage": stage,
        "prompt": prompt or "根据音频生成对应视频",
        "negative_prompt": negative_prompt
        or "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
        "cfg_scale": cfg_scale,
        "duration": duration,
    }
    if seed is not None:
        payload["seed"] = seed
    if input_image:
        payload["input_image"] = input_image
    if input_audio:
        payload["input_audio"] = input_audio
    out = await _request("POST", "/api/v1/task/submit", base_url, access_token, json_body=payload)
    if not out.get("success"):
        return out
    if "task_id" not in out:
        return {"success": False, "error": "No task_id in response"}
    return out


async def query_task(base_url: str, access_token: str, task_id: str) -> Dict[str, Any]:
    """GET /api/v1/task/query?task_id=..."""
    return await _request(
        "GET",
        "/api/v1/task/query",
        base_url,
        access_token,
        params={"task_id": task_id},
    )


async def get_result_url(
    base_url: str,
    access_token: str,
    task_id: str,
    name: str = "output_video",
) -> Optional[str]:
    """GET /api/v1/task/result_url?task_id=...&name=...，返回 url 或 None。"""
    out = await _request(
        "GET",
        "/api/v1/task/result_url",
        base_url,
        access_token,
        params={"task_id": task_id, "name": name},
    )
    if not out.get("success"):
        return None
    return out.get("url")


async def get_input_url(
    base_url: str,
    access_token: str,
    task_id: str,
    name: str,
    filename: Optional[str] = None,
) -> Optional[str]:
    """GET /api/v1/task/input_url?task_id=...&name=...，返回 url 或 None。"""
    params = {"task_id": task_id, "name": name}
    if filename is not None:
        params["filename"] = filename
    out = await _request(
        "GET",
        "/api/v1/task/input_url",
        base_url,
        access_token,
        params=params,
    )
    if not out.get("success"):
        return None
    return out.get("url")


async def cancel_task(base_url: str, access_token: str, task_id: str) -> bool:
    """GET /api/v1/task/cancel?task_id=...，返回是否成功。"""
    out = await _request(
        "GET",
        "/api/v1/task/cancel",
        base_url,
        access_token,
        params={"task_id": task_id},
    )
    if not out.get("success"):
        return False
    msg = out.get("msg", "")
    return "cancelled" in msg.lower() or "cancel" in msg.lower()


async def resume_task(base_url: str, access_token: str, task_id: str) -> Tuple[bool, Optional[str]]:
    """GET /api/v1/task/resume?task_id=...，返回 (成功, 错误信息)。"""
    out = await _request(
        "GET",
        "/api/v1/task/resume",
        base_url,
        access_token,
        params={"task_id": task_id},
    )
    if not out.get("success"):
        return False, out.get("error") or out.get("raw") or "Resume failed"
    msg = out.get("msg", "")
    if (msg or "").strip().lower() == "ok":
        return True, None
    return False, msg or "Resume failed"


async def wait_for_task(
    base_url: str,
    access_token: str,
    task_id: str,
    poll_interval: int = 5,
    timeout: int = 3600,
) -> Dict[str, Any]:
    """轮询 query 直到 SUCCEED/FAILED/CANCELLED 或超时。"""
    import time
    start = time.time()
    while True:
        if time.time() - start > timeout:
            return {"success": False, "error": "Timeout", "task_id": task_id}
        r = await query_task(base_url, access_token, task_id)
        if not r.get("success"):
            return r
        status = r.get("status", "UNKNOWN")
        if isinstance(status, str):
            status_upper = status.upper()
        else:
            status_upper = str(status)
        if status_upper in ("SUCCEED", "FAILED", "CANCELLED"):
            return {"success": True, "status": status_upper, **r}
        await asyncio.sleep(poll_interval)
