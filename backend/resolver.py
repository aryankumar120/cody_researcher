import re
from urllib.parse import urlsplit

from backend.search import web_search
from backend.llm import ask_json
from backend.canonical import registered_domain

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

RESOLVE_SYSTEM = """You resolve a company name to its real official corporate website.
You will be given a company name and a list of search results (title, url, snippet).
Pick the single result that is the company's own official site - not a Wikipedia page,
not a social media profile, not a news article about the company, not a stock-listing
page, not a reseller or directory, and not a different company with a similar name.
If two results look like official domains for the same company (e.g. a country-specific
subdomain), prefer the global/main one.
Reply with ONLY a JSON object: {"official_domain": "example.com", "reasoning": "short reason",
"confidence": "high|medium|low"}
If nothing in the results looks like a genuine official site, reply with
{"official_domain": null, "reasoning": "why", "confidence": "low"}
"""


def resolve_target(target: str) -> dict:
    """Turns whatever the user gave us (a name, a bare domain, or a full URL)
    into a starting URL plus the domain(s) the crawl is allowed to touch.
    Returns {"start_url", "official_domain", "allowed_domains", "reasoning"}.
    """
    target = target.strip()

    if URL_RE.match(target):
        domain = registered_domain(target)
        return {
            "start_url": target,
            "official_domain": domain,
            "allowed_domains": [domain],
            "reasoning": "a direct URL was given, so no resolution search was needed",
        }

    if "." in target and " " not in target:
        start_url = target if URL_RE.match(target) else f"https://{target}"
        domain = registered_domain(start_url)
        return {
            "start_url": start_url,
            "official_domain": domain,
            "allowed_domains": [domain],
            "reasoning": "a bare domain was given, so no resolution search was needed",
        }

    results = web_search(f"{target} official website", max_results=8)
    if not results:
        return {"start_url": None, "official_domain": None, "allowed_domains": [],
                 "reasoning": "search returned no results for this name"}

    formatted = "\n".join(
        f"{i+1}. {r['title']} | {r['url']} | {r['snippet'][:180]}" for i, r in enumerate(results)
    )
    decision = ask_json(
        RESOLVE_SYSTEM,
        f"Company name: {target}\n\nSearch results:\n{formatted}",
        max_tokens=400,
    )

    domain = decision.get("official_domain")
    if not domain:
        return {"start_url": None, "official_domain": None, "allowed_domains": [],
                 "reasoning": decision.get("reasoning", "model could not identify an official site")}

    start_url = domain if URL_RE.match(domain) else f"https://{domain}"
    clean_domain = registered_domain(start_url)
    return {
        "start_url": start_url,
        "official_domain": clean_domain,
        "allowed_domains": [clean_domain],
        "reasoning": decision.get("reasoning", ""),
        "confidence": decision.get("confidence", "medium"),
    }
