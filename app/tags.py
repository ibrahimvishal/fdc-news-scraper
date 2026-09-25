import re
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup

from .config import BASE_DIR
from .http import request_with_retry, USER_AGENT

# An article link is recognized by its URL path shape, not by guessing a
# per-site selector: either it contains a run of 4+ digits (the common
# numeric-article-ID pattern - /85761, /news/54293, /articles/21805, ...) or
# it's a long hyphenated slug (corporatemaldives.com's style -
# /fdc-signs-epc-contract-with-ashoka-buildcon-limited.../). Verified against
# 11 real tag/search pages; both patterns are needed since sites differ.
DIGIT_RUN = re.compile(r"\d{4,}")
MIN_SLUG_HYPHENS = 4
MIN_SLUG_LENGTH = 30

# Nav/utility paths that could otherwise slip through the shape check on some
# site (e.g. a tag page linking to itself, or a paginated tag/tags listing).
EXCLUDED_PATH_PREFIXES = (
    "/category", "/tag", "/tags", "/journalist", "/e-paper", "/ethics",
    "/login", "/register", "/subscribe", "/en", "/about", "/editorial-policy",
    "/code-of-conduct", "/privacy", "/terms-of-use", "/team", "/multimedia",
)

def _load_yaml_urls(filename: str) -> list[str]:
    path = BASE_DIR / filename
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [u for u in data.get("urls", []) if u]

def tag_page_urls() -> list[str]:
    return _load_yaml_urls("tags.yaml")

def search_page_urls() -> list[str]:
    return _load_yaml_urls("search.yaml")

def _looks_like_article(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in EXCLUDED_PATH_PREFIXES):
        return False
    if DIGIT_RUN.search(path):
        return True
    if path.count("-") >= MIN_SLUG_HYPHENS and len(path) >= MIN_SLUG_LENGTH:
        return True
    return False

def extract_articles(page_url: str) -> list[str]:
    """Fetch a tag/search page and return the article URLs on it (first page
    only - repeat runs plus DB dedupe handle catching up over time, no
    pagination needed)."""
    response = request_with_retry("GET", page_url, headers={"User-Agent": USER_AGENT})
    if response is None:
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    page_domain = urlparse(page_url).netloc.removeprefix("www.")

    urls = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"]).split("#")[0]
        parsed = urlparse(href)
        if parsed.netloc.removeprefix("www.") != page_domain:
            continue
        if _looks_like_article(parsed.path):
            urls.append(href)

    return list(dict.fromkeys(urls))

def discover() -> dict[str, str]:
    """Fetch every configured tag/search page. Returns {article_url: source_domain}."""
    results = {}
    for page_url in tag_page_urls() + search_page_urls():
        domain = urlparse(page_url).netloc
        for article_url in extract_articles(page_url):
            results.setdefault(article_url, domain)
    return results
