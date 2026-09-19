import time
from contextlib import asynccontextmanager

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.agent_state import AgentState
from backend.config import settings
from backend import nodes


def _route_after_resolve(state: AgentState) -> str:
    return "end" if state.get("done") else "seed"


def _route_after_decide(state: AgentState) -> str:
    return "synthesize" if state.get("done") else "crawl"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("resolve", nodes.resolve_node)
    graph.add_node("seed", nodes.seed_node)
    graph.add_node("crawl", nodes.crawl_batch_node)
    graph.add_node("decide", nodes.decide_node)
    graph.add_node("synthesize", nodes.synthesize_node)
    graph.add_node("validate", nodes.validate_node)
    graph.add_node("finalize", nodes.finalize_node)

    graph.set_entry_point("resolve")
    graph.add_conditional_edges("resolve", _route_after_resolve, {"seed": "seed", "end": "finalize"})
    graph.add_edge("seed", "decide")
    graph.add_conditional_edges("decide", _route_after_decide, {"crawl": "crawl", "synthesize": "synthesize"})
    graph.add_edge("crawl", "decide")
    graph.add_edge("synthesize", "validate")
    graph.add_edge("validate", "finalize")
    graph.add_edge("finalize", END)
    return graph


# We use LangGraph's own SQLite checkpointer, so every node's output is
# persisted as a checkpoint keyed by thread_id (= our run_id). This is
# what makes a run resumable: if the process dies mid-crawl, calling
# run_research again with the same run_id and input=None continues from
# the last saved checkpoint instead of starting over. It also lines up
# with the second sqlite file (data/cody_researcher.db, our own tables)
# that stores the human-readable run/page/evidence records the API and
# frontend actually read from.
CHECKPOINT_PATH = settings.sqlite_path.replace(".db", "_checkpoints.db")


@asynccontextmanager
async def _saver():
    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_PATH) as saver:
        yield saver


async def run_research(run_id: str, target: str, task: str):
    graph = build_graph()
    async with _saver() as saver:
        app = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 200}
        initial_state: AgentState = {
            "run_id": run_id,
            "target": target,
            "task": task,
            "allowed_domains": [],
            "iteration": 0,
            "llm_calls": 0,
            "pages_fetched": 0,
            "pages_failed": 0,
            "done": False,
            "_started_at": time.time(),
        }
        await app.ainvoke(initial_state, config=config)


async def resume_research(run_id: str):
    """Continues a previously interrupted run from its last checkpoint.
    Requires that run_research was called at least once with this run_id
    so a checkpoint exists."""
    graph = build_graph()
    async with _saver() as saver:
        app = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 200}
        checkpoint = await saver.aget(config)
        if checkpoint is None:
            raise ValueError(f"no checkpoint found for run {run_id}, cannot resume")
        await app.ainvoke(None, config=config)
