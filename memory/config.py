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

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            # Ensure all default keys exist
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
    except Exception:
        return DEFAULT_CONFIG

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def get_config_value(key):
    config = load_config()
    return config.get(key, DEFAULT_CONFIG.get(key))
