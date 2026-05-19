"""News sentiment analysis — Bing News RSS (primary) + Google News RSS (fallback).

Bing News RSS provides direct article URLs and real description snippets
extracted from the source article.  For truncated summaries, the actual
``og:description`` meta tag is fetched from the article page in parallel.

Scoring is keyword-based (no ML library required).  Each headline and summary
is scanned against ``_BULLISH`` / ``_BEARISH`` / ``_STRONG_*`` word sets to
produce a score in ``[-1.0, +1.0]``.

The Bing RSS ``<News:Source>`` namespace is query-specific (e.g.
``xmlns:News="https://www.bing.com/news/search?q=TCS&format=RSS"``), so the
URI must be extracted dynamically from the raw XML and URL-unescaped before
use with ElementTree.
"""

import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import List

import httpx

logger = logging.getLogger(__name__)

# ── Sentiment keyword sets ─────────────────────────────────────────────────────

_BULLISH: frozenset[str] = frozenset({
    "profit", "growth", "record", "surge", "rally", "strong", "buy",
    "upgrade", "target", "upside", "positive", "earnings beat", "dividend",
    "expansion", "invest", "gain", "robust", "outperform", "deal", "win",
    "breakthrough", "acquisition", "partnership", "order", "contract",
    "recovery", "rebound", "high", "rise", "increase", "improved",
    "bullish", "opportunity", "recommend", "overweight", "beat", "boost",
    "momentum", "green", "advance", "higher", "peak", "approve", "approved",
    "award", "launch", "new high", "all-time", "outperform",
})

_BEARISH: frozenset[str] = frozenset({
    "loss", "decline", "fall", "concern", "sell", "weak", "cut",
    "downgrade", "risk", "fraud", "penalty", "fine", "lawsuit", "debt",
    "default", "miss", "disappoint", "layoff", "probe", "investigation",
    "warning", "underperform", "bearish", "crash", "drop", "lower",
    "pressure", "worry", "fear", "uncertain", "volatile", "challenge",
    "regulatory", "ban", "halt", "delay", "recession", "slowdown",
    "inflation", "rate hike", "interest rate", "tighten", "negative",
    "withdrawal", "outflow", "sell-off", "correction", "bear", "plunge",
    "slump", "weaken", "disappointing", "missed", "reduced", "worse",
})

#: Two-word phrases that add double weight when matched.
_STRONG_BULLISH: frozenset[str] = frozenset({
    "record high", "all-time high", "beats estimate", "strong buy", "outperform",
})
_STRONG_BEARISH: frozenset[str] = frozenset({
    "fraud", "ban", "default", "bankruptcy", "crash", "investigation", "probe",
})

# ── In-memory caches ───────────────────────────────────────────────────────────

_CACHE: dict = {}
_TTL: int = 600       # 10-minute sentiment cache (news changes frequently)

_ART_CACHE: dict = {}
_ART_TTL: int = 86400  # 24-hour article summary cache (article text is immutable)

# ── HTTP headers ───────────────────────────────────────────────────────────────

_BROWSER_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

#: Maximum characters of article HTML to read when extracting og:description.
_HEAD_SCAN_CHARS: int = 20_000


# ── Text helpers ───────────────────────────────────────────────────────────────


def _clean_text(raw: str) -> str:
    """Decode HTML entities, strip tags, and normalise whitespace.

    Args:
        raw: Raw HTML or plain-text string (may be ``None``).

    Returns:
        Cleaned plain-text string, capped at 400 characters.
    """
    text = unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def _is_dupe_of_title(summary: str, title: str) -> bool:
    """Detect whether *summary* is essentially a repetition of *title*.

    A summary is considered a duplicate when it is very short, or when it
    starts with the first 60 characters of the title, or when it contains the
    first 50 characters of the title and is not substantially longer.

    Args:
        summary: Candidate summary text.
        title: Article headline to compare against.

    Returns:
        ``True`` if the summary adds no information beyond the title.
    """
    s = summary.lower().strip()
    t = title.lower().strip()
    if not s or len(s) < 25:
        return True
    if s.startswith(t[:60]):
        return True
    if t[:50] in s and len(s) < len(t) + 60:
        return True
    return False


def _to_two_sentences(text: str) -> str:
    """Trim *text* to at most two sentences, capped at 280 characters.

    Args:
        text: Input text (may be longer than two sentences).

    Returns:
        Up to two full sentences, truncated with ``"…"`` if still over
        280 characters after joining.
    """
    text = text.strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    result = " ".join(parts[:2])
    if len(result) > 280:
        result = result[:277].rsplit(" ", 1)[0] + "…"
    return result


def _is_truncated(s: str) -> bool:
    """Return ``True`` when *s* looks like a truncated snippet.

    Detects both Unicode ellipsis ``…`` and ASCII ``...`` endings, as Bing
    uses the ASCII form in its RSS snippets.  Also flags very short strings
    (under 60 characters) that are unlikely to be useful summaries.

    Args:
        s: Summary string to test.

    Returns:
        ``True`` if the string is empty, ends with an ellipsis, or is shorter
        than 60 characters.
    """
    t = s.rstrip() if s else ""
    return not t or t.endswith("…") or t.endswith("...") or len(t) < 60


def _score_headline(text: str) -> float:
    """Score *text* on a sentiment scale from ``-1.0`` (very bearish) to ``+1.0`` (very bullish).

    Keyword matching: each ``_BULLISH`` hit scores +1, each ``_BEARISH`` hit
    scores -1, and ``_STRONG_*`` phrases score ±2.  The raw count is normalised
    by the total to stay in ``[-1.0, +1.0]``.

    Args:
        text: Combined headline + summary string to analyse.

    Returns:
        Sentiment float in ``[-1.0, +1.0]``, or ``0.0`` if no keywords match.
    """
    low = text.lower()
    bull = sum(1 for w in _BULLISH if w in low)
    bear = sum(1 for w in _BEARISH if w in low)
    bull += sum(2 for w in _STRONG_BULLISH if w in low)
    bear += sum(2 for w in _STRONG_BEARISH if w in low)
    total = bull + bear
    return 0.0 if total == 0 else max(-1.0, min(1.0, (bull - bear) / total))


# ── Article og:description fetcher ────────────────────────────────────────────


def _fetch_og_desc(url: str) -> str:
    """Fetch the ``og:description`` (or ``meta[name=description]``) from *url*.

    Only reads the first ``_HEAD_SCAN_CHARS`` characters of the response to
    avoid downloading entire article bodies.  Results are cached for
    ``_ART_TTL`` seconds so the same article is never fetched twice.

    Bing and Google tracking URLs are skipped — they don't carry article content.

    Args:
        url: Direct article URL (not a Bing/Google redirect).

    Returns:
        Cleaned description string, or ``""`` on failure or cache miss.
    """
    if not url or "google.com" in url or "bing.com" in url:
        return ""
    entry = _ART_CACHE.get(url)
    if entry is not None and time.time() - entry["ts"] < _ART_TTL:
        return entry["val"]
    val = ""
    try:
        resp = httpx.get(url, timeout=4.0, follow_redirects=True, headers=_BROWSER_HEADERS)
        if resp.status_code == 200:
            head = resp.text[:_HEAD_SCAN_CHARS]
            for pat in (
                r'property=["\']og:description["\'][^>]+content=["\']([^"\']{20,})["\']',
                r'content=["\']([^"\']{20,})["\'][^>]+property=["\']og:description["\']',
                r'name=["\']description["\'][^>]+content=["\']([^"\']{20,})["\']',
                r'content=["\']([^"\']{20,})["\'][^>]+name=["\']description["\']',
            ):
                m = re.search(pat, head, re.IGNORECASE)
                if m:
                    val = _clean_text(m.group(1))
                    break
    except Exception:  # noqa: BLE001 — network errors must not bubble up
        pass
    _ART_CACHE[url] = {"ts": time.time(), "val": val}
    return val


def _enrich_summaries(items: List[dict], max_fetch: int = 5) -> None:
    """Replace truncated summaries with ``og:description`` fetched in parallel.

    Only articles with a ``link`` field and a truncated ``summary`` are
    targeted.  Up to *max_fetch* articles are fetched concurrently using a
    ``ThreadPoolExecutor``.  The items are modified **in place**.

    Args:
        items: List of article dicts (modified in place).
        max_fetch: Maximum number of parallel article fetches.
    """
    need = [
        it for it in items
        if it.get("link") and _is_truncated(it.get("summary", ""))
    ]
    if not need:
        return
    targets = need[:max_fetch]
    with ThreadPoolExecutor(max_workers=4) as pool:
        fmap = {pool.submit(_fetch_og_desc, it["link"]): it for it in targets}
        for fut in as_completed(fmap, timeout=6):
            it = fmap[fut]
            try:
                desc = fut.result() or ""
                if desc and not _is_dupe_of_title(desc, it["title"]):
                    it["summary"] = _to_two_sentences(desc)
                    s = round(_score_headline(it["title"] + " " + it["summary"]), 3)
                    it["score"] = s
                    it["sentiment"] = "bullish" if s > 0.1 else "bearish" if s < -0.1 else "neutral"
                    it["impact"] = "positive" if s > 0.2 else "negative" if s < -0.2 else "neutral"
            except Exception:  # noqa: BLE001
                pass


# ── Bing News RSS (primary) ────────────────────────────────────────────────────


def _bing_url_to_real(bing_link: str) -> str:
    """Extract the real article URL from a Bing News tracking URL.

    Bing News links are of the form
    ``https://www.bing.com/news/apiclick.aspx?...&url=<encoded_url>&...``.
    This function extracts the ``url`` query parameter.

    Args:
        bing_link: Raw ``<link>`` text from the Bing RSS feed.

    Returns:
        The decoded article URL, or *bing_link* unchanged if extraction fails.
    """
    try:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(bing_link).query)
        return params.get("url", [""])[0] or bing_link
    except Exception:  # noqa: BLE001
        return bing_link


def _fetch_bing_rss(query: str, max_items: int = 10) -> List[dict]:
    """Fetch Bing News RSS and return structured article dicts.

    The Bing RSS feed uses a query-specific ``xmlns:News`` namespace whose URI
    includes the URL-encoded query string.  The raw XML contains ``&amp;``
    while ElementTree internally stores ``&``, so the namespace URI must be
    extracted from the raw XML with regex and then unescaped before use in
    ``item.find(f'{{{news_ns}}}Source')``.

    Args:
        query: Search query string (e.g. ``"TCS.NS Tata Consultancy NSE stock"``).
        max_items: Maximum number of articles to return.

    Returns:
        List of article dicts with keys: ``title``, ``source``, ``summary``,
        ``link``, ``published``, ``score``, ``sentiment``, ``impact``, ``scope``.
        Empty list on network/parse failure.
    """
    items = []
    try:
        url = (
            f"https://www.bing.com/news/search"
            f"?q={urllib.parse.quote_plus(query)}&format=RSS"
        )
        resp = httpx.get(url, timeout=8.0, headers=_BROWSER_HEADERS)
        if resp.status_code != 200:
            return items

        raw_xml = resp.text
        root = ET.fromstring(raw_xml)

        # Bing's namespace URI is query-specific and contains &amp; in raw XML.
        # ElementTree parses & internally, so unescape the raw-XML match.
        ns_m = re.search(r'xmlns:News="([^"]+)"', raw_xml)
        news_ns = unescape(ns_m.group(1)) if ns_m else ""

        seen: set = set()

        for item in root.findall(".//item"):
            title_el = item.find("title")
            if title_el is None:
                continue
            raw_title = _clean_text(title_el.text or "").strip()
            if not raw_title or raw_title in seen:
                continue
            seen.add(raw_title)

            link_el = item.find("link")
            pub_el = item.find("pubDate")
            desc_el = item.find("description")
            src_el = item.find(f"{{{news_ns}}}Source") if news_ns else None

            raw_link = link_el.text if link_el is not None else None
            real_link = _bing_url_to_real(raw_link) if raw_link else None

            raw_desc = (desc_el.text or "") if desc_el is not None else ""
            summary = _clean_text(raw_desc)
            if _is_dupe_of_title(summary, raw_title):
                summary = ""
            elif summary and not _is_truncated(summary):
                summary = _to_two_sentences(summary)

            source = ""
            if src_el is not None and src_el.text:
                source = src_el.text.strip()
            if not source:
                m = re.search(r"\s[-–]\s([^-–]{4,40})$", raw_title)
                if m:
                    source = m.group(1).strip()

            m2 = re.search(r"\s[-–]\s[^-–]{4,40}$", raw_title)
            clean_title = raw_title[: m2.start()].strip() if m2 else raw_title

            score = _score_headline(clean_title + " " + summary)
            sentiment = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"

            items.append({
                "title": clean_title or raw_title,
                "source": source,
                "summary": summary,
                "link": real_link,
                "published": pub_el.text if pub_el is not None else None,
                "score": round(score, 3),
                "sentiment": sentiment,
                "impact": "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral",
                "scope": "domestic",
            })
            if len(items) >= max_items:
                break
    except Exception as exc:  # noqa: BLE001
        logger.debug("Bing RSS fetch failed: %s", exc)
    return items


# ── Google News RSS (fallback) ─────────────────────────────────────────────────


def _fetch_google_rss(url: str, max_items: int = 8) -> List[dict]:
    """Fetch Google News RSS from a pre-built URL and return article dicts.

    Used as a fallback when Bing returns fewer than 4 results, and for
    international / macro news queries.  Google News links are tracking URLs
    that redirect to the article — ``og:description`` enrichment is skipped
    for these.

    Args:
        url: Full Google News RSS URL (including query params).
        max_items: Maximum number of articles to return.

    Returns:
        List of article dicts (same schema as ``_fetch_bing_rss``).
        Empty list on failure.
    """
    items = []
    try:
        resp = httpx.get(url, timeout=10.0, headers=_BROWSER_HEADERS)
        if resp.status_code != 200:
            return items
        root = ET.fromstring(resp.text)
        seen: set = set()

        for item in root.findall(".//item"):
            title_el = item.find("title")
            if title_el is None:
                continue
            raw_title = _clean_text(title_el.text or "").strip()
            if not raw_title or raw_title in seen:
                continue
            seen.add(raw_title)

            link_el = item.find("link")
            pub_el = item.find("pubDate")
            desc_el = item.find("description")
            src_el = item.find("source")

            raw_desc = _clean_text(desc_el.text) if (desc_el is not None and desc_el.text) else ""
            raw_desc = re.sub(r"\s*[-–]\s*[A-Z][A-Za-z .]{3,40}$", "", raw_desc).strip()
            summary = "" if _is_dupe_of_title(raw_desc, raw_title) else _to_two_sentences(raw_desc)

            source = ""
            if src_el is not None and src_el.text:
                source = src_el.text.strip()
            if not source:
                m = re.search(r"\s[-–]\s([^-–]{4,40})$", raw_title)
                if m:
                    source = m.group(1).strip()

            m2 = re.search(r"\s[-–]\s[^-–]{4,40}$", raw_title)
            clean_title = raw_title[: m2.start()].strip() if m2 else raw_title

            score = _score_headline(clean_title + " " + summary)
            sentiment = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"
            link = link_el.text if link_el is not None else None

            items.append({
                "title": clean_title or raw_title,
                "source": source,
                "summary": summary,
                "link": link,
                "published": pub_el.text if pub_el is not None else None,
                "score": round(score, 3),
                "sentiment": sentiment,
                "impact": "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral",
                "scope": "domestic",
            })
            if len(items) >= max_items:
                break
    except Exception as exc:  # noqa: BLE001
        logger.debug("Google RSS fetch failed for %s: %s", url, exc)
    return items


# ── News category fetchers ─────────────────────────────────────────────────────


def _fetch_domestic_news(company: str, symbol_base: str) -> List[dict]:
    """Fetch NSE stock-specific domestic news via Bing, with Google fallback.

    After fetching, calls ``_enrich_summaries`` to replace truncated snippets
    with real ``og:description`` content from the article pages.

    Args:
        company: Company name (e.g. ``"Tata Consultancy Services"``).
        symbol_base: Ticker without exchange suffix (e.g. ``"TCS"``).

    Returns:
        List of up to 10 article dicts tagged with ``scope="domestic"``.
    """
    q = f"{symbol_base} {company} NSE stock India"
    items = _fetch_bing_rss(q, max_items=10)

    if len(items) < 4:
        gurl = (
            f"https://news.google.com/rss/search"
            f"?q={symbol_base.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        items = _fetch_google_rss(gurl, max_items=10)

    for it in items:
        it["scope"] = "domestic"
    _enrich_summaries(items, max_fetch=5)
    return items


def _fetch_international_news(company: str, sector: str) -> List[dict]:
    """Fetch international and FII-related news for *company* / *sector*.

    Args:
        company: Company name used for the primary query.
        sector: Sector name used for the secondary macro query.

    Returns:
        List of up to 6 article dicts tagged with ``scope="international"``.
    """
    queries = [
        f"{company} global stock market",
        f"{sector} sector global outlook FII",
    ]
    results = []
    for q in queries[:2]:
        items = _fetch_bing_rss(q, max_items=4)
        if not items:
            gurl = (
                f"https://news.google.com/rss/search"
                f"?q={q.replace(' ', '+')}&hl=en&gl=US&ceid=US:en"
            )
            items = _fetch_google_rss(gurl, max_items=4)
        for it in items:
            it["scope"] = "international"
        results.extend(items)
    _enrich_summaries(results, max_fetch=3)
    return results[:6]


def _fetch_macro_news() -> List[dict]:
    """Fetch RBI / monetary policy macro news relevant to all NSE stocks.

    Returns:
        List of up to 4 article dicts tagged with ``scope="macro"``.
    """
    queries = ["RBI monetary policy India interest rate market"]
    results = []
    for q in queries[:1]:
        items = _fetch_bing_rss(q, max_items=4)
        if not items:
            gurl = (
                f"https://news.google.com/rss/search"
                f"?q={q.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
            )
            items = _fetch_google_rss(gurl, max_items=4)
        for it in items:
            it["scope"] = "macro"
        results.extend(items)
    _enrich_summaries(results, max_fetch=2)
    return results[:4]


# ── Main entry point ───────────────────────────────────────────────────────────


def analyze_sentiment(
    symbol: str, company_name: str = "", sector: str = ""
) -> dict:
    """Return a comprehensive sentiment analysis for *symbol*.

    Fetches domestic, international, and macro news in sequence.  The
    composite sentiment score is the arithmetic mean of domestic headline
    scores.  Results are cached for ``_TTL`` seconds.

    Args:
        symbol: Yahoo Finance ticker symbol (e.g. ``"TCS.NS"``).
        company_name: Full company name used to build the Bing search query.
            Defaults to the ticker base (e.g. ``"TCS"``).
        sector: Sector name used for the international news query.

    Returns:
        Dict with:
        - ``score``: Composite sentiment float in ``[-1.0, +1.0]``.
        - ``label``: ``"Bullish"``, ``"Neutral"``, or ``"Bearish"``.
        - ``confidence``: ``"Strong"``, ``"Moderate"``, or ``"Weak"``.
        - ``headlines``: Up to 10 domestic article dicts.
        - ``intl_news``: Up to 6 international article dicts.
        - ``macro_news``: Up to 4 macro article dicts.
        - ``counts``: ``{"bullish": n, "bearish": n, "neutral": n}``.
    """
    cache_key = f"sentiment:{symbol}"
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry["ts"] < _TTL:
        return entry["data"]

    symbol_base = symbol.replace(".NS", "").replace(".BO", "")
    company = company_name or symbol_base
    sec = sector or ""

    domestic = _fetch_domestic_news(company, symbol_base)
    intl = _fetch_international_news(company, sec)
    macro = _fetch_macro_news()

    dom_scores = [h["score"] for h in domestic]

    if not dom_scores:
        result = {
            "symbol": symbol,
            "score": 0.0,
            "label": "Neutral",
            "confidence": "Weak",
            "headlines": [],
            "intl_news": intl,
            "macro_news": macro,
            "counts": {"bullish": 0, "bearish": 0, "neutral": 0},
        }
        _CACHE[cache_key] = {"ts": time.time(), "data": result}
        return result

    avg = sum(dom_scores) / len(dom_scores)
    bull_n = sum(1 for s in dom_scores if s > 0.1)
    bear_n = sum(1 for s in dom_scores if s < -0.1)
    neut_n = len(dom_scores) - bull_n - bear_n

    label = "Bullish" if avg > 0.2 else "Bearish" if avg < -0.2 else "Neutral"
    dom = max(bull_n, bear_n, neut_n)
    conf = (
        "Strong" if dom >= len(dom_scores) * 0.65
        else "Moderate" if dom >= len(dom_scores) * 0.40
        else "Weak"
    )

    result = {
        "symbol": symbol,
        "score": round(avg, 3),
        "label": label,
        "confidence": conf,
        "headlines": domestic[:10],
        "intl_news": intl,
        "macro_news": macro,
        "counts": {"bullish": bull_n, "bearish": bear_n, "neutral": neut_n},
    }
    _CACHE[cache_key] = {"ts": time.time(), "data": result}
    return result
