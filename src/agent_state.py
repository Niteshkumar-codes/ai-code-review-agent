from typing import TypedDict


class AgentState(TypedDict):
    diff: str
    context: str | None
    change_analysis: str | None
    security_review: str | None
    error_handling_review: str | None
    quality_review: str | None
    final_review: str | None
