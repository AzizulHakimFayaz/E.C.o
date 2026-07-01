import sys
import os
import math
import json
from contextlib import contextmanager

# Ensure workspace root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from memory.config import load_config, save_config, DEFAULT_CONFIG
from memory import db_sqlite
from memory import chroma_client
from memory import neo4j_client
from memory import query_analyzer
from memory import orchestrator

MEMORY_TABLES = [
    "conversations",
    "messages",
    "local_nodes",
    "local_edges",
    "local_rag_entries",
]

@contextmanager
def preserve_memory_tables():
    db_sqlite.init_db()
    conn = db_sqlite.get_connection()
    backups = {}
    original_config = load_config()
    try:
        test_config = dict(original_config)
        test_config["use_chroma"] = False
        save_config(test_config)
        chroma_client._CHROMA_CLIENT = None
        chroma_client._CHROMA_FAILED = False

        for table in MEMORY_TABLES:
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
            backups[table] = rows
        yield
    finally:
        for table in ["messages", "conversations", "local_edges", "local_nodes", "local_rag_entries"]:
            conn.execute(f"DELETE FROM {table}")
        for table in MEMORY_TABLES:
            rows = backups[table]
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join(["?"] * len(columns))
            column_sql = ", ".join(columns)
            values = [[row[col] for col in columns] for row in rows]
            conn.executemany(
                f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
                values
            )
        conn.commit()
        conn.close()
        save_config(original_config)
        chroma_client._CHROMA_CLIENT = None
        chroma_client._CHROMA_FAILED = False

def test_config():
    print("--- 1. Testing Config Module ---")
    config = load_config()
    assert config is not None
    assert "sqlite_db_path" in config
    print("[OK] Config loaded successfully.")
    print(f"Active Provider: {config['active_provider']}")
    print(f"SQLite Path: {config['sqlite_db_path']}")
    print()

def test_sqlite_backend():
    print("--- 2. Testing SQLite Backend ---")
    db_sqlite.init_db()
    
    # Create conversation
    conv_id = db_sqlite.create_conversation("E.C.o Test Conversation")
    assert conv_id > 0
    print(f"[OK] Created conversation with ID: {conv_id}")
    
    # Add messages
    msg1 = db_sqlite.add_message(conv_id, "user", "Hello E.C.o", "General Query")
    msg2 = db_sqlite.add_message(conv_id, "assistant", "Hello Shahriar, how can I help you?", "General Query")
    
    assert msg1 > 0
    assert msg2 > 0
    print("[OK] Added user and assistant messages to database.")
    
    # Read history
    history = db_sqlite.get_messages(conv_id)
    assert len(history) == 2
    assert history[0]["content"] == "Hello E.C.o"
    assert history[1]["content"] == "Hello Shahriar, how can I help you?"
    print("[OK] Verified message history retrieval.")
    print()

def test_vector_fallback():
    print("--- 3. Testing Embedding Vectorizer & Vector Search Fallback ---")
    text1 = "Long term memory systems in AI assistants enable personalization"
    text2 = "Long term memory systems in AI assistants enable personalization"
    text3 = "Windows automation with Python and pywinauto allows clicking desktop items"
    
    # Verify hashing generator
    vec1 = chroma_client.hash_vectorize(text1)
    vec2 = chroma_client.hash_vectorize(text2)
    vec3 = chroma_client.hash_vectorize(text3)
    
    assert len(vec1) == 512
    assert len(vec3) == 512
    
    # Verify unit normalization (L2 norm should equal 1.0)
    norm1 = math.sqrt(sum(x*x for x in vec1))
    assert abs(norm1 - 1.0) < 1e-5
    
    # Verify cosine similarity values
    sim_identical = chroma_client.cosine_similarity(vec1, vec2)
    sim_different = chroma_client.cosine_similarity(vec1, vec3)
    
    assert abs(sim_identical - 1.0) < 1e-5
    assert sim_different < 0.9  # Distinct sentences should have lower similarity
    print("[OK] Custom hashing embedding generator generates valid unit-normalized vectors.")
    print(f"  Similarity (Identical): {sim_identical:.4f}")
    print(f"  Similarity (Different): {sim_different:.4f}")
    
    # Add document to index
    doc_id = chroma_client.add_document("Memory Systems", text1, "research_note")
    print(f"[OK] Added document to memory index with ID: {doc_id}")
    
    # Search document
    results = chroma_client.search_documents("memory personalization", limit=2)
    assert len(results) > 0
    assert "Memory Systems" in [r["title"] for r in results]
    print(f"[OK] Vector search found matching document: '{results[0]['title']}' with score {results[0]['score']:.4f}")
    print()

def test_graph_fallback():
    print("--- 4. Testing Graph Database Operations & Fallback ---")
    user_id = "user:shahriar"
    proj_id = "project:e_c_o"
    style_id = "style:shahriar"
    pref_id = "pref:language"
    
    # Clear fallback database first
    conn = db_sqlite.get_connection()
    conn.execute("DELETE FROM local_nodes")
    conn.execute("DELETE FROM local_edges")
    conn.commit()
    conn.close()
    
    # Add nodes
    neo4j_client.add_graph_node(user_id, "Shahriar", "User")
    neo4j_client.add_graph_node(proj_id, "E.C.o Memory System", "Project", {"status": "Active"})
    neo4j_client.add_graph_node(style_id, "UserStyle", "Style", {"details": "Informal, short replies, mixes Bengali"})
    neo4j_client.add_graph_node(pref_id, "LanguagePreference", "Preference", {"value": "Bengali + English"})
    
    # Add edges
    neo4j_client.add_graph_edge(user_id, proj_id, "WORKING_ON")
    neo4j_client.add_graph_edge(user_id, style_id, "WRITES_WITH")
    neo4j_client.add_graph_edge(user_id, pref_id, "PREFERS")
    
    print("[OK] Graph nodes and relationships created successfully in SQLite graph fallback.")
    
    # Verify graph loader
    G = neo4j_client.build_networkx_graph()
    assert user_id in G
    assert proj_id in G
    assert G.has_edge(user_id, proj_id)
    print("[OK] Successfully loaded SQLite nodes and edges into NetworkX DiGraph.")
    
    # Load profile
    profile = neo4j_client.get_profile_context("Shahriar", include_message_overrides=False)
    assert profile["name"] == "Shahriar"
    assert "Informal" in profile["style"]
    assert "LanguagePreference=Bengali + English" in profile["preferences"]
    assert "E.C.o Memory System (Status: Active)" in profile["projects"]
    
    print("[OK] Successfully compiled profile context from graph traversal:")
    print(f"  Name: {profile['name']}")
    print(f"  Style: {profile['style']}")
    print(f"  Preferences: {profile['preferences']}")
    print(f"  Projects: {profile['projects']}")
    print()

def test_query_analyzer():
    print("--- 5. Testing Query Intent Analyzer Heuristics ---")
    q1 = "what did we discuss about Bengali NLP yesterday?"
    q2 = "explain the state of the art in graph databases and Neo4j"
    q3 = "please call me Shahriar and answer casually from now on!"
    q4 = "how do I run tests on Windows?"
    q5 = "please tell me about the reseach projects that i was asking about"
    q6 = "What is my name"
    
    a1 = query_analyzer.classify_query_heuristics(q1)
    a2 = query_analyzer.classify_query_heuristics(q2)
    a3 = query_analyzer.classify_query_heuristics(q3)
    a4 = query_analyzer.classify_query_heuristics(q4)
    a5 = query_analyzer.classify_query_heuristics(q5)
    a6 = query_analyzer.classify_query_heuristics(q6)
    
    assert a1["classification"] == "Memory Query"
    assert a2["classification"] == "Research Query"
    assert a3["classification"] == "Style/Preference Update"
    assert a4["classification"] == "General Query"
    assert a5["classification"] == "Memory Query"
    assert a6["classification"] == "Memory Query"
    
    print(f"[OK] Resolved Query Classification (Heuristics):")
    print(f"  '{q1}' -> {a1['classification']}")
    print(f"  '{q2}' -> {a2['classification']}")
    print(f"  '{q3}' -> {a3['classification']}")
    print(f"  '{q4}' -> {a4['classification']}")
    print(f"  '{q5}' -> {a5['classification']}")
    print(f"  '{q6}' -> {a6['classification']}")
    print()

def test_closed_loop_extraction_dry_run():
    print("--- 6. Testing Closed-Loop Extraction Structure ---")
    # Simulate a JSON payload that the extractor receives from the LLM
    simulated_llm_json = {
        "user_profile": {
            "name": "Shahriar",
            "active_project": "E.C.o Memory Core",
            "preferences": [
                {"key": "CodeStyle", "value": "Async IO"}
            ],
            "style": {
                "formal_level": "casual",
                "tone": "conversational",
                "custom_notes": "uses bang ! at times"
            }
        },
        "research": {
            "questions": [
                {"id": "q:bengali_graph_rag", "text": "Are there benchmarks for Bengali GraphRAG?", "status": "explored"}
            ],
            "findings": [
                {
                    "id": "finding:no_bengali_benchmarks",
                    "content": "No dedicated GraphRAG benchmarks exist for Bengali, requiring novel evaluation datasets.",
                    "confidence": "high",
                    "related_question_id": "q:bengali_graph_rag",
                    "sources": [
                        {"id": "src:bengali_nlp_survey", "title": "Survey of Bengali NLP 2025", "url_or_file": "arxiv.org/abs/2501.9999"}
                    ],
                    "concepts": [
                        {"id": "concept:graph_rag", "name": "GraphRAG", "description": "Graph-based Retrieval Augmented Generation"}
                    ]
                }
            ]
        }
    }
    
    # We will test the extractor parsing and writing workflow
    # by writing the nodes and edges manually mimicking the database extraction routine
    user_node = "user:shahriar"
    proj_node = "project:eco_memory_core"
    pref_node = "pref:codestyle"
    
    neo4j_client.add_graph_node(user_node, "Shahriar", "User")
    neo4j_client.add_graph_node(proj_node, "E.C.o Memory Core", "Project", {"status": "Active"})
    neo4j_client.add_graph_edge(user_node, proj_node, "WORKING_ON")
    
    # Extract findings
    findings = simulated_llm_json["research"]["findings"]
    for f in findings:
        f_id = f["id"]
        f_content = f["content"]
        neo4j_client.add_graph_node(f_id, f_content[:30] + "...", "Finding", {"content": f_content})
        
        # Link source
        for src in f["sources"]:
            src_id = src["id"]
            neo4j_client.add_graph_node(src_id, src["title"], "Source", {"url_or_file": src["url_or_file"]})
            neo4j_client.add_graph_edge(f_id, src_id, "FROM_SOURCE")
            
        # Link concepts
        for c in f["concepts"]:
            c_id = c["id"]
            neo4j_client.add_graph_node(c_id, c["name"], "Concept", {"description": c["description"]})
            neo4j_client.add_graph_edge(f_id, c_id, "RELATESTO_CONCEPT")
            
    # Verify graph links
    G = neo4j_client.build_networkx_graph()
    assert "finding:no_bengali_benchmarks" in G
    assert "src:bengali_nlp_survey" in G
    assert "concept:graph_rag" in G
    assert G.has_edge("finding:no_bengali_benchmarks", "src:bengali_nlp_survey")
    assert G.has_edge("finding:no_bengali_benchmarks", "concept:graph_rag")
    
    print("[OK] Successfully parsed and created nodes/edges mimicking the closed-loop knowledge extractor.")
    print()

if __name__ == "__main__":
    print("====================================================")
    print("         E.C.o CORE MEMORY SYSTEM TEST SUITE       ")
    print("====================================================")
    print()
    try:
        with preserve_memory_tables():
            test_config()
            test_sqlite_backend()
            test_vector_fallback()
            test_graph_fallback()
            test_query_analyzer()
            test_closed_loop_extraction_dry_run()
        print("====================================================")
        print("    SUCCESS: ALL CORE MEMORY TEST MODULES PASSED    ")
        print("====================================================")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("====================================================")
        print("          FAILURE: TEST MODULE RUN FAILED           ")
        print("====================================================")
        sys.exit(1)
