"""
认证管理 - 用户认证和授权
"""
import hashlib
import secrets
import jwt
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import json
from loguru import logger


class AuthManager:
    """认证管理器"""
    
    def __init__(self, secret_key: Optional[str] = None, storage_file: str = "./data/users.json", data_manager=None):
        """
        初始化认证管理器
        
        Args:
            secret_key: JWT 密钥
            storage_file: 用户数据存储文件（当不使用 data_manager 时）
            data_manager: 数据管理器（可选，如果提供则使用它存储 JSON）
        """
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_manager = data_manager
        self.storage_filename = "users.json"
        
        # 加载用户数据
        self._users: Dict[str, Dict[str, Any]] = {}
        self._load_users()
        
        # 创建默认管理员账户
        if "admin" not in self._users:
            self.create_user("admin", "admin", is_admin=True, credits=9999)
        
        logger.info(f"AuthManager initialized with {len(self._users)} users (storage: {'S3' if data_manager else 'local'})")
    
    def _load_users(self):
        """从存储加载用户数据（支持本地文件或 S3）"""
        if self.data_manager:
            # 使用 DataManager（可能是 S3）
            try:
                # 检查是否有事件循环在运行
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果循环正在运行，创建任务（但这在同步方法中可能有问题）
                        # 使用 run_coroutine_threadsafe 或直接同步调用
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(self._load_users_async)
                            data = future.result()
                    else:
                        data = loop.run_until_complete(self._load_users_async())
                except RuntimeError:
                    # 没有事件循环，创建一个新的
                    data = asyncio.run(self._load_users_async())
                
                if data:
                    self._users = json.loads(data.decode('utf-8'))
                else:
                    self._users = {}
            except Exception as e:
                logger.error(f"Failed to load users from data_manager: {e}")
                self._users = {}
        else:
            # 使用本地文件
            if self.storage_file.exists():
                try:
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        self._users = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load users: {e}")
                    self._users = {}
    
    async def _load_users_async(self) -> bytes:
        """异步加载用户数据"""
        try:
            # users.json 存储在根目录，不使用子目录
            if await self.data_manager.file_exists(self.storage_filename):
                return await self.data_manager.load_bytes(self.storage_filename)
            return None
        except Exception as e:
            logger.error(f"Failed to load users from S3: {e}")
            return None
    
    def _save_users(self):
        """保存用户数据到存储（支持本地文件或 S3）"""
        if self.data_manager:
            # 使用 DataManager（可能是 S3）
            try:
                data = json.dumps(self._users, ensure_ascii=False, indent=2).encode('utf-8')
                # 检查是否有事件循环在运行
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(asyncio.run, self._save_users_async(data))
                            future.result()
                    else:
                        loop.run_until_complete(self._save_users_async(data))
                except RuntimeError:
                    asyncio.run(self._save_users_async(data))
            except Exception as e:
                logger.error(f"Failed to save users to data_manager: {e}")
        else:
            # 使用本地文件
            try:
                with open(self.storage_file, "w", encoding="utf-8") as f:
                    json.dump(self._users, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to save users: {e}")
    
    async def _save_users_async(self, data: bytes):
        """异步保存用户数据"""
        try:
            # users.json 存储在根目录，不使用子目录
            await self.data_manager.save_bytes(data, self.storage_filename)
        except Exception as e:
            logger.error(f"Failed to save users to S3: {e}")
            raise
    
    def _hash_password(self, password: str) -> str:
        """哈希密码"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(
        self,
        username: str,
        password: str,
        is_admin: bool = False,
        credits: int = 100,
    ) -> Dict[str, Any]:
        """
        创建用户
        
        Returns:
            用户信息字典
        """
        if username in self._users:
            raise ValueError(f"User {username} already exists")
        
        user_id = f"u-{len(self._users) + 1}"
        user_data = {
            "id": user_id,
            "username": username,
            "password_hash": self._hash_password(password),
            "credits": credits,
            "is_admin": is_admin,
            "created_at": datetime.now().isoformat(),
        }
        
        self._users[username] = user_data
        self._save_users()
        
        logger.info(f"Created user: {username}")
        return user_data
    
    def verify_password(self, username: str, password: str) -> bool:
        """验证密码"""
        user = self._users.get(username)
        if not user:
            return False
        
        password_hash = self._hash_password(password)
        return user["password_hash"] == password_hash
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """获取用户信息（不包含密码）"""
        user = self._users.get(username)
        if not user:
            return None
        
        return {
            "id": user["id"],
            "username": user["username"],
            "credits": user["credits"],
            "isAdmin": user["is_admin"],
        }
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """根据用户ID获取用户信息"""
        for user in self._users.values():
            if user["id"] == user_id:
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "credits": user["credits"],
                    "isAdmin": user["is_admin"],
                }
        return None
    
    def update_user_credits(self, user_id: str, new_credits: int) -> bool:
        """更新用户点数"""
        for user in self._users.values():
            if user["id"] == user_id:
                user["credits"] = new_credits
                self._save_users()
                logger.info(f"Updated credits for user {user_id}: {new_credits}")
                return True
        return False
    
    def deduct_credits(self, user_id: str, amount: int) -> bool:
        """扣除用户点数"""
        for user in self._users.values():
            if user["id"] == user_id:
                if user["credits"] < amount:
                    return False
                user["credits"] -= amount
                self._save_users()
                logger.info(f"Deducted {amount} credits from user {user_id}, remaining: {user['credits']}")
                return True
        return False
    
    def get_all_users(self) -> list:
        """获取所有用户信息"""
        return [
            {
                "id": user["id"],
                "username": user["username"],
                "credits": user["credits"],
                "isAdmin": user["is_admin"],
            }
            for user in self._users.values()
        ]
    
    def generate_token(self, user: Dict[str, Any]) -> str:
        """生成 JWT token"""
        payload = {
            "user_id": user["id"],
            "username": user["username"],
            "is_admin": user.get("isAdmin", False),
            "exp": datetime.utcnow() + timedelta(days=7),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证 JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return {
                "user_id": payload["user_id"],
                "username": payload["username"],
                "is_admin": payload.get("is_admin", False),
            }
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """
        修改用户密码
        
        Args:
            username: 用户名
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            是否成功
        """
        if not self.verify_password(username, old_password):
            return False
        
        if username not in self._users:
            return False
        
        # 更新密码
        self._users[username]["password_hash"] = self._hash_password(new_password)
        self._save_users()
        
        logger.info(f"Password changed for user: {username}")
        return True

