"""
主应用文件 - FastAPI 服务器
"""
import os
import asyncio
import json
import zipfile
import tempfile
import math
from pathlib import Path
from typing import Optional
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
from server.task_manager import TaskManager
from server.batch_processor import BatchProcessor

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
    """创建批次任务"""
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
    
    # 检查用户灵感值
    user_info = auth_manager.get_user_by_id(user["user_id"])
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 保存音频文件并获取音频时长
    audio_data = await audio.read()
    audio_filename = f"{user['user_id']}_{audio.filename}"
    await data_manager.save_audio(audio_data, audio_filename)
    
    # 计算音频时长（秒）
    audio_duration = await get_audio_duration(audio_data)
    
    # 计算灵感值：≤30s = 1灵感值/视频，>30s = ceil(时长/30)灵感值/视频
    credits_per_video = 1 if audio_duration <= 30 else math.ceil(audio_duration / 30)
    required_credits = credits_per_video * len(images)
    
    if user_info["credits"] < required_credits:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient credits. Required: {required_credits} (audio: {audio_duration:.1f}s, {credits_per_video} credits/video × {len(images)} videos), Available: {user_info['credits']}"
        )
    
    # 并发保存所有图片文件以提高速度
    async def save_single_image(img: UploadFile) -> str:
        """保存单张图片并返回文件名"""
        img_data = await img.read()
        img_filename = f"{user['user_id']}_{img.filename}"
        await data_manager.save_image(img_data, img_filename)
        return img_filename
    
    # 使用 asyncio.gather 并发上传所有图片
    image_filenames = await asyncio.gather(*[save_single_image(img) for img in images])
    
    # 扣除灵感值
    if not await auth_manager.deduct_credits(user["user_id"], required_credits):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient credits"
        )
    
    # 创建批次（记录消耗的积分）
    batch_name = f"批次 {user_info['username']} {asyncio.get_event_loop().time()}"
    batch = await task_manager.create_batch(
        user_id=user["user_id"],
        user_name=user_info["username"],
        name=batch_name,
        prompt=prompt,
        audio_filename=audio_filename,
        image_filenames=image_filenames,
        credits_used=required_credits,  # 记录消耗的灵感值
    )
    
    # 异步处理批次
    asyncio.create_task(batch_processor.process_batch(batch.id))
    
    return {"batch_id": batch.id}


@app.get("/api/video/batches")
async def get_batches(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """获取当前用户的批次列表"""
    batches = task_manager.get_user_batches(user["user_id"], limit=limit, offset=offset)
    
    # 为每个批次添加文件 URL
    result = []
    for batch in batches:
        batch_dict = batch.to_dict()
        # 转换 items 中的 sourceImage 为 URL
        for item in batch_dict["items"]:
            if item["sourceImage"]:
                item["sourceImage"] = await data_manager.get_url(item["sourceImage"], "images")
        result.append(batch_dict)
    
    return {"batches": result, "total": len(result)}


@app.get("/api/video/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    user: dict = Depends(get_current_user),
):
    """获取特定批次的详细信息"""
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    
    # 检查权限
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    batch_dict = batch.to_dict()
    # 转换 items 中的 sourceImage 为 URL
    for item in batch_dict["items"]:
        if item["sourceImage"]:
            item["sourceImage"] = await data_manager.get_url(item["sourceImage"], "images")
    
    return batch_dict


@app.get("/api/video/batches/{batch_id}/export")
async def export_batch_videos(
    batch_id: str,
    user: dict = Depends(get_current_user),
):
    """导出批次的所有已完成视频为zip文件"""
    from server.task_manager import VideoItemStatus
    
    batch = task_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found"
        )
    
    # 检查权限
    if batch.user_id != user["user_id"] and not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # 获取所有已完成的视频项（检查 video_url 或 video_filename）
    completed_items = [
        item for item in batch.items 
        if item.status == VideoItemStatus.COMPLETED and (item.video_url or item.video_filename)
    ]
    
    if not completed_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed videos to export"
        )
    
    # 创建临时zip文件
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    temp_zip_path = temp_zip.name
    temp_zip.close()
    
    try:
        import aiohttp
        
        # 创建zip文件并添加视频
        added_count = 0
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            async with aiohttp.ClientSession() as session:
                for item in completed_items:
                    try:
                        video_data = None
                        file_ext = '.mp4'
                        
                        # 优先使用 video_filename（本地或S3存储）
                        if item.video_filename:
                            try:
                                video_data = await data_manager.load_bytes(item.video_filename, "videos")
                                file_ext = os.path.splitext(item.video_filename)[1] or '.mp4'
                                logger.info(f"Loaded video {item.id} from data_manager: {item.video_filename}")
                            except Exception as e:
                                logger.warning(f"Failed to load video {item.id} from data_manager: {e}, trying video_url")
                        
                        # 如果没有 video_filename 或加载失败，尝试从 video_url 下载
                        if not video_data and item.video_url:
                            try:
                                async with session.get(item.video_url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                                    if response.status == 200:
                                        video_data = await response.read()
                                        # 尝试从 URL 或 Content-Type 获取扩展名
                                        content_type = response.headers.get('Content-Type', '')
                                        if 'mp4' in content_type:
                                            file_ext = '.mp4'
                                        elif 'webm' in content_type:
                                            file_ext = '.webm'
                                        else:
                                            # 从 URL 提取扩展名
                                            url_path = item.video_url.split('?')[0]  # 移除查询参数
                                            url_ext = os.path.splitext(url_path)[1]
                                            if url_ext:
                                                file_ext = url_ext
                                        logger.info(f"Downloaded video {item.id} from URL: {item.video_url}")
                                    else:
                                        logger.error(f"Failed to download video {item.id} from URL: HTTP {response.status}")
                            except Exception as e:
                                logger.error(f"Failed to download video {item.id} from URL: {e}")
                        
                        # 如果成功获取视频数据，添加到zip
                        if video_data:
                            zip_filename = f"{item.id}{file_ext}"
                            # 确保文件名是字符串，并且使用 ZipInfo 来支持 UTF-8 编码
                            try:
                                # 尝试直接写入（适用于 ASCII 文件名）
                                zip_file.writestr(zip_filename, video_data)
                            except (UnicodeEncodeError, ValueError):
                                # 如果包含非 ASCII 字符，使用 ZipInfo 并设置 UTF-8 标志
                                zip_info = zipfile.ZipInfo(zip_filename)
                                # 设置 UTF-8 标志位（0x800 = UTF-8 encoding flag）
                                zip_info.flag_bits = 0x800
                                zip_file.writestr(zip_info, video_data)
                            added_count += 1
                            logger.info(f"Added video {item.id} to zip: {zip_filename}")
                        else:
                            logger.warning(f"Skipping video {item.id}: no video data available")
                            
                    except Exception as e:
                        logger.error(f"Failed to add video {item.id} to zip: {e}")
                        # 继续处理其他视频，不中断整个导出过程
        
        # 检查是否有视频被成功添加到zip
        if added_count == 0:
            # 清理临时文件
            try:
                os.unlink(temp_zip_path)
            except:
                pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No videos could be downloaded or loaded for export"
            )
        
        # 生成下载文件名（确保只包含 ASCII 字符）
        batch_name_safe = "".join(c for c in batch.name if c.isascii() and (c.isalnum() or c in (' ', '-', '_'))).rstrip()
        if not batch_name_safe:
            batch_name_safe = "batch"
        download_filename = f"{batch_name_safe}_{batch_id}.zip"
        
        # 获取zip文件大小
        zip_size = os.path.getsize(temp_zip_path)
        
        # 对文件名进行 URL 编码以支持非 ASCII 字符
        from urllib.parse import quote
        encoded_filename = quote(download_filename.encode('utf-8'))
        
        logger.info(f"Returning zip file: {download_filename}, size: {zip_size} bytes, added_count: {added_count}")
        
        # 在 Railway 环境中，使用 FileResponse 更可靠
        # 延迟清理临时文件，确保响应已发送
        import asyncio
        async def cleanup_file():
            await asyncio.sleep(10)  # 等待10秒确保响应已发送
            try:
                if os.path.exists(temp_zip_path):
                    os.unlink(temp_zip_path)
                    logger.debug(f"Cleaned up temp zip file: {temp_zip_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp zip file: {e}")
        asyncio.create_task(cleanup_file())
        
        # 使用 FileResponse，它会在文件发送完成后自动关闭文件句柄
        return FileResponse(
            temp_zip_path,
            media_type='application/zip',
            filename=download_filename,
            headers={
                'Content-Disposition': f'attachment; filename="{download_filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'X-Content-Type-Options': 'nosniff'
            }
        )
        
    except Exception as e:
        # 清理临时文件
        try:
            if os.path.exists(temp_zip_path):
                os.unlink(temp_zip_path)
        except:
            pass
        
        logger.error(f"Failed to create zip file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create zip file: {str(e)}"
        )


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
    """获取所有批次（系统历史）"""
    batches = task_manager.get_all_batches(limit=limit, offset=offset)
    logger.info(f"Admin requested all batches: found {len(batches)} batches")
    
    # 为每个批次添加文件 URL
    result = []
    for batch in batches:
        batch_dict = batch.to_dict()
        # 转换 items 中的 sourceImage 为 URL
        for item in batch_dict.get("items", []):
            # 兼容旧数据格式：可能是 sourceImage 或 source_image_filename
            source_image = item.get("sourceImage") or item.get("source_image_filename", "")
            if source_image:
                item["sourceImage"] = await data_manager.get_url(source_image, "images")
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

