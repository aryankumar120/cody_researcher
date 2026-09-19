"""
Fires the 10+ required test cases at a locally running Cody Researcher
instance and prints/saves the raw results so they can be pasted into
docs/test_report.md. Run this after `bash run.sh` is up on port 8000.

    python scripts/run_tests.py
"""
import json
import time
import httpx

BASE = "http://127.0.0.1:8000"

TEST_CASES = [
    {
        "name": "company-name-only",
        "target": "Siemens",
        "task": "Find the company's major product areas and the markets mentioned on its official website.",
    },
    {
        "name": "direct-url",
        "target": "https://www.python.org/about/",
        "task": "What is the mission of the Python Software Foundation and who runs it?",
    },
    {
        "name": "navigation-required",
        "target": "https://www.anthropic.com",
        "task": "List the models Claude currently offers and one stated use case for each, according to the site.",
    },
    {
        "name": "dynamic-js-site",
        "target": "https://stripe.com",
        "task": "What payment methods does Stripe say it supports, according to their website?",
    },
    {
        "name": "pagination-multi-page",
        "target": "https://openai.com/news",
        "task": "List the five most recent news posts and a one-line summary of each.",
    },
    {
        "name": "irrelevant-links-present",
        "target": "https://www.nasa.gov",
        "task": "What is the goal of the Artemis program according to NASA's official site?",
    },
    {
        "name": "information-not-findable",
        "target": "https://www.apple.com",
        "task": "What was Apple's exact revenue for the most recent fiscal quarter, in dollars?",
    },
    {
        "name": "bare-domain-no-scheme",
        "target": "wikipedia.org",
        "task": "What is the stated mission of the Wikimedia Foundation?",
    },
    {
        "name": "cross-domain-official-content",
        "target": "Google",
        "task": "What are Google's official developer documentation domains and what do they cover?",
    },
    {
        "name": "small-company-low-authority",
        "target": "Basecamp",
        "task": "What product does Basecamp sell today and what is its pricing model?",
    },
]


def run_case(case, poll_seconds=5, timeout_seconds=700):
    print(f"\n=== {case['name']} ===")
    resp = httpx.post(f"{BASE}/api/research", json={"target": case["target"], "task": case["task"]}, timeout=30)
    resp.raise_for_status()
    run_id = resp.json()["run_id"]
    print(f"run_id: {run_id}")

    start = time.time()
    while time.time() - start < timeout_seconds:
        r = httpx.get(f"{BASE}/api/research/{run_id}", timeout=30).json()
        status = r["run"]["status"]
        if status not in ("pending", "running", "resuming"):
            print(f"status: {status}  pages: {r['run']['pages_fetched']}  llm_calls: {r['run']['llm_calls']}")
            print(f"answer: {r['run']['final_answer']}")
            return {"case": case["name"], "run_id": run_id, "result": r}
        time.sleep(poll_seconds)
    print("timed out waiting for run to finish")
    return {"case": case["name"], "run_id": run_id, "result": None}


if __name__ == "__main__":
    all_results = [run_case(c) for c in TEST_CASES]
    with open("docs/test_run_raw_output.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print("\nSaved raw results to docs/test_run_raw_output.json")
