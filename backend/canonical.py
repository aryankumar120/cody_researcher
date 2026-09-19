from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import tldextract

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid", "_hsenc", "_hsmi",
}


def registered_domain(url: str) -> str:
    ext = tldextract.extract(url)
    return ".".join(part for part in [ext.domain, ext.suffix] if part)


def canonicalize(url: str) -> str:
    """Normalize a URL so equivalent pages map to the same key.

    Lowercases scheme/host, drops the fragment, strips known tracking
    params, sorts remaining query params, and removes a trailing slash
    (except for the bare root path).
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)

    return urlunsplit((scheme, netloc, path, query, ""))


def is_same_registrable_domain(url: str, allowed_domains: list[str]) -> bool:
    dom = registered_domain(url)
    return dom in allowed_domains
