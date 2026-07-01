import os
import sys
import json
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add current workspace directory to sys.path so we can import from local files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory import db_sqlite
from memory.config import load_config, save_config
from memory import neo4j_client
from agent.graph import EcoStateGraph

app = FastAPI(
    title="E.C.o API Server",
    description="Backend API endpoints for E.C.o (Graph-Memory Agentic Personal AI Assistant)",
    version="1.0.0"
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure database is initialized on start
db_sqlite.init_db()

# --- Config Endpoints ---
@app.get("/api/config")
def get_config():
    try:
        return load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")

@app.post("/api/config")
def update_config(config_data: Dict[str, Any] = Body(...)):
    try:
        # Load existing config to merge changes
        current = load_config()
        current.update(config_data)
        save_config(current)
        return {"status": "success", "message": "Configuration updated successfully", "config": current}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")

# --- Conversation Endpoints ---
@app.get("/api/conversations")
def list_conversations():
    try:
        return db_sqlite.get_conversations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list conversations: {str(e)}")

@app.post("/api/conversations")
def create_conversation(payload: Dict[str, str] = Body(...)):
    title = payload.get("title", "E.C.o Interactive Chat")
    try:
        conv_id = db_sqlite.create_conversation(title)
        return {"id": conv_id, "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")

@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: int):
    try:
        conn = db_sqlite.get_connection()
        cursor = conn.cursor()
        # Enable foreign keys for cascade delete of messages
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Conversation {conv_id} deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete conversation: {str(e)}")

@app.get("/api/conversations/{conv_id}/messages")
def get_messages(conv_id: int):
    try:
        return db_sqlite.get_messages(conv_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")

# --- Chat & Agent Execution Endpoints ---
@app.post("/api/chat")
def run_chat(payload: Dict[str, Any] = Body(...)):
    message = payload.get("message")
    conversation_id = payload.get("conversation_id")
    user_name = payload.get("user_name", "Shahriar")
    
    if not message or conversation_id is None:
        raise HTTPException(status_code=400, detail="Missing required parameters 'message' or 'conversation_id'")
        
    try:
        agent = EcoStateGraph()
        result = agent.run(message, user_name=user_name, conversation_id=conversation_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent loop error: {str(e)}")

# --- Graph Data & Memory Operations ---
def get_neo4j_graph_data() -> Optional[Dict[str, List[Dict[str, Any]]]]:
    driver = neo4j_client.get_neo4j_driver()
    if driver is None:
        return None
    try:
        with driver.session() as session:
            # Get all nodes
            nodes_res = session.run("MATCH (n:MemoryNode) RETURN n.id as id, n.name as name, n.type as type, n.metadata as metadata")
            nodes = []
            for r in nodes_res:
                meta = {}
                if r["metadata"]:
                    try:
                        meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
                    except:
                        meta = {"raw": r["metadata"]}
                nodes.append({
                    "id": r["id"],
                    "name": r["name"],
                    "type": r["type"],
                    "metadata": meta
                })
                
            # Get all edges
            edges_res = session.run("MATCH (s:MemoryNode)-[r]->(t:MemoryNode) RETURN s.id as source_id, t.id as target_id, type(r) as type")
            edges = []
            for r in edges_res:
                edges.append({
                    "source_id": r["source_id"],
                    "target_id": r["target_id"],
                    "type": r["type"]
                })
            return {"nodes": nodes, "edges": edges}
    except Exception as e:
        print(f"[API Server] Error reading Neo4j graph: {e}. Falling back to SQLite.")
        return None

@app.get("/api/graph")
def get_graph():
    # Try Neo4j graph first, then fall back to SQLite
    graph = get_neo4j_graph_data()
    if graph is None:
        try:
            graph = db_sqlite.sqlite_get_graph_data()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch SQLite graph: {str(e)}")
    return graph

@app.post("/api/graph/nodes")
def add_node(payload: Dict[str, Any] = Body(...)):
    node_id = payload.get("id")
    name = payload.get("name")
    node_type = payload.get("type", "Concept")
    metadata = payload.get("metadata", {})
    
    if not node_id or not name:
        raise HTTPException(status_code=400, detail="Missing required parameters 'id' or 'name'")
        
    try:
        neo4j_client.add_graph_node(node_id, name, node_type, metadata)
        return {"status": "success", "message": f"Node '{name}' added/updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add node: {str(e)}")

@app.delete("/api/graph/nodes/{node_id}")
def delete_node(node_id: str):
    try:
        # Delete from SQLite local DB
        conn = db_sqlite.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM local_nodes WHERE id = ?", (node_id,))
        cursor.execute("DELETE FROM local_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        conn.commit()
        conn.close()
        
        # Delete from Neo4j if active
        driver = neo4j_client.get_neo4j_driver()
        if driver is not None:
            try:
                with driver.session() as session:
                    session.run("MATCH (n:MemoryNode {id: $id}) DETACH DELETE n", id=node_id)
            except Exception as ne:
                print(f"[API Server] Neo4j node deletion failed: {ne}")
                
        return {"status": "success", "message": f"Node {node_id} and all its connected edges deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete node: {str(e)}")

@app.post("/api/graph/edges")
def add_edge(payload: Dict[str, str] = Body(...)):
    source_id = payload.get("source_id")
    target_id = payload.get("target_id")
    edge_type = payload.get("type")
    
    if not source_id or not target_id or not edge_type:
        raise HTTPException(status_code=400, detail="Missing source_id, target_id or type")
        
    try:
        neo4j_client.add_graph_edge(source_id, target_id, edge_type)
        return {"status": "success", "message": f"Edge {source_id} -[{edge_type}]-> {target_id} created."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add edge: {str(e)}")

@app.delete("/api/graph/edges")
def delete_edge(edge_type: str, source_id: str, target_id: str):
    try:
        # Delete from SQLite local DB
        conn = db_sqlite.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM local_edges WHERE source_id = ? AND target_id = ? AND type = ?",
            (source_id, target_id, edge_type)
        )
        conn.commit()
        conn.close()
        
        # Delete from Neo4j if active
        driver = neo4j_client.get_neo4j_driver()
        if driver is not None:
            try:
                with driver.session() as session:
                    # Sanitize label type
                    clean_type = "".join([c for c in edge_type if c.isalnum() or c == "_"])
                    query = f"MATCH (s:MemoryNode {{id: $s_id}})-[r:{clean_type}]->(t:MemoryNode {{id: $t_id}}) DELETE r"
                    session.run(query, s_id=source_id, t_id=target_id)
            except Exception as ne:
                print(f"[API Server] Neo4j edge deletion failed: {ne}")
                
        return {"status": "success", "message": f"Edge {source_id} -[{edge_type}]-> {target_id} deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete edge: {str(e)}")

# --- RAG Documents Endpoints ---
@app.get("/api/rag")
def get_rag_entries(type: Optional[str] = None):
    try:
        return db_sqlite.sqlite_get_rag_entries(type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch RAG entries: {str(e)}")

# --- Mount Static Files ---
# Create static directory if it does not exist
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)

# Mount the static directory
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
