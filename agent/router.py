from memory.config import load_config, save_config

def route_next_node(state: dict) -> str:
    """
    Decides the next transition step based on state properties.
    Incorporate self-healing logic: If local models throw consecutive connection errors,
    switch provider to Groq API (fallback layer) automatically to recover.
    """
    errors = state.get("errors", [])
    
    # Self-healing logic
    if len(errors) >= 1:
        config = load_config()
        if config.get("active_provider") == "ollama" and config.get("groq_api_key"):
            print("\n⚠️ [Self-Healing Router] Ollama errors detected. Switching active provider to Groq Fallback API...")
            config["active_provider"] = "groq"
            save_config(config)
            # Clear errors list and try re-reasoning
            state["errors"] = []
            return "reason"
            
    return state.get("next_node", "end")
