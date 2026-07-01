import os
import sys
import json

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from memory import db_sqlite
from memory.config import load_config, save_config
from memory.neo4j_client import add_graph_node, add_graph_edge, get_profile_context
from memory import voice_manager
from agent.graph import EcoStateGraph

BANNER = r"""
  _____ ____       
 | ____/ ___|___   
 |  _|| |   / _ \  
 | |__| |__| (_) | 
 |_____\____\___/  
                                 
  ⚡ Graph-Memory Agentic Personal Assistant
  ✓ Local-First | Qwen3 + Neo4j + ChromaDB Fallbacks
------------------------------------------------------------
"""

def setup_initial_profile(user_name: str = "Shahriar"):
    """
    Bootstrap the database with initial user information if empty.
    """
    user_node_id = f"user:{user_name.lower()}"
    proj_node_id = "project:e_c_o"
    style_node_id = f"style:{user_name.lower()}"
    pref_node_id = "pref:response_style"
    
    # Check if user profile already exists
    profile = get_profile_context(user_name, include_message_overrides=False)
    if not profile["projects"]:
        print(f"🔧 [Bootstrap] Setting up initial memory graph for user '{user_name}'...")
        # Add User
        add_graph_node(user_node_id, user_name, "User")
        # Add active project
        add_graph_node(proj_node_id, "E.C.o Memory System", "Project", {"status": "Active"})
        add_graph_edge(user_node_id, proj_node_id, "WORKING_ON")
        # Add style preferences
        add_graph_node(style_node_id, "UserStyle", "Style", {"details": "Casual, direct replies, mixes Bengali + English"})
        add_graph_edge(user_node_id, style_node_id, "WRITES_WITH")
        # Add custom preference
        add_graph_node(pref_node_id, "ResponseLength", "Preference", {"value": "short and concise"})
        add_graph_edge(user_node_id, pref_node_id, "PREFERS")
        print("✓ Initial profile graph nodes linked.")

def print_settings(config: dict):
    print("\n--- E.C.o Settings ---")
    print(f"Active Provider:   {config.get('active_provider')}")
    print(f"Ollama URL:        {config.get('ollama_url')}")
    print(f"Ollama Model:      {config.get('ollama_chat_model')}")
    print(f"Ollama Embedding:  {config.get('ollama_embedding_model')}")
    print(f"Groq Model:        {config.get('groq_chat_model')}")
    print(f"Groq API Key:      {'Configured' if config.get('groq_api_key') else 'Not Configured'}")
    print(f"Neo4j Config:      {config.get('neo4j_uri')} (Use: {config.get('use_neo4j')})")
    print(f"ChromaDB Config:   {config.get('chroma_db_path')} (Use: {config.get('use_chroma')})")
    print(f"SQLite Path:       {config.get('sqlite_db_path')}")
    print("-----------------------\n")

def main():
    print(BANNER)
    
    # 1. Initialize databases
    db_sqlite.init_db()
    
    # 2. Bootstrap initial graph profile
    setup_initial_profile("Shahriar")
    
    # 3. Resume last conversation or create new one
    config = load_config()
    existing_convos = db_sqlite.get_conversations()
    if existing_convos:
        conv_id = existing_convos[0]["id"]  # Most recent (ORDER BY created_at DESC)
        msg_count = len(db_sqlite.get_messages(conv_id))
        print(f"📂 Resumed conversation #{conv_id} ({msg_count} messages in history)")
    else:
        conv_id = db_sqlite.create_conversation("E.C.o Interactive Chat")
        print(f"📂 Started new conversation #{conv_id}")
    
    print("\nWelcome! Type your prompt below to start talking to E.C.o.")
    print("Special Commands:")
    print("  /config    - View/Edit system settings and LLM keys")
    print("  /graph     - Print graph memory status and nodes")
    print("  /voice     - Toggle voice mode (speak & listen via microphone)")
    print("  /new       - Start a fresh conversation (clear context)")
    print("  /quit      - Exit E.C.o panel\n")
    
    voice_enabled = config.get("voice_mode", False)
    if voice_enabled:
        print("🎤 [Voice Mode: ON] E.C.o will speak and listen to your microphone.\n")
        
    agent = EcoStateGraph()
    
    while True:
        try:
            if voice_enabled:
                try:
                    user_input = voice_manager.listen().strip()
                except KeyboardInterrupt:
                    print("\n🎤 Voice Mode cancelled. Switching to text input...")
                    voice_enabled = False
                    config = load_config()
                    config["voice_mode"] = False
                    save_config(config)
                    continue
                
                if not user_input:
                    print("No speech detected. Switch to typing (or press Enter to try speaking again).")
                    user_input = input("You: ").strip()
            else:
                user_input = input("You: ").strip()
                
            if not user_input:
                continue
                
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                print("\nGoodbye! E.C.o memory preserved.")
                break
            
            elif user_input.lower() == "/new":
                conv_id = db_sqlite.create_conversation("E.C.o Interactive Chat")
                print(f"\n🆕 Started fresh conversation #{conv_id}. Previous conversations are still saved.")
                continue
                
            elif user_input.lower() in ("/voice", "voice"):
                voice_enabled = not voice_enabled
                config = load_config()
                config["voice_mode"] = voice_enabled
                save_config(config)
                state_str = "ON" if voice_enabled else "OFF"
                print(f"\n🎤 Voice Mode is now: {state_str}")
                if voice_enabled:
                    voice_manager.speak("Voice mode activated.")
                else:
                    voice_manager.speak("Voice mode deactivated.")
                continue
                
            elif user_input.lower() == "/config":
                config = load_config()
                print_settings(config)
                
                prov = input("Change active provider? (ollama/groq / press enter to skip): ").strip().lower()
                if prov in ("ollama", "groq"):
                    config["active_provider"] = prov
                
                active_provider = config["active_provider"]
                print(f"\nActive Provider is set to: {active_provider.upper()}")
                
                if active_provider == "ollama":
                    # Fetch installed Ollama models
                    print("Connecting to local Ollama service to fetch installed models...")
                    import requests
                    ollama_url = config.get("ollama_url", "http://localhost:11434")
                    try:
                        res = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=3.0)
                        if res.status_code == 200:
                            models = [m["name"] for m in res.json().get("models", [])]
                        else:
                            models = []
                    except Exception:
                        models = []
                        
                    if models:
                        print("\nInstalled local models (Ollama):")
                        for idx, model in enumerate(models, 1):
                            current_marker = " (current)" if model == config.get("ollama_chat_model") else ""
                            print(f"  [{idx}] {model}{current_marker}")
                        print(f"  [{len(models) + 1}] Enter custom model name manually")
                        
                        sel = input(f"Choose model [1-{len(models) + 1}] (press enter to keep current): ").strip()
                        if sel.isdigit():
                            sel_idx = int(sel)
                            if 1 <= sel_idx <= len(models):
                                config["ollama_chat_model"] = models[sel_idx - 1]
                                print(f"✓ Selected local model: {config['ollama_chat_model']}")
                            elif sel_idx == len(models) + 1:
                                custom_model = input("Enter custom Ollama model name: ").strip()
                                if custom_model:
                                    config["ollama_chat_model"] = custom_model
                                    print(f"✓ Configured custom model: {custom_model}")
                    else:
                        print("\n⚠️ Could not connect to local Ollama API or no models found.")
                        custom_model = input(f"Enter Ollama model name manually (current: {config.get('ollama_chat_model')}): ").strip()
                        if custom_model:
                            config["ollama_chat_model"] = custom_model
                            print(f"✓ Configured Ollama model: {custom_model}")
                            
                elif active_provider == "groq":
                    # Common Groq models list
                    groq_models = [
                        "llama-3.3-70b-versatile",
                        "llama-3.1-8b-instant",
                        "mixtral-8x7b-32768",
                        "gemma2-9b-it"
                    ]
                    print("\nAvailable cloud models (Groq):")
                    for idx, model in enumerate(groq_models, 1):
                        current_marker = " (current)" if model == config.get("groq_chat_model") else ""
                        print(f"  [{idx}] {model}{current_marker}")
                    print(f"  [{len(groq_models) + 1}] Enter custom model name manually")
                    
                    sel = input(f"Choose model [1-{len(groq_models) + 1}] (press enter to keep current): ").strip()
                    if sel.isdigit():
                        sel_idx = int(sel)
                        if 1 <= sel_idx <= len(groq_models):
                            config["groq_chat_model"] = groq_models[sel_idx - 1]
                            print(f"✓ Selected Groq model: {config['groq_chat_model']}")
                        elif sel_idx == len(groq_models) + 1:
                            custom_model = input("Enter custom Groq model name: ").strip()
                            if custom_model:
                                config["groq_chat_model"] = custom_model
                                print(f"✓ Configured custom model: {custom_model}")
                                
                    key = input(f"Update Groq API Key? (current: {'Configured' if config.get('groq_api_key') else 'Not Configured'} / press enter to skip): ").strip()
                    if key:
                        config["groq_api_key"] = key
                        
                save_config(config)
                print("\n✓ Configurations updated and saved.")
                continue
                
            elif user_input.lower() == "/graph":
                data = db_sqlite.sqlite_get_graph_data()
                print(f"\n--- Graph Memory Status ({len(data['nodes'])} nodes, {len(data['edges'])} edges) ---")
                for node in data["nodes"]:
                    meta = json.dumps(node["metadata"])
                    print(f"- [{node['type']}] {node['name']} (ID: {node['id']}) [{meta[:80]}]")
                print("------------------------------------------------------------------\n")
                continue
                
            # Run query through ReAct state graph loop
            print("\n🤖 E.C.o is thinking...")
            result = agent.run(user_input, user_name="Shahriar", conversation_id=conv_id)
            
            print(f"\nE.C.o: {result['response']}\n")
            print("-" * 60)
            
            if voice_enabled:
                voice_manager.speak(result['response'])
            
        except KeyboardInterrupt:
            print("\n\nGoodbye! Session ended.")
            break
        except Exception as e:
            print(f"\n❌ Error occurred: {e}\n")

if __name__ == "__main__":
    main()
