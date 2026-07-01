import json
from memory import orchestrator
from memory import neo4j_client
from memory import chroma_client
from memory import knowledge_extractor
from memory import db_sqlite
from memory.llm_client import call_llm

# Tool imports
from tools.web_search import web_search
from tools.file_reader import read_local_file
from tools.folder_search import search_folder
from tools.run_command import run_terminal_command
from tools.browser import scrape_webpage
from tools.open_app import open_windows_app

# Define the tools mapping for the agent node execution
TOOLS_MAPPING = {
    "web_search": lambda args: web_search(args.get("query", "")),
    "read_file": lambda args: read_local_file(args.get("filepath", ""), args.get("start_line", 1), args.get("end_line", 250)),
    "search_folder": lambda args: search_folder(args.get("directory", "."), args.get("pattern", "*")),
    "run_command": lambda args: run_terminal_command(args.get("command", ""), args.get("cwd")),
    "open_browser": lambda args: scrape_webpage(args.get("url", "")),
    "open_app": lambda args: open_windows_app(args.get("app_name", ""))
}

TOOLS_SCHEMA_GUIDE = """
You have direct access to these Windows automation and research tools.
If you need to use one, respond ONLY with a JSON block in a markdown wrapper:
```json
{
  "tool": "tool_name",
  "arguments": {
    "arg1": "value"
  }
}
```
Available tools:
1. web_search(query: str) -> searches online.
2. read_file(filepath: str, start_line: int, end_line: int) -> reads lines from a file.
3. search_folder(directory: str, pattern: str) -> finds files recursively.
4. run_command(command: str, cwd: str) -> runs terminal/PowerShell tasks.
5. open_browser(url: str) -> loads website and scrapes plain text content.
6. open_app(app_name: str) -> launches any Windows program (e.g. notepad, calc).

Choose the right tool or respond with regular text if no tools are needed.
"""

def load_context_node(state: dict) -> dict:
    """
    State Node: Loads profile data and relevant memories to configure system prompts.
    Always retrieves at least basic memory context so E.C.o can recall past interactions.
    """
    user_name = state.get("user_name", "Shahriar")
    query = state["user_query"]
    
    # Load profile details (projects, preferences, style — always available)
    profile = neo4j_client.get_profile_context(user_name)
    
    # Classify query and run memory searches
    analysis = orchestrator.analyze_query(query)
    q_type = analysis["classification"]
    state["classification"] = q_type
    
    rag_results = []
    graph_results = {"nodes": [], "edges": []}
    conversation_context = []
    
    if q_type == "Memory Query":
        # Deep memory search — more results for explicit recall requests
        rag_results = chroma_client.search_documents(query, limit=8)
        conversation_context = orchestrator._merge_conversation_context(
            db_sqlite.search_messages(query, conversation_id=state.get("conversation_id"), limit=12),
            db_sqlite.get_recent_messages(state.get("conversation_id"), limit=24)
        )
    elif q_type == "Research Query":
        # Hybrid retrieval: vector search + graph traversal
        rag_results = chroma_client.search_documents(query, limit=6)
        conversation_context = db_sqlite.search_messages(
            query,
            conversation_id=state.get("conversation_id"),
            limit=10
        )
        referenced = orchestrator.scan_query_for_nodes(query)
        if referenced:
            graph_results = neo4j_client.get_relevant_subgraph(referenced[0], max_depth=2)
    else:
        # General Query / Style Update — still do a lightweight memory search
        # so E.C.o always has some awareness of past context
        rag_results = chroma_client.search_documents(query, limit=2)
            
    # Compile prompt
    system_prompt = orchestrator.compile_unified_system_prompt(
        user_name, query, profile, rag_results, graph_results, conversation_context
    )
    # Inject tool schemas instructions
    system_prompt += "\n" + TOOLS_SCHEMA_GUIDE
    
    state["system_prompt"] = system_prompt
    state["next_node"] = "reason"
    return state

def reason_node(state: dict) -> dict:
    """
    State Node: Dispatches chat to LLM and parses if tools are required.
    """
    messages = state["messages"]
    system_prompt = state["system_prompt"]
    
    # Reconstruct messages list for LLM context
    llm_history = []
    # Send last 8 turns of context
    for msg in messages[-8:]:
        item = {"role": msg["role"], "content": msg["content"]}
        if "name" in msg:
            item["name"] = msg["name"]
        llm_history.append(item)
        
    try:
        response_text = call_llm(llm_history, system_prompt=system_prompt)
    except Exception as e:
        state["errors"].append(str(e))
        # Log error in response and return
        response_text = f"Error calling LLM provider: {e}"
        state["next_node"] = "end"
        state["messages"].append({"role": "assistant", "content": response_text})
        return state
        
    # Check for JSON markdown tool calls
    tool_calls = []
    json_blocks = re_parse_json_blocks(response_text)
    
    for block in json_blocks:
        if isinstance(block, dict) and "tool" in block:
            tool_calls.append(block)
            
    if tool_calls:
        state["tool_calls"] = tool_calls
        state["next_node"] = "execute_tools"
        # Append assistant's thoughts to message log
        state["messages"].append({
            "role": "assistant", 
            "content": f"Thinking: I will execute the tools: {', '.join(tc['tool'] for tc in tool_calls)}.\n{response_text}"
        })
    else:
        state["tool_calls"] = []
        state["next_node"] = "save_memory"
        state["messages"].append({"role": "assistant", "content": response_text})
        
    return state

def execute_tools_node(state: dict) -> dict:
    """
    State Node: Processes all requested tool actions.
    """
    tool_calls = state.get("tool_calls", [])
    
    for call in tool_calls:
        tool_name = call.get("tool")
        arguments = call.get("arguments", {})
        
        print(f"\n⚡ [Agent Engine] Executing Tool: {tool_name} with arguments: {arguments}")
        
        if tool_name in TOOLS_MAPPING:
            try:
                result = TOOLS_MAPPING[tool_name](arguments)
                if isinstance(result, dict):
                    result_str = json.dumps(result, indent=2)
                else:
                    result_str = str(result)
            except Exception as e:
                result_str = f"Error executing tool '{tool_name}': {e}"
        else:
            result_str = f"Error: Tool '{tool_name}' is not registered in E.C.o Tool Layer."
            
        # Append tool results back into loop
        state["messages"].append({
            "role": "tool",
            "name": tool_name,
            "content": result_str
        })
        
    # Clean parsed tools for next reasoning iteration
    state["tool_calls"] = []
    state["next_node"] = "reason"
    return state

def save_memory_node(state: dict) -> dict:
    """
    State Node: Updates Neo4j and ChromaDB databases with extracted insights.
    """
    user_query = state["user_query"]
    user_name = state.get("user_name", "Shahriar")
    
    # Get last assistant reply
    assistant_reply = ""
    for msg in reversed(state["messages"]):
        if msg["role"] == "assistant":
            assistant_reply = msg["content"]
            break
            
    if assistant_reply:
        from memory.config import load_config
        config = load_config()
        
        if config.get("fast_mode", True):
            import threading
            print(f"\n🧠 [Learning Loop] Starting background knowledge extraction...")
            
            def run_background_extraction(q, r, name):
                try:
                    knowledge_extractor.extract_and_build_knowledge(q, r, name)
                except Exception as ex:
                    print(f"[Background Learning Loop] Closed-loop learning error: {ex}")
                try:
                    chroma_client.add_document(
                        title=f"Chat QA: {q[:40]}...",
                        content=f"User Query: {q}\n\nE.C.o Response:\n{r}",
                        doc_type="conversation"
                    )
                except Exception as ex:
                    print(f"[Background Learning Loop] Error indexing exchange: {ex}")
            
            t = threading.Thread(
                target=run_background_extraction,
                args=(user_query, assistant_reply, user_name),
                daemon=True
            )
            t.start()
        else:
            # Trigger closed loop extraction synchronously
            print(f"\n🧠 [Learning Loop] Running knowledge extraction (synchronous)...")
            knowledge_extractor.extract_and_build_knowledge(user_query, assistant_reply, user_name)
            
            # Save exchange history for future conversations
            try:
                chroma_client.add_document(
                    title=f"Chat QA: {user_query[:40]}...",
                    content=f"User Query: {user_query}\n\nE.C.o Response:\n{assistant_reply}",
                    doc_type="conversation"
                )
            except Exception as e:
                print(f"[Learning Loop] Error indexing exchange: {e}")
            
    state["next_node"] = "end"
    return state

def re_parse_json_blocks(text: str) -> list:
    """
    Utility parser that extracts JSON content blocks from LLM markdown.
    """
    blocks = []
    if not text:
        return blocks
        
    # 1. Match ```json ... ``` blocks
    import re
    matches = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    for m in matches:
        try:
            data = json.loads(m.strip())
            if isinstance(data, list):
                blocks.extend(data)
            else:
                blocks.append(data)
        except Exception:
            pass
            
    # 2. Check if whole text is raw JSON
    if not blocks:
        try:
            trimmed = text.strip()
            if trimmed.startswith("{") and trimmed.endswith("}"):
                data = json.loads(trimmed)
                blocks.append(data)
        except:
            pass
            
    return blocks
