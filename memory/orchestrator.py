import json
from memory import db_sqlite
from memory.config import load_config
from memory.chroma_client import search_documents, add_document
from memory.neo4j_client import get_profile_context, get_relevant_subgraph, build_networkx_graph
from memory.query_analyzer import analyze_query
from memory.llm_client import call_llm
from memory.knowledge_extractor import extract_and_build_knowledge

def scan_query_for_nodes(query: str) -> list[str]:
    """
    Checks if any node IDs or names from the graph are mentioned in the query text.
    """
    q_lower = query.lower()
    referenced_nodes = []
    
    try:
        # Load the graph layout (offline/online) to scan ids
        G = build_networkx_graph()
        for node_id in G.nodes:
            node_name = G.nodes[node_id].get("name", "").lower()
            clean_id = node_id.split(":")[-1].lower()
            
            if (node_name and node_name in q_lower) or (clean_id and clean_id in q_lower):
                referenced_nodes.append(node_id)
    except Exception:
        pass
        
    return referenced_nodes

def compile_unified_system_prompt(
    user_name: str,
    query: str,
    profile: dict,
    rag_results: list[dict] = None,
    graph_results: dict = None,
    conversation_context: list[dict] = None
) -> str:
    """
    Formats user preferences, style guide, and retrieved memories into a structured system prompt.
    """
    sections = []
    
    # 1. Identity & Style Guide
    actual_name = profile.get("name") or user_name
    sections.append(f"You are E.C.o, the personal AI research assistant for {actual_name}.")
    sections.append(f"Style Instructions: {profile.get('style', 'Reply helpfully and direct.')}")
    
    # 2. Preferences
    if profile.get("preferences"):
        sections.append("\n=== USER PREFERENCES ===")
        for pref in profile["preferences"]:
            sections.append(f"- {pref}")
            
    # 3. Active Projects
    if profile.get("projects"):
        sections.append("\n=== ACTIVE PROJECTS ===")
        for proj in profile["projects"]:
            sections.append(f"- {proj}")

    # 4. Raw conversation recall
    if conversation_context:
        sections.append("\n=== RECENT / MATCHED CONVERSATION HISTORY ===")
        sections.append(
            "Prefer this exact chat history when the user asks what they were doing, "
            "what they asked before, their name, or previous research topics. "
            "If it conflicts with semantic summaries, trust the exact chat history first. "
            "For identity and preference facts, trust explicit user messages and USER PREFERENCES "
            "over assistant replies that merely claimed a memory."
        )
        for msg in conversation_context:
            content = (msg.get("content") or "").strip()
            if len(content) > 900:
                content = content[:900].rstrip() + "..."
            sections.append(
                f"- Message #{msg.get('id', '?')} [{msg.get('role', '?')}"
                f"{', ' + msg.get('classification') if msg.get('classification') else ''}]: {content}"
            )
            
    # 5. RAG semantic memory
    if rag_results:
        sections.append("\n=== RETRIEVED SEMANTIC MEMORY & NOTES ===")
        for i, item in enumerate(rag_results, 1):
            sections.append(
                f"Memory #{i} (Type: {item['type']}, Title: {item['title']}, Score: {item['score']:.2f}):\n"
                f"\"\"\"\n{item['content']}\n\"\"\"\n"
            )
            
    # 6. Graph memory
    if graph_results and graph_results.get("nodes"):
        sections.append("\n=== RETRIEVED KNOWLEDGE GRAPH ===")
        sections.append("The following concepts, findings, and research questions are relevant:")
        for node in graph_results["nodes"]:
            meta_str = ", ".join(f"{k}: {v}" for k, v in node["metadata"].items())
            sections.append(f"- [{node['type']}] {node['name']} ({node['id']}) [{meta_str}]")
            
        if graph_results.get("edges"):
            sections.append("\nGraph relationships:")
            for edge in graph_results["edges"]:
                sections.append(f"  {edge['source_id']} --[{edge['type']}]--> {edge['target_id']}")
                
    # Final assembly
    system_instructions = (
        "\n".join(sections) +
        "\n\nUse this retrieved context to answer the user's request. "
        "Keep your response highly personalized, aligning with their preferred tone and active projects. "
        "Do not invent facts; if you do not know something, state it."
    )
    return system_instructions

def _merge_conversation_context(*groups: list[dict]) -> list[dict]:
    seen = set()
    merged = []
    for group in groups:
        for item in group or []:
            msg_id = item.get("id")
            if msg_id in seen:
                continue
            seen.add(msg_id)
            merged.append(item)
    merged.sort(key=lambda item: item.get("id", 0))
    return merged

def execute_chat(conversation_id: int, query: str, user_name: str = "Shahriar") -> dict:
    """
    Primary orchestrator pipeline:
    1. Retrieve profile context
    2. Analyze user intent
    3. Retrieve relevant graph/vector records
    4. Compile unified prompt
    5. Load chat history & invoke LLM
    6. Update SQLite message logs
    7. Execute closed-loop extraction to Neo4j/ChromaDB
    """
    # 1. Fetch user profile
    profile = get_profile_context(user_name)
    
    # 2. Categorize query
    analysis = analyze_query(query)
    q_type = analysis["classification"]
    
    rag_results = []
    graph_results = {"nodes": [], "edges": []}
    conversation_context = []
    
    # 3. Retrieve relevant memory blocks
    if q_type == "Memory Query":
        # Search semantic vector notes
        rag_results = search_documents(query, limit=6)
        conversation_context = _merge_conversation_context(
            db_sqlite.search_messages(query, conversation_id=conversation_id, limit=12),
            db_sqlite.get_recent_messages(conversation_id, limit=24)
        )
        
    elif q_type == "Research Query":
        # Hybrid retrieval: Search documents + fetch subgraph
        rag_results = search_documents(query, limit=5)
        conversation_context = db_sqlite.search_messages(query, conversation_id=conversation_id, limit=8)
        referenced = scan_query_for_nodes(query)
        if referenced:
            sub = get_relevant_subgraph(referenced[0], max_depth=2)
            graph_results = sub
        else:
            # Fallback: Load recent concepts from graph
            G = build_networkx_graph()
            nodes = []
            for n_id, data in G.nodes(data=True):
                if data.get("type") in ("Concept", "Finding", "ResearchQuestion"):
                    nodes.append({
                        "id": n_id,
                        "name": data.get("name", n_id),
                        "type": data.get("type"),
                        "metadata": data.get("metadata", {})
                    })
            graph_results["nodes"] = nodes[:10]
            
    elif q_type == "Style/Preference Update":
        # Load current style guide to confirm details
        referenced = scan_query_for_nodes(query)
        if referenced:
            graph_results = get_relevant_subgraph(referenced[0], max_depth=1)
            
    else: # General Query
        # Minimal context lookup
        pass
        
    # 4. Build Prompt
    system_prompt = compile_unified_system_prompt(
        user_name, query, profile, rag_results, graph_results, conversation_context
    )
    
    # 5. Load recent history
    history_rows = db_sqlite.get_messages(conversation_id)
    messages = []
    # Fetch last 8 messages for sliding context window
    for msg in history_rows[-8:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    messages.append({"role": "user", "content": query})
    
    # 6. Call LLM
    ai_response = call_llm(messages, system_prompt=system_prompt)
    
    # 7. Persist turns to SQLite
    sources_summary = {
        "rag_items": len(rag_results),
        "graph_nodes": len(graph_results.get("nodes", []))
    }
    
    db_sqlite.add_message(
        conversation_id=conversation_id,
        role="user",
        content=query,
        classification=q_type,
        retrieved_sources=json.dumps(sources_summary)
    )
    db_sqlite.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=ai_response,
        classification=q_type,
        retrieved_sources=None
    )
    
    # 8. CLOSED-LOOP LEARNING & 9. Index current exchange into Vector DB
    config = load_config()
    if config.get("fast_mode", True):
        import threading
        print(f"\n🧠 [Orchestrator] Starting background knowledge extraction and indexing...")
        
        def run_background_extraction(q, r, name):
            try:
                extract_and_build_knowledge(q, r, name)
            except Exception as ex:
                print(f"[Background Orchestrator] Closed-loop learning error: {ex}")
            try:
                add_document(
                    title=f"Chat QA: {q[:40]}...",
                    content=f"User Query: {q}\n\nE.C.o Response:\n{r}",
                    doc_type="conversation"
                )
            except Exception as ex:
                print(f"[Background Orchestrator] Error indexing exchange: {ex}")
        
        t = threading.Thread(
            target=run_background_extraction,
            args=(query, ai_response, user_name),
            daemon=True
        )
        t.start()
    else:
        # Synchronous execution
        print(f"\n🧠 [Orchestrator] Running knowledge extraction (synchronous)...")
        extract_and_build_knowledge(query, ai_response, user_name)
        try:
            add_document(
                title=f"Chat QA: {query[:40]}...",
                content=f"User Query: {query}\n\nE.C.o Response:\n{ai_response}",
                doc_type="conversation"
            )
        except Exception as e:
            print(f"[Orchestrator] Error index chat to RAG: {e}")
        
    return {
        "response": ai_response,
        "classification": q_type,
        "retrieved_context": {
            "rag": rag_results,
            "graph": graph_results,
            "profile": profile
        }
    }
