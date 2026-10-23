from langgraph.graph import END, START, StateGraph
from src.agent_state import AgentState
from src.review_nodes import (
    analyze_changes,
    generate_final_review,
    review_code_quality,
    review_error_handling,
    review_security,
)


def create_review_graph():
    builder = StateGraph(AgentState)

    builder.add_node("analyze_changes", analyze_changes)
    builder.add_node("review_security", review_security)
    builder.add_node("review_error_handling", review_error_handling)
    builder.add_node("review_code_quality", review_code_quality)
    builder.add_node("generate_final_review", generate_final_review)

    builder.add_edge(START, "analyze_changes")
    builder.add_edge("analyze_changes", "review_security")
    builder.add_edge("review_security", "review_error_handling")
    builder.add_edge("review_error_handling", "review_code_quality")
    builder.add_edge("review_code_quality", "generate_final_review")
    builder.add_edge("generate_final_review", END)

    return builder.compile()
