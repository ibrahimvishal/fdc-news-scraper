from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params that only describe *where a link was rendered* or who clicked
# it, never which article it is. edition.mv, for one, appends
# ?ref=tagpage-latest / ?ref=cat-sub / ?ref=article-related depending on the
# page section, so one article used to be posted several times.
TRACKING_PARAMS = {
    "ref", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "mkt_tok",
}
TRACKING_PREFIXES = ("utm_",)

def _is_tracking(name: str) -> bool:
    name = name.lower()
    return name in TRACKING_PARAMS or name.startswith(TRACKING_PREFIXES)

def normalize_url(url: str) -> str:
    """Canonical form of an article URL, used for dedup and posting: no
    fragment, no tracking params, no trailing /amp or slash, lowercase host."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not _is_tracking(k)])
    path = parts.path
    if path.lower().endswith("/amp"):
        path = path[:-4]
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, query, ""))

def is_related_link(url: str) -> bool:
    """True for links a site tags as 'related'/'recommended' widgets (e.g.
    edition.mv's ?ref=article-related, ?ref=cat-tag-related) - not part of the
    tag listing itself, so they can surface old or unrelated articles."""
    refs = [v.lower() for k, v in parse_qsl(urlsplit(url).query) if k.lower() == "ref"]
    return any("related" in v for v in refs)
