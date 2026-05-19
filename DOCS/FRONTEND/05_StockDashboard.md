# Frontend — `pages/StockDashboard/index.jsx`

## What Is This File?

The most complex frontend file (~1600 lines). It implements the complete NSE Stock
Dashboard with 5 main tabs, each containing multiple sub-components:

| Tab | What It Shows |
|---|---|
| **Analyser** | Search any NSE stock → full analysis (price, fundamentals, technicals, valuation, entry/exit, schemes, financials, news) |
| **Screener** | Filter NSE universe by PE, dividend yield, composite score with buy/sell signals |
| **Portfolio** | Transaction history, P&L per holding, AI insights |
| **Watchlist** | Tracked stocks with target price and stop-loss |
| **Global Markets** | World indices live prices |

---

## Top-Level State

```jsx
function StockDashboard() {
  // Tab navigation
  const [activeTab, setActiveTab] = useState('Analyser');

  // Analyser state
  const [query,     setQuery]     = useState('');
  const [results,   setResults]   = useState([]);
  const [symbol,    setSymbol]    = useState('');
  const [analysis,  setAnalysis]  = useState(null);
  const [sentiment, setSentiment] = useState(null);
  const [chart,     setChart]     = useState([]);
  const [period,    setPeriod]    = useState('1y');

  // Screener state
  const [screenerData,  setScreenerData]  = useState([]);
  const [screenerFilter, setScreenerFilter] = useState({ min_yield: 0, max_pe: 50 });

  // Portfolio / watchlist
  const [portfolio,  setPortfolio]  = useState(null);
  const [watchlist,  setWatchlist]  = useState([]);

  // Loading and error flags
  const [analysisLoading,  setAnalysisLoading]  = useState(false);
  const [screenerLoading,  setScreenerLoading]  = useState(false);
```

### Why Separate Loading Flags?

Each tab has independent loading state. If you used one global `loading`:
- Screener loading would show spinner on the Analyser tab
- Portfolio loading would block the Screener

Separate flags: `analysisLoading`, `screenerLoading` — each tab manages its own state.

---

## Tab Rendering Pattern

```jsx
{activeTab === 'Analyser'  && <AnalyserTab  ... />}
{activeTab === 'Screener'  && <ScreenerTab  ... />}
{activeTab === 'Portfolio' && <PortfolioTab ... />}
{activeTab === 'Watchlist' && <WatchlistTab ... />}
{activeTab === 'Global'    && <GlobalTab    ... />}
```

**`&&` conditional rendering:**

When `activeTab !== 'Screener'`, `<ScreenerTab />` is **unmounted** (removed from DOM).
All its state is lost.

**Trade-off:**
- Pro: Components unmount → cleanup runs → no memory leaks
- Con: Switching back to a tab re-fetches data

For the Portfolio tab (expensive aggregation call), this is fine — data is re-fetched
on demand. For heavy components that should preserve state, use CSS `display: none` instead.

---

## `AnalyserTab` — Stock Search and Analysis

### Search Flow

```jsx
const handleSearch = async () => {
  if (!query.trim()) return;
  const res = await stockService.search(query);
  setResults(res.data);
};

const handleSelect = async (sym) => {
  setSymbol(sym);
  setResults([]);   // Clear dropdown
  setAnalysisLoading(true);

  // Parallel requests — all three fire at the same time
  const [anaRes, sentRes, chartRes] = await Promise.all([
    stockService.analyse(sym),
    stockService.sentiment(sym),
    stockService.chart(sym, period),
  ]);

  setAnalysis(anaRes.data);
  setSentiment(sentRes.data);
  setChart(chartRes.data);
  setAnalysisLoading(false);
};
```

**`Promise.all` for parallel loading:**

Analysis, sentiment (news), and chart data are independent — they can load concurrently.
Total time = max(analysis_time, sentiment_time, chart_time) instead of their sum.
Sentiment takes longest (Bing News + og:description enrichment ~2-5s).
Analysis is fastest (cache hit ~1ms, cache miss ~500ms).

---

## `CompositeScore` Component — Visual Score Bar

```jsx
function CompositeScore({ score }) {
  // score range: -15 to +15
  const pct = Math.round(((score + 15) / 30) * 100);   // map to 0-100%

  const color = score >= 8  ? '#237804' :   // dark green
                score >= 3  ? '#52c41a' :   // green
                score >= -3 ? '#fa8c16' :   // orange
                score >= -8 ? '#f5222d' :   // red
                              '#820014';    // dark red

  return (
    <div className="composite-score">
      <div className="score-bar-bg">
        <div className="score-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="score-label">{score > 0 ? '+' : ''}{score}</span>
    </div>
  );
}
```

**Linear mapping: score → percentage**

`score = -15` → `pct = ((-15+15)/30)*100 = 0%` (empty bar)
`score = 0`   → `pct = ((0+15)/30)*100 = 50%` (half bar)
`score = +15` → `pct = ((15+15)/30)*100 = 100%` (full bar)

The bar width visually represents where the stock falls on the Buy-Sell spectrum.

---

## `SignalDetail` Popup — 9-Dimension Signal Breakdown

```jsx
function SignalDetail({ analysis }) {
  const [show, setShow] = useState(false);

  const dims = [
    { label: 'Fundamentals',  val: analysis?.fundamental_score, max: 5 },
    { label: 'Technical',     val: analysis?.technical_score,   max: 5 },
    { label: 'Valuation',     val: analysis?.valuation_score,   max: 3 },
    { label: 'Sentiment',     val: analysis?.sentiment_score,   max: 2 },
    { label: 'Macro/RBI',     val: analysis?.macro_score,       max: 2 },
    ...
  ];

  return (
    <div className="signal-detail-wrapper">
      <button onClick={() => setShow(!show)} className="signal-detail-btn">
        {analysis?.recommendation?.signal} ▾
      </button>
      {show && (
        <div className="signal-detail-popup">
          {dims.map(d => (
            <div key={d.label} className="signal-dim-row">
              <span>{d.label}</span>
              <span style={{ color: d.val > 0 ? 'green' : d.val < 0 ? 'red' : 'gray' }}>
                {d.val > 0 ? '+' : ''}{d.val}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

Local `show` state — independent per stock card. Clicking "Buy ▾" toggles the breakdown.
The popup is rendered conditionally: `{show && <div>...</div>}` — unmounts when closed.

---

## `WatchBtn` — Add to Watchlist from Screener

```jsx
function WatchBtn({ symbol, name, watchlist, onRefresh }) {
  const [status, setStatus] = useState('idle');   // idle | success | error

  const isWatched = watchlist.some(w => w.symbol === symbol);

  const handleAdd = async () => {
    if (isWatched) return;
    try {
      await stockService.addWatchlist({ symbol, company_name: name });
      setStatus('success');
      onRefresh();   // Refresh parent watchlist state
      setTimeout(() => setStatus('idle'), 2000);   // Reset after 2s
    } catch {
      setStatus('error');
      setTimeout(() => setStatus('idle'), 2000);
    }
  };

  if (isWatched) return <span className="watch-already">✓ Watching</span>;

  return (
    <button onClick={handleAdd} className={`watch-btn watch-btn--${status}`}>
      {status === 'idle'    && '+ Watch'}
      {status === 'success' && '✓ Added'}
      {status === 'error'   && '✗ Failed'}
    </button>
  );
}
```

**Three-state button pattern:**

`idle` → `success` or `error` → `idle` (after 2 seconds)

This gives the user immediate visual feedback without a loading spinner.
The `setTimeout` auto-resets to `idle` — the user sees the confirmation briefly then
it returns to the normal state.

`watchlist.some(w => w.symbol === symbol)` — O(n) check if already in watchlist.
For the ~10-20 items in a typical watchlist, this is perfectly adequate.

---

## `FinancialsSection` — Lazy-Loading Accordion

```jsx
function FinancialsSection({ symbol }) {
  const [open,    setOpen]    = useState(false);
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [subtab,  setSubtab]  = useState('P&L Annual');

  useEffect(() => {
    if (!open || data) return;   // Only load once, only when opened
    setLoading(true);
    stockService.financials(symbol)
      .then(r => setData(r.data))
      .catch(() => setData({ error: 'Failed to load financials' }))
      .finally(() => setLoading(false));
  }, [open, symbol]);   // Re-fetch if symbol changes
```

**Lazy Loading Pattern:**

The financial statements are not fetched when the page loads — only when the user opens
the accordion (`open = true`).

`if (!open || data) return` — two guards:
1. `!open` — don't load until user expands the section
2. `data` — don't reload if already loaded (navigating away and back doesn't re-fetch)

`[open, symbol]` dependency — if the user searches a different stock, `symbol` changes
→ `data` is stale → `!open || data` check: `data` is truthy (stale data), so we
need another guard: the `data` check should be `data && data.symbol === symbol`.
Actually the component is re-mounted when `symbol` changes (different page re-render),
so `data` resets to `null` naturally.

---

## `FinTable` — Financial Table with Growth Arrows

```jsx
function FinTable({ rows, periods, unit }) {
  return (
    <div className="fin-table-wrapper">
      <table className="fin-table">
        <thead>
          <tr>
            <th className="fin-label-col">Metric</th>
            {periods.map(p => <th key={p}>{p}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.label} className="fin-row">
              <td className="fin-label">{row.label}</td>
              {row.values.map((v, i) => {
                const prev = row.values[i + 1];   // Next column = older period
                const arrow = (v !== null && prev !== null)
                  ? (v > prev ? '▲' : v < prev ? '▼' : '→')
                  : '';
                const arrowColor = arrow === '▲' ? '#237804' : arrow === '▼' ? '#cf1322' : '#595959';
                return (
                  <td key={i} className="fin-value">
                    {v !== null ? v.toLocaleString('en-IN') : '—'}
                    {arrow && <span style={{ color: arrowColor, fontSize: 10 }}> {arrow}</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="fin-unit-note">Values in {unit}</p>
    </div>
  );
}
```

**Growth arrows:**

Periods are ordered newest-first (columns: 2024, 2023, 2022...).
`row.values[i + 1]` is the older period — so comparing `values[0]` to `values[1]`
is current year vs previous year.

`▲` = current > previous (growth, green)
`▼` = current < previous (decline, red)
`→` = unchanged

`toLocaleString('en-IN')` — formats numbers in Indian number system:
`1234567` → `12,34,567` (lakhs notation, not millions).

---

## Indian Fiscal Year Computation (Half-Yearly, 9-Month)

```jsx
const getFY = d => {
  const m = new Date(d).getMonth() + 1;   // 1-12
  const y = new Date(d).getFullYear();
  return m > 3 ? y + 1 : y;
  // April (4) starts FY — FY2025 = Apr 2024 to Mar 2025
  // Jun 2024 → m=6 > 3 → FY = 2024+1 = 2025
  // Mar 2025 → m=3 ≤ 3 → FY = 2025
};

function computePeriodGroups(quarterly, periodType) {
  const { periods = [], rows = [] } = quarterly;

  // Group quarter-end months by FY
  const fyGroups = {};   // { "FY2025": [idx0, idx1, idx2, idx3], ... }
  periods.forEach((p, idx) => {
    const fy = getFY(p);
    const key = `FY${fy}`;
    if (!fyGroups[key]) fyGroups[key] = [];
    fyGroups[key].push(idx);
  });

  // H1 = quarters ending June + September (months 6, 9)
  // H2 = quarters ending December + March (months 12, 3)
  // 9M = June + September + December (months 6, 9, 12)
  const PERIOD_MONTHS = {
    'H1': [6, 9],
    'H2': [12, 3],
    '9M': [6, 9, 12],
  };

  const targetMonths = PERIOD_MONTHS[periodType] || [];

  // Sum selected quarters
  const groupedPeriods = [];
  const groupedRows    = rows.map(r => ({ ...r, values: [] }));

  Object.entries(fyGroups)
    .sort(([a], [b]) => parseInt(b.slice(2)) - parseInt(a.slice(2)))  // Newest FY first
    .forEach(([fyKey, indices]) => {
      const selectedIdx = indices.filter(idx => {
        const month = new Date(periods[idx]).getMonth() + 1;
        return targetMonths.includes(month);
      });
      if (selectedIdx.length === 0) return;

      groupedPeriods.push(fyKey + ' ' + periodType);
      groupedRows.forEach((gr, ri) => {
        const sum = selectedIdx.reduce((acc, idx) => {
          const val = rows[ri].values[idx];
          return acc + (val !== null ? val : 0);
        }, 0);
        gr.values.push(selectedIdx.every(idx => rows[ri].values[idx] === null)
          ? null : round(sum, 2));
      });
    });

  return { periods: groupedPeriods, rows: groupedRows };
}
```

**Why this computation?**

yfinance provides quarterly data (Mar, Jun, Sep, Dec period-end dates).
H1/H2/9M are NOT directly available — they must be derived by summing quarters.

Indian FY: April to March.
- H1 FY2025 = Q1 (Apr-Jun 2024) + Q2 (Jul-Sep 2024) → period-end dates: Jun 2024 + Sep 2024
- H2 FY2025 = Q3 (Oct-Dec 2024) + Q4 (Jan-Mar 2025) → December + March

The computation groups quarters by fiscal year, selects the relevant quarter-end months,
and sums the values. EPS values should not be summed — in real financial reporting,
H1 EPS is not H1Q1 + H1Q2 (it's recomputed from net income / weighted shares).
This is a known simplification in this implementation.

---

## `NewsSection` — Display News with Source and Summary

```jsx
function NewsSection({ sentiment, symbol }) {
  const allItems = [
    ...domestic.slice(0, 7).map(n => ({ ...n, scope: 'domestic' })),
    ...intl.slice(0, 4).map(n => ({ ...n, scope: 'international' })),
    ...macro.slice(0, 3).map(n => ({ ...n, scope: 'macro' })),
  ];

  return (
    <div className="stock-news-card">
      {allItems.map((item, i) => {
        const pubDate = item.published
          ? new Date(item.published).toLocaleDateString('en-IN', {
              day: 'numeric', month: 'short', year: 'numeric'
            })
          : null;

        return (
          <div key={i} className="news-item-card">
            <div className="news-item-tags">
              <span className="news-scope-tag">{sc.label}</span>
              <span className="news-impact-badge">{im.label}</span>
              {item.source && <span className="news-source-tag">{item.source}</span>}
            </div>
            <a href={item.link} target="_blank" rel="noopener noreferrer">
              {item.title}
            </a>
            {item.summary
              ? <p className="news-summary">{item.summary}</p>
              : <p className="news-summary news-summary--na">
                  Summary not available — click the headline to read the full article.
                </p>
            }
            <div className="news-meta-row">
              {pubDate && <span>📅 {pubDate}</span>}
              {item.link && (
                <a href={item.link} target="_blank" rel="noopener noreferrer">
                  Read full article →
                </a>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

**`rel="noopener noreferrer"`** — Security attribute for external links:
- `noopener` — prevents the new tab from accessing `window.opener` (prevents tab-napping attacks)
- `noreferrer` — doesn't send `Referer` header to the linked site (privacy)
Always use both on `target="_blank"` links.

**Scope spread with map:**
```javascript
...domestic.slice(0, 7).map(n => ({ ...n, scope: 'domestic' }))
```

`...n` spreads existing article fields. Adding `scope: 'domestic'` ensures every item
has a `scope` field for the tag display, even if the backend sent items without it.

---

## `RefreshPanel` — Data Cache TTL Display

```jsx
function RefreshPanel() {
  const [open, setOpen] = useState(false);
  const CACHE_TTLS = [
    { label: 'Stock Analysis (full)',  freq: '15 min',  note: 'Price, fundamentals, technicals, recommendation' },
    { label: 'Chart Data',             freq: '30 min',  note: 'OHLCV historical candles' },
    { label: 'Stock Screener',         freq: '20 min',  note: 'Filtered NSE universe results' },
    { label: 'Detailed Financials',    freq: '60 min',  note: 'Balance sheet, P&L, cash flows' },
    { label: 'News & Sentiment',       freq: '10 min',  note: 'Bing News RSS + sentiment score' },
    { label: 'Article Summaries',      freq: '24 hr',   note: 'og:description from article pages' },
    { label: 'Global Markets',         freq: '5 min',   note: 'World index prices' },
    { label: 'Basic Quote',            freq: '5 min',   note: 'Fast price + change %' },
  ];
```

Displays the backend cache TTLs to users — helps them understand why data might be
slightly stale and when it will refresh automatically.

---

## Interview Questions

**Q: What is the difference between controlled and uncontrolled components?**

**Controlled:** React state is the source of truth for the input value.
```jsx
const [val, setVal] = useState('');
<input value={val} onChange={e => setVal(e.target.value)} />
```

**Uncontrolled:** DOM is the source of truth. React reads it via a ref when needed.
```jsx
const ref = useRef();
<input ref={ref} defaultValue="" />
// ref.current.value to read
```

This project uses controlled components throughout — React state always matches
what's displayed, making it predictable and easier to test.

**Q: How does `Promise.all` make the Analyser faster?**

Without `Promise.all`:
```
1. Fetch analysis (500ms)
2. Wait...
3. Fetch sentiment (2000ms)
4. Wait...
5. Fetch chart (300ms)
Total: 2800ms
```

With `Promise.all`:
```
1. Fetch analysis  ─┐
2. Fetch sentiment  ├─ all fire simultaneously
3. Fetch chart     ─┘
Wait for slowest: 2000ms (sentiment)
Total: 2000ms (30% faster)
```

**Q: When would you use `useMemo` in this component?**

For expensive derived calculations that shouldn't recompute on every render:
```jsx
const { periods: h1Periods, rows: h1Rows } = useMemo(
  () => computePeriodGroups(quarterly, 'H1'),
  [quarterly]   // Only recompute when quarterly data changes
);
```

Without `useMemo`, `computePeriodGroups` (which sorts, filters, and sums across quarters)
runs on every render — including rerenders caused by hover events, unrelated state changes, etc.
