import os
import json
import networkx as nx
from memory.config import load_config
from memory import db_sqlite

# Singleton Neo4j Driver
_NEO4J_DRIVER = None
_NEO4J_FAILED = False

def get_neo4j_driver():
    """
    Returns the Neo4j driver singleton if available and configured.
    """
    global _NEO4J_DRIVER, _NEO4J_FAILED
    if _NEO4J_FAILED:
        return None
    if _NEO4J_DRIVER is not None:
        return _NEO4J_DRIVER
        
    config = load_config()
    if not config.get("use_neo4j", True):
        _NEO4J_FAILED = True
        return None
        
    try:
        from neo4j import GraphDatabase
        uri = config.get("neo4j_uri", "bolt://localhost:7687")
        user = config.get("neo4j_user", "neo4j")
        password = config.get("neo4j_password", "password")
        
        # Test connection with a short timeout
        _NEO4J_DRIVER = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=1.0)
        _NEO4J_DRIVER.verify_connectivity()
        return _NEO4J_DRIVER
    except Exception as e:
        print(f"[Graph Memory] Neo4j connection failed: {e}. Falling back to SQLite/NetworkX graph storage.")
        _NEO4J_FAILED = True
        _NEO4J_DRIVER = None
        return None

def build_networkx_graph() -> nx.DiGraph:
    """
    Builds a NetworkX directed graph from SQLite nodes and edges (Offline Fallback).
    """
    data = db_sqlite.sqlite_get_graph_data()
    G = nx.DiGraph()
    
    for node in data["nodes"]:
        G.add_node(
            node["id"],
            name=node["name"],
            type=node["type"],
            metadata=node["metadata"]
        )
        
    for edge in data["edges"]:
        G.add_edge(
            edge["source_id"],
            edge["target_id"],
            type=edge["type"]
        )
        
    return G

# --- Graph Writing Operations ---
def add_graph_node(node_id: str, name: str, node_type: str, metadata: dict = None):
    """
    Adds/Updates a node in Neo4j (if available) or the SQLite/NetworkX fallback.
    """
    metadata = metadata or {}
    driver = get_neo4j_driver()
    
    # Always write to SQLite fallback
    db_sqlite.sqlite_add_node(node_id, name, node_type, metadata)
    
    if driver is not None:
        try:
            with driver.session() as session:
                query = """
                MERGE (n:MemoryNode {id: $id})
                SET n.name = $name,
                    n.type = $type,
                    n.metadata = $metadata
                """
                session.run(query, id=node_id, name=name, type=node_type, metadata=json.dumps(metadata))
        except Exception as e:
            print(f"[Graph Memory] Neo4j write failed: {e}. Using SQLite fallback.")

def add_graph_edge(source_id: str, target_id: str, edge_type: str):
    """
    Creates an edge in Neo4j (if available) or the SQLite/NetworkX fallback.
    """
    driver = get_neo4j_driver()
    
    # Always write to SQLite fallback
    db_sqlite.sqlite_add_edge(source_id, target_id, edge_type)
    
    if driver is not None:
        try:
            with driver.session() as session:
                # Sanitize edge type (must be alphanumeric/underscore for Cypher injection)
                clean_edge_type = "".join([c for c in edge_type if c.isalnum() or c == "_"])
                query = f"""
                MATCH (s:MemoryNode {{id: $source_id}})
                MATCH (t:MemoryNode {{id: $target_id}})
                MERGE (s)-[r:{clean_edge_type}]->(t)
                """
                session.run(query, source_id=source_id, target_id=target_id)
        except Exception as e:
            print(f"[Graph Memory] Neo4j edge write failed: {e}. Using SQLite fallback.")

def _append_unique(items: list[str], value: str):
    if value and value not in items:
        items.append(value)

def _apply_sqlite_profile_overrides(profile: dict) -> dict:
    try:
        inferred = db_sqlite.infer_profile_from_messages()
    except Exception:
        return profile

    if inferred.get("name"):
        profile["name"] = inferred["name"]

    if inferred.get("nickname"):
        _append_unique(profile["preferences"], f"Preferred nickname={inferred['nickname']}")

    avoid_terms = inferred.get("avoid_address_terms") or []
    for term in avoid_terms:
        _append_unique(profile["preferences"], f"Do not call the user={term}")

    if avoid_terms:
        avoid_text = ", ".join(avoid_terms)
        override = f"IMPORTANT: Do not use these address terms for the user: {avoid_text}."
        if profile.get("style") and override not in profile["style"]:
            profile["style"] = f"{profile['style']}; {override}"
        else:
            profile["style"] = override

    return profile

# --- Personal Profile Retrieval ---
def get_profile_context(user_name: str = "Shahriar", include_message_overrides: bool = True) -> dict:
    """
    Reads the User node, working Projects, Preferences, and Style nodes,
    and returns a structured dict for system prompt personalization.
    """
    driver = get_neo4j_driver()
    user_node_id = f"user:{user_name.lower()}"
    
    profile = {
        "name": user_name,
        "style": "Default helpful assistant.",
        "preferences": [],
        "projects": []
    }
    
    if driver is not None:
        try:
            with driver.session() as session:
                # 0. Fetch actual name
                name_query = "MATCH (u:MemoryNode {id: $user_id}) RETURN u.name as name"
                name_res = session.run(name_query, user_id=user_node_id)
                name_record = name_res.single()
                if name_record and name_record["name"]:
                    profile["name"] = name_record["name"]

                # 1. Fetch style
                style_query = """
                MATCH (u:MemoryNode {id: $user_id})-[:WRITES_WITH]->(s:MemoryNode)
                RETURN s.name as style_name, s.metadata as metadata
                """
                style_res = session.run(style_query, user_id=user_node_id)
                styles = []
                for record in style_res:
                    meta = json.loads(record["metadata"]) if record["metadata"] else {}
                    details = meta.get("details", "")
                    styles.append(f"{record['style_name']}: {details}")
                if styles:
                    profile["style"] = "; ".join(styles)
                
                # 2. Fetch preferences
                pref_query = """
                MATCH (u:MemoryNode {id: $user_id})-[:PREFERS]->(p:MemoryNode)
                RETURN p.name as name, p.metadata as metadata
                """
                pref_res = session.run(pref_query, user_id=user_node_id)
                for record in pref_res:
                    meta = json.loads(record["metadata"]) if record["metadata"] else {}
                    val = meta.get("value", "")
                    profile["preferences"].append(f"{record['name']}={val}")
                    
                # 3. Fetch active projects
                proj_query = """
                MATCH (u:MemoryNode {id: $user_id})-[:WORKING_ON]->(p:MemoryNode)
                RETURN p.name as name, p.metadata as metadata
                """
                proj_res = session.run(proj_query, user_id=user_node_id)
                for record in proj_res:
                    meta = json.loads(record["metadata"]) if record["metadata"] else {}
                    status = meta.get("status", "Active")
                    profile["projects"].append(f"{record['name']} (Status: {status})")
            return _apply_sqlite_profile_overrides(profile) if include_message_overrides else profile
        except Exception as e:
            print(f"[Graph Memory] Neo4j profile read failed: {e}. Falling back to SQLite/NetworkX.")
            
    # SQLite / NetworkX fallback
    G = build_networkx_graph()
    if user_node_id not in G:
        return _apply_sqlite_profile_overrides(profile) if include_message_overrides else profile
        
    user_node_data = G.nodes[user_node_id]
    if user_node_data.get("name"):
        profile["name"] = user_node_data["name"]
        
    styles = []
    # Find style edges
    for succ in G.successors(user_node_id):
        edge_data = G.edges[user_node_id, succ]
        node_data = G.nodes[succ]
        
        if edge_data.get("type") == "WRITES_WITH":
            details = node_data.get("metadata", {}).get("details", "")
            styles.append(f"{node_data.get('name')}: {details}")
        elif edge_data.get("type") == "PREFERS":
            val = node_data.get("metadata", {}).get("value", "")
            profile["preferences"].append(f"{node_data.get('name')}={val}")
        elif edge_data.get("type") == "WORKING_ON":
            status = node_data.get("metadata", {}).get("status", "Active")
            profile["projects"].append(f"{node_data.get('name')} (Status: {status})")
            
    if styles:
        profile["style"] = "; ".join(styles)
        
    return _apply_sqlite_profile_overrides(profile) if include_message_overrides else profile

# --- Research Graph Traversals ---
def get_relevant_subgraph(node_id: str, max_depth: int = 2) -> dict:
    """
    Retrieves connected nodes and edges (up to max_depth) centered at node_id.
    """
    driver = get_neo4j_driver()
    
    if driver is not None:
        try:
            with driver.session() as session:
                query = """
                MATCH (start:MemoryNode {id: $node_id})
                CALL apoc.path.subgraphAll(start, {
                    maxLevel: $max_depth,
                    relationshipFilter: ""
                }) YIELD nodes, relationships
                RETURN nodes, relationships
                """
                # APOC fallback in case APOC is missing
                fallback_query = """
                MATCH p=(start:MemoryNode {id: $node_id})-[*1..2]-(connected:MemoryNode)
                RETURN nodes(p) as nodes, relationships(p) as rels
                """
                
                nodes_dict = {}
                edges_list = []
                
                try:
                    res = session.run(fallback_query, node_id=node_id)
                    for record in res:
                        for n in record["nodes"]:
                            meta = json.loads(n["metadata"]) if n.get("metadata") else {}
                            nodes_dict[n["id"]] = {
                                "id": n["id"],
                                "name": n["name"],
                                "type": n["type"],
                                "metadata": meta
                            }
                        for r in record["rels"]:
                            edges_list.append({
                                "source_id": r.nodes[0]["id"],
                                "target_id": r.nodes[1]["id"],
                                "type": r.type
                            })
                except Exception:
                    # Very simple manual 1-hop traversal if 2-hop list is error prone
                    simple_query = """
                    MATCH (s:MemoryNode {id: $node_id})-[r]-(t:MemoryNode)
                    RETURN s, r, t
                    """
                    res = session.run(simple_query, node_id=node_id)
                    for record in res:
                        s_node = record["s"]
                        t_node = record["t"]
                        r_rel = record["r"]
                        
                        s_meta = json.loads(s_node["metadata"]) if s_node.get("metadata") else {}
                        t_meta = json.loads(t_node["metadata"]) if t_node.get("metadata") else {}
                        
                        nodes_dict[s_node["id"]] = {"id": s_node["id"], "name": s_node["name"], "type": s_node["type"], "metadata": s_meta}
                        nodes_dict[t_node["id"]] = {"id": t_node["id"], "name": t_node["name"], "type": t_node["type"], "metadata": t_meta}
                        
                        edges_list.append({
                            "source_id": s_node["id"],
                            "target_id": t_node["id"],
                            "type": r_rel.type
                        })
                
                return {"nodes": list(nodes_dict.values()), "edges": edges_list}
        except Exception as e:
            print(f"[Graph Memory] Neo4j subgraph fetch failed: {e}. Using SQLite fallback.")
            
    # SQLite / NetworkX fallback
    G = build_networkx_graph()
    if node_id not in G:
        return {"nodes": [], "edges": []}
        
    visited_nodes = {node_id}
    queue = [(node_id, 0)]
    
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
            
        for succ in G.successors(current):
            if succ not in visited_nodes:
                visited_nodes.add(succ)
                queue.append((succ, depth + 1))
                
        for pred in G.predecessors(current):
            if pred not in visited_nodes:
                visited_nodes.add(pred)
                queue.append((pred, depth + 1))
                
    subgraph_nodes = []
    for n in visited_nodes:
        node_attr = G.nodes[n]
        subgraph_nodes.append({
            "id": n,
            "name": node_attr.get("name", n),
            "type": node_attr.get("type", "Unknown"),
            "metadata": node_attr.get("metadata", {})
        })
        
    subgraph_edges = []
    for u, v, data in G.edges(data=True):
        if u in visited_nodes and v in visited_nodes:
            subgraph_edges.append({
                "source_id": u,
                "target_id": v,
                "type": data.get("type", "related_to")
            })
            
    return {"nodes": subgraph_nodes, "edges": subgraph_edges}
