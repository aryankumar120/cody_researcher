import httpx
from bs4 import BeautifulSoup

from backend.config import settings


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Returns [{title, url, snippet}]. Uses Tavily if a key is configured
    (built for LLM agents, gives clean snippets and is fast), otherwise
    falls back to scraping DuckDuckGo's no-JS HTML results page so the
    project still runs with zero paid signup."""
    if settings.tavily_api_key:
        return _tavily_search(query, max_results)
    return _duckduckgo_search(query, max_results)


def _tavily_search(query: str, max_results: int) -> list[dict]:
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": settings.tavily_api_key, "query": query, "max_results": max_results},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]


def _duckduckgo_search(query: str, max_results: int) -> list[dict]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CodyResearcher/1.0)"}
    resp = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers=headers,
        timeout=15,
        follow_redirects=True,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for result in soup.select("div.result")[:max_results]:
        link = result.select_one("a.result__a")
        snippet_el = result.select_one("a.result__snippet") or result.select_one(".result__snippet")
        if not link:
            continue
        results.append({
            "title": link.get_text(strip=True),
            "url": link.get("href", ""),
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })
    return results
