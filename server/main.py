"""
主应用文件 - FastAPI 服务器
"""
import os
import asyncio
import json
import zipfile
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
import uvicorn

from server.auth import AuthManager
from server.data_manager import LocalDataManager
from server.task_manager import TaskManager
from server.batch_processor import BatchProcessor

# 延迟导入 S3DataManager，只在需要时导入
S3DataManager = None

# 初始化数据目录（仅用于本地存储）
def init_data_directory():
    """初始化数据目录和初始数据（仅用于本地存储）"""
    # 检查存储类型，如果是 S3 则跳过本地目录初始化
    storage_type = os.getenv("STORAGE_TYPE", "local").lower()
    if storage_type == "s3":
        logger.info("Using S3 storage, skipping local data directory initialization")
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
        
        # 创建子目录
        for subdir in ["images", "audios", "videos", "batches"]:
            (base_path / subdir).mkdir(parents=True, exist_ok=True)
        
        # 初始化 users.json（如果不存在，仅用于本地存储）
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
            logger.info("✅ Created default users.json with admin user (local storage)")
    except Exception as e:
        logger.warning(f"Failed to initialize data directory: {e}")

# 初始化数据目录（仅用于本地存储）
init_data_directory()

# 初始化组件
data_dir = os.getenv("DATA_DIR", "./data")

# 选择数据管理器：S3 或本地
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
            logger.info("Using S3DataManager for storage (will initialize on startup)")
        except ImportError as e:
            logger.error(f"Failed to import S3DataManager: {e}. Please install aioboto3: pip install aioboto3")
            logger.warning("Falling back to local storage")
            data_manager = LocalDataManager(base_dir=data_dir)
else:
    data_manager = LocalDataManager(base_dir=data_dir)
    logger.info(f"Using LocalDataManager for storage (base_dir: {data_dir})")

# 初始化 AuthManager 和 TaskManager，传入 data_manager 以支持 S3 存储 JSON
auth_manager = AuthManager(data_manager=data_manager)
task_manager = TaskManager(storage_dir=f"{data_dir}/batches", data_manager=data_manager)

# S2V API 配置
S2V_BASE_URL = os.getenv("LIGHTX2V_BASE_URL", "https://x2v.light-ai.top")
S2V_ACCESS_TOKEN = os.getenv("LIGHTX2V_ACCESS_TOKEN", "")

if not S2V_ACCESS_TOKEN:
    logger.warning("⚠️  LIGHTX2V_ACCESS_TOKEN not set, batch processing will fail")

batch_processor = BatchProcessor(
    task_manager=task_manager,
    data_manager=data_manager,
    base_url=S2V_BASE_URL,
    access_token=S2V_ACCESS_TOKEN,
)

# FastAPI 应用
app = FastAPI(title="AI Vision Batch Service")

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化 S3 连接和加载数据"""
    # 检查是否是 S3DataManager（需要动态检查，因为可能延迟导入）
    if hasattr(data_manager, 'init') and callable(getattr(data_manager, 'init', None)):
        try:
            await data_manager.init()
            logger.info("S3DataManager initialized successfully")
        except AttributeError:
            # 不是 S3DataManager，跳过
            pass
    
    # 如果是 S3 存储，异步加载用户和批次数据
    if STORAGE_TYPE == "s3":
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
    # 检查是否是 S3DataManager（需要动态检查）
    if hasattr(data_manager, 'close') and callable(getattr(data_manager, 'close', None)):
        try:
            await data_manager.close()
            logger.info("S3DataManager closed")
        except AttributeError:
            # 不是 S3DataManager，跳过
            pass

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
    
    if not S2V_ACCESS_TOKEN:
        return {"valid": False, "error": "Token not configured"}
    
    try:
        # 尝试调用一个简单的 API 端点来验证 token
        # 使用 /api/v1/model/list 或类似的端点
        url = f"{S2V_BASE_URL}/api/v1/model/list"
        headers = {
            "Authorization": f"Bearer {S2V_ACCESS_TOKEN}",
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
    
    if not auth_manager.change_password(username, old_password, new_password):
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
    
    # 检查用户点数
    user_info = auth_manager.get_user_by_id(user["user_id"])
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    required_credits = len(images)
    if user_info["credits"] < required_credits:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient credits. Required: {required_credits}, Available: {user_info['credits']}"
        )
    
    # 保存音频文件
    audio_data = await audio.read()
    audio_filename = f"{user['user_id']}_{audio.filename}"
    await data_manager.save_audio(audio_data, audio_filename)
    
    # 并发保存所有图片文件以提高速度
    async def save_single_image(img: UploadFile) -> str:
        """保存单张图片并返回文件名"""
        img_data = await img.read()
        img_filename = f"{user['user_id']}_{img.filename}"
        await data_manager.save_image(img_data, img_filename)
        return img_filename
    
    # 使用 asyncio.gather 并发上传所有图片
    image_filenames = await asyncio.gather(*[save_single_image(img) for img in images])
    
    # 扣除点数
    auth_manager.deduct_credits(user["user_id"], required_credits)
    
    # 创建批次
    batch_name = f"批次 {user_info['username']} {asyncio.get_event_loop().time()}"
    batch = task_manager.create_batch(
        user_id=user["user_id"],
        user_name=user_info["username"],
        name=batch_name,
        prompt=prompt,
        audio_filename=audio_filename,
        image_filenames=image_filenames,
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
        
        # 创建生成器函数来流式传输文件（分块读取，避免内存问题）
        def generate():
            try:
                with open(temp_zip_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)  # 8KB chunks for better streaming
                        if not chunk:
                            break
                        yield chunk
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_zip_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp zip file: {e}")
        
        return StreamingResponse(
            generate(),
            media_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{download_filename}"; filename*=UTF-8\'\'{encoded_filename}',
                'Content-Length': str(zip_size),
                'Cache-Control': 'no-cache',
                'Accept-Ranges': 'bytes'
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
        user_data = auth_manager.create_user(
            username=username,
            password=default_password,
            is_admin=is_admin,
            credits=credits
        )
        
        # 如果是 S3 存储，需要异步保存
        if STORAGE_TYPE == "s3" and auth_manager.data_manager:
            users_data = json.dumps(auth_manager._users, ensure_ascii=False, indent=2).encode('utf-8')
            await auth_manager._save_users_async(users_data)
        
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
    """更新用户点数"""
    if new_credits < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credits must be non-negative"
        )
    
    success = auth_manager.update_user_credits(user_id, new_credits)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"success": True, "user_id": user_id, "credits": new_credits}


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

