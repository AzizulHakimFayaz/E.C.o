import os
import json
import math
import hashlib
import requests
from memory.config import load_config
from memory.db_sqlite import sqlite_add_rag_entry, sqlite_get_all_embeddings, sqlite_get_rag_entries

LOCAL_EMBEDDING_DIM = 512
_CHROMA_CLIENT = None
_CHROMA_FAILED = False

def hash_vectorize(text: str, dimension: int = LOCAL_EMBEDDING_DIM) -> list[float]:
    """
    Stable bag-of-words MD5 hashing vectorizer. Generates a fixed-dimension L2-normalized vector.
    Used as an offline fallback.
    """
    words = [w.strip(".,!?;:()\"'-_*`").lower() for w in text.split()]
    words = [w for w in words if w and len(w) > 1]
    
    vec = [0.0] * dimension
    if not words:
        return vec
        
    for word in words:
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dimension
        vec[idx] += 1.0
        
    # L2 normalization to make cosine similarity a simple dot product
    norm = math.sqrt(sum(x*x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec

def get_ollama_embedding(text: str, config: dict) -> list[float]:
    """
    Retrieves embeddings from Ollama embeddings endpoint.
    """
    url = f"{config.get('ollama_url', 'http://localhost:11434')}/api/embeddings"
    data = {
        "model": config.get("ollama_embedding_model", "nomic-embed-text"),
        "prompt": text
    }
    res = requests.post(url, json=data, timeout=5)
    res.raise_for_status()
    return res.json()["embedding"]

def get_embedding(text: str) -> list[float]:
    """
    Unified embedding retrieval. Tries Ollama and falls back to local hashing.
    """
    config = load_config()
    provider = config.get("active_provider", "ollama")
    
    if provider == "ollama":
        try:
            return get_ollama_embedding(text, config)
        except Exception as e:
            # Silence warning and fallback
            pass
            
    return hash_vectorize(text)

def get_chroma_client():
    """
    Singleton persistent ChromaDB client builder. Handles connection fallbacks.
    """
    global _CHROMA_CLIENT, _CHROMA_FAILED
    if _CHROMA_FAILED:
        return None
    if _CHROMA_CLIENT is not None:
        return _CHROMA_CLIENT
        
    config = load_config()
    if not config.get("use_chroma", True):
        _CHROMA_FAILED = True
        return None
        
    try:
        import chromadb  # type: ignore[import-not-found]
        db_path = config.get("chroma_db_path", "./chroma_db")
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), db_path))
            
        os.makedirs(db_path, exist_ok=True)
        _CHROMA_CLIENT = chromadb.PersistentClient(path=db_path)
        return _CHROMA_CLIENT
    except Exception as e:
        print(f"[Vector Memory] ChromaDB initialization failed: {e}. Falling back to SQLite RAG storage.")
        _CHROMA_FAILED = True
        return None

def get_chroma_collection():
    global _CHROMA_FAILED
    if _CHROMA_FAILED:
        return None
    client = get_chroma_client()
    if client is None:
        return None
    try:
        # Create or fetch collection
        return client.get_or_create_collection("eco_vector_memory")
    except Exception as e:
        print(f"[Vector Memory] Error getting Chroma collection: {e}")
        _CHROMA_FAILED = True
        return None

def add_document(title: str, content: str, doc_type: str) -> str:
    """
    Stores document in ChromaDB or SQLite fallback. Returns structural entry ID.
    """
    embedding = get_embedding(f"{title}\n{content}")
    collection = get_chroma_collection()
    
    # Save to SQLite fallback always for record persistence and audits
    entry_id = sqlite_add_rag_entry(title, content, doc_type, embedding)
    entry_str_id = f"doc_{entry_id}"
    
    if collection is not None:
        try:
            collection.add(
                ids=[entry_str_id],
                embeddings=[embedding],
                metadatas=[{"title": title, "type": doc_type}],
                documents=[content]
            )
        except Exception as e:
            print(f"[Vector Memory] Chroma add failed: {e}. SQLite record saved.")
            
    return entry_str_id

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if v1 is None or v2 is None:
        return 0.0
    if hasattr(v1, "tolist"):
        v1 = v1.tolist()
    if hasattr(v2, "tolist"):
        v2 = v2.tolist()
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(x*y for x, y in zip(v1, v2))

def search_documents(query: str, limit: int = 5, min_score: float = 0.05) -> list[dict]:
    """
    Performs vector similarity search. Queries ChromaDB or falls back to SQLite dot-product scan.
    """
    query_emb = get_embedding(query)
    collection = get_chroma_collection()
    
    if collection is not None:
        try:
            results = collection.query(
                query_embeddings=[query_emb],
                n_results=limit,
                include=["documents", "metadatas", "embeddings"]
            )
            
            formatted_results = []
            if results and results["ids"] and results["ids"][0]:
                for idx in range(len(results["ids"][0])):
                    doc_id = results["ids"][0][idx]
                    metadata = results["metadatas"][0][idx]
                    content = results["documents"][0][idx]
                    emb = results["embeddings"][0][idx]
                    
                    # Compute L2 dot-product score
                    score = cosine_similarity(query_emb, emb)
                    if score >= min_score:
                        formatted_results.append({
                            "id": doc_id,
                            "title": metadata.get("title", "Untitled"),
                            "content": content,
                            "type": metadata.get("type", "document"),
                            "score": score
                        })
            # Sort by score descending
            formatted_results.sort(key=lambda x: x["score"], reverse=True)
            return formatted_results[:limit]
        except Exception as e:
            print(f"[Vector Memory] Chroma search failed: {e}. Falling back to SQLite search.")
            
    # SQLite fallback
    all_entries = sqlite_get_all_embeddings()
    results = []
    for entry in all_entries:
        score = cosine_similarity(query_emb, entry["embedding"])
        if score >= min_score:
            results.append({
                "id": f"doc_{entry['id']}",
                "title": entry["title"],
                "content": entry["content"],
                "type": entry["type"],
                "score": score
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
