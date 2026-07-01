import urllib.request
import urllib.parse
import re

def scrape_webpage(url: str) -> str:
    """
    Fetches the HTML of a webpage and extracts clean readable text.
    Uses Playwright if installed (for JS pages), falling back to urllib.
    """
    # 1. Try Playwright first
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=15000)
            text_content = page.evaluate("() => document.body.innerText")
            browser.close()
            return text_content.strip()
    except Exception:
        # Fallback to urllib if Playwright is not installed or errors
        pass
        
    # 2. Urllib fallback
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
            
        # Strip script and style blocks
        html = re.sub(r'<script[^>]*?>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*?>.*?</style>', '', html, flags=re.DOTALL)
        
        # Extract tag contents
        text = re.sub(r'<[^>]*>', ' ', html)
        
        # Clean whitespaces
        lines = [line.strip() for line in text.splitlines()]
        chunks = [phrase.strip() for line in lines for phrase in line.split("  ")]
        clean_text = "\n".join(chunk for chunk in chunks if chunk)
        
        # Truncate output to avoid blowing context limits
        if len(clean_text) > 8000:
            clean_text = clean_text[:8000] + "\n\n...[Page Content Truncated to 8000 Characters]..."
            
        return clean_text
        
    except Exception as e:
        return f"Error retrieving page: {e}"

if __name__ == "__main__":
    # Test read on simple page
    print(scrape_webpage("https://example.com")[:300])
