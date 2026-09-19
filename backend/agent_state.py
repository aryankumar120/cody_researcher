from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    run_id: str
    target: str
    task: str
    start_url: Optional[str]
    official_domain: Optional[str]
    allowed_domains: list[str]
    resolve_reasoning: str
    iteration: int
    llm_calls: int
    pages_fetched: int
    pages_failed: int
    done: bool
    stop_reason: Optional[str]
    final_answer: Optional[str]
    coverage_note: Optional[str]
