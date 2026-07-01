import json
import re
from memory.llm_client import call_llm

CLASSIFICATION_PROMPT = """
You are the Query Analyzer component of the E.C.o Personal AI Assistant.
Your task is to classify a user's query into one of these four categories:
1. "Memory Query": Requesting recall of past conversations, unstructured notes, or old discussions.
2. "Research Query": Requesting structured findings, scientific papers, concepts, or facts that have been explored before.
3. "Style/Preference Update": The user is explicitly defining or changing their preferences, tone, communication style, or target project (e.g. "prefer short responses", "my name is Shahriar", "I'm working on E.C.o now").
4. "General Query": Basic chatting, coding help, scripting, or standard task requests that do not require deep memory lookup.

Respond ONLY with a JSON object of this schema:
{
    "classification": "Memory Query" | "Research Query" | "Style/Preference Update" | "General Query",
    "confidence": float (between 0.0 and 1.0),
    "reasoning": "Brief explanation of the choice"
}
Do not write markdown formatting wrappers besides the raw JSON itself (do not wrap in ```json).
"""

def classify_query_heuristics(query: str) -> dict:
    """
    Keyword-based heuristic query classification fallback.
    """
    q = query.lower()
    
    # 1. Style / Preference Updates
    style_keywords = [
        "call me", "my name is", "nickname is", "prefer", "don't like",
        "dont call me", "don't call me", "do not call me", "never call me",
        "change my style", "working on", "project name", "workspace is"
    ]
    if any(k in q for k in style_keywords):
        return {
            "classification": "Style/Preference Update",
            "confidence": 0.85,
            "reasoning": "Heuristics: Detected style or profile configuration keyword triggers."
        }

    # 2. Memory Queries
    # Check recall before research so "the research I was asking about" retrieves history.
    memory_keywords = [
        "what did we discuss", "discuss about", "discuss", "remember", "recall",
        "past chat", "past conversation", "convo", "we said", "meeting notes",
        "notes on", "we talked", "what was i doing", "what i was doing",
        "tell me what i was", "what were we doing", "what was i working",
        "what i was working", "what were we working", "what was i asking",
        "what i asked", "i was asking", "that i was asking about", "last time",
        "previously", "previous research", "previous paper", "before i left",
        "last session", "earlier", "yesterday", "forgot", "what did i",
        "what have i", "what have we", "remind me", "what is my name",
        "whats my name", "what's my name", "who am i"
    ]
    if any(k in q for k in memory_keywords):
        return {
            "classification": "Memory Query",
            "confidence": 0.85,
            "reasoning": "Heuristics: Detected conversational recollection keywords."
        }

    # 3. Research Queries
    research_keywords = ["state of", "literature", "paper on", "research", "reseach", "finding about", "findings on", 
                         "concept of", "scientific", "history of", "discover", "experiment", "paper about",
                         "paper names", "papper", "pappers", "study on", "study about",
                         "what do we know about", "findings", "bidwesh", "dataset"]
    if any(k in q for k in research_keywords):
        return {
            "classification": "Research Query",
            "confidence": 0.80,
            "reasoning": "Heuristics: Detected research, literature, or structural concept keywords."
        }

    # 4. General Queries
    return {
        "classification": "General Query",
        "confidence": 0.50,
        "reasoning": "Heuristics: Default fallback."
    }

def analyze_query(query: str, use_llm: bool = None) -> dict:
    """
    Analyzes the query category using active LLM, falling back to heuristics on failure.
    """
    if use_llm is None:
        from memory.config import load_config
        config = load_config()
        use_llm = not config.get("fast_mode", True)
        
    if not use_llm:
        return classify_query_heuristics(query)
        
    try:
        messages = [{"role": "user", "content": f"Classify this query: \"{query}\""}]
        response_text = call_llm(messages, system_prompt=CLASSIFICATION_PROMPT)
        
        # Clean JSON markdown blocks
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        result = json.loads(clean_text)
        if "classification" in result and "confidence" in result:
            return result
    except Exception as e:
        print(f"[Query Analyzer] LLM categorization failed, using heuristics fallback: {e}")
        
    return classify_query_heuristics(query)
