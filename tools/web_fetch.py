# -*- coding: utf-8 -*-
"""
网页内容获取工具

用于获取指定 URL 的网页内容，包括 HTML、文本、标题等信息
"""

import os
import json
import requests
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from loguru import logger

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("BeautifulSoup4 is not installed. Install it with: pip install beautifulsoup4")


def fetch_webpage(
    url: str,
    timeout: int = 30,
    extract_text: bool = True,
    extract_links: bool = False,
    user_agent: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    获取网页内容
    
    Args:
        url: 要获取的网页 URL
        timeout: 请求超时时间（秒），默认 30
        extract_text: 是否提取纯文本内容（去除 HTML 标签），默认 True
        extract_links: 是否提取页面中的所有链接，默认 False
        user_agent: 自定义 User-Agent，默认使用常见的浏览器 User-Agent
        headers: 自定义请求头
        
    Returns:
        包含网页信息的字典：
        {
            "status": "success" | "failed",
            "url": "原始 URL",
            "title": "页面标题",
            "html": "HTML 内容（如果 extract_text=False）",
            "text": "纯文本内容（如果 extract_text=True）",
            "links": ["链接列表（如果 extract_links=True）"],
            "meta": {
                "description": "页面描述",
                "keywords": "关键词",
                ...
            },
            "status_code": HTTP 状态码,
            "content_type": "内容类型",
            "error": "错误信息（如果失败）"
        }
    """
    if not url or not isinstance(url, str) or not url.strip():
        return {
            "status": "failed",
            "error": "URL is required and must be a non-empty string"
        }
    
    # 确保 URL 有协议
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    # 设置默认 User-Agent
    default_headers = {
        "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    if headers:
        default_headers.update(headers)
    
    try:
        logger.info(f"Fetching webpage: {url}")
        response = requests.get(url, headers=default_headers, timeout=timeout)
        response.raise_for_status()
        
        # 检查内容类型
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return {
                "status": "failed",
                "error": f"Content type is not HTML: {content_type}",
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type
            }
        
        html_content = response.text
        result = {
            "status": "success",
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content_length": len(html_content)
        }
        
        # 如果安装了 BeautifulSoup，进行内容提取
        if BS4_AVAILABLE:
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                
                # 提取标题
                title_tag = soup.find("title")
                result["title"] = title_tag.get_text(strip=True) if title_tag else ""
                
                # 提取 meta 信息
                meta_info = {}
                meta_tags = soup.find_all("meta")
                for meta in meta_tags:
                    name = meta.get("name") or meta.get("property")
                    content = meta.get("content")
                    if name and content:
                        meta_info[name.lower()] = content
                
                # 提取 description
                description = (
                    meta_info.get("description") or
                    meta_info.get("og:description") or
                    meta_info.get("twitter:description") or
                    ""
                )
                if description:
                    meta_info["description"] = description
                
                result["meta"] = meta_info
                
                # 提取纯文本
                if extract_text:
                    # 移除 script 和 style 标签
                    for script in soup(["script", "style", "noscript"]):
                        script.decompose()
                    
                    # 获取文本内容
                    text = soup.get_text(separator="\n", strip=True)
                    # 清理多余的空白行
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    result["text"] = "\n".join(lines)
                else:
                    result["html"] = html_content
                
                # 提取链接
                if extract_links:
                    links = []
                    for link in soup.find_all("a", href=True):
                        href = link.get("href")
                        text = link.get_text(strip=True)
                        # 处理相对链接
                        if href.startswith("/"):
                            parsed_url = urlparse(url)
                            href = f"{parsed_url.scheme}://{parsed_url.netloc}{href}"
                        elif not href.startswith(("http://", "https://")):
                            continue
                        links.append({
                            "url": href,
                            "text": text
                        })
                    result["links"] = links
                
            except Exception as e:
                logger.warning(f"Failed to parse HTML with BeautifulSoup: {e}")
                # 如果解析失败，返回原始 HTML
                result["html"] = html_content
                result["title"] = ""
                result["text"] = ""
                result["meta"] = {}
        else:
            # 如果没有 BeautifulSoup，返回原始 HTML
            result["html"] = html_content
            result["title"] = ""
            result["text"] = ""
            result["meta"] = {}
            if extract_text:
                logger.warning("BeautifulSoup4 is not installed. Cannot extract text. Install it with: pip install beautifulsoup4")
        
        return result
        
    except requests.exceptions.Timeout:
        return {
            "status": "failed",
            "error": f"Request timeout after {timeout} seconds",
            "url": url
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "failed",
            "error": f"Request failed: {str(e)}",
            "url": url
        }
    except Exception as e:
        logger.error(f"Unexpected error fetching webpage: {e}")
        return {
            "status": "failed",
            "error": f"Unexpected error: {str(e)}",
            "url": url
        }


def fetch_webpage_simple(url: str, timeout: int = 30) -> str:
    """
    简单获取网页文本内容（便捷函数）
    
    Args:
        url: 要获取的网页 URL
        timeout: 请求超时时间（秒），默认 30
        
    Returns:
        网页的纯文本内容，如果失败则返回错误信息
    """
    result = fetch_webpage(url, timeout=timeout, extract_text=True)
    if result.get("status") == "success":
        return result.get("text", "")
    else:
        return f"Error: {result.get('error', 'Unknown error')}"


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python web_fetch.py <url> [--extract-links] [--html-only]")
        print("\nExample:")
        print("  python web_fetch.py https://example.com")
        print("  python web_fetch.py https://example.com --extract-links")
        print("  python web_fetch.py https://example.com --html-only")
        sys.exit(1)
    
    url = sys.argv[1]
    extract_links = "--extract-links" in sys.argv
    html_only = "--html-only" in sys.argv
    
    result = fetch_webpage(
        url,
        extract_text=not html_only,
        extract_links=extract_links
    )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))



