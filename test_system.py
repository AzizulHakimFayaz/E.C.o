"""Quick system test for E.C.o memory + agent stack."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_chroma():
    print("=== Testing ChromaDB / Vector Memory ===")
    from memory.chroma_client import add_document, search_documents, get_embedding
    
    emb = get_embedding("test query")
    print(f"  Embedding dimension: {len(emb)}")
    
    doc_id = add_document("Test Document", "This is a test document about graph memory and neural networks.", "research_note")
    print(f"  Added document: {doc_id}")
    
    results = search_documents("graph memory", limit=3)
    print(f"  Search results: {len(results)}")
    for r in results:
        print(f"    - {r['title']} (score: {r['score']:.4f})")
    print("  [OK] ChromaDB / Vector Memory works!\n")

def test_query_analyzer():
    print("=== Testing Query Analyzer (Heuristics) ===")
    from memory.query_analyzer import analyze_query
    
    tests = [
        "What did we discuss yesterday about the project?",
        "Tell me about the state of NLP research in 2026",
        "My name is Shahriar, I prefer short answers",
        "Write a Python function to sort a list"
    ]
    
    for q in tests:
        result = analyze_query(q, use_llm=False)
        print(f"  Query: '{q[:50]}...'")
        print(f"    -> {result['classification']} (conf: {result['confidence']})")
    print("  [OK] Query Analyzer works!\n")

def test_orchestrator():
    print("=== Testing Orchestrator (Prompt Compilation) ===")
    from memory.neo4j_client import get_profile_context
    from memory.orchestrator import compile_unified_system_prompt
    
    profile = get_profile_context("Shahriar")
    prompt = compile_unified_system_prompt("Shahriar", "How do I build a graph memory?", profile, [], {})
    print(f"  System prompt length: {len(prompt)} chars")
    print(f"  Preview: {prompt[:200]}...")
    print("  [OK] Orchestrator works!\n")

def test_agent_imports():
    print("=== Testing Agent Layer Imports ===")
    from agent.graph import EcoStateGraph
    from agent.nodes import TOOLS_MAPPING, re_parse_json_blocks
    from agent.router import route_next_node
    
    # Test JSON parser
    test_text = '```json\n{"tool": "web_search", "arguments": {"query": "test"}}\n```'
    blocks = re_parse_json_blocks(test_text)
    print(f"  Parsed JSON blocks: {blocks}")
    
    # Test tool mapping keys
    print(f"  Registered tools: {list(TOOLS_MAPPING.keys())}")
    
    # Test router with mock state
    state = {"next_node": "reason", "errors": []}
    next_node = route_next_node(state)
    print(f"  Router test: next_node = '{next_node}'")
    print("  [OK] Agent Layer works!\n")

def test_tools():
    print("=== Testing Tool Layer ===")
    from tools.file_reader import read_local_file
    from tools.folder_search import search_folder
    from tools.run_command import run_terminal_command
    
    # File reader
    result = read_local_file(__file__, 1, 5)
    print(f"  File reader: read {len(result)} chars")
    
    # Folder search
    files = search_folder(".", "*.py", recursive=False)
    print(f"  Folder search: found {len(files)} .py files in root")
    
    # Run command
    cmd_result = run_terminal_command("echo hello", cwd=".")
    print(f"  Run command: exit_code={cmd_result['exit_code']}, output='{cmd_result['output'].strip()}'")
    
    print("  [OK] Tool Layer works!\n")

def test_main_import():
    print("=== Testing Main Entry Point (import-only) ===")
    # We can't run the full main() because it starts the interactive loop,
    # but we can test that main.py imports correctly
    import importlib
    # Just test the import doesn't crash
    try:
        # main.py has json import but it's not imported at module level in main
        # Check if there's a missing import
        import main as m
        print(f"  main.py functions: {[f for f in dir(m) if not f.startswith('_')]}")
        print("  [OK] Main entry point imports correctly!\n")
    except Exception as e:
        print(f"  [ERROR] Main entry point import failed: {e}\n")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("   E.C.o SYSTEM INTEGRATION TEST")
    print("="*60 + "\n")
    
    try:
        test_chroma()
    except Exception as e:
        print(f"  [ERROR] ChromaDB test failed: {e}\n")
    
    try:
        test_query_analyzer()
    except Exception as e:
        print(f"  [ERROR] Query Analyzer test failed: {e}\n")
    
    try:
        test_orchestrator()
    except Exception as e:
        print(f"  [ERROR] Orchestrator test failed: {e}\n")
    
    try:
        test_agent_imports()
    except Exception as e:
        print(f"  [ERROR] Agent Layer test failed: {e}\n")
    
    try:
        test_tools()
    except Exception as e:
        print(f"  [ERROR] Tool Layer test failed: {e}\n")

    try:
        test_main_import()
    except Exception as e:
        print(f"  [ERROR] Main import test failed: {e}\n")
    
    print("="*60)
    print("   ALL TESTS COMPLETE")
    print("="*60)
