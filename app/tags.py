import re
from collections import defaultdict
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

MAX_ANCESTOR_DEPTH = 15
# Two cards are considered the same template if their nearest classed
# ancestor's class sets overlap by at least this fraction (Jaccard
# similarity). Exact-match was tried first and was too strict - real sites
# vary a card's classes slightly between instances (e.g. a conditional
# spacing utility like Tailwind's "mb-7" on all-but-the-last item in a row),
# which falsely split one genuine listing into multiple smaller clusters
# (verified on avas.mv: exact matching only kept 18 of 25 genuine articles).
TEMPLATE_SIMILARITY_THRESHOLD = 0.5

def _template_signature(a_tag):
    """The (tag name, class set) of the link's nearest classed ancestor - a
    proxy for "which template rendered this card". Cards from the same
    repeating listing share this closely; an unrelated card from a
    same-shaped-URL sidebar/"trending" widget elsewhere on the page renders
    from a visibly different template."""
    node = a_tag.parent
    depth = 0
    while node is not None and depth < MAX_ANCESTOR_DEPTH:
        classes = getattr(node, "attrs", {}).get("class") if hasattr(node, "attrs") else None
        if classes:
            return (node.name, frozenset(classes))
        node = node.parent
        depth += 1
    return None

def _jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 1.0

def _cluster_by_template(candidates: list[tuple[str, object]]) -> list[str]:
    """Union-find clustering of candidates by template-signature similarity;
    returns the hrefs of the largest cluster."""
    signatures = [_template_signature(a) for _, a in candidates]
    parent = list(range(len(candidates)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(candidates)):
        if signatures[i] is None:
            continue
        tag_i, classes_i = signatures[i]
        for j in range(i + 1, len(candidates)):
            if signatures[j] is None:
                continue
            tag_j, classes_j = signatures[j]
            if tag_i == tag_j and _jaccard(classes_i, classes_j) >= TEMPLATE_SIMILARITY_THRESHOLD:
                union(i, j)

    clusters = defaultdict(list)
    for i, (href, _) in enumerate(candidates):
        clusters[find(i)].append(href)

    return max(clusters.values(), key=lambda hrefs: len(set(hrefs)))

def extract_articles(page_url: str) -> list[str]:
    """Fetch a tag/search page and return the article URLs on it (first page
    only - repeat runs plus DB dedupe handle catching up over time, no
    pagination needed)."""
    response = request_with_retry("GET", page_url, headers={"User-Agent": USER_AGENT})
    if response is None:
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    page_domain = urlparse(page_url).netloc.removeprefix("www.")

    candidates = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"]).split("#")[0]
        parsed = urlparse(href)
        if parsed.netloc.removeprefix("www.") != page_domain:
            continue
        if _looks_like_article(parsed.path):
            candidates.append((href, a))

    if not candidates:
        return []

    # Some sites' tag pages mix the actual tag listing with a smaller
    # "related"/"trending" sidebar widget that happens to use the same URL
    # shape (verified on javiyani.mv, where this let an unrelated Asian
    # Games article slip through to the Telegram channel). Cluster
    # candidates by template signature and keep only the largest cluster -
    # the real listing is presumed to be the dominant one on the page.
    urls = _cluster_by_template(candidates)

    return list(dict.fromkeys(urls))

def discover() -> dict[str, str]:
    """Fetch every configured tag/search page. Returns {article_url: source_domain}."""
    results = {}
    for page_url in tag_page_urls() + search_page_urls():
        domain = urlparse(page_url).netloc
        for article_url in extract_articles(page_url):
            results.setdefault(article_url, domain)
    return results
