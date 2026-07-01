import sqlite3
import json
import os
import re
from datetime import datetime
from memory.config import load_config

def get_connection():
    config = load_config()
    db_path = config.get("sqlite_db_path", "./eco_memory.db")
    # Resolve path relative to E.C.o folder if needed
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path))
    
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        role TEXT NOT NULL, -- 'user', 'assistant', 'system'
        content TEXT NOT NULL,
        classification TEXT, -- e.g. 'Memory Query', 'Research Query'
        retrieved_sources TEXT, -- JSON summary of retrieved info
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    )
    """)
    
    # 3. Fallback Graph Nodes table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS local_nodes (
        id TEXT PRIMARY KEY, -- e.g. 'project:BIDWESH', 'user:Shahriar'
        name TEXT NOT NULL,
        type TEXT NOT NULL, -- 'User', 'Project', 'Topic', 'Preference', 'Style', 'ResearchQuestion', 'Finding', 'Source', 'Concept'
        metadata TEXT -- JSON string
    )
    """)
    
    # 4. Fallback Graph Edges table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS local_edges (
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        type TEXT NOT NULL, -- 'WORKING_ON', 'PREFERS', 'HAS_QUESTION', 'HAS_FINDING', 'FROM_SOURCE'
        PRIMARY KEY (source_id, target_id, type)
    )
    """)
    
    # 5. Fallback Vector (RAG) entries table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS local_rag_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        type TEXT NOT NULL, -- 'document', 'conversation', 'research_note'
        embedding TEXT, -- JSON float array string
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

# --- Conversations & Messages ---
def create_conversation(title: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    conn.commit()
    conv_id = cursor.lastrowid
    conn.close()
    return conv_id

def get_conversations():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_messages(conversation_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC", (conversation_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_recent_messages(conversation_id: int, limit: int = 20):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM (
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        ORDER BY id ASC
        """,
        (conversation_id, limit)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

_MESSAGE_SEARCH_STOPWORDS = {
    "the", "and", "you", "your", "was", "were", "what", "when", "where",
    "tell", "about", "that", "this", "with", "have", "from", "please",
    "again", "doing", "asking", "asked", "previous", "previously", "i",
    "me", "my", "we", "our", "for", "like", "more"
}

def _search_tokens(query: str) -> set[str]:
    raw_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    tokens = {t for t in raw_tokens if len(t) > 2 and t not in _MESSAGE_SEARCH_STOPWORDS}

    typo_expansions = {
        "reseach": "research",
        "reserch": "research",
        "papper": "paper",
        "pappers": "paper",
        "bidwesh": "bidwesh",
    }
    for misspelled, normalized in typo_expansions.items():
        if misspelled in raw_tokens:
            tokens.add(normalized)

    if {"research", "paper", "papers", "bidwesh"} & tokens:
        tokens.update({"bangla", "bengali", "hate", "speech", "dataset", "bidwesh"})

    return tokens

def search_messages(query: str, conversation_id: int = None, limit: int = 12):
    tokens = _search_tokens(query)
    if not tokens:
        if conversation_id is not None:
            return get_recent_messages(conversation_id, limit=limit)
        return []

    conn = get_connection()
    cursor = conn.cursor()
    if conversation_id is None:
        cursor.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 500")
    else:
        cursor.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 500",
            (conversation_id,)
        )

    scored = []
    for row in cursor.fetchall():
        item = dict(row)
        content = item.get("content", "")
        content_lower = content.lower()
        score = sum(content_lower.count(token) for token in tokens)

        if "bidwesh" in content_lower and {"research", "paper", "bidwesh"} & tokens:
            score += 5
        if item.get("classification") == "Research Query" and {"research", "paper", "bidwesh"} & tokens:
            score += 2
        if item.get("role") == "user":
            score += 0.25

        if score > 0:
            scored.append((score, item["id"], item))

    conn.close()
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item for _, _, item in scored[:limit]]

def _clean_profile_capture(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .,!?:;\"'")
    value = re.sub(r"\b(from now on|again|anymore|please)\b.*$", "", value, flags=re.IGNORECASE).strip(" .,!?:;\"'")
    return value

def _normalize_person_name(value: str) -> str:
    value = _clean_profile_capture(value)
    if not value:
        return value
    return " ".join(part[:1].upper() + part[1:] for part in value.split())

def infer_profile_from_messages(limit: int = 250) -> dict:
    """
    Deterministically recover explicit user profile updates from saved user turns.
    This prevents stale bootstrap profile data from overriding direct user statements.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT content FROM messages WHERE role = 'user' ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = [r["content"] for r in cursor.fetchall()]
    conn.close()

    profile = {
        "name": None,
        "nickname": None,
        "avoid_address_terms": []
    }

    for content in rows:
        if not profile["name"]:
            name_match = re.search(
                r"\bmy\s+name\s+is\s+(.+?)(?:\s+(?:and\s+)?nick(?:name)?\s+is\b|[.!?\n]|$)",
                content,
                flags=re.IGNORECASE
            )
            if name_match:
                profile["name"] = _normalize_person_name(name_match.group(1))

        if not profile["nickname"]:
            nickname_match = re.search(
                r"\bnick(?:name)?\s+is\s+(.+?)(?:[.!?\n]|$)",
                content,
                flags=re.IGNORECASE
            )
            if nickname_match:
                profile["nickname"] = _normalize_person_name(nickname_match.group(1))

        avoid_match = re.search(
            r"\b(?:don'?t|do\s+not|never)\s+call\s+me\s+['\"]?(.+?)(?:['\".!?\n]|$)",
            content,
            flags=re.IGNORECASE
        )
        if avoid_match:
            term = _clean_profile_capture(avoid_match.group(1)).lower()
            if term and term not in profile["avoid_address_terms"]:
                profile["avoid_address_terms"].append(term)

    return profile

def add_message(conversation_id: int, role: str, content: str, classification: str = None, retrieved_sources: str = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, classification, retrieved_sources) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, role, content, classification, retrieved_sources)
    )
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()
    return msg_id

# --- Offline Fallback Graph Storage ---
def sqlite_add_node(node_id: str, name: str, node_type: str, metadata: dict = None):
    conn = get_connection()
    cursor = conn.cursor()
    meta_str = json.dumps(metadata) if metadata else None
    cursor.execute(
        "INSERT OR REPLACE INTO local_nodes (id, name, type, metadata) VALUES (?, ?, ?, ?)",
        (node_id, name, node_type, meta_str)
    )
    conn.commit()
    conn.close()

def sqlite_add_edge(source_id: str, target_id: str, edge_type: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO local_edges (source_id, target_id, type) VALUES (?, ?, ?)",
        (source_id, target_id, edge_type)
    )
    conn.commit()
    conn.close()

def sqlite_get_graph_data():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, type, metadata FROM local_nodes")
    nodes = []
    for r in cursor.fetchall():
        nodes.append({
            "id": r["id"],
            "name": r["name"],
            "type": r["type"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else {}
        })
        
    cursor.execute("SELECT source_id, target_id, type FROM local_edges")
    edges = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return {"nodes": nodes, "edges": edges}

# --- Offline Fallback Vector Storage ---
def sqlite_add_rag_entry(title: str, content: str, entry_type: str, embedding: list[float] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    emb_str = json.dumps(embedding) if embedding else None
    cursor.execute(
        "INSERT INTO local_rag_entries (title, content, type, embedding) VALUES (?, ?, ?, ?)",
        (title, content, entry_type, emb_str)
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()
    return entry_id

def sqlite_get_rag_entries(entry_type: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if entry_type:
        cursor.execute("SELECT id, title, content, type, created_at FROM local_rag_entries WHERE type = ? ORDER BY created_at DESC", (entry_type,))
    else:
        cursor.execute("SELECT id, title, content, type, created_at FROM local_rag_entries ORDER BY created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def sqlite_get_all_embeddings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, type, embedding FROM local_rag_entries WHERE embedding IS NOT NULL")
    rows = []
    for r in cursor.fetchall():
        rows.append({
            "id": r["id"],
            "title": r["title"],
            "content": r["content"],
            "type": r["type"],
            "embedding": json.loads(r["embedding"])
        })
    conn.close()
    return rows
