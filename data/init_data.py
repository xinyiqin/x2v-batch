"""
初始化数据脚本 - 用于首次部署时创建初始数据
"""
import json
import os
from pathlib import Path

def init_data(base_dir: str = "./data"):
    """初始化数据目录和初始数据"""
    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    
    # 创建子目录
    for subdir in ["images", "audios", "videos", "batches"]:
        (base_path / subdir).mkdir(parents=True, exist_ok=True)
    
    # 初始化 users.json（如果不存在）
    users_file = base_path / "users.json"
    if not users_file.exists():
        import hashlib
        # 使用 SHA256 哈希（与 AuthManager 一致）
        def hash_password(password: str) -> str:
            return hashlib.sha256(password.encode()).hexdigest()
        
        default_users = {
            "admin": {
                "id": "u-0",
                "username": "admin",
                "password_hash": hash_password("admin8888"),
                "credits": 9999,
                "is_admin": True,
                "created_at": "2026-01-01T00:00:00"
            },
            "user1": {
                "id": "u-1",
                "username": "user1",
                "password_hash": hash_password("lightx2v9999"),
                "credits": 10,
                "is_admin": False,
                "created_at": "2026-01-01T00:00:00"
            }
        }
        with open(users_file, "w", encoding="utf-8") as f:
            json.dump(default_users, f, indent=2, ensure_ascii=False)
        print(f"✅ Created default users.json at {users_file}")
        print("   Default users:")
        print("   - admin / admin8888 (管理员, 9999 点数)")
        print("   - user1 / lightx2v9999 (普通用户, 10 点数)")
    
    # 初始化空的 batches 目录（如果为空）
    batches_dir = base_path / "batches"
    if not any(batches_dir.iterdir()):
        print(f"✅ Batches directory is empty (ready for new batches)")
    
    print(f"✅ Data directory initialized at {base_path.absolute()}")

if __name__ == "__main__":
    # 从环境变量获取数据目录，默认为 ./data
    data_dir = os.getenv("DATA_DIR", "./data")
    init_data(data_dir)

