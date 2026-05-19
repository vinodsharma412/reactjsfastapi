# Frontend — `services/api.js` + All Service Files

## Architecture — Service Layer Pattern

```
React Component
    │
    ▼
Service Function (e.g., stockService.analyse("TCS.NS"))
    │
    ▼
Axios Instance (api.js) — adds JWT header, handles 401
    │
    ▼
FastAPI Backend /api/v1/stocks/analyse/TCS.NS
```

Components never call `fetch()` or `axios` directly. They call service functions.
Service functions call the configured axios instance. This separation means:
- Change base URL → change one place (`constants.js`)
- Change auth header → change one place (`api.js`)
- Change endpoint path → change one service file

---

## `services/api.js` — Axios Instance with Interceptors

```javascript
import axios from 'axios';
import { API_URL, TOKEN_KEY } from '../utils/constants';

const api = axios.create({ baseURL: API_URL });
```

`axios.create({ baseURL })` creates an isolated axios instance. All requests made
via this `api` object automatically prepend the `baseURL`.

```javascript
api.get('/stocks/search', { params: { q: 'tcs' } })
// → GET http://localhost:9000/api/v1/stocks/search?q=tcs
```

---

### Request Interceptor — Attach JWT

```javascript
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
```

This interceptor runs **before every request** made via the `api` instance.

**Flow:**
```
api.get('/users/me')
    │
    ▼
interceptor runs
    ├── read token from localStorage: "eyJhbGci..."
    ├── add header: Authorization: "Bearer eyJhbGci..."
    └── return modified config
    │
    ▼
actual HTTP request with Authorization header
```

**Why `localStorage`?**

`localStorage` persists across browser tabs and page refreshes (unlike `sessionStorage`).
The token is valid for 24 hours — you want it to survive refreshing the page.

**Security note:** `localStorage` is accessible by JavaScript — vulnerable to XSS attacks.
Alternative: `httpOnly` cookies (JS can't read them). This project uses `localStorage`
for simplicity (no backend cookie configuration needed).

---

### Response Interceptor — Handle 401 Globally

```javascript
api.interceptors.response.use(
  (res) => res,   // success passthrough

  (err) => {
    const isLoginRequest = err.config?.url?.includes('/auth/token');
    if (err.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);
```

**Without this interceptor:**

Every component that makes API calls would need to handle 401:
```javascript
// In StockDashboard, Users page, Portfolio page, Watchlist page...
try {
  const res = await stockService.analyse('TCS.NS');
} catch(err) {
  if (err.response?.status === 401) {
    localStorage.removeItem('access_token');
    navigate('/login');
  }
}
```

Repeated code across every component. One interceptor handles all 401s globally.

**`isLoginRequest` guard:**

Without this guard, a wrong password at login (401 response) would immediately
redirect to `/login` — the user is ALREADY on `/login`. This creates a redirect loop
or confusing UX. The guard skips the redirect for the login endpoint itself.

**`err.config?.url`** — optional chaining:
- `err.config` might be `undefined` for network errors (no response at all)
- `?.url` safely returns `undefined` instead of throwing `TypeError`
- `?.includes('/auth/token')` → `undefined?.includes(...)` → `undefined` (falsy) → guard is false → 401 handling proceeds normally

**`window.location.href = '/login'` vs `navigate('/login')`:**

Interceptors are created outside React's component tree — `useNavigate()` is not available.
`window.location.href` is a hard redirect: the browser loads `/login` as a new page,
clearing all component state. This is actually desirable — you don't want stale state
from a logged-out session.

**`return Promise.reject(err)`:**

After handling the 401 (or for non-401 errors), we re-reject the promise.
This lets the calling component's `catch` block still run if it has error-specific handling.
If we returned `Promise.resolve()`, the component would think the request succeeded.

---

## All Service Files

### `services/authService.js`

```javascript
export const authService = {
  login:           async (u, p) => { /* URLSearchParams POST, store token */ },
  logout:          ()           => localStorage.removeItem(TOKEN_KEY),
  getMe:           ()           => api.get('/users/me'),
  isAuthenticated: ()           => !!localStorage.getItem(TOKEN_KEY),
};
```

(See `02_AuthContext.md` for detailed explanation)

---

### `services/stockService.js`

```javascript
export const stockService = {
  search:             (q)              => api.get('/stocks/search', { params: { q } }),
  basicQuote:         (symbol)         => api.get(`/stocks/basic/${symbol}`),
  analyse:            (symbol)         => api.get(`/stocks/analyse/${symbol}`),
  chart:              (symbol, period) => api.get(`/stocks/chart/${symbol}`, { params: { period } }),
  sentiment:          (symbol)         => api.get(`/stocks/sentiment/${symbol}`),
  financials:         (symbol)         => api.get(`/stocks/financials/${symbol}`),
  screener:           (params)         => api.get('/stocks/screener', { params }),
  globalMarkets:      ()               => api.get('/stocks/market/global'),
  getPortfolio:       ()               => api.get('/stocks/portfolio'),
  portfolioInsights:  ()               => api.get('/stocks/portfolio/insights'),
  addTransaction:     (data)           => api.post('/stocks/portfolio/transactions', data),
  deleteTransaction:  (id)             => api.delete(`/stocks/portfolio/transactions/${id}`),
  getWatchlist:       ()               => api.get('/stocks/watchlist'),
  addWatchlist:       (data)           => api.post('/stocks/watchlist', data),
  removeWatchlist:    (id)             => api.delete(`/stocks/watchlist/${id}`),
};
```

**Pattern: Object with arrow functions**

Each property is an arrow function that returns a Promise (axios always returns Promises).

```javascript
// Template literal in URL
analyse: (symbol) => api.get(`/stocks/analyse/${symbol}`)
// api.get('/stocks/analyse/TCS.NS')

// Query parameters via params object
chart: (symbol, period) => api.get(`/stocks/chart/${symbol}`, { params: { period } })
// api.get('/stocks/chart/TCS.NS', { params: { period: '1y' } })
// → GET /stocks/chart/TCS.NS?period=1y

// POST with JSON body
addTransaction: (data) => api.post('/stocks/portfolio/transactions', data)
// data = { symbol, transaction_type, quantity, price, brokerage }
// axios automatically serialises to JSON

// DELETE with path parameter
deleteTransaction: (id) => api.delete(`/stocks/portfolio/transactions/${id}`)
// → DELETE /stocks/portfolio/transactions/42
```

---

### `services/userService.js`

```javascript
export const userService = {
  list:         (params) => api.get('/users', { params }),
  create:       (data)   => api.post('/users', data),
  update:       (id, d)  => api.put(`/users/${id}`, d),
  remove:       (id)     => api.delete(`/users/${id}`),
  uploadAvatar: (file)   => {
    const form = new FormData();
    form.append('file', file);
    return api.post('/users/me/avatar', form);
  },
  removeAvatar: () => api.delete('/users/me/avatar'),
};
```

**`FormData` for file upload:**

Binary file uploads use `multipart/form-data` encoding (not JSON).
`new FormData()` creates a multipart body. `form.append('file', file)` adds the file.
Axios automatically sets `Content-Type: multipart/form-data; boundary=...` when it
detects a `FormData` body.

The server receives the file via `UploadFile` in FastAPI:
```python
async def upload_avatar(file: UploadFile = File(...)):
    contents = await file.read()
```

---

### `services/scrapingService.js`

```javascript
export const scrapingService = {
  createJob:  (asins)   => api.post('/scraping/jobs', { asins }),
  getJobs:    ()        => api.get('/scraping/jobs'),
  getJob:     (id)      => api.get(`/scraping/jobs/${id}`),
  deleteJob:  (id)      => api.delete(`/scraping/jobs/${id}`),
  exportCsv:  (id)      => api.get(`/scraping/jobs/${id}/export`, { responseType: 'blob' }),
};
```

**`responseType: 'blob'` for CSV export:**

By default, axios parses responses as JSON. For file downloads, you need raw binary.
`responseType: 'blob'` tells axios to return a `Blob` object (binary data).

```javascript
// Component usage:
const res = await scrapingService.exportCsv(jobId);
const url = URL.createObjectURL(res.data);   // Create temporary URL
const a = document.createElement('a');
a.href = url;
a.download = `job_${jobId}.csv`;
a.click();
URL.revokeObjectURL(url);   // Clean up memory
```

---

## How Components Use Services

### Pattern: useEffect + async call

```jsx
function StockDashboard() {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);

  const loadAnalysis = async (symbol) => {
    setLoading(true);
    setError(null);
    try {
      const res = await stockService.analyse(symbol);
      setAnalysis(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load analysis');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (symbol) loadAnalysis(symbol);
  }, [symbol]);
```

**`err.response?.data?.detail`:**

FastAPI error responses have shape `{ detail: "Error message" }`.
`err.response?.data?.detail` safely navigates: if any part is undefined (network error),
it returns `undefined` and falls back to `'Failed to load analysis'`.

### Pattern: Parallel Requests

```jsx
useEffect(() => {
  Promise.all([
    stockService.getPortfolio(),
    stockService.getWatchlist(),
    stockService.globalMarkets(),
  ]).then(([portfolio, watchlist, markets]) => {
    setPortfolio(portfolio.data);
    setWatchlist(watchlist.data);
    setMarkets(markets.data);
  });
}, []);
```

`Promise.all` fires all three requests simultaneously. Total time = slowest of the three
(not sum of all three). Without parallel requests: 300ms + 400ms + 200ms = 900ms.
With parallel: max(300, 400, 200) = 400ms.

---

## Interview Questions

**Q: What is an Axios interceptor and what are use cases?**

An interceptor is middleware that runs for every request/response. Use cases:
- Request: attach auth token, add request ID, log outgoing requests
- Response: handle global errors (401, 503), transform response format, log timing

**Q: What is `optional chaining` (`?.`) and why is it useful with API responses?**

`obj?.prop` returns `undefined` if `obj` is `null` or `undefined`, instead of throwing
`TypeError: Cannot read property 'prop' of null`. API error objects have variable shapes:
network errors have no `response`, server errors have `response.data`, etc.
Optional chaining safely navigates uncertain object structures.

**Q: What is the difference between `Promise.all` and `Promise.allSettled`?**

`Promise.all`: if ANY promise rejects, the entire `all` rejects immediately.
Good when all requests must succeed.

`Promise.allSettled`: waits for ALL promises regardless of rejection. Returns an array
of `{status: 'fulfilled'|'rejected', value|reason}`. Good when some can fail without
blocking others — you handle each result individually.
