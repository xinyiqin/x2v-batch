import os
import json
import time
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from duckduckgo_search import DDGS

load_dotenv()


def web_search(
    query: str,
    num_results: int = 5,
    timeout_seconds: int = 20,
    region: str = "us-en",  # Default to US English
    safesearch: str = "moderate",
) -> Dict[str, Any]:

    if not query or not isinstance(query, str) or not query.strip():
        return {
            "status": "failed",
            "error": {
                "error_type": "USER_INPUT_VALIDATION_ERROR",
                "error_code": "INVALID_QUERY",
                "technical_message": "A valid, non-empty search query is required."
            }
        }

    # Try DuckDuckGo first
    try:
        print(f"🔍 Trying DuckDuckGo search (region: {region})...")
        search_results = []
        with DDGS(timeout=float(timeout_seconds)) as ddgs:
            # Use text() with region and safesearch parameters
            for i, item in enumerate(ddgs.text(
                keywords=query, 
                max_results=num_results,
                region=region,
                safesearch=safesearch
            )):
                if i >= num_results:
                    break
                # Filter out low-quality results
                title = str(item.get("title", "N/A"))
                body = str(item.get("body", "N/A"))
                href = str(item.get("href", "#"))
                
                # Skip if title or body is too short or seems irrelevant
                if len(title) < 5 or len(body) < 20:
                    continue
                    
                search_results.append({
                    "title": title,
                    "snippet": body,
                    "link": href
                })
                
                # Stop if we have enough results
                if len(search_results) >= num_results:
                    break

        result = {
            "status": "success",
            "data": {
                "engine": "duckduckgo",
                "query": query,
                "num_results_requested": num_results,
                "num_results_returned": len(search_results),
                "results_json_string": json.dumps(search_results, ensure_ascii=False)
            }
        }

    except Exception as e:
        print(f"⚠️ DuckDuckGo failed: {e}\n⏭️ Falling back to Brave...")
        api_key = os.environ.get("BRAVE_API_KEY","BSAdnotPtb1IsFqlIcLAUswod4pu70V")
        if not api_key:
            return {
                "status": "failed",
                "error": {
                    "error_type": "CONFIGURATION_ERROR",
                    "error_code": "MISSING_API_KEY",
                    "technical_message": "BRAVE_API_KEY not set."
                }
            }

        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": api_key
            }
            params = {
                "q": query,
                "count": num_results,
                "search_lang": "en",  # Force English results
                "country": "us",  # US region
                "safesearch": "moderate"
            }
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=timeout_seconds
            )
            response.raise_for_status()

            raw_results = response.json().get("web", {}).get("results", [])
            search_results = []
            for r in raw_results:
                title = r.get("title", "N/A")
                description = r.get("description", "N/A")
                url = r.get("url", "#")
                
                # Filter out low-quality results
                if len(title) < 5 or len(description) < 20:
                    continue
                    
                search_results.append({
                    "title": title,
                    "snippet": description,
                    "link": url
                })
                
                if len(search_results) >= num_results:
                    break

            result = {
                "status": "success",
                "data": {
                    "engine": "brave",
                    "query": query,
                    "num_results_requested": num_results,
                    "num_results_returned": len(search_results),
                    "results_json_string": json.dumps(search_results, ensure_ascii=False)
                }
            }

        except Exception as be:
            return {
                "status": "failed",
                "error": {
                    "error_type": "HTTP_REQUEST_ERROR",
                    "error_code": "FALLBACK_FAILED",
                    "technical_message": f"Web Search Failed: {be}"
                }
            }

    return result

if __name__ == "__main__":
    response = web_search(
        "United States economy", 
        num_results=5,
        # save_path="./search/search_results.json"
        )
    print(json.dumps(response, indent=2, ensure_ascii=False))
