#!/usr/bin/env python3
"""
测试前后端连接
"""
import requests
import json

API_BASE = "http://localhost:8000"

def test_backend():
    """测试后端是否运行"""
    print("🔍 测试后端连接...")
    try:
        response = requests.get(f"{API_BASE}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ 后端服务运行正常")
            return True
        else:
            print(f"❌ 后端响应异常: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到后端服务，请确保后端已启动")
        print("   启动命令: python -m server.main")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_login():
    """测试登录接口"""
    print("\n🔍 测试登录接口...")
    try:
        data = {
            "username": "admin",
            "password": "admin8888"
        }
        response = requests.post(
            f"{API_BASE}/api/auth/login",
            data=data,
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            print("✅ 登录成功")
            print(f"   Token: {result['token'][:50]}...")
            print(f"   用户: {result['user_info']['username']}")
            print(f"   点数: {result['user_info']['credits']}")
            return result['token']
        else:
            print(f"❌ 登录失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 登录测试失败: {e}")
        return None

def test_authenticated_api(token):
    """测试需要认证的接口"""
    print("\n🔍 测试认证接口...")
    try:
        headers = {
            "Authorization": f"Bearer {token}"
        }
        response = requests.get(
            f"{API_BASE}/api/user/profile",
            headers=headers,
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            print("✅ 认证接口正常")
            print(f"   用户信息: {result}")
            return True
        else:
            print(f"❌ 认证接口失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 认证测试失败: {e}")
        return False

def main():
    print("=" * 50)
    print("前后端连接测试")
    print("=" * 50)
    
    # 测试后端
    if not test_backend():
        return
    
    # 测试登录
    token = test_login()
    if not token:
        return
    
    # 测试认证接口
    test_authenticated_api(token)
    
    print("\n" + "=" * 50)
    print("✅ 所有测试完成")
    print("=" * 50)

if __name__ == "__main__":
    main()

