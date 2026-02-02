"""
主应用文件 - FastAPI 服务器
"""
import base64
import os
import asyncio
import json
import zipfile
import tempfile
import math
from pathlib import Path
from typing import Any, Optional
from io import BytesIO

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
import uvicorn

# 尝试导入音频处理库
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    logger.warning("mutagen not installed, audio duration detection may not work. Install with: pip install mutagen")

from server.auth import AuthManager
from server.data_manager import LocalDataManager
from server.task_manager import TaskManager, VideoItemStatus
from server.batch_processor import BatchProcessor
from server import lightx2v_api

# 延迟导入 S3DataManager，只在需要时导入
S3DataManager = None

async def get_audio_duration(audio_data: bytes) -> float:
    """
    获取音频时长（秒）
    
    Args:
        audio_data: 音频文件的字节数据
        
    Returns:
        音频时长（秒），如果无法检测则返回默认值 30.0
    """
    if not MUTAGEN_AVAILABLE:
        logger.warning("mutagen not available, using default audio duration 30.0s")
        return 30.0
    
    try:
        # 使用 mutagen 读取音频元数据
        audio_file = MutagenFile(BytesIO(audio_data))
        if audio_file is None:
            logger.warning("Failed to parse audio file, using default duration 30.0s")
            return 30.0
        
        duration = audio_file.info.length if hasattr(audio_file, 'info') and hasattr(audio_file.info, 'length') else None
        if duration is None or duration <= 0:
            logger.warning(f"Invalid audio duration: {duration}, using default 30.0s")
            return 30.0
        
        logger.debug(f"Detected audio duration: {duration:.2f}s")
        return float(duration)
    except Exception as e:
        logger.warning(f"Failed to detect audio duration: {e}, using default 30.0s")
        return 30.0

# 初始化数据目录（仅用于本地存储）
def init_data_directory():
    """初始化数据目录和初始数据（仅用于本地存储）"""
    # 检查任务存储类型，如果 task 存储在 S3，则跳过本地 users.json 初始化
    # users.json 现在与 task 数据存储位置一致
    task_storage_type = os.getenv("TASK_STORAGE_TYPE", "local").lower()
    if task_storage_type == "s3":
        logger.info("Using S3 for task storage, users.json will be stored in S3 (skipping local initialization)")
    
    # 检查数据存储类型，如果 data 存储在 S3，则跳过本地数据目录初始化
    storage_type = os.getenv("STORAGE_TYPE", "local").lower()
    if storage_type == "s3":
        logger.info("Using S3 for data storage, skipping local data directory initialization")
        # 如果 task 存储也是 S3，完全跳过本地初始化
        if task_storage_type == "s3":
            return
    
    data_dir = os.getenv("DATA_DIR", "./data")
    try:
        # 导入并运行初始化脚本
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        # 直接调用初始化逻辑，避免导入问题
        from pathlib import Path as PathLib
        base_path = PathLib(data_dir)
        base_path.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录（仅用于本地数据存储）
        if storage_type != "s3":
            for subdir in ["images", "audios", "videos"]:
                (base_path / subdir).mkdir(parents=True, exist_ok=True)
        
        # 创建 batches 目录（仅用于本地 task 存储）
        if task_storage_type != "s3":
            (base_path / "batches").mkdir(parents=True, exist_ok=True)
        
        # 初始化 users.json（如果不存在，仅用于本地 task 存储）
        # users.json 现在与 task 数据存储位置一致
        if task_storage_type != "s3":
            users_file = base_path / "users.json"
            if not users_file.exists():
                import hashlib
                import json
                def hash_password(password: str) -> str:
                    return hashlib.sha256(password.encode()).hexdigest()
                
                # 从环境变量获取管理员初始密码，默认使用 admin8888
                admin_password = os.getenv("ADMIN_PASSWORD", "admin8888")
                
                if not admin_password:
                    admin_password = "admin8888"
                
                default_users = {
                    "admin": {
                        "id": "u-0",
                        "username": "admin",
                        "password_hash": hash_password(admin_password),
                        "credits": 9999,
                        "is_admin": True,
                        "created_at": "2026-01-01T00:00:00"
                    }
                }
                with open(users_file, "w", encoding="utf-8") as f:
                    json.dump(default_users, f, indent=2, ensure_ascii=False)
                logger.info("✅ Created default users.json with admin user (local task storage)")
    except Exception as e:
        logger.warning(f"Failed to initialize data directory: {e}")

# 初始化数据目录（仅用于本地存储）
init_data_directory()

# 初始化组件
data_dir = os.getenv("DATA_DIR", "./data")

# 选择数据管理器：用于存储实际文件数据（图片、音频、视频等）
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local").lower()
if STORAGE_TYPE == "s3":
    s3_config = os.getenv("S3_CONFIG")
    if not s3_config:
        logger.warning("STORAGE_TYPE=s3 but S3_CONFIG not set, falling back to local storage")
        data_manager = LocalDataManager(base_dir=data_dir)
    else:
        # 只在需要时导入 S3DataManager
        try:
            from server.s3_data_manager import S3DataManager
            data_manager = S3DataManager(s3_config)
            logger.info("Using S3DataManager for data storage (will initialize on startup)")
        except ImportError as e:
            logger.error(f"Failed to import S3DataManager: {e}. Please install aioboto3: pip install aioboto3")
            logger.warning("Falling back to local storage")
            data_manager = LocalDataManager(base_dir=data_dir)
else:
    data_manager = LocalDataManager(base_dir=data_dir)
    logger.info(f"Using LocalDataManager for data storage (base_dir: {data_dir})")

# 选择任务存储管理器：用于存储任务相关的 JSON 数据（batches/*.json, users.json）
# 可以与 data_manager 独立配置，例如：task 存储在本地，data 存储在 S3
TASK_STORAGE_TYPE = os.getenv("TASK_STORAGE_TYPE", "local").lower()
if TASK_STORAGE_TYPE == "s3":
    task_s3_config = os.getenv("TASK_S3_CONFIG")
    if not task_s3_config:
        # 如果没有单独配置 TASK_S3_CONFIG，尝试使用 S3_CONFIG
        task_s3_config = os.getenv("S3_CONFIG")
    if not task_s3_config:
        logger.warning("TASK_STORAGE_TYPE=s3 but TASK_S3_CONFIG not set, falling back to local storage")
        task_storage_manager = LocalDataManager(base_dir=data_dir)
    else:
        try:
            from server.s3_data_manager import S3DataManager
            task_storage_manager = S3DataManager(task_s3_config)
            logger.info("Using S3DataManager for task storage (will initialize on startup)")
        except ImportError as e:
            logger.error(f"Failed to import S3DataManager: {e}. Please install aioboto3: pip install aioboto3")
            logger.warning("Falling back to local storage")
            task_storage_manager = LocalDataManager(base_dir=data_dir)
else:
    task_storage_manager = LocalDataManager(base_dir=data_dir)
    logger.info(f"Using LocalDataManager for task storage (base_dir: {data_dir})")

# 初始化 AuthManager 和 TaskManager
# AuthManager 使用 task_storage_manager 存储 users.json
# TaskManager 使用 task_storage_manager 存储 batches/*.json
# data_manager 用于存储实际文件数据（图片、音频、视频等）
auth_manager = AuthManager(data_manager=task_storage_manager)
task_manager = TaskManager(storage_dir=f"{data_dir}/batches", task_storage_manager=task_storage_manager, data_manager=data_manager)

# S2V API 配置（支持动态更新）
S2V_BASE_URL = os.getenv("LIGHTX2V_BASE_URL", "https://x2v.light-ai.top")
# 使用可变变量存储 token，允许运行时更新
_S2V_ACCESS_TOKEN = os.getenv("LIGHTX2V_ACCESS_TOKEN", "")

if not _S2V_ACCESS_TOKEN:
    logger.warning("⚠️  LIGHTX2V_ACCESS_TOKEN not set, batch processing will fail")

batch_processor = BatchProcessor(
    task_manager=task_manager,
    data_manager=data_manager,
    auth_manager=auth_manager,
    base_url=S2V_BASE_URL,
    access_token=_S2V_ACCESS_TOKEN,
)

# FastAPI 应用
app = FastAPI(title="AI Vision Batch Service")

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化 S3 连接和加载数据"""
    # 初始化 data_manager（用于存储实际文件数据）
    if hasattr(data_manager, 'init') and callable(getattr(data_manager, 'init', None)):
        try:
            await data_manager.init()
            logger.info("✅ DataManager (S3) initialized successfully")
        except AttributeError:
            # 不是 S3DataManager，跳过
            pass
        except Exception as e:
            logger.error(f"❌ Failed to initialize DataManager (S3): {e}")
            raise
    
    # 初始化 task_storage_manager（用于存储任务 JSON 数据）
    if hasattr(task_storage_manager, 'init') and callable(getattr(task_storage_manager, 'init', None)):
        try:
            await task_storage_manager.init()
            logger.info("✅ TaskStorageManager (S3) initialized successfully")
        except AttributeError:
            # 不是 S3DataManager，跳过
            pass
        except Exception as e:
            logger.error(f"❌ Failed to initialize TaskStorageManager (S3): {e}")
            raise
    
    # 如果是 S3 存储，异步加载用户和批次数据
    if TASK_STORAGE_TYPE == "s3":
        try:
            await auth_manager.ensure_users_loaded()
        except Exception as e:
            logger.error(f"Failed to load users on startup: {e}")
        
        try:
            await task_manager.ensure_batches_loaded()
        except Exception as e:
            logger.error(f"Failed to load batches on startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    # 关闭 data_manager
    if hasattr(data_manager, 'close') and callable(getattr(data_manager, 'close', None)):
        try:
            await data_manager.close()
            logger.info("✅ DataManager (S3) closed successfully")
        except AttributeError:
            # 不是 S3DataManager，跳过
            pass
        except Exception as e:
            logger.error(f"❌ Failed to close DataManager (S3): {e}")
    
    # 关闭 task_storage_manager
    if hasattr(task_storage_manager, 'close') and callable(getattr(task_storage_manager, 'close', None)):
        try:
            await task_storage_manager.close()
            logger.info("✅ TaskStorageManager (S3) closed successfully")
        except AttributeError:
            # 不是 S3DataManager，跳过
            pass
        except Exception as e:
            logger.error(f"❌ Failed to close TaskStorageManager (S3): {e}")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 认证依赖
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """获取当前用户"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    user_info = auth_manager.verify_token(token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    return user_info


async def get_current_admin(
    user: dict = Depends(get_current_user)
) -> dict:
    """获取当前管理员用户"""
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


# ==================== 健康检查 ====================

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "S2V Batch Service"}

@app.get("/api/token/status")
async def check_token_status():
    """检查 S2V API token 是否有效"""
    import requests
    
    # 使用 batch_processor 的当前 token
    current_token = batch_processor.access_token
    
    if not current_token:
        return {"valid": False, "error": "Token not configured"}
    
    try:
        # 尝试调用一个简单的 API 端点来验证 token
        # 使用 /api/v1/model/list 或类似的端点
        url = f"{S2V_BASE_URL}/api/v1/model/list"
        headers = {
            "Authorization": f"Bearer {current_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            return {"valid": True}
        elif response.status_code == 401:
            return {"valid": False, "error": "Unauthorized - token may be expired"}
        else:
            return {"valid": False, "error": f"HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to check token status: {e}")
        return {"valid": False, "error": str(e)}


# ==================== 认证接口 ====================

@app.post("/api/auth/login")
async def login(username: str = Form(...), password: str = Form(...)):
    """用户登录"""
    if not auth_manager.verify_password(username, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    user = auth_manager.get_user(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    token = auth_manager.generate_token(user)
    
    return {
        "token": token,
        "user_info": user
    }


# ==================== 用户接口 ====================

@app.post("/api/user/change-password")
async def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    user: dict = Depends(get_current_user)
):
    """修改当前用户密码"""
    username = user["username"]
    
    if not await auth_manager.change_password(username, old_password, new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password"
        )
    
    return {"success": True, "message": "Password changed successfully"}


@app.get("/api/user/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    user_info = auth_manager.get_user_by_id(user["user_id"])
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user_info


# ==================== 视频生成接口 ====================

@app.post("/api/video/batch")
async def create_batch(
    images: list[UploadFile] = File(...),
    audio: UploadFile = File(...),
    prompt: str = Form(""),
    user: dict = Depends(get_current_user),
):
    """创建批次任务：读入内存后立即提交到 LightX2V，每个 item 记录 task_id；媒体不落 S3，仅用 result_url/input_url 按需取。"""
    if len(images) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image is required"
        )
    if len(images) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 images allowed"
        )

    user_info = auth_manager.get_user_by_id(user["user_id"])
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 读入内存，不写 S3
    audio_data = await audio.read()
    audio_duration = await get_audio_duration(audio_data)
    credits_per_video = 1 if audio_duration <= 30 else math.ceil(audio_duration / 30)
    required_credits = credits_per_video * len(images)
    if user_info["credits"] < required_credits:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient credits. Required: {required_credits} (audio: {audio_duration:.1f}s, {credits_per_video} credits/video × {len(images)} videos), Available: {user_info['credits']}"
        )

    async def read_image(img: UploadFile) -> tuple[bytes, str]:
        data = await img.read()
        return data, img.filename or "image.png"
    image_list = await asyncio.gather(*[read_image(img) for img in images])
    image_datas = [x[0] for x in image_list]
    image_filenames = [x[1] for x in image_list]

    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
    audio_filename = audio.filename or "audio.wav"

    # 先创建批次（仅 display 用文件名，不存媒体）；每个 item 已有临时 id，暂无 api_task_id，前端显示「排队中」
    batch_name = f"批次 {user_info['username']} {asyncio.get_event_loop().time()}"
    batch = await task_manager.create_batch(
        user_id=user["user_id"],
        user_name=user_info["username"],
        name=batch_name,
        prompt=prompt or "根据音频生成对应视频",
        audio_filename=audio_filename,
        image_filenames=image_filenames,
        credits_used=0,
        credits_per_video=credits_per_video,
    )

    base_url = S2V_BASE_URL
    token = batch_processor.access_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LightX2V token not configured",
        )

    # 立即返回 batch_id，前端跳转详情；后台按「一次最多 3 个 + 错峰 + 重试」提交，提交成功后写入正式 api_task_id
    asyncio.create_task(
        _submit_batch_tasks(
            batch_id=batch.id,
            image_datas=image_datas,
            audio_b64=audio_b64,
            prompt_text=batch.prompt or "根据音频生成对应视频",
            base_url=base_url,
            token=token,
        )
    )
    return {"batch_id": batch.id}


# 后端限制：user_visit_frequency≈0.05s、user_max_active_tasks=3；错峰 + 最多 3 个并发 + 重试
_SUBMIT_CONCURRENCY = 3
_SUBMIT_STAGGER_SEC = 0.06
_SUBMIT_RETRY_ATTEMPTS = 3
_SUBMIT_RETRY_BASE_SEC = 1


async def _submit_batch_tasks(
    batch_id: str,
    image_datas: list[bytes],
    audio_b64: str,
    prompt_text: str,
    base_url: str,
    token: str,
) -> None:
    """后台：按 3 个并发 + 错峰提交，成功后写 api_task_id，全部完成后启动轮询并 save_batch。"""
    batch = task_manager.get_batch(batch_id)
    if not batch or not batch.items:
        return
    sem = asyncio.Semaphore(_SUBMIT_CONCURRENCY)

    async def submit_one(i: int, item: Any) -> None:
        await asyncio.sleep(i * _SUBMIT_STAGGER_SEC)  # 错峰，满足后端 visit_frequency
        async with sem:
            image_b64 = base64.b64encode(image_datas[i]).decode("utf-8")
            last_err = None
            for attempt in range(_SUBMIT_RETRY_ATTEMPTS):
                submit_out = await lightx2v_api.submit_task(
                    base_url=base_url,
                    access_token=token,
                    prompt=prompt_text,
                    input_image={"type": "base64", "data": image_b64},
                    input_audio={"type": "base64", "data": audio_b64},
                )
                if submit_out.get("success"):
                    api_task_id = submit_out.get("task_id")
                    if api_task_id:
                        await task_manager.update_video_item(
                            batch_id=batch_id,
                            item_id=item.id,
                            api_task_id=api_task_id,
                            persist=False,
                        )
                    return
                last_err = submit_out.get("error", "Unknown error")
                if attempt < _SUBMIT_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_SUBMIT_RETRY_BASE_SEC * (attempt + 1))

            await task_manager.update_video_item(
                batch_id=batch_id,
                item_id=item.id,
                status=VideoItemStatus.PENDING,
                error_msg=f"Submit failed: {last_err}",
                persist=False,
            )

    await asyncio.gather(*[submit_one(i, item) for i, item in enumerate(batch.items)])
    asyncio.create_task(batch_processor.process_batch(batch_id))
    asyncio.create_task(task_manager.save_batch(batch_id))


def _item_input_url_path(batch_id: str, item_id: str, name: str = "input_image") -> str:
    """返回前端可调用的 input_url 代理路径（缩略图等）。"""
    return f"/api/video/batches/{batch_id}/items/{item_id}/input_url?name={name}"


@app.get("/api/video/batches")
async def get_batches(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """获取当前用户的批次列表。sourceImage 为 input_url 代理路径，按 task_id 从后端取图。"""
    batches = task_manager.get_user_batches(user["user_id"], limit=limit, offset=offset)
    result = []
    for batch in batches:
        batch_dict = batch.to_dict()
        for item in batch_dict["items"]:
            if item.get("api_task_id"):
                item["sourceImage"] = _item_input_url_path(batch.id, item["id"], "input_image")
            # 否则保留 display 用 sourceImage 或空
        result.append(batch_dict)
    return {"batches": result, "total": len(result)}


@app.get("/api/video/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    user: dict = Depends(get_current_user),
):
    """获取特定批次的详细信息。sourceImage 为 input_url 代理路径。"""
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    batch_dict = batch.to_dict()
    for item in batch_dict["items"]:
        if item.get("api_task_id"):
            item["sourceImage"] = _item_input_url_path(batch_id, item["id"], "input_image")
    return batch_dict


@app.get("/api/video/batches/{batch_id}/items/{item_id}/result_url")
async def get_item_result_url(
    batch_id: str,
    item_id: str,
    name: str = "output_video",
    user: dict = Depends(get_current_user),
):
    """代理 LightX2V result_url，按需取结果 URL（不存 CDN URL 防过期）。"""
    batch = task_manager.get_batch(batch_id)
    if not batch or (batch.user_id != user["user_id"] and not user.get("is_admin")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    item = task_manager.get_video_item(batch_id, item_id)
    if not item or not item.api_task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item or task_id not found")
    url = await lightx2v_api.get_result_url(
        S2V_BASE_URL,
        batch_processor.access_token,
        item.api_task_id,
        name=name,
    )
    if not url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to get result URL")
    return {"url": url}


@app.get("/api/video/batches/{batch_id}/items/{item_id}/input_url")
async def get_item_input_url(
    batch_id: str,
    item_id: str,
    name: str = "input_image",
    filename: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """代理 LightX2V input_url，用于缩略图等。"""
    batch = task_manager.get_batch(batch_id)
    if not batch or (batch.user_id != user["user_id"] and not user.get("is_admin")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    item = task_manager.get_video_item(batch_id, item_id)
    if not item or not item.api_task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item or task_id not found")
    url = await lightx2v_api.get_input_url(
        S2V_BASE_URL,
        batch_processor.access_token,
        item.api_task_id,
        name=name,
        filename=filename,
    )
    if not url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to get input URL")
    return {"url": url}


@app.post("/api/video/batches/{batch_id}/items/{item_id}/cancel")
async def cancel_batch_item(
    batch_id: str,
    item_id: str,
    user: dict = Depends(get_current_user),
):
    """取消单个任务"""
    from server.task_manager import VideoItemStatus
    
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    item = task_manager.get_video_item(batch_id, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    if item.status in [VideoItemStatus.COMPLETED, VideoItemStatus.FAILED, VideoItemStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item already finished"
        )
    
    success = await batch_processor.cancel_item(batch_id, item_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancel failed"
        )
    
    return {"success": True}


@app.post("/api/video/batches/{batch_id}/items/{item_id}/resume")
async def resume_batch_item(
    batch_id: str,
    item_id: str,
    user: dict = Depends(get_current_user),
):
    """重试单个失败任务"""
    from server.task_manager import VideoItemStatus
    
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    item = task_manager.get_video_item(batch_id, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    if item.status != VideoItemStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed items can be retried"
        )
    
    asyncio.create_task(batch_processor.resume_item(batch_id, item_id))
    return {"success": True}


@app.post("/api/video/batches/{batch_id}/retry_failed")
async def retry_failed_items(
    batch_id: str,
    user: dict = Depends(get_current_user),
):
    """批量重试失败任务"""
    from server.task_manager import VideoItemStatus
    
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    failed_items = [item for item in batch.items if item.status == VideoItemStatus.FAILED]
    cancelled_items = [item for item in batch.items if item.status == VideoItemStatus.CANCELLED]
    to_retry_count = len(failed_items) + len(cancelled_items)
    if to_retry_count == 0:
        return {"success": True, "count": 0}
    
    asyncio.create_task(batch_processor.resume_failed_items(batch_id))
    return {"success": True, "count": to_retry_count}


@app.get("/api/video/batches/{batch_id}/export")
async def export_batch_videos(
    batch_id: str,
    user: dict = Depends(get_current_user),
):
    """获取批次已完成视频下载清单：通过 result_url 接口取最新 URL（不存 CDN 防过期）。"""
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    completed_items = [
        item for item in batch.items
        if item.status == VideoItemStatus.COMPLETED and item.api_task_id
    ]
    if not completed_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed videos to export"
        )

    files = []
    for item in completed_items:
        url = await lightx2v_api.get_result_url(
            S2V_BASE_URL,
            batch_processor.access_token,
            item.api_task_id,
            name="output_video",
        )
        if not url:
            continue
        url_path = url.split("?")[0]
        url_filename = os.path.basename(url_path)
        if not url_filename or "." not in url_filename:
            url_filename = f"{item.id}.mp4"
        name_part, ext = os.path.splitext(url_filename)
        safe_name = "".join(c for c in name_part if c.isalnum() or c in ("-", "_")).strip() or item.id
        safe_filename = f"{safe_name}{ext}" if ext else f"{safe_name}.mp4"
        files.append({"name": safe_filename, "url": url, "id": item.id})

    logger.info(f"Returning download list for batch {batch_id}: {len(files)} files")
    return {
        "batch_id": batch_id,
        "batch_name": batch.name,
        "files": files,
        "total": len(files),
    }


# ==================== 管理员接口 ====================

@app.get("/api/admin/users")
async def get_all_users(admin: dict = Depends(get_current_admin)):
    """获取所有用户列表"""
    users = auth_manager.get_all_users()
    return {"users": users}


@app.post("/api/admin/users")
async def create_user(
    username: str = Form(...),
    credits: int = Form(100),
    is_admin: bool = Form(False),
    admin: dict = Depends(get_current_admin),
):
    """创建新用户（管理员功能）"""
    if credits < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credits must be non-negative"
        )
    
    try:
        # 新用户的初始密码固定为 123456
        default_password = "123456"
        user_data = await auth_manager.create_user(
            username=username,
            password=default_password,
            is_admin=is_admin,
            credits=credits
        )
        
        return {
            "success": True,
            "user": {
                "id": user_data["id"],
                "username": user_data["username"],
                "credits": user_data["credits"],
                "isAdmin": user_data["is_admin"],
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@app.patch("/api/admin/users/{user_id}/credits")
async def update_user_credits(
    user_id: str,
    new_credits: int = Form(...),
    admin: dict = Depends(get_current_admin),
):
    """更新用户灵感值"""
    if new_credits < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credits must be non-negative"
        )
    
    success = await auth_manager.update_user_credits(user_id, new_credits)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"success": True, "user_id": user_id, "credits": new_credits}


@app.patch("/api/admin/token")
async def update_s2v_token(
    new_token: str = Form(...),
    admin: dict = Depends(get_current_admin),
):
    """更新 S2V API token（仅管理员）"""
    if not new_token or not new_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token cannot be empty"
        )
    
    # 更新 batch_processor 的 token
    batch_processor.update_token(new_token.strip())
    
    # 验证新 token 是否有效
    try:
        import requests
        url = f"{S2V_BASE_URL}/api/v1/model/list"
        headers = {
            "Authorization": f"Bearer {new_token.strip()}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            logger.info(f"Admin {admin['username']} updated S2V token successfully")
            return {"success": True, "message": "Token updated and verified successfully"}
        elif response.status_code == 401:
            logger.warning(f"Admin {admin['username']} updated S2V token, but verification failed (401)")
            return {
                "success": True,
                "message": "Token updated, but verification failed (may be expired)",
                "warning": "Token may be expired or invalid"
            }
        else:
            logger.warning(f"Admin {admin['username']} updated S2V token, verification returned {response.status_code}")
            return {
                "success": True,
                "message": f"Token updated, but verification returned HTTP {response.status_code}",
                "warning": "Token verification failed"
            }
    except Exception as e:
        logger.error(f"Failed to verify new token: {e}")
        return {
            "success": True,
            "message": "Token updated, but verification failed",
            "warning": str(e)
        }


@app.get("/api/admin/batches")
async def get_all_batches(
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(get_current_admin),
):
    """获取所有批次（系统历史）。sourceImage 为 input_url 代理路径。"""
    batches = task_manager.get_all_batches(limit=limit, offset=offset)
    logger.info(f"Admin requested all batches: found {len(batches)} batches")
    result = []
    for batch in batches:
        batch_dict = batch.to_dict()
        for item in batch_dict.get("items", []):
            if item.get("api_task_id"):
                item["sourceImage"] = _item_input_url_path(batch.id, item["id"], "input_image")
        result.append(batch_dict)
    logger.info(f"Returning {len(result)} batches to admin")
    return {"batches": result, "total": len(result)}


# ==================== 文件服务接口 ====================

@app.get("/api/files/{subdir}/{filename:path}")
async def get_file(subdir: str, filename: str):
    """获取文件（支持 URL 编码的文件名）"""
    from urllib.parse import unquote
    
    # 解码 URL 编码的文件名（处理空格和特殊字符）
    decoded_filename = unquote(filename)
    file_path = data_manager._get_path(decoded_filename, subdir)
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {decoded_filename}"
        )
    
    # 设置正确的 MIME 类型
    mime_type = "application/octet-stream"
    if decoded_filename.lower().endswith((".jpg", ".jpeg")):
        mime_type = "image/jpeg"
    elif decoded_filename.lower().endswith(".png"):
        mime_type = "image/png"
    elif decoded_filename.lower().endswith(".gif"):
        mime_type = "image/gif"
    elif decoded_filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        mime_type = "video/mp4"
    
    return FileResponse(str(file_path), media_type=mime_type)


if __name__ == "__main__":
    # 使用导入字符串以支持 reload
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)

