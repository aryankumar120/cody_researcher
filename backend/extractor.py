import hashlib
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup

from backend.canonical import canonicalize, registered_domain


def extract_text(html: str, url: str) -> tuple[str, str]:
    """Returns (title, main_text). Uses trafilatura, a deterministic
    boilerplate-removal library, rather than an LLM - stripping nav bars,
    footers and ads from HTML is a solved parsing problem and doesn't need
    a model call."""
    extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
    text = extracted or ""
    title = ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
    except Exception:
        pass
    if not text.strip():
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
        except Exception:
            text = ""
    return title, text.strip()


def extract_links(html: str, base_url: str, same_domain_only: bool, allowed_domains: list[str]) -> list[dict]:
    """Pulls out anchor text + href pairs for every link on the page. This
    is deterministic HTML parsing, not something worth an LLM call - the
    LLM only gets involved later, when deciding *which* of these links are
    worth visiting for the task at hand."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        canon = canonicalize(absolute)
        if canon in seen:
            continue
        domain = registered_domain(canon)
        if same_domain_only and domain not in allowed_domains:
            continue
        seen.add(canon)
        text = a.get_text(strip=True)[:200]
        links.append({"url": canon, "text": text or canon})
    return links


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
