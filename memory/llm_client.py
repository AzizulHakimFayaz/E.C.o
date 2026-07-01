import requests
import json
import time
from memory.config import load_config

def call_llm(messages: list[dict], system_prompt: str = None) -> str:
    """
    Sends chat completion request to the active LLM provider (Ollama or Groq).
    """
    config = load_config()
    provider = config.get("active_provider", "ollama")
    
    formatted_messages = []
    if system_prompt:
        formatted_messages.append({"role": "system", "content": system_prompt})
    formatted_messages.extend(messages)
    
    try:
        if provider == "groq":
            api_key = config.get("groq_api_key")
            if not api_key:
                raise ValueError("Groq API Key is missing in settings.json.")
            
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # Map tool messages to user messages to avoid 400 Bad Request
            groq_messages = []
            for msg in formatted_messages:
                if msg.get("role") == "tool":
                    tool_name = msg.get("name", "tool")
                    groq_messages.append({
                        "role": "user",
                        "content": f"[Tool Output: {tool_name}]\n{msg.get('content')}"
                    })
                else:
                    groq_messages.append(msg)
                    
            # Consolidate consecutive messages with the same role to avoid Groq 400 Bad Request
            consolidated_messages = []
            for msg in groq_messages:
                if consolidated_messages and consolidated_messages[-1]["role"] == msg["role"]:
                    consolidated_messages[-1]["content"] += "\n\n" + msg["content"]
                else:
                    consolidated_messages.append(msg.copy())
                    
            data = {
                "model": config.get("groq_chat_model", "llama-3.3-70b-versatile"),
                "messages": consolidated_messages,
                "temperature": 0.2
            }
            
            max_retries = 4
            backoff_factor = 1.5
            
            for attempt in range(max_retries):
                try:
                    res = requests.post(url, headers=headers, json=data, timeout=30)
                    if res.status_code == 429:
                        # Extract Retry-After or calculate backoff
                        retry_after = res.headers.get("retry-after") or res.headers.get("Retry-After")
                        try:
                            wait_time = float(retry_after) if retry_after else (backoff_factor ** attempt)
                        except ValueError:
                            wait_time = backoff_factor ** attempt
                        
                        wait_time = min(max(wait_time, 1.0), 10.0)
                        print(f"\n⚠️ [Groq API] rate limited (429). Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    
                    if res.status_code in (502, 503, 504) and attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        print(f"\n⚠️ [Groq API] server error ({res.status_code}). Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                        
                    res.raise_for_status()
                    return res.json()["choices"][0]["message"]["content"]
                except requests.exceptions.RequestException as e:
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        print(f"\n⚠️ [Groq API] network error ({e}). Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                        continue
                    raise e
            
        else: # Default is Ollama
            ollama_url = config.get("ollama_url", "http://localhost:11434")
            # First try OpenAI compatible route in Ollama
            url = f"{ollama_url}/v1/chat/completions"
            data = {
                "model": config.get("ollama_chat_model", "qwen3:4b"),
                "messages": formatted_messages,
                "temperature": 0.2
            }
            try:
                res = requests.post(url, json=data, timeout=120)
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except Exception:
                # Fallback to Ollama direct endpoint
                direct_url = f"{ollama_url}/api/chat"
                direct_data = {
                    "model": config.get("ollama_chat_model", "qwen3:4b"),
                    "messages": formatted_messages,
                    "stream": False,
                    "options": {"temperature": 0.2}
                }
                res = requests.post(direct_url, json=direct_data, timeout=120)
                res.raise_for_status()
                return res.json()["message"]["content"]
                
    except Exception as e:
        # If active provider fails, log error and raise
        error_msg = f"LLM client routing failed for provider '{provider}': {e}"
        raise RuntimeError(error_msg)
