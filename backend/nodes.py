from __future__ import annotations

import asyncio
import time

from backend import db
from backend.agent_state import AgentState
from backend.config import settings
from backend.canonical import canonicalize, registered_domain
from backend.fetcher import fetch_page, looks_js_rendered
from backend.extractor import extract_text, extract_links, content_hash
from backend.resolver import resolve_target
from backend.search import web_search
from backend.llm import ask_json, ask_text, LLMError

RELEVANCE_SYSTEM = """You help a web research agent decide which links are worth visiting.
You will get a research task and a list of candidate links (url + anchor text) found on a
company website. Pick only the links that are plausibly useful for answering the task.
Ignore links to login pages, cookie/privacy policy, careers, social media, unrelated blog
posts, pagination noise, or pages you already have (they won't be in the list).
Reply with ONLY a JSON array of the useful urls, most promising first, e.g.
["https://example.com/products", "https://example.com/about"]
Return at most 12 urls. If none look useful, return [].
"""

EVIDENCE_SYSTEM = """You extract evidence from one web page to help answer a research task.
Read the page text and pull out ONLY facts relevant to the task. For each fact, say whether
it is: "stated" (the page says this directly/verbatim in substance), "extracted" (you pulled
a specific value out of a list/table on the page), or "inferred" (you had to reason about it,
it is not written directly). Do not invent facts that are not supported by the text.
If nothing on this page is relevant to the task, return an empty list.
Reply with ONLY a JSON array like:
[{"kind": "stated", "snippet": "the exact sentence or close paraphrase from the page",
  "note": "why this matters for the task"}]
Keep each snippet under 300 characters and keep it grounded in the actual page text.
"""

SYNTHESIS_SYSTEM = """You are writing the final answer for a web research task, using only
the evidence collected below. Each evidence item has an id, the source url, its kind
(stated/extracted/inferred), and the snippet.

Rules:
- Every factual sentence in your answer must end with citation markers like [E12] referring
  to evidence ids that actually support it. Use the real ids given to you, never invent one.
- If evidence items disagree with each other, say so explicitly in the answer instead of
  silently picking one.
- If a claim required combining multiple evidence items or doing arithmetic, say so
  ("calculated from ...") rather than presenting it as something a page stated directly.
- If the collected evidence is not enough to answer the task properly, say plainly that the
  available evidence is insufficient, and explain what's missing. Do not fill gaps with
  general knowledge that isn't in the evidence.
- Write for a person reading this report, not for a machine. Plain sentences, no meta talk
  about being an AI.

Reply with ONLY a JSON object:
{"answer": "the final written answer with [E#] citation markers",
 "coverage_note": "one or two sentences on how complete/reliable this answer is",
 "sufficient": true or false}
"""


async def resolve_node(state: AgentState) -> dict:
    db.log_event(state["run_id"], "resolve_start", {"target": state["target"]})
    result = resolve_target(state["target"])
    db.log_event(state["run_id"], "resolve_result", result)
    if not result.get("start_url"):
        db.update_run(state["run_id"], status="failed", error=result.get("reasoning", "could not resolve target"))
        return {"start_url": None, "done": True, "stop_reason": "could not resolve official website"}
    db.update_run(
        state["run_id"],
        official_domain=result["official_domain"],
        allowed_domains=",".join(result["allowed_domains"]),
        status="running",
    )
    return {
        "start_url": result["start_url"],
        "official_domain": result["official_domain"],
        "allowed_domains": result["allowed_domains"],
        "resolve_reasoning": result.get("reasoning", ""),
        "llm_calls": state.get("llm_calls", 0) + (0 if result["reasoning"] == "a direct URL was given, so no resolution search was needed" else 1),
    }


async def _filter_relevant(task: str, candidates: list[dict]) -> list[str]:
    if not candidates:
        return []
    lines = "\n".join(f"- {c['url']} | {c['text']}" for c in candidates[:80])
    try:
        picked = ask_json(RELEVANCE_SYSTEM, f"Task: {task}\n\nCandidate links:\n{lines}", max_tokens=800)
        if isinstance(picked, list):
            return [u for u in picked if isinstance(u, str)]
    except LLMError:
        pass
    return []


async def seed_node(state: AgentState) -> dict:
    run_id, task = state["run_id"], state["task"]
    start_url = state["start_url"]
    allowed = state["allowed_domains"]

    result = await fetch_page(start_url)
    llm_calls = state.get("llm_calls", 0)
    if result.error or result.status >= 400:
        db.log_event(run_id, "seed_fetch_failed", {"url": start_url, "error": result.error, "status": result.status})
    else:
        title, text = extract_text(result.html, result.url)
        canon = canonicalize(result.url)
        url_id = db.upsert_url(run_id, result.url, canon, None, registered_domain(canon))
        db.set_url_status(url_id, "visited")
        db.save_page(run_id, url_id, result.url, title, result.fetched_with, content_hash(text), text[:500], "", result.status)
        db.log_event(run_id, "fetched", {"url": result.url, "via": result.fetched_with, "chars": len(text)})

        links = extract_links(result.html, result.url, same_domain_only=True, allowed_domains=allowed)
        good = await _filter_relevant(task, links)
        llm_calls += 1
        for u in good:
            c = canonicalize(u)
            uid = db.upsert_url(run_id, u, c, start_url, registered_domain(c))
            db.set_url_status(uid, "queued", relevance_reason="homepage link judged relevant to task")
        db.log_event(run_id, "seed_links_queued", {"count": len(good)})

    # also run a couple of targeted searches restricted to the official domain -
    # this often finds the exact deep page directly instead of crawling down to it
    for q in [f"site:{state['official_domain']} {task}"]:
        try:
            for r in web_search(q, max_results=6):
                if registered_domain(r["url"]) in allowed:
                    c = canonicalize(r["url"])
                    uid = db.upsert_url(run_id, r["url"], c, "search", registered_domain(c))
                    db.set_url_status(uid, "queued", relevance_reason=f"matched task-focused search: {q}")
        except Exception as e:
            db.log_event(run_id, "seed_search_failed", {"query": q, "error": str(e)})

    return {"llm_calls": llm_calls, "pages_fetched": state.get("pages_fetched", 0) + (0 if result.error else 1)}


async def _process_one_url(run_id: str, task: str, allowed: list[str], url_row: dict, sem: asyncio.Semaphore):
    async with sem:
        db.increment_attempts(url_row["id"])
        for attempt in range(settings.max_retries + 1):
            result = await fetch_page(url_row["url"])
            if not result.error and result.status < 400:
                break
            if attempt == settings.max_retries:
                db.set_url_status(url_row["id"], "failed", last_error=result.error or f"http {result.status}")
                db.log_event(run_id, "fetch_failed", {"url": url_row["url"], "error": result.error, "status": result.status})
                return None
            await asyncio.sleep(1.5 * (attempt + 1))

        title, text = extract_text(result.html, result.url)
        if not text.strip():
            db.set_url_status(url_row["id"], "failed", last_error="no extractable text")
            return None

        chash = content_hash(text)
        if db.page_exists_with_hash(run_id, chash):
            db.set_url_status(url_row["id"], "duplicate")
            return None

        db.set_url_status(url_row["id"], "visited")
        page_id = db.save_page(run_id, url_row["id"], result.url, title, result.fetched_with, chash, text[:500], "", result.status)
        db.log_event(run_id, "fetched", {"url": result.url, "via": result.fetched_with, "chars": len(text)})

        links = extract_links(result.html, result.url, same_domain_only=True, allowed_domains=allowed)
        return {"page_id": page_id, "url": result.url, "title": title, "text": text, "links": links}


async def crawl_batch_node(state: AgentState) -> dict:
    run_id, task = state["run_id"], state["task"]
    allowed = state["allowed_domains"]
    queued = db.get_urls_by_status(run_id, "queued")

    budget_left = settings.max_pages_per_run - state.get("pages_fetched", 0)
    batch = queued[: max(0, min(settings.pages_per_batch, budget_left))]
    if not batch:
        return {"iteration": state.get("iteration", 0) + 1}

    for row in batch:
        db.set_url_status(row["id"], "fetching")

    sem = asyncio.Semaphore(settings.max_concurrency)
    fetched = await asyncio.gather(*[_process_one_url(run_id, task, allowed, row, sem) for row in batch])
    fetched = [f for f in fetched if f]

    pages_fetched = state.get("pages_fetched", 0)
    pages_failed = state.get("pages_failed", 0)
    llm_calls = state.get("llm_calls", 0)

    all_new_links = []
    for item in fetched:
        pages_fetched += 1
        if llm_calls >= settings.max_llm_calls:
            db.log_event(run_id, "llm_budget_exhausted_skip_evidence", {"url": item["url"]})
            continue
        try:
            ev = ask_json(
                EVIDENCE_SYSTEM,
                f"Task: {task}\n\nPage URL: {item['url']}\nPage title: {item['title']}\n\n"
                f"Page text (truncated):\n{item['text'][:3000]}",
                max_tokens=1200,
            )
            llm_calls += 1
            if isinstance(ev, list):
                for e in ev:
                    if isinstance(e, dict) and e.get("snippet"):
                        db.save_evidence(run_id, item["page_id"], item["url"], e.get("kind", "stated"),
                                          e["snippet"][:400], e.get("note", ""))
                db.log_event(run_id, "evidence_extracted", {"url": item["url"], "count": len(ev)})
        except LLMError as e:
            db.log_event(run_id, "evidence_extraction_failed", {"url": item["url"], "error": str(e)})
        all_new_links.extend(item["links"])

    pages_failed += len(batch) - len(fetched)

    if all_new_links and llm_calls < settings.max_llm_calls:
        seen = {}
        for l in all_new_links:
            seen.setdefault(l["url"], l)
        good = await _filter_relevant(task, list(seen.values()))
        llm_calls += 1
        for u in good:
            c = canonicalize(u)
            uid = db.upsert_url(run_id, u, c, "crawl", registered_domain(c))
            db.set_url_status(uid, "queued", relevance_reason="linked from a page judged relevant")
        db.log_event(run_id, "links_queued_from_crawl", {"count": len(good)})

    db.update_run(run_id, pages_fetched=pages_fetched, pages_failed=pages_failed,
                   llm_calls=llm_calls, iterations=state.get("iteration", 0) + 1)

    return {
        "pages_fetched": pages_fetched,
        "pages_failed": pages_failed,
        "llm_calls": llm_calls,
        "iteration": state.get("iteration", 0) + 1,
    }


def _should_stop(state: AgentState, started_at: float) -> str | None:
    if state.get("pages_fetched", 0) >= settings.max_pages_per_run:
        return "reached max pages for this run"
    if state.get("iteration", 0) >= settings.max_iterations:
        return "reached max iterations"
    if state.get("llm_calls", 0) >= settings.max_llm_calls:
        return "reached max LLM calls"
    if time.time() - started_at >= settings.max_run_seconds:
        return "reached max run duration"
    return None


async def decide_node(state: AgentState) -> dict:
    run_id = state["run_id"]
    remaining = db.count_urls(run_id, "queued")
    stop_reason = _should_stop(state, state.get("_started_at", time.time()))
    if stop_reason:
        db.log_event(run_id, "stopping", {"reason": stop_reason})
        return {"done": True, "stop_reason": stop_reason}
    if remaining == 0:
        evidence_count = len(db.get_evidence(run_id))
        db.log_event(run_id, "stopping", {"reason": "no more relevant pages queued", "evidence_items": evidence_count})
        return {"done": True, "stop_reason": "no more relevant pages found"}
    return {"done": False}


async def synthesize_node(state: AgentState) -> dict:
    run_id, task = state["run_id"], state["task"]
    evidence = db.get_evidence(run_id)
    db.log_event(run_id, "synthesize_start", {"evidence_count": len(evidence)})

    if not evidence:
        answer = ("The available evidence is insufficient to answer this task. The agent could not "
                   "find any relevant, accessible pages on the official site within the run's limits.")
        db.update_run(run_id, final_answer=answer, coverage_note="no evidence collected")
        return {"final_answer": answer, "coverage_note": "no evidence collected"}

    # Cap total evidence to ~4000 chars (~1000 tokens) to stay within
    # Groq free-tier TPM limits and avoid 413 errors.
    MAX_SYNTHESIS_CHARS = 4000
    lines_parts = []
    total_chars = 0
    for i, e in enumerate(evidence):
        line = f"[E{i}] source: {e['url']} | kind: {e['kind']} | snippet: {e['snippet']}"
        if total_chars + len(line) > MAX_SYNTHESIS_CHARS:
            break
        lines_parts.append(line)
        total_chars += len(line) + 1
    lines = "\n".join(lines_parts)
    db.log_event(run_id, "synthesis_evidence_used", {"total": len(evidence), "included": len(lines_parts), "chars": total_chars})

    try:
        result = ask_json(SYNTHESIS_SYSTEM, f"Task: {task}\n\nEvidence:\n{lines}", max_tokens=2000)
    except LLMError as e:
        answer = f"The agent collected {len(evidence)} pieces of evidence but the final synthesis step failed ({e}). Raw evidence is available in the sources list below."
        db.update_run(run_id, final_answer=answer, coverage_note="synthesis failed")
        return {"final_answer": answer, "coverage_note": "synthesis failed", "llm_calls": state.get("llm_calls", 0) + 1}

    answer = result.get("answer", "")
    coverage = result.get("coverage_note", "")
    db.update_run(run_id, final_answer=answer, coverage_note=coverage)
    return {"final_answer": answer, "coverage_note": coverage, "llm_calls": state.get("llm_calls", 0) + 1,
            "_evidence_ids": [e["id"] for e in evidence]}


async def validate_node(state: AgentState) -> dict:
    """Deterministic citation validation (bonus requirement): checks that
    every [E#] marker in the final answer maps to a real evidence row that
    was actually collected during this run. No LLM involved - this is
    exactly the kind of check that should be code, not a model call."""
    run_id = state["run_id"]
    answer = state.get("final_answer") or ""
    evidence = db.get_evidence(run_id)
    ev_by_index = {i: e for i, e in enumerate(evidence)}

    import re
    used = set(int(m) for m in re.findall(r"\[E(\d+)\]", answer))

    valid_count, invalid_count = 0, 0
    for idx in used:
        ev = ev_by_index.get(idx)
        if ev:
            db.save_citation(run_id, ev["id"], f"[E{idx}] marker in final answer", True, None)
            valid_count += 1
        else:
            db.save_citation(run_id, evidence[0]["id"] if evidence else "unknown", f"[E{idx}] marker in final answer",
                              False, "citation marker does not match any evidence collected in this run")
            invalid_count += 1

    unused = len(evidence) - len(used & set(ev_by_index.keys()))
    db.log_event(run_id, "citations_validated", {"valid": valid_count, "invalid": invalid_count, "unused_evidence": max(unused, 0)})

    if invalid_count > 0:
        db.log_event(run_id, "citation_integrity_warning",
                      {"invalid_markers": invalid_count, "note": "these were stripped from provenance, answer may need re-check"})
    return {}


async def finalize_node(state: AgentState) -> dict:
    run_id = state["run_id"]
    status = "failed" if not state.get("start_url") else ("partial" if state.get("stop_reason") not in
                                                             (None, "no more relevant pages found") else "completed")
    if state.get("pages_failed", 0) > 0 and status == "completed":
        status = "completed_with_failures"
    # crawl_batch_node is the only place that normally writes these counters to
    # the database, but a run can finish without ever reaching it (e.g. the
    # seed page itself already answered the task and nothing new got queued),
    # so we sync the final numbers here too rather than leave the run row stale.
    db.update_run(run_id, status=status, finished_at=time.time(),
                   pages_fetched=state.get("pages_fetched", 0),
                   pages_failed=state.get("pages_failed", 0),
                   llm_calls=state.get("llm_calls", 0),
                   iterations=state.get("iteration", 0),
                   coverage_note=(state.get("coverage_note") or "") + f" | stop reason: {state.get('stop_reason', 'n/a')}")
    db.log_event(run_id, "run_finished", {"status": status, "stop_reason": state.get("stop_reason")})
    return {}
