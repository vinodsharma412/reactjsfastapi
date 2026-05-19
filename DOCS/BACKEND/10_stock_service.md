# `backend/app/services/stock_service.py` — Stock Analysis Engine

## What Is This File?

The largest and most complex file in the project (~1400 lines). It is the core **business logic**
layer for everything stock-related:

- Fetching live data from Yahoo Finance (yfinance)
- Computing 15+ technical indicators (RSI, MACD, Bollinger Bands, etc.)
- Valuation analysis (DCF, P/E, P/B comparisons)
- Entry/exit zone calculation
- Composite buy/sell/hold scoring
- Portfolio P&L calculation
- Stock screener
- Global markets data
- Detailed financial statements (balance sheet, P&L, cash flow)

---

## Key Design Patterns

### 1. Rate-Limit-Aware Fetcher with Retry + Backoff

```python
def _yf_info(symbol: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            ticker = _ticker(symbol)
            info   = ticker.info or {}
            if info and len(info) > 3:
                return info
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:
            msg = str(exc)
            is_retriable = any(k in msg for k in ("429", "Too Many Requests", "Expecting value"))
            if is_retriable and attempt < retries - 1:
                delay = 3.0 * (2 ** attempt)   # 3s → 6s → 12s
                logger.warning("Rate-limited for %s — sleeping %.0fs", symbol, delay)
                time.sleep(delay)
                continue
            logger.warning("yf_info failed for %s: %s", symbol, exc)
            return {}
    return {}
```

**Why Exponential Backoff?**

Yahoo Finance rate-limits at 429 Too Many Requests. If you retry immediately,
you hit the rate limit again. Exponential backoff gives the server time to recover:

```
Attempt 1: instant
Attempt 2: wait 3 seconds
Attempt 3: wait 6 seconds  (2^1 × 3)
(would be 12s for attempt 4)
```

**`"Expecting value"` — What Is This?**

When Yahoo Finance rate-limits, it sometimes returns an empty HTTP body. `json.loads("")`
raises `json.JSONDecodeError: Expecting value at line 1 col 1`. yfinance propagates this
as an exception, which we catch and treat as a retriable error.

**`len(info) > 3`** — Yahoo Finance occasionally returns partial dicts like
`{"trailingPegRatio": None}` (1 key) instead of a full info dict (200+ keys).
The `> 3` check filters these out and retries.

---

### 2. Browser Impersonation (`curl_cffi`)

```python
try:
    from curl_cffi import requests as cffi_requests
    _SESSION = cffi_requests.Session(impersonate="chrome110")
except ImportError:
    _SESSION = None   # fallback to standard requests

def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol, session=_SESSION) if _SESSION else yf.Ticker(symbol)
```

**Why `curl_cffi`?**

Yahoo Finance blocks Python's standard `requests` library. The blocking happens at the
**TLS fingerprinting** level — Yahoo checks the TLS Client Hello message. Python's
`ssl` library produces a distinctive fingerprint that Yahoo recognises and blocks.

`curl_cffi` uses Chrome's TLS stack (via libcurl compiled with BoringSSL), producing
the same TLS fingerprint as a real Chrome browser. Yahoo cannot distinguish it from
a real user.

`impersonate="chrome110"` — mimics Chrome 110's exact TLS settings.

`_SESSION` is shared across all ticker requests — **connection pooling**. Creating a
new TLS connection for every request takes ~200ms. Reusing the session takes ~20ms.

---

### 3. In-Memory TTL Cache

```python
_CACHE: dict = {}
_CACHE_TTL_ANALYSIS  = 900    # 15 minutes
_CACHE_TTL_CHART     = 1800   # 30 minutes
_CACHE_TTL_SCREENER  = 1200   # 20 minutes
_CACHE_TTL_FINANCIALS = 3600  # 60 minutes

def _cached(key: str, fn, ttl: int = _CACHE_TTL_ANALYSIS):
    entry = _CACHE.get(key)
    if entry and time.time() - entry['ts'] < ttl:
        return entry['data']   # Cache hit — return immediately
    data = fn()                # Cache miss — call the actual function
    _CACHE[key] = {'ts': time.time(), 'data': data}
    return data
```

**Usage:**
```python
def get_stock_analysis(symbol: str, sentiment_score: float = 0.0) -> dict:
    def _fetch():
        info = _yf_info(symbol)      # ~500ms Yahoo Finance call
        hist = _yf_history(symbol, "1y")
        ...
    return _cached(f"analysis:{symbol}", _fetch, _CACHE_TTL_ANALYSIS)
```

Without caching, 10 users viewing TCS.NS would trigger 10 × 500ms Yahoo Finance calls.
With caching, only the first call hits Yahoo Finance; the next 9 return in <1ms.

**Cache key convention:**
- `"analysis:TCS.NS"` — stock analysis
- `"chart:TCS.NS:1y"` — chart data for 1-year period
- `"screener:0.03:50.0"` — screener with specific parameters

**Limitation:** This is an in-process Python dict. If you run 2 uvicorn workers
(processes), each has its own cache. Solution for production: Redis.

---

### 4. Technical Analysis Calculations

```python
def _calculate_technicals(hist: pd.DataFrame) -> dict:
    close  = hist['Close']
    volume = hist['Volume']
    high   = hist['High']
    low    = hist['Low']
```

**RSI (Relative Strength Index):**
```python
delta   = close.diff()
gain    = delta.clip(lower=0)
loss    = (-delta).clip(lower=0)
avg_gain = gain.ewm(com=13, adjust=False).mean()   # 14-period EWM
avg_loss = loss.ewm(com=13, adjust=False).mean()
rs  = avg_gain / avg_loss
rsi = 100 - (100 / (1 + rs))
```

RSI measures momentum: 0-30 = oversold (potential buy), 70-100 = overbought (potential sell).
`ewm(com=13)` = exponential weighted mean with centre-of-mass 13 (equivalent to 14-period EMA).

**MACD (Moving Average Convergence Divergence):**
```python
ema12  = close.ewm(span=12, adjust=False).mean()
ema26  = close.ewm(span=26, adjust=False).mean()
macd   = ema12 - ema26      # MACD line
signal = macd.ewm(span=9, adjust=False).mean()   # Signal line
histogram = macd - signal   # Positive = bullish momentum
```

MACD crossover: when MACD crosses above signal → buy signal. Below → sell signal.

**Bollinger Bands:**
```python
sma20  = close.rolling(20).mean()
std20  = close.rolling(20).std()
bb_upper = sma20 + 2 * std20
bb_lower = sma20 - 2 * std20
```

Price outside upper band = overbought. Below lower band = oversold.
`bb_width = (upper - lower) / sma20` measures market volatility.

**Ichimoku Cloud:**
```python
high9  = high.rolling(9).max()
low9   = low.rolling(9).min()
tenkan = (high9 + low9) / 2           # Conversion line (9-period)

high26 = high.rolling(26).max()
low26  = low.rolling(26).min()
kijun  = (high26 + low26) / 2         # Base line (26-period)

span_a = ((tenkan + kijun) / 2).shift(26)   # Leading Span A
span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
# Cloud: area between span_a and span_b
# Price above cloud = bullish, below = bearish
```

---

### 5. Composite Scoring System

```python
def _generate_recommendation(info: dict, technicals: dict, sentiment_score: float) -> dict:
    score   = 0
    reasons = []

    # ── Fundamental signals ───────────────────────────────────
    pe = info.get('trailingPE')
    if pe and pe < 15:
        score += 2; reasons.append("Low P/E (deep value)")
    elif pe and pe < 25:
        score += 1; reasons.append("Reasonable P/E")
    elif pe and pe > 40:
        score -= 2; reasons.append("High P/E (expensive)")

    roe = info.get('returnOnEquity')
    if roe and roe > 0.20:
        score += 2; reasons.append("Strong ROE > 20%")

    de = info.get('debtToEquity')
    if de is not None:
        if de < 30:
            score += 1; reasons.append("Low debt")
        elif de > 150:
            score -= 2; reasons.append("High debt risk")

    # ── Technical signals ─────────────────────────────────────
    rsi = technicals.get('rsi')
    if rsi:
        if rsi < 35:
            score += 2; reasons.append("RSI oversold — potential reversal")
        elif rsi > 70:
            score -= 2; reasons.append("RSI overbought")

    macd = technicals.get('macd')
    sig  = technicals.get('macd_signal')
    if macd and sig:
        if macd > sig:
            score += 1; reasons.append("MACD bullish crossover")
        else:
            score -= 1; reasons.append("MACD bearish crossover")

    # ── Sentiment signal ──────────────────────────────────────
    sentiment_component = round(sentiment_score * 2)  # -2 to +2
    score += sentiment_component

    # ── Final label ───────────────────────────────────────────
    if score >= 10:
        signal, color = "Strong Buy", "darkgreen"
    elif score >= 5:
        signal, color = "Buy", "green"
    elif score >= 0:
        signal, color = "Hold", "orange"
    elif score >= -4:
        signal, color = "Sell", "red"
    else:
        signal, color = "Strong Sell", "darkred"

    return {"signal": signal, "score": score, "color": color, "reasons": reasons}
```

**Score range:** approximately -15 to +15.
Each dimension contributes ±1 or ±2 points.
Sentiment adds ±2 (scaled from -1.0 to +1.0).

**Why this approach vs ML model?**

- No training data needed — works immediately
- Interpretable — `reasons` list explains exactly why
- Adjustable — easy to add new signals
- Fast — no model inference overhead

---

### 6. Portfolio P&L Calculation

```python
def calculate_portfolio(transactions: list) -> dict:
    holdings = {}   # symbol → {quantity, invested, avg_price}

    for txn in transactions:
        sym = txn.symbol
        if sym not in holdings:
            holdings[sym] = {"quantity": 0, "invested": 0.0, "avg_price": 0.0}

        h = holdings[sym]
        if txn.transaction_type == "buy":
            new_qty      = h["quantity"] + txn.quantity
            new_invested = h["invested"] + txn.quantity * txn.price
            h["avg_price"] = new_invested / new_qty if new_qty else 0
            h["quantity"]  = new_qty
            h["invested"]  = new_invested

        elif txn.transaction_type == "sell":
            h["quantity"] = max(0, h["quantity"] - txn.quantity)
            h["invested"] = h["avg_price"] * h["quantity"]  # recalc based on remaining

    # Fetch current prices for all held symbols
    for sym, h in holdings.items():
        if h["quantity"] > 0:
            quote = get_basic_quote(sym)
            h["current_price"] = quote.get("price", h["avg_price"])
            h["current_value"] = h["current_price"] * h["quantity"]
            h["pnl"]           = h["current_value"] - h["invested"]
            h["pnl_pct"]       = (h["pnl"] / h["invested"] * 100) if h["invested"] else 0
```

**Average Cost Method:**

When you buy 10 shares at 100 and 10 more at 120:
```
avg_price = (10×100 + 10×120) / 20 = 110
invested = 20 × 110 = 2200
```

When you sell 5 shares:
```
remaining_qty = 15
remaining_invested = 15 × 110 = 1650  (avg_price unchanged)
```

This is the **FIFO average cost** method — standard for retail investors.

---

### 7. NSE Universe Dictionary

```python
NSE_UNIVERSE = {
    "TCS.NS":       "Tata Consultancy Services",
    "INFY.NS":      "Infosys",
    "HDFCBANK.NS":  "HDFC Bank",
    # ... 100+ stocks
}
```

This serves several purposes:
1. **Screener** — iterates over all symbols to compute scores
2. **Search** — matches company names to user queries
3. **Auto-fill** — when adding a transaction, fills company name automatically
4. **Sentiment** — provides company name for news search queries

---

### 8. `get_detailed_financials()` — Financial Statements

```python
_PER_SHARE_ROWS = {'Basic EPS', 'Diluted EPS'}
_COUNT_ROWS     = {'Ordinary Shares Number'}

def _extract_fin_rows(df: pd.DataFrame, keys: dict, divisor: float) -> tuple:
    if df is None or df.empty:
        return [], []
    periods = [str(c)[:10] for c in df.columns]
    rows = []
    for raw_key, label in keys.items():
        if raw_key not in df.index:
            continue
        # EPS is already per-share (₹), do NOT divide by 1e7
        div = 1.0 if (raw_key in _PER_SHARE_ROWS or raw_key in _COUNT_ROWS) else divisor
        vals = [None if pd.isna(float(v)) else round(float(v)/div, 2)
                for v in df.loc[raw_key]]
        rows.append({"label": label, "values": vals})
    return rows, periods
```

**Unit Conversion:** yfinance returns raw INR values (e.g., TCS revenue = 2,670,210,000,000).
Dividing by `1e7` (10 million) converts to Crores (2,67,021 Crores).

**Why `_PER_SHARE_ROWS` exception?**

EPS (Earnings Per Share) is already in rupees per share (e.g., 134.19 ₹/share).
It's not a total amount — dividing by 1e7 would give 0.0000134 which is meaningless.
The set check prevents this incorrect conversion.

---

## Interview Questions

**Q: What is Exponential Backoff and why is it used?**

Exponential backoff is a retry strategy where the wait time doubles after each failure:
1st retry = 3s, 2nd = 6s, 3rd = 12s. It prevents the "thundering herd" problem — if 100
clients all retry simultaneously after a rate limit, they cause another rate limit.
Spreading retries over time lets the server recover.

**Q: What is RSI and what does a value of 30 mean?**

RSI (Relative Strength Index) is a momentum oscillator measuring the speed and change
of price movements, ranging 0-100. Below 30 = oversold (selling pressure exceeded,
reversal likely). Above 70 = overbought (buying pressure exceeded, correction likely).
Between 30-70 = neutral momentum.

**Q: How does the composite scoring system handle conflicting signals?**

Signals are additive — bullish signals add points, bearish subtract. A stock with strong
fundamentals (+4) but overbought technicals (-2) scores +2 (Hold). The system doesn't
veto on any single signal — it aggregates all signals into one number. The `reasons` list
shows which signals fired, giving transparency.

**Q: What is the difference between `pandas.rolling()` and `pandas.ewm()`?**

`rolling(20)` = simple moving average — all 20 periods weighted equally.
`ewm(span=20)` = exponential weighted — recent periods weighted more heavily.
EWM reacts faster to recent price changes. SMA is smoother and less reactive.
Technical analysis uses EWM for MACD (fast reaction) and SMA for support/resistance.
