# `backend/app/services/sentiment_service.py` — News Intelligence & Sentiment

## What Is This File?

Fetches financial news from Bing News RSS, extracts real article summaries,
scores each article as bullish/bearish/neutral using keyword analysis, and
returns a composite sentiment score that feeds into the stock recommendation engine.

---

## Architecture Overview

```
analyze_sentiment("TCS.NS", "Tata Consultancy Services")
    │
    ├── _fetch_domestic_news("Tata Consultancy Services", "TCS")
    │       ├── _fetch_bing_rss("TCS Tata Consultancy Services NSE stock India")
    │       │       └── Bing News RSS → XML → parse items → extract source/summary/link
    │       └── _enrich_summaries(items, max_fetch=5)    ← parallel HTTP
    │               └── _fetch_og_desc(article_url)       ← for truncated summaries
    │
    ├── _fetch_international_news("Tata Consultancy Services", "IT")
    │       └── _fetch_bing_rss("TCS global stock market")
    │
    └── _fetch_macro_news()
            └── _fetch_bing_rss("RBI monetary policy India interest rate")
```

---

## Sentiment Keywords

```python
_BULLISH = {
    "profit", "growth", "record", "surge", "rally", "strong", "buy",
    "upgrade", "target", "upside", "positive", "earnings beat", "dividend",
    "expansion", "invest", "gain", "robust", "outperform", "deal", "win",
    "breakthrough", "acquisition", "partnership", "order", "contract",
    "recovery", "rebound", "high", "rise", "increase", "improved",
    "bullish", "opportunity", "recommend", "overweight", "beat", "boost",
    ...
}

_BEARISH = {
    "loss", "decline", "fall", "concern", "sell", "weak", "cut",
    "downgrade", "risk", "fraud", "penalty", "fine", "lawsuit", "debt",
    "default", "miss", "disappoint", "layoff", "probe", "investigation",
    ...
}

_STRONG_BULLISH = {"record high", "all-time high", "beats estimate", "strong buy", "outperform"}
_STRONG_BEARISH = {"fraud", "ban", "default", "bankruptcy", "crash", "investigation", "probe"}
```

### How Keyword Scoring Works

```python
def _score_headline(text: str) -> float:
    low  = text.lower()
    bull = sum(1 for w in _BULLISH        if w in low)   # count bullish hits
    bear = sum(1 for w in _BEARISH        if w in low)   # count bearish hits
    bull += sum(2 for w in _STRONG_BULLISH if w in low)  # strong = double weight
    bear += sum(2 for w in _STRONG_BEARISH if w in low)
    total = bull + bear
    return 0.0 if total == 0 else max(-1.0, min(1.0, (bull - bear) / total))
```

**Example:**
```
Title: "TCS Q3 earnings beat estimates, strong profit growth"
Bullish hits: "beat" (+1), "earnings beat" (+2), "strong" (+1), "profit" (+1), "growth" (+1) = 6
Bearish hits: 0
Score = (6 - 0) / (6 + 0) = 1.0  → "Bullish"

Title: "Fraud investigation probe launched against fund manager"
Bullish hits: 0
Bearish hits: "fraud" (+2), "investigation" (+2), "probe" (+2) = 6
Score = (0 - 6) / (0 + 6) = -1.0  → "Bearish"
```

---

## Bing News RSS Integration

### Why Bing Instead of Google News?

| | Google News RSS | Bing News RSS |
|---|---|---|
| Article URL | Encoded redirect (JS-only) | Direct article URL |
| Description | Just the title re-linked | Real 1-2 sentence extract |
| Source tag | `<source>` element | `<News:Source>` namespaced |
| Scraping | Cannot follow links server-side | Full direct URLs work |

Google News encodes article URLs as base64 protobuf IDs. These IDs resolve via JavaScript
redirects that return HTTP 400 to server-side HTTP clients. Bing News provides direct URLs.

### The Namespace Bug (Real-World Problem Solved)

```python
# Bing RSS XML header:
# xmlns:News="https://www.bing.com/news/search?q=TCS+Tata+...&format=RSS"
#
# The namespace URI CHANGES with every query!
# <News:Source>The Economic Times</News:Source>
# becomes after ElementTree parsing:
# tag = "{https://www.bing.com/news/search?q=TCS...&format=RSS}Source"

# WRONG — static namespace URI
item.find('{https://www.bing.com/news/search}Source')  # → None

# WRONG — wildcard doesn't work here due to &amp; vs & issue
item.find('{*}Source')  # → None (namespace URI mismatch)

# CORRECT — extract URI from XML, unescape HTML entities, then use it
ns_m = re.search(r'xmlns:News="([^"]+)"', raw_xml)
news_ns = unescape(ns_m.group(1))   # &amp; → &
src_el = item.find(f'{{{news_ns}}}Source')   # → "The Economic Times"
```

**Why does `unescape()` matter here?**

The raw XML has `&amp;format=RSS` (XML-encoded `&`). After ElementTree parsing,
the namespace URI has `&format=RSS` (decoded `&`). We extract from the raw XML string,
so we get `&amp;` — but ElementTree stored `&`. We must unescape to match.

---

## Article URL Extraction from Bing Tracking Links

```python
def _bing_url_to_real(bing_link: str) -> str:
    """Extract actual article URL from Bing tracking URL."""
    try:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(bing_link).query)
        return params.get('url', [''])[0] or bing_link
    except Exception:
        return bing_link
```

Bing wraps article URLs in tracking links:
```
http://www.bing.com/news/apiclick.aspx?ref=FexRss&url=https%3a%2f%2feconomictimes.indiatimes.com%2f...
```

`urllib.parse.parse_qs(query)` extracts all query parameters as a dict:
```python
{"ref": ["FexRss"], "url": ["https://economictimes.indiatimes.com/..."]}
```

`.get('url', [''])[0]` → `"https://economictimes.indiatimes.com/..."`

If parsing fails (malformed URL), returns the original Bing link as fallback.

---

## Summary Enrichment — Parallel og:description Fetching

```python
def _is_truncated(s: str) -> bool:
    t = s.rstrip() if s else ''
    return not t or t.endswith('…') or t.endswith('...') or len(t) < 60


def _enrich_summaries(items: List[dict], max_fetch: int = 5) -> None:
    """For items with truncated summaries, fetch og:description in parallel."""
    need = [it for it in items if it.get('link') and _is_truncated(it.get('summary', ''))]
    if not need:
        return
    targets = need[:max_fetch]

    with ThreadPoolExecutor(max_workers=4) as pool:
        fmap = {pool.submit(_fetch_og_desc, it['link']): it for it in targets}
        for fut in as_completed(fmap, timeout=6):
            it = fmap[fut]
            try:
                desc = fut.result() or ''
                if desc and not _is_dupe_of_title(desc, it['title']):
                    it['summary']   = _to_two_sentences(desc)
                    s               = round(_score_headline(it['title'] + ' ' + it['summary']), 3)
                    it['score']     = s
                    it['sentiment'] = 'bullish' if s > 0.1 else 'bearish' if s < -0.1 else 'neutral'
                    it['impact']    = 'positive' if s > 0.2 else 'negative' if s < -0.2 else 'neutral'
            except Exception:
                pass
```

### ThreadPoolExecutor Pattern

```python
with ThreadPoolExecutor(max_workers=4) as pool:
    fmap = {pool.submit(_fetch_og_desc, it['link']): it for it in targets}
```

`pool.submit(fn, arg)` — starts `fn(arg)` in a thread immediately, returns a `Future`.
`fmap` is a dict: `{Future: article_item}` — maps results back to their article.

```python
for fut in as_completed(fmap, timeout=6):
```

`as_completed()` yields futures **as they finish** (fastest article first, not submission order).
`timeout=6` — if all futures don't complete within 6 seconds, `TimeoutError` is raised
and remaining ones are cancelled. Prevents slow article pages from blocking the response.

**Why threads, not asyncio?**

`_fetch_og_desc` uses `httpx.get()` — synchronous blocking I/O. In asyncio, blocking calls
freeze the event loop. Threads run in parallel without needing `async/await`.
For async HTTP, you'd use `httpx.AsyncClient` with `await` — more complex refactor.

### og:description Extraction

```python
def _fetch_og_desc(url: str) -> str:
    if not url or 'google.com' in url or 'bing.com' in url:
        return ''   # Skip non-article URLs
    entry = _ART_CACHE.get(url)
    if entry and time.time() - entry['ts'] < _ART_TTL:
        return entry['val']   # 24-hour cache
    val = ''
    try:
        resp = httpx.get(url, timeout=4.0, follow_redirects=True, headers=_BROWSER_HEADERS)
        if resp.status_code == 200:
            head = resp.text[:20000]   # Only read first 20KB (meta tags are in <head>)
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
    except Exception:
        pass
    _ART_CACHE[url] = {'ts': time.time(), 'val': val}
    return val
```

**Why 4 regex patterns?**

HTML attributes can appear in either order:
```html
<!-- Order 1: property before content -->
<meta property="og:description" content="Article summary...">

<!-- Order 2: content before property -->
<meta content="Article summary..." property="og:description">
```

Patterns 1 and 2 handle `og:description`. Patterns 3 and 4 handle `name="description"`
as a fallback (many sites use standard meta description, not Open Graph).

**`resp.text[:20000]`** — only read the first 20KB. Meta tags are in `<head>`, which
always appears before `<body>`. Reading the full HTML page (can be 500KB+) wastes time.

---

## Two-Sentence Cap

```python
def _to_two_sentences(text: str) -> str:
    """Return at most two sentences, capped at 280 chars."""
    text = text.strip()
    parts = re.split(r'(?<=[.!?])\s+', text)   # split on sentence boundary
    result = ' '.join(parts[:2])
    if len(result) > 280:
        result = result[:277].rsplit(' ', 1)[0] + '…'
    return result
```

`(?<=[.!?])` is a **lookbehind assertion** — matches a space that follows `.`, `!`, or `?`.
This splits on sentence boundaries without consuming the punctuation.

`rsplit(' ', 1)[0]` — splits from the right at the first space, taking the left part.
Prevents cutting a word in the middle: `"Hello wor…"` → instead: `"Hello…"`.

---

## 24-Hour Article Cache

```python
_ART_CACHE: dict = {}
_ART_TTL = 86400   # 24 hours in seconds

_ART_CACHE[url] = {'ts': time.time(), 'val': val}
```

Article content doesn't change. Caching og:descriptions for 24 hours means:
- First request for an article: 4s HTTP fetch
- Subsequent requests: instant dict lookup

This is critical because multiple stocks in the same sector share news articles.

---

## Final Sentiment Aggregation

```python
dom_scores = [h['score'] for h in domestic]  # e.g., [0.8, 0.5, -0.2, 0.6, 0.3]
avg    = sum(dom_scores) / len(dom_scores)    # 0.4
bull_n = sum(1 for s in dom_scores if s > 0.1)   # 4
bear_n = sum(1 for s in dom_scores if s < -0.1)   # 1
neut_n = len(dom_scores) - bull_n - bear_n         # 0

label = "Bullish" if avg > 0.2 else "Bearish" if avg < -0.2 else "Neutral"
conf  = ("Strong"   if dom >= len(dom_scores) * 0.65 else
         "Moderate" if dom >= len(dom_scores) * 0.40 else "Weak")
```

**`confidence` calculation:**
- `dom` = the largest of (bull_n, bear_n, neut_n) — dominant sentiment count
- If 65%+ articles agree → "Strong"
- If 40%+ agree → "Moderate"
- Otherwise → "Weak"

Example: 8 articles, 6 bullish, 1 bearish, 1 neutral:
- dom = 6 (bullish)
- 6/8 = 0.75 > 0.65 → "Strong Bullish"

---

## Interview Questions

**Q: Why use keyword scoring instead of ML sentiment analysis?**

Keyword scoring: instant, no training data, no model files, interpretable, zero latency.
ML (e.g., FinBERT): better accuracy on complex sentences, handles negation, requires GPU or
large model files. For this use case, keyword scoring is sufficient — financial headlines
use predictable vocabulary. ML would be valuable for full article text analysis.

**Q: What is `as_completed()` vs waiting for all futures?**

`as_completed(fmap, timeout=6)` yields futures as they finish — you process each result
immediately. `concurrent.futures.wait(fmap)` waits for ALL to finish before processing any.
`as_completed` is faster in practice: if 3 out of 5 articles respond in 1 second and 2 take
5 seconds, you can process the 3 fast results immediately while the others are still in flight.

**Q: What is a lookbehind assertion in regex?**

`(?<=[.!?])` matches a position (zero-width) that is immediately preceded by `.`, `!`, or `?`.
The punctuation is not consumed. Contrast with `[.!?]\s+` which would consume the punctuation,
requiring it to be added back. Lookbehind enables splitting without removing delimiters.
