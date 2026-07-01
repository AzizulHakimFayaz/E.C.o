from agent import nodes
from agent import router

class EcoStateGraph:
    """
    State Graph implementation that runs ReAct loops.
    """
    def __init__(self):
        # Register node functions
        self.nodes = {
            "load_context": nodes.load_context_node,
            "reason": nodes.reason_node,
            "execute_tools": nodes.execute_tools_node,
            "save_memory": nodes.save_memory_node
        }
        
    def run(self, user_query: str, user_name: str = "Shahriar", conversation_id: int = 1) -> dict:
        """
        Executes the agent graph loop up to 15 iterations.
        """
        # Fetch existing conversation history from SQLite
        from memory import db_sqlite
        history_rows = db_sqlite.get_messages(conversation_id)
        
        messages = []
        for r in history_rows:
            messages.append({"role": r["role"], "content": r["content"]})
            
        # Initialize state
        state = {
            "user_name": user_name,
            "user_query": user_query,
            "conversation_id": conversation_id,
            "messages": messages,
            "system_prompt": "",
            "classification": "General Query",
            "next_node": "load_context",
            "tool_calls": [],
            "errors": []
        }
        
        # Add user query as the current turn message
        state["messages"].append({"role": "user", "content": user_query})
        
        current_node = "load_context"
        max_iterations = 15
        iteration = 0
        
        while current_node != "end" and iteration < max_iterations:
            print(f"🤖 [Agent Node] Entering: {current_node}...")
            
            # Execute current node
            node_func = self.nodes[current_node]
            state = node_func(state)
            
            # Evaluate routing edge
            current_node = router.route_next_node(state)
            iteration += 1
            
        if iteration >= max_iterations:
            print("⚠️ [Agent Engine] Loop reached maximum safety limit of 15 steps.")
            
        # Extract final answer
        response_content = "Failed to compile response."
        for msg in reversed(state["messages"]):
            if msg["role"] == "assistant":
                response_content = msg["content"]
                break
                
        # Persist conversation turn into SQLite logs
        db_sqlite.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_query,
            classification=state["classification"],
            retrieved_sources=None
        )
        db_sqlite.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_content,
            classification=state["classification"],
            retrieved_sources=None
        )
        
        return {
            "response": response_content,
            "classification": state["classification"],
            "messages": state["messages"]
        }
