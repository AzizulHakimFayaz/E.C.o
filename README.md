# E.C.o Memory System

> **A Personal AI Research Assistant with Graph-Based Long-Term Memory**

E.C.o is an agentic AI assistant designed to function as a long-term research partner rather than a simple chatbot. It maintains a structured memory of projects, goals, user profile, and findings across sessions.

---

## ⚡ Core Features

- **ReAct Agent Loop**: Iterative thinking process using tool execution, reasoning, and self-correction.
- **Dual-Layer Memory**:
  - **Graph Memory** (Neo4j / SQLite + NetworkX fallback): Tracks users, projects, research questions, concepts, and relationships.
  - **Vector Memory** (ChromaDB / SQLite + hash-vectorizer fallback): Stores research notes, web scrapes, and details for similarity-based RAG.
- **Robust LLM Router**: Seamless integration with local Ollama (`qwen3` / custom models) or cloud Groq APIs with automatic self-healing fallback.
- **Local Fallback Mode**: Zero external service requirements. Runs offline out of the box using SQLite and standard libraries.
- **Interactive Windows Tools**: Built-in capabilities to search directories, view local files, run terminal commands, search the web, and launch applications.

---

## 🛠️ Project Structure

```
E.C.o/
│
├── main.py                     # CLI Interactive Panel & Controller
├── test_system.py              # Core System Integration Tests
├── test_memory_system.py       # Core Memory Layer Isolation Tests
├── requirements.txt            # System Dependencies List
│
├── agent/                      # State Graph & ReAct Loop
│   ├── __init__.py
│   ├── graph.py                # E.C.o State Graph Execution Engine
│   ├── nodes.py                # State Nodes (load_context, reason, execute_tools, save_memory)
│   └── router.py               # Conditional Router & Error Healer
│
├── memory/                     # Multi-Layer Memory & Context DBs
│   ├── __init__.py
│   ├── settings.json           # User Configuration, API Keys, and Feature Flags
│   ├── config.py               # Configuration Loader
│   ├── db_sqlite.py            # SQLite Base Tables (Conversations, Messages, Graph, RAG fallbacks)
│   ├── chroma_client.py        # Vector Retrieval Client (ChromaDB with SQLite/Hash vector fallback)
│   ├── neo4j_client.py         # Graph Retrieval Client (Neo4j with SQLite/NetworkX fallback)
│   ├── llm_client.py           # Multi-Provider LLM Wrapper (Ollama & Groq)
│   ├── query_analyzer.py       # Heuristic and LLM Intent Classifier
│   └── knowledge_extractor.py  # Learning Loop extraction of facts into memory
│
└── tools/                      # Interactive Windows Operating System Tools
    ├── __init__.py
    ├── browser.py              # Playwright scraper with urllib text fallback
    ├── file_reader.py          # Line-based safe file content reader
    ├── folder_search.py        # Recursive file search with glob patterns
    ├── open_app.py             # OS-specific application launcher (Notepad, VS Code, etc.)
    ├── run_command.py          # Shell command execution shell runner
    └── web_search.py           # DuckDuckGo scraper (zero API key required)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.13)
- (Optional) **Ollama** installed locally for local LLM inference.
- (Optional) **Neo4j Desktop** or **Neo4j Aura** for the graphical database console.

### 2. Installation
Clone or navigate to the workspace directory and install requirements:
```bash
pip install -r requirements.txt
```

### 3. Run Tests
Verify all fallbacks and integration components are operational:
```bash
python test_system.py
python test_memory_system.py
```

### 4. Start E.C.o
Start the interactive CLI:
```bash
python main.py
```

---

## ⚙️ Configuration & Special Commands

While inside the interactive E.C.o terminal (`python main.py`), you can use the following commands:
- `/config` — Review or modify current active LLM providers (Ollama vs. Groq) and API keys.
- `/graph` — Print a quick text-based outline of active nodes in your Graph Memory.
- `/quit` — Safely exit and save the conversation to database.

---

## 🧬 Memory Persistence Details

If Neo4j or ChromaDB are not running or installed, E.C.o will automatically fall back to standard **SQLite** (`eco_memory.db` in the root folder):
1. **Graph Nodes**: Stored in the `local_nodes` and `local_edges` tables, loaded into memory via `networkx.DiGraph`.
2. **Vector Documents**: Stored in the `local_rag_entries` table. Embeddings are generated using a stable bag-of-words MD5 hashing vectorizer (`hash_vectorize`) or Ollama embedding models, and matching is done via cosine-similarity dot-products.
3. **Chat History**: Fully tracked and preserved in `conversations` and `messages` tables.
