# Cody Researcher

An autonomous web research agent. Give it a company (name, domain, or URL) and a question. It finds the official site, reads the relevant pages, and answers with citations(proof behind the claim) back to the exact source page.

# Demo Video - 3 min only: 

https://github.com/user-attachments/assets/413736f7-f44f-4e0f-b771-a3875b82aa38


## Setup - bash 

1. In the project root:

brew install python@3.11
python3.11 -m venv .venv          
source .venv/bin/activate         
pip install --upgrade pip         
pip install -r requirements.txt
playwright install chromium

3. Run server:

python3 -m uvicorn backend.main:app --reload --port 8000
 
## How it works

- **Resolve** — A URL/domain used, a company name gets searched and the model picks the real official site.
- **Seed** — fetches the homepage, filters its links for relevance, also runs one task-focused `site:domain` search to jump straight to deep pages.
- **Crawl** — fetches pages in small batches, pulls task-relevant facts from each, queues new relevant links found along the way.
- **Decide** — after each batch, checks queue + guardrails then continue loops or stops.
- **Synthesize** — writes the final answer from the collected items, with `[E#]` citation markers.
- **Validate** — plain code checks every citation marker matches real collected evidence before the answer is shown.

## Tool choices, briefly

- **Playwright** — For fallback, used when a plain HTTP fetch fails or looks broken (JS-heavy pages). Not used by default.

- **React + Tailwind (Vite build)** — Frontend for project.

- **LangGraph** — A plain loop can't pause and resume on its own, I'd have to build that myself. LangGraph gives resumability if something gets disrupted/paused.
Role in Cody Researcher : It runs the pipeline as a state graph (resolve → seed → crawl → decide → synthesize → validate → finalize)

- **SQLite** — This runs on one person's machine, not a server with many users — Postgres would mean an extra thing to install and configure which is not needed here. SQLite just works with zero setup.

## Failure handling

- Bad/failed LLM call → retried, then a typed error the caller handles gracefully (skips that one page/batch, doesn't crash the run).
- Failed page fetch → retried up to `MAX_RETRIES`, then marked failed with the error saved; run finishes as `completed_with_failures` rather than hiding the something.
- Playwright crash/timeout → caught and logged, page marked failed, nothing invented.
- Process dies mid-run → `/resume` picks up from the last LangGraph checkpoint.

## Scaling to hundreds of pages

The idea: keep the expensive stuff (AI calls) small and fixed, even as the number of pages grows.

- No page gets read twice. Every URL is checked against what's already been visited before fetching it, so the same page never gets processed twice, even under a different link.
- The AI doesn't look at every link one by one. A whole batch of new links is shown to the model in a single call, and it picks out which ones matter — so 200 links still cost one AI call, not 200.
- Sevral pages are fetched at a time, not one by one. There's a setting (MAX_CONCURRENCY) that controls how many pages get fetched at once — turning that number up is the main way to go faster on a bigger site.
- The final answer doesn't grow with the crawl. By the end, the AI writing the answer only looks at the short list of facts already pulled out — not the raw pages themselves. So, whether 10 pages or 200 got crawled, that last step costs about the same.


## Testing

- 10 required test cases live in `docs/test_report.md`.
- Run them all: `python scripts/run_tests.py`.
- Results have to be actually run locally — see the note at the top of the test report for why.

## Limitations

- No PDF/image/video content extraction — treated as a fetch failure.
- No login/paywall handling.
- Relevance filtering and fact extraction are one LLM call per batch/page, no chunking for unusually large pages.
- Search quality without a Tavily key depends on free DuckDuckGo scraping.

## Known issues found during development

- **413 crash on synthesis:** The first Siemens run collected 34 pages of evidence and the synthesis prompt exceeded Groq's 8,000 TPM limit (sent ~12K tokens). Fixed by capping the evidence payload to ~4,000 characters before sending to the LLM.

- **86 API calls for a single run:** The `@retry` was retrying non-retryable errors like 413 (payload too large) 3 times, and `ask_json` added another retry layer on top — so one failed call cost up to 6 actual API calls. Fixed by adding a `retry_if_exception` filter that skips 400/413/422 errors.

- **Playwright launching for 404 pages:** Every HTTP error (including genuine 404s) triggered a full Chromium launch. A 404 page won't magically have content in a browser. Changed to only use Playwright when HTTP succeeds but the body looks empty (JS-rendered apps).

- **Guardrails too generous for free tier:** Default limits (40 pages, 15 iterations, 40 LLM calls) were fine for paid API tiers but caused the agent to accumulate too much evidence on the free tier before hitting synthesis. Lowered to 15 pages, 8 iterations, 20 LLM calls.

- **No rate limiting between API calls:** Burst calls would hit the tokens-per-minute ceiling. Added a 2-second minimum interval between Groq calls.

- **Page text too large for evidence extraction:** Sending 6,000 characters per page (~2K tokens) to the evidence extraction prompt was expensive. Halved to 3,000 characters — still enough for fact extraction but cuts per-page cost significantly.

## Project layout

```
backend/
  main.py             FastAPI app and routes
  graph.py            LangGraph code
  nodes.py            Agents
  resolver.py         takes company name -> official website
  fetcher.py          HTTP fetch with Playwright fallback
  extractor.py        HTML -> text and HTML -> links 
  canonical.py        URL normalization and dedup
  search.py           Tavily or DuckDuckGo search
  llm.py              Groq API wrapper with retries and JSON parsing
  db.py               SQLite schema and all data access
  config.py           Settings with fallback
frontend/             
  src/
    App.jsx             
    api.js              
    components/         
  dist/               Output
scripts/
  run_tests.py        Runs the 10 testcases
docs/
  design_note.pdf     System Design format
  test_report.md      Test report
```
