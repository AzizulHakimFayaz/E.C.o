import urllib.parse
import urllib.request
import re

def web_search(query: str, num_results: int = 5) -> list[dict]:
    """
    Performs a web search using DuckDuckGo HTML endpoint and parses result listings.
    No API keys needed.
    """
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
            
        # Parse HTML results blocks using regex
        # Results are grouped inside blocks with class="result"
        result_blocks = re.findall(r'<div class="result[^"]*">(.*?)</div>\s*</div>', html, re.DOTALL)
        
        parsed_results = []
        for block in result_blocks:
            # 1. Extract URL and Title
            link_match = re.search(r'<a class="result__url"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
            # Alternatively look for result__snippet and result__snippet
            snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
            
            if not link_match:
                # Fallback matching
                link_match = re.search(r'<a class="result__link"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
                
            if link_match:
                href = link_match.group(1)
                title = link_match.group(2)
                
                # Unquote URL parameters if it's a DuckDuckGo redirects URL
                # e.g., //duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com
                if "uddg=" in href:
                    parsed_params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if "uddg" in parsed_params:
                        href = parsed_params["uddg"][0]
                elif href.startswith("//"):
                    href = "https:" + href
                    
                # Clean title tags
                title = re.sub(r'<[^>]*>', '', title).strip()
                
                snippet = ""
                if snippet_match:
                    snippet = snippet_match.group(1)
                    snippet = re.sub(r'<[^>]*>', '', snippet).strip()
                    
                parsed_results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet
                })
                
                if len(parsed_results) >= num_results:
                    break
                    
        return parsed_results
        
    except Exception as e:
        print(f"[Web Search Tool] Error searching: {e}")
        return []

if __name__ == "__main__":
    # Quick self-test
    res = web_search("Bengali NLP state of the art 2026")
    for idx, r in enumerate(res, 1):
        print(f"{idx}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n")
