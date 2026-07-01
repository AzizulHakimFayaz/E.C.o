import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULT_CONFIG = {
    "active_provider": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_chat_model": "qwen3:4b",
    "ollama_embedding_model": "nomic-embed-text",
    
    "groq_api_key": "",
    "groq_chat_model": "llama-3.3-70b-versatile",
    
    "neo4j_uri": "bolt://localhost:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "password",
    "use_neo4j": True,
    
    "chroma_db_path": "./chroma_db",
    "use_chroma": True,
    
    "sqlite_db_path": "./eco_memory.db",
    "voice_mode": False,
    "voice_name": "en-US-AriaNeural",
    "fast_mode": True
}

def load_env_file():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root_dir, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        if val.startswith('"') and val.endswith('"'):
                            val = val[1:-1]
                        elif val.startswith("'") and val.endswith("'"):
                            val = val[1:-1]
                        os.environ[key] = val
        except Exception:
            pass

def save_to_env_file(sensitive_values):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root_dir, ".env")
    
    existing_lines = []
    updated_keys = set()
    
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()
        except Exception:
            pass
            
    new_env_entries = {}
    for k, v in sensitive_values.items():
        new_env_entries[k.upper()] = v
        
    modified_lines = []
    for line in existing_lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            key_part, val_part = trimmed.split("=", 1)
            key_part = key_part.strip()
            key_upper = key_part.upper()
            if key_upper in new_env_entries:
                modified_lines.append(f"{key_part}={new_env_entries[key_upper]}\n")
                updated_keys.add(key_upper)
                os.environ[key_part] = new_env_entries[key_upper]
                continue
        modified_lines.append(line)
        
    for k, v in sensitive_values.items():
        k_upper = k.upper()
        if k_upper not in updated_keys:
            if modified_lines and not modified_lines[-1].endswith("\n"):
                modified_lines[-1] += "\n"
            modified_lines.append(f"{k_upper}={v}\n")
            os.environ[k_upper] = v
            
    try:
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(modified_lines)
    except Exception:
        pass

def load_config():
    load_env_file()
    
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config = json.load(f)
        except Exception:
            pass
            
    # Ensure all default keys exist
    for k, v in DEFAULT_CONFIG.items():
        if k not in config:
            config[k] = v
            
    # Overlay environment variables (matching keys case-insensitively)
    for k in DEFAULT_CONFIG.keys():
        env_keys = [k.upper(), k]
        for env_key in env_keys:
            if env_key in os.environ:
                val = os.environ[env_key]
                default_val = DEFAULT_CONFIG[k]
                if isinstance(default_val, bool):
                    config[k] = val.lower() in ("true", "1", "yes")
                elif isinstance(default_val, int):
                    try:
                        config[k] = int(val)
                    except ValueError:
                        pass
                else:
                    config[k] = val
                break
                
    return config

def save_config(config):
    # Sensitive keys that shouldn't go to settings.json
    sensitive_keys = {"groq_api_key"}
    sensitive_values = {}
    config_to_save = config.copy()
    
    for key in sensitive_keys:
        if key in config_to_save:
            val = config_to_save[key]
            if val:
                sensitive_values[key] = val
            config_to_save[key] = ""
            
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_to_save, f, indent=4)
        
    if sensitive_values:
        save_to_env_file(sensitive_values)

def get_config_value(key):
    config = load_config()
    return config.get(key, DEFAULT_CONFIG.get(key))
