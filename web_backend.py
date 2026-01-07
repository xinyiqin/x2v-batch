"""
批量 S2V API 调用的 Web 后端服务
"""
import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import base64
import tempfile

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tools.s2v_client import S2VClient

app = FastAPI(title="S2V Batch API Service")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 任务存储（生产环境应该使用数据库）
tasks_db: Dict[str, Dict[str, Any]] = {}

# 全局客户端（从环境变量读取配置）
BASE_URL = os.getenv("LIGHTX2V_BASE_URL", "https://x2v.light-ai.top")
ACCESS_TOKEN = os.getenv("LIGHTX2V_ACCESS_TOKEN", "")

if not ACCESS_TOKEN:
    print("⚠️  警告: 未设置 LIGHTX2V_ACCESS_TOKEN 环境变量")


class TaskRequest(BaseModel):
    """单个任务请求"""
    prompt: str
    negative_prompt: Optional[str] = None
    cfg_scale: Optional[int] = 5
    duration: Optional[int] = 7
    seed: Optional[int] = None
    model_cls: Optional[str] = "SekoTalk"
    stage: Optional[str] = "single_stage"


class BatchTaskRequest(BaseModel):
    """批量任务请求"""
    tasks: List[TaskRequest]
    wait_for_completion: Optional[bool] = False
    poll_interval: Optional[int] = 5
    timeout: Optional[int] = 3600


def save_upload_file(upload_file: UploadFile) -> Path:
    """保存上传的文件到临时目录"""
    temp_dir = Path(tempfile.gettempdir()) / "s2v_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = temp_dir / f"{uuid.uuid4()}_{upload_file.filename}"
    with open(file_path, "wb") as f:
        content = upload_file.file.read()
        f.write(content)
    
    return file_path


async def process_single_task(
    task_req: TaskRequest,
    image_file: Optional[UploadFile],
    audio_file: Optional[UploadFile],
    task_id: str,
    wait_for_completion: bool = False,
    poll_interval: int = 5,
    timeout: int = 3600
) -> Dict[str, Any]:
    """处理单个任务"""
    client = S2VClient(base_url=BASE_URL, access_token=ACCESS_TOKEN)
    
    try:
        # 保存上传的文件
        image_path = None
        audio_path = None
        
        if image_file:
            image_path = save_upload_file(image_file)
        if audio_file:
            audio_path = save_upload_file(audio_file)
        
        # 更新任务状态
        tasks_db[task_id]["status"] = "SUBMITTING"
        tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
        
        # 提交任务
        submit_result = await client.submit_task(
            task="s2v",
            model_cls=task_req.model_cls,
            stage=task_req.stage,
            prompt=task_req.prompt,
            negative_prompt=task_req.negative_prompt,
            cfg_scale=task_req.cfg_scale,
            duration=task_req.duration,
            seed=task_req.seed,
            input_image_path=str(image_path) if image_path else None,
            input_audio_path=str(audio_path) if audio_path else None,
        )
        
        if not submit_result.get("success"):
            tasks_db[task_id]["status"] = "FAILED"
            tasks_db[task_id]["error"] = submit_result.get("error", "Unknown error")
            tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
            return tasks_db[task_id]
        
        api_task_id = submit_result["task_id"]
        tasks_db[task_id]["api_task_id"] = api_task_id
        tasks_db[task_id]["status"] = "PENDING"
        tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
        
        # 如果需要等待完成
        if wait_for_completion:
            tasks_db[task_id]["status"] = "PROCESSING"
            tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
            
            final_result = await client.wait_for_task(
                api_task_id,
                poll_interval=poll_interval,
                timeout=timeout
            )
            
            if final_result.get("success"):
                status = final_result.get("status", "UNKNOWN")
                tasks_db[task_id]["status"] = status
                tasks_db[task_id]["api_status"] = status
                
                if status == "SUCCEED":
                    result_url = await client.get_result_url(api_task_id, name="output_video")
                    tasks_db[task_id]["result_url"] = result_url
            else:
                tasks_db[task_id]["status"] = "FAILED"
                tasks_db[task_id]["error"] = final_result.get("error", "Unknown error")
            
            tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
        
        # 清理临时文件
        if image_path and image_path.exists():
            image_path.unlink()
        if audio_path and audio_path.exists():
            audio_path.unlink()
        
        return tasks_db[task_id]
        
    except Exception as e:
        tasks_db[task_id]["status"] = "FAILED"
        tasks_db[task_id]["error"] = str(e)
        tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
        return tasks_db[task_id]
    finally:
        client.close()


@app.post("/api/submit")
async def submit_task(
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    cfg_scale: int = Form(5),
    duration: int = Form(7),
    seed: Optional[int] = Form(None),
    model_cls: str = Form("SekoTalk"),
    stage: str = Form("single_stage"),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    wait_for_completion: bool = Form(False),
):
    """提交单个任务"""
    task_id = str(uuid.uuid4())
    
    tasks_db[task_id] = {
        "task_id": task_id,
        "status": "CREATED",
        "prompt": prompt,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    task_req = TaskRequest(
        prompt=prompt,
        negative_prompt=negative_prompt,
        cfg_scale=cfg_scale,
        duration=duration,
        seed=seed,
        model_cls=model_cls,
        stage=stage,
    )
    
    # 异步处理任务
    asyncio.create_task(
        process_single_task(
            task_req,
            image,
            audio,
            task_id,
            wait_for_completion=wait_for_completion,
        )
    )
    
    return {"task_id": task_id, "status": "CREATED"}


@app.post("/api/batch-submit")
async def batch_submit(
    tasks: List[TaskRequest],
    wait_for_completion: bool = False,
    poll_interval: int = 5,
    timeout: int = 3600,
):
    """批量提交任务（注意：这个接口需要文件，建议使用单个提交接口）"""
    task_ids = []
    
    for task_req in tasks:
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        
        tasks_db[task_id] = {
            "task_id": task_id,
            "status": "CREATED",
            "prompt": task_req.prompt,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        # 注意：批量接口无法直接处理文件上传
        # 建议使用单个提交接口循环调用
        asyncio.create_task(
            process_single_task(
                task_req,
                None,  # 批量接口不支持文件上传
                None,
                task_id,
                wait_for_completion=wait_for_completion,
                poll_interval=poll_interval,
                timeout=timeout,
            )
        )
    
    return {"task_ids": task_ids, "count": len(task_ids)}


@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    """查询任务状态"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks_db[task_id]
    
    # 如果任务还在处理中，尝试查询最新状态
    if task["status"] in ["PENDING", "PROCESSING"]:
        api_task_id = task.get("api_task_id")
        if api_task_id:
            client = S2VClient(base_url=BASE_URL, access_token=ACCESS_TOKEN)
            try:
                result = await client.query_task(api_task_id)
                if result.get("success"):
                    status = result.get("status", "UNKNOWN")
                    task["api_status"] = status
                    if status in ["SUCCEED", "FAILED", "CANCELLED"]:
                        task["status"] = status
                        if status == "SUCCEED":
                            result_url = await client.get_result_url(api_task_id, name="output_video")
                            task["result_url"] = result_url
                    task["updated_at"] = datetime.now().isoformat()
            finally:
                client.close()
    
    return task


@app.get("/api/tasks")
async def list_tasks(limit: int = 50, offset: int = 0):
    """列出所有任务"""
    tasks = list(tasks_db.values())
    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "tasks": tasks[offset:offset + limit],
        "total": len(tasks),
        "limit": limit,
        "offset": offset,
    }


@app.delete("/api/task/{task_id}")
async def cancel_task(task_id: str):
    """取消任务"""
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks_db[task_id]
    api_task_id = task.get("api_task_id")
    
    if api_task_id:
        client = S2VClient(base_url=BASE_URL, access_token=ACCESS_TOKEN)
        try:
            success = await client.cancel_task(api_task_id)
            if success:
                task["status"] = "CANCELLED"
                task["updated_at"] = datetime.now().isoformat()
        finally:
            client.close()
    
    return {"success": True, "task_id": task_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

