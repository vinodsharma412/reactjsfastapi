# Architecture — Design Patterns, Decisions & Trade-offs

## System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    BROWSER (React SPA)                             │
│                                                                    │
│  App.jsx                                                           │
│   ├── BrowserRouter     (React Router v6 — client-side routing)   │
│   ├── AuthProvider      (Context API — global auth state)         │
│   └── AppRoutes                                                    │
│        ├── PrivateRoute (authentication guard)                     │
│        ├── RoleRoute    (authorisation guard — role + menu RBAC)   │
│        └── Layout → Outlet → Pages                                 │
│              └── StockDashboard → stockService → api.js (axios)   │
│                                                                    │
└──────────────────────────┬─────────────────────────────────────────┘
                           │  HTTPS  /api/v1/*
                           │  Authorization: Bearer JWT
┌──────────────────────────▼─────────────────────────────────────────┐
│                    FASTAPI BACKEND (Python)                        │
│                                                                    │
│  Uvicorn ASGI Server                                               │
│   └── main.py (FastAPI app)                                        │
│        ├── CORSMiddleware                                          │
│        ├── LoggingMiddleware                                        │
│        └── /api/v1/* router                                        │
│             ├── /auth    → auth_service → JWT creation             │
│             ├── /users   → crud_user → PostgreSQL                  │
│             ├── /stocks  → stock_service → yfinance                │
│             │            → sentiment_service → Bing News           │
│             └── /scraping → scraping_queue → worker process        │
│                                                                    │
│  worker.py (separate OS process)                                   │
│   └── poll DB → scraper.py → Playwright → Amazon.in               │
│                                                                    │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │ PostgreSQL  │
                    │  - users    │
                    │  - stocks   │
                    │  - scraping │
                    └─────────────┘
```

---

## Design Patterns Used

### 1. Repository Pattern (CRUD Layer)

**What:** Centralises all database access in `crud/` classes.
**Why:** Endpoints stay thin (HTTP logic only). CRUD functions stay pure (DB logic only).
**How:** `CRUDBase[Model]` provides generic get/get_all/delete. Subclasses add domain operations.
**Trade-off:** Extra layer of abstraction. Simple projects might skip this and query in endpoints.

### 2. Dependency Injection (FastAPI `Depends`)

**What:** FastAPI resolves and injects dependencies (auth, DB session) before calling endpoints.
**Why:** Decouples endpoint logic from infrastructure. Dependencies are testable and swappable.
**How:** `Depends(get_db)` → creates session. `Depends(get_current_active_user)` → validates JWT.
**Trade-off:** More abstract than direct function calls. Requires understanding of FastAPI's DI system.

### 3. Context API (React global state)

**What:** `AuthContext` holds user/menus/login/logout, accessible to any component.
**Why:** Avoids prop drilling (passing user through many component layers).
**How:** `createContext` → `AuthProvider` wraps app → `useAuth()` in any component.
**Trade-off:** All consumers re-render when context changes. Use selectors or split contexts for performance.

### 4. Interceptor Pattern (Axios)

**What:** Request/response middleware that runs on every API call.
**Why:** Centralises auth header attachment and global 401 handling.
**How:** `api.interceptors.request.use()` and `api.interceptors.response.use()`.
**Trade-off:** Global side effects (redirect to /login) can be surprising if not well documented.

### 5. Factory Function (require_roles)

**What:** `require_roles(Role.ADMIN, Role.MANAGER)` returns a FastAPI dependency.
**Why:** Parameterise dependencies without changing the dependency signature.
**How:** Closure captures `roles` tuple; returned `checker` function is a standard dependency.
**Trade-off:** One extra indirection layer. Worth it for the DRY benefit.

### 6. Strategy Pattern (News Sources)

**What:** Bing News is the primary strategy; Google News is the fallback.
**Why:** Single news source creates brittleness — if Bing is down, use Google.
**How:** `items = _fetch_bing_rss(q)` → `if len(items) < 4: items = _fetch_google_rss(url)`.
**Trade-off:** Fallback adds latency when primary fails (two HTTP calls).

### 7. Generic Base Class (CRUDBase[ModelType])

**What:** `CRUDBase[User]` → typed CRUD that IDE understands as working with `User` objects.
**Why:** Eliminates duplicated get/get_all/delete code across every model's CRUD class.
**How:** Python `TypeVar` + `Generic[T]` → type-safe specialisation.
**Trade-off:** Requires understanding of Python generics. Adds abstraction.

### 8. In-Memory TTL Cache

**What:** Python dict `_CACHE` with timestamps. Different TTLs per data type.
**Why:** Yahoo Finance calls are rate-limited (429) and slow (~500ms). Cache avoids redundant calls.
**How:** `_cached(key, fn, ttl)` — check timestamp, call fn if stale, store result.
**Trade-off:** Single-process only. Multiple uvicorn workers → cache diverges. Production: Redis.

### 9. Composite Scoring

**What:** Multiple signals (fundamental, technical, sentiment, valuation, macro) summed to a score.
**Why:** No single indicator is reliable. Aggregating reduces false signals.
**How:** Each signal contributes ±1 or ±2 points. Total maps to Strong Buy/Buy/Hold/Sell/Strong Sell.
**Trade-off:** Equal weighting. A ML model could learn optimal weights from historical data.

### 10. PID File Singleton

**What:** Worker writes its PID to a file; on startup checks if old PID is alive.
**Why:** Prevents multiple worker processes from running simultaneously (double-processing tasks).
**How:** `os.kill(pid, 0)` checks process existence. `atexit` cleanup removes file on exit.
**Trade-off:** Race condition if two workers start simultaneously. Acceptable for single-server deploy.

---

## Technology Choices and Rationale

### FastAPI over Flask/Django

| | Flask | Django | FastAPI |
|---|---|---|---|
| Performance | Moderate | Slow | Fast (async) |
| Type hints | Optional | None | First-class |
| Auto docs | No | DRF only | Built-in OpenAPI |
| Async | With extensions | With ASGI extensions | Native |
| ORM | Choose your own | Built-in (Django ORM) | Choose your own |

FastAPI was chosen for: automatic OpenAPI docs, native async, Pydantic validation,
and speed. The project doesn't need Django's admin or built-in ORM.

### SQLAlchemy over Django ORM / Tortoise / SQLModel

SQLAlchemy is the most mature Python ORM. Explicit session management (`get_db`)
gives full control. `Alembic` (by the same author) provides migration tooling.

### JWT over Session Cookies

| | JWT (Bearer) | Session Cookies |
|---|---|---|
| State | Stateless (server has no memory of tokens) | Stateful (server stores sessions) |
| Scaling | Each server can verify any token | Sessions must be shared (Redis) |
| Mobile | Works natively | Cookie handling is complex |
| Logout | Cannot truly invalidate (token lives until expiry) | Delete session row |
| This project | ✅ JWT | |

Stateless JWT is suitable for this single-server app. For true logout before expiry,
a token blacklist (Redis set) would be needed.

### Context API over Redux

Redux is justified for:
- Complex state with many concurrent updates
- Dev tools (time-travel debugging)
- Large teams (enforced patterns)

Context API is sufficient for:
- Simple auth state (user, menus)
- Infrequent updates (login/logout)
- Small-medium teams

### React over Next.js/Vue

Plain React (Create React App) was chosen for simplicity. No SSR needed — all data
is user-specific (requires auth) so SEO is not a concern. Next.js adds complexity
that isn't justified here.

---

## Security Architecture

### Authentication Flow
```
Client → POST /auth/token (username + password)
       ← JWT (expires in 24h)

Client → GET /stocks/* (Authorization: Bearer JWT)
       → FastAPI: decode JWT → verify signature → check exp
       → DB: SELECT user WHERE username = payload.sub
       → check is_active
       ← 200 OK / 401 Unauthorized
```

### Authorisation Layers (Defence in Depth)

```
Layer 1: Authentication  → get_current_active_user (JWT valid + user active)
Layer 2: Role check      → require_roles(Role.ADMIN) (user.role in allowed roles)
Layer 3: Menu permission → RoleRoute menu.can_view check (DB-driven, per-page)
Layer 4: Frontend guard  → useMenuAccess() hides buttons (UX, not security)
```

Layers 1-3 are server-side (enforced). Layer 4 is client-side (convenience only).

### Password Security
- bcrypt with auto-generated salt (work factor 12 = 2^12 = 4096 iterations)
- Never stored or logged in plain text
- `hashed_password` field name enforces the convention
- `verify_password` always uses `pwd_context.verify()` (not string comparison)

### File Upload Security
- Content-type validation (MIME type check)
- File size limit (3 MB)
- Random UUID in filename (prevents path traversal: `../../etc/passwd`)
- Old avatar deleted on replacement (no orphaned files)

---

## Performance Architecture

### Backend Caching Strategy

```
Request → _cached(key, fn, ttl)
              │
              ├── Cache hit (< TTL ago)? → return cached → <1ms
              │
              └── Cache miss → fn() → ~500ms-5s → store → return
```

| Data | TTL | Reason |
|---|---|---|
| Stock Analysis | 15 min | Price changes slowly intraday |
| Chart OHLCV | 30 min | Historical data changes rarely |
| Screener | 20 min | Iterates 100+ stocks — expensive |
| Financials | 60 min | Quarterly data — very stable |
| Sentiment | 10 min | News changes frequently |
| Article summaries | 24 hr | Article text doesn't change |
| Global markets | 5 min | World indices need freshness |

### Frontend Performance

**Lazy loading:** Financial statements only fetched when accordion opened.
**Parallel requests:** `Promise.all([analyse, sentiment, chart])` — all fire simultaneously.
**Conditional rendering:** Unmounted tabs don't run effects or hold memory.
**`useCallback`:** Stable function references prevent child re-renders.
**`useMemo` (opportunity):** `computePeriodGroups` should be memoised — currently runs on every render.

---

## Scalability Considerations

### Current Limitations (Single Server)

| Component | Limitation | Solution |
|---|---|---|
| In-memory cache | Single process | Redis |
| DB connection pool | Fixed size (5) | PgBouncer |
| Scraping worker | 1 process, 2 concurrent | Celery + workers |
| File storage | Local disk | S3/GCS |
| Session | JWT stateless ✅ | Already scales |

### Scaling the Backend

```
Load Balancer
    ├── Uvicorn process 1  ← Each has own _CACHE dict (diverges)
    ├── Uvicorn process 2
    └── Uvicorn process 3

Solution: Replace _CACHE with Redis
    cache.set(key, json.dumps(data), ex=ttl)
    cached = cache.get(key)
```

### Database Indices (Current)

```sql
users: ix_users_id, ix_users_username (unique)
stock_transactions: ix_stock_transactions_id, ix_stock_transactions_symbol
stock_watchlist: ix_stock_watchlist_id, ix_stock_watchlist_symbol (unique)
scraping_tasks: ix_scraping_tasks_id, status (no index — should add for poll query)
```

Missing index: `CREATE INDEX ix_scraping_tasks_status ON scraping_tasks(status)`.
The worker poll query (`WHERE status = 'pending'`) does a full table scan currently.

---

## Interview Questions

**Q: How would you add real-time price updates without the user refreshing?**

Option 1: **SSE** (already used for scraping) — server pushes updates every N seconds.
Option 2: **WebSockets** — bidirectional, good if client also needs to send data.
Option 3: **React Query / SWR** — client polls on an interval with smart invalidation.

For stock prices, SSE is appropriate — server-to-client push, no need for client-to-server during streaming.

**Q: How would you add rate limiting to the API?**

Use `slowapi` (FastAPI-compatible rate limiter):
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@router.get("/stocks/screener")
@limiter.limit("10/minute")   # Max 10 screener requests per minute per IP
def screener(...):
    ...
```

For per-user limiting: use `get_current_user` as the key function.

**Q: How would you add WebSocket support for real-time stock prices?**

```python
from fastapi import WebSocket

@router.websocket("/ws/prices")
async def price_stream(websocket: WebSocket, token: str):
    await websocket.accept()
    # Validate token
    user = validate_token(token)
    while True:
        prices = get_quick_prices(['TCS.NS', 'INFY.NS'])
        await websocket.send_json(prices)
        await asyncio.sleep(5)
```

React side:
```javascript
const ws = new WebSocket(`ws://localhost:9000/ws/prices?token=${token}`);
ws.onmessage = (e) => setPrices(JSON.parse(e.data));
```

**Q: How would you implement audit logging for all user actions?**

Add a middleware or endpoint-level logging:
```python
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method in ('POST', 'PUT', 'DELETE'):
            # Log to audit_logs table: user_id, method, path, status, timestamp
            await audit_log(request, response)
        return response
```

Or use a database trigger that logs any INSERT/UPDATE/DELETE with `OLD` and `NEW` row values.
