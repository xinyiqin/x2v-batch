"""
主应用文件 - FastAPI 服务器
"""
import os
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
import uvicorn

from server.auth import AuthManager
from server.data_manager import LocalDataManager
from server.task_manager import TaskManager
from server.batch_processor import BatchProcessor

# 初始化组件
auth_manager = AuthManager()
data_manager = LocalDataManager(base_dir="./data")
task_manager = TaskManager(storage_dir="./data/batches")

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
    
    # 保存图片文件
    image_filenames = []
    for img in images:
        img_data = await img.read()
        img_filename = f"{user['user_id']}_{img.filename}"
        await data_manager.save_image(img_data, img_filename)
        image_filenames.append(img_filename)
    
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


# ==================== 管理员接口 ====================

@app.get("/api/admin/users")
async def get_all_users(admin: dict = Depends(get_current_admin)):
    """获取所有用户列表"""
    users = auth_manager.get_all_users()
    return {"users": users}


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

