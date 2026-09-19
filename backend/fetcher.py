from __future__ import annotations

import httpx
from playwright.async_api import async_playwright

from backend.config import settings

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CodyResearcherBot/1.0; +https://github.com)"}

# pages under this many characters of body text are treated as "probably
# needs JS to render" and get a second attempt through a real browser
LIKELY_JS_THRESHOLD = 400


class FetchResult:
    def __init__(self, url: str, html: str, status: int, fetched_with: str, error: str | None = None):
        self.url = url
        self.html = html
        self.status = status
        self.fetched_with = fetched_with
        self.error = error


async def fetch_http(url: str) -> FetchResult:
    async with httpx.AsyncClient(headers=HEADERS, timeout=settings.fetch_timeout_seconds, follow_redirects=True) as client:
        resp = await client.get(url)
        return FetchResult(str(resp.url), resp.text, resp.status_code, "http")


async def fetch_rendered(url: str) -> FetchResult:
    """Renders the page with a real browser. Used only when a plain HTTP
    GET looks like it returned an empty shell (JS-rendered app) - spinning
    up a browser for every page would be slow and resource-heavy, so this
    is the fallback path, not the default one."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=HEADERS["User-Agent"])
            page.set_default_timeout(settings.fetch_timeout_seconds * 1000)
            resp = await page.goto(url, wait_until="networkidle")
            html = await page.content()
            status = resp.status if resp else 0
            return FetchResult(page.url, html, status, "playwright")
        finally:
            await browser.close()


def looks_js_rendered(text_len: int) -> bool:
    return text_len < LIKELY_JS_THRESHOLD


async def fetch_page(url: str) -> FetchResult:
    """Tries a cheap HTTP GET first (fast, no browser resources). Only
    escalates to Playwright if the HTTP response succeeded but the body
    looks empty/JS-rendered, or if the HTTP call failed at the network
    level. Does NOT launch Playwright for HTTP error codes (404, 403 etc)
    since those pages won't have content in a browser either."""
    try:
        result = await fetch_http(url)
        if result.status >= 400:
            # HTTP error (404, 403 etc) — don't waste Playwright on these
            return result
        # HTTP succeeded — check if the page looks JS-rendered (too little text)
        from backend.extractor import extract_text
        _, text = extract_text(result.html, result.url)
        if looks_js_rendered(len(text)):
            try:
                return await fetch_rendered(url)
            except Exception:
                return result  # Return the thin HTTP result rather than failing
        return result
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        # Network-level failure — try Playwright as last resort
        try:
            return await fetch_rendered(url)
        except Exception as e2:
            return FetchResult(url, "", 0, "failed", error=f"http: {e}; playwright: {e2}")
