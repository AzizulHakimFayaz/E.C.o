import json
import re
from memory.llm_client import call_llm
from memory.chroma_client import add_document
from memory.neo4j_client import add_graph_node, add_graph_edge, get_profile_context

KNOWLEDGE_EXTRACTION_PROMPT = """
Analyze the user query and the assistant response to extract key profile updates, preference changes, and research knowledge.
If none are mentioned, return empty dictionaries or lists.

Format your response ONLY as a JSON object matching this schema:
{
    "user_profile": {
        "name": "User's name if explicitly mentioned or updated, otherwise null",
        "active_project": "Name of the active project the user is working on if mentioned, otherwise null",
        "preferences": [
            {
                "key": "Category of preference (e.g. language, tools, time, format)",
                "value": "Value of the preference (e.g. Bengali + English mixed, Playwright, late night)"
            }
        ],
        "style": {
            "formal_level": "casual | formal | direct | null",
            "tone": "informal | technical | enthusiastic | null",
            "custom_notes": "e.g., uses bang '!' frequently, keeps replies short, mixes Bengali words"
        }
    },
    "research": {
        "questions": [
            {
                "id": "q:short_slug_of_question",
                "text": "The research question being asked",
                "status": "explored"
            }
        ],
        "findings": [
            {
                "id": "finding:short_slug",
                "content": "Specific key finding, fact, or discovery in the response",
                "confidence": "high | medium | low",
                "related_question_id": "id of the matching question in the questions array above",
                "sources": [
                    {
                        "id": "src:slug",
                        "title": "Title of paper, website, or source name",
                        "url_or_file": "URL or filename referenced"
                    }
                ],
                "concepts": [
                    {
                        "id": "concept:slug",
                        "name": "Concept Name",
                        "description": "Definition or short description of the concept"
                    }
                ]
            }
        ]
    }
}
Do not write markdown formatting wrappers besides the raw JSON itself (do not wrap in ```json).
"""

def _clean_capture(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .,!?:;\"'")
    value = re.sub(r"\b(from now on|again|anymore|please)\b.*$", "", value, flags=re.IGNORECASE).strip(" .,!?:;\"'")
    return value

def _normalize_name(value: str) -> str:
    value = _clean_capture(value)
    if not value:
        return value
    return " ".join(part[:1].upper() + part[1:] for part in value.split())

def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return value or "value"

def apply_deterministic_profile_updates(user_query: str, user_name: str = "Shahriar") -> dict:
    """
    Persist direct profile instructions without waiting for the LLM extractor.
    """
    updates = {"name": None, "nickname": None, "avoid_address_terms": []}

    name_match = re.search(
        r"\bmy\s+name\s+is\s+(.+?)(?:\s+(?:and\s+)?nick(?:name)?\s+is\b|[.!?\n]|$)",
        user_query,
        flags=re.IGNORECASE
    )
    if name_match:
        updates["name"] = _normalize_name(name_match.group(1))

    nickname_match = re.search(
        r"\bnick(?:name)?\s+is\s+(.+?)(?:[.!?\n]|$)",
        user_query,
        flags=re.IGNORECASE
    )
    if nickname_match:
        updates["nickname"] = _normalize_name(nickname_match.group(1))

    avoid_match = re.search(
        r"\b(?:don'?t|do\s+not|never)\s+call\s+me\s+['\"]?(.+?)(?:['\".!?\n]|$)",
        user_query,
        flags=re.IGNORECASE
    )
    if avoid_match:
        term = _clean_capture(avoid_match.group(1)).lower()
        if term:
            updates["avoid_address_terms"].append(term)

    if not any([updates["name"], updates["nickname"], updates["avoid_address_terms"]]):
        return updates

    user_node_id = f"user:{user_name.lower()}"
    current_profile = get_profile_context(user_name)
    actual_name = updates["name"] or current_profile.get("name") or user_name
    metadata = {"name": actual_name}
    if updates["nickname"]:
        metadata["nickname"] = updates["nickname"]

    add_graph_node(user_node_id, actual_name, "User", metadata)

    if updates["nickname"]:
        pref_node_id = "pref:nickname"
        add_graph_node(pref_node_id, "PreferredNickname", "Preference", {"value": updates["nickname"]})
        add_graph_edge(user_node_id, pref_node_id, "PREFERS")

    for term in updates["avoid_address_terms"]:
        pref_node_id = f"pref:avoid_address_{_slug(term)}"
        add_graph_node(pref_node_id, "AvoidAddressTerm", "Preference", {"value": term})
        add_graph_edge(user_node_id, pref_node_id, "PREFERS")

    if updates["avoid_address_terms"]:
        style_node_id = f"style:{user_name.lower()}"
        add_graph_node(
            style_node_id,
            "UserStyle",
            "Style",
            {"details": f"Do not call the user: {', '.join(updates['avoid_address_terms'])}"}
        )
        add_graph_edge(user_node_id, style_node_id, "WRITES_WITH")

    return updates

def extract_and_build_knowledge(user_query: str, ai_response: str, user_name: str = "Shahriar"):
    """
    Closed-loop learning processor. Parses interaction to update graph and vector memories.
    """
    user_node_id = f"user:{user_name.lower()}"
    apply_deterministic_profile_updates(user_query, user_name)
    
    try:
        extraction_prompt = (
            f"{KNOWLEDGE_EXTRACTION_PROMPT}\n\n"
            f"User Query: \"{user_query}\"\n\n"
            f"AI Response:\n{ai_response}"
        )
        
        messages = [{"role": "user", "content": "Extract memory and knowledge from this exchange."}]
        response_text = call_llm(messages, system_prompt=extraction_prompt)
        
        # Clean markdown code wrappers
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        extracted = json.loads(clean_text)
        
        # 1. Process User Profile Updates
        profile_data = extracted.get("user_profile", {})
        if profile_data:
            style_data = profile_data.get("style", {}) or {}
            has_profile_update = any([
                profile_data.get("name"),
                profile_data.get("active_project"),
                profile_data.get("preferences"),
                any(style_data.values())
            ])
            if not has_profile_update:
                profile_data = {}

        if profile_data:
            # Upsert User node
            current_name = get_profile_context(user_name).get("name") or user_name
            actual_name = profile_data.get("name") or current_name
            add_graph_node(user_node_id, actual_name, "User", {"name": actual_name})
            
            # Save preferences
            for pref in profile_data.get("preferences", []):
                key = pref.get("key")
                val = pref.get("value")
                if key and val:
                    pref_node_id = f"pref:{key.lower().replace(' ', '_')}"
                    add_graph_node(pref_node_id, key, "Preference", {"value": val})
                    add_graph_edge(user_node_id, pref_node_id, "PREFERS")
                    
            # Save style updates
            if any(style_data.values()):
                style_node_id = f"style:{user_name.lower()}"
                add_graph_node(
                    style_node_id, 
                    "UserStyle", 
                    "Style", 
                    {
                        "formal_level": style_data.get("formal_level", "casual"),
                        "tone": style_data.get("tone", "informal"),
                        "details": style_data.get("custom_notes", "")
                    }
                )
                add_graph_edge(user_node_id, style_node_id, "WRITES_WITH")
                
            # Save active project
            active_proj = profile_data.get("active_project")
            if active_proj:
                proj_node_id = f"project:{active_proj.lower().replace(' ', '_')}"
                add_graph_node(proj_node_id, active_proj, "Project", {"status": "Active"})
                add_graph_edge(user_node_id, proj_node_id, "WORKING_ON")
                
        # 2. Process Research & Findings
        research_data = extracted.get("research", {})
        if research_data:
            # Active project for linking research
            active_proj_id = None
            if profile_data and profile_data.get("active_project"):
                active_proj_id = f"project:{profile_data['active_project'].lower().replace(' ', '_')}"
            
            # Map questions
            q_map = {}
            for q in research_data.get("questions", []):
                q_id = q.get("id")
                q_text = q.get("text")
                status = q.get("status", "explored")
                if q_id and q_text:
                    add_graph_node(q_id, q_text, "ResearchQuestion", {"status": status})
                    q_map[q_id] = q_text
                    if active_proj_id:
                        add_graph_edge(active_proj_id, q_id, "HAS_QUESTION")
                        
            # Map findings
            for f in research_data.get("findings", []):
                f_id = f.get("id")
                f_content = f.get("content")
                confidence = f.get("confidence", "high")
                q_link_id = f.get("related_question_id")
                
                if f_id and f_content:
                    # Save Finding node
                    add_graph_node(f_id, f_content[:50] + "...", "Finding", {"content": f_content, "confidence": confidence})
                    
                    # Link to Question
                    if q_link_id:
                        add_graph_edge(q_link_id, f_id, "HAS_FINDING")
                        
                    # Process Sources
                    for src in f.get("sources", []):
                        src_id = src.get("id")
                        title = src.get("title", "Reference Source")
                        url_file = src.get("url_or_file", "")
                        if src_id:
                            add_graph_node(src_id, title, "Source", {"url_or_file": url_file, "type": "citation"})
                            add_graph_edge(f_id, src_id, "FROM_SOURCE")
                            
                    # Process Concepts
                    for c in f.get("concepts", []):
                        c_id = c.get("id")
                        c_name = c.get("name")
                        desc = c.get("description", "")
                        if c_id and c_name:
                            add_graph_node(c_id, c_name, "Concept", {"description": desc})
                            add_graph_edge(f_id, c_id, "RELATESTO_CONCEPT")
                            
                    # Also persist to Vector Database for semantic search queries
                    try:
                        add_document(
                            title=f"Research Finding: {f_content[:40]}...",
                            content=f_content,
                            doc_type="research_note"
                        )
                    except Exception as ve:
                        print(f"[Knowledge Extractor] Error adding finding to vector index: {ve}")
                        
    except Exception as e:
        # Graceful logging in case of LLM parse issues
        print(f"[Knowledge Extractor] Closed-loop learning error: {e}")
        pass
