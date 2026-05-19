# Developer Documentation — NSE Stock Dashboard

Complete code documentation for interview preparation and developer onboarding.
Every file in the project is explained: what it does, why it exists, and how the code works.

---

## Reading Order

### Start Here
| File | Read When |
|---|---|
| [00_PROJECT_OVERVIEW.md](00_PROJECT_OVERVIEW.md) | First — understand what the project is and its directory structure |
| [01_ARCHITECTURE.md](01_ARCHITECTURE.md) | Second — understand patterns, decisions, and trade-offs |

### Backend (Python / FastAPI)
| File | Covers |
|---|---|
| [BACKEND/01_main.md](BACKEND/01_main.md) | `main.py` — lifespan, CORS, middleware, StaticFiles, router mounting |
| [BACKEND/02_config.md](BACKEND/02_config.md) | `config.py` — Pydantic BaseSettings, .env, DATABASE_URL property |
| [BACKEND/03_database.md](BACKEND/03_database.md) | `db/base.py` + `db/session.py` — SQLAlchemy engine, session, get_db, Alembic |
| [BACKEND/04_models.md](BACKEND/04_models.md) | `models/` — ORM models, Column types, relationships, cascade |
| [BACKEND/05_schemas.md](BACKEND/05_schemas.md) | `schemas/` — Pydantic v2 validators, In/Out pairs, from_attributes |
| [BACKEND/06_crud.md](BACKEND/06_crud.md) | `crud/` — Repository pattern, Generic[T], partial update |
| [BACKEND/07_core.md](BACKEND/07_core.md) | `core/` — bcrypt, JWT, RBAC roles, exceptions, logging |
| [BACKEND/08_dependencies.md](BACKEND/08_dependencies.md) | `dependencies.py` — DI graph, JWT validation, chained deps |
| [BACKEND/09_endpoints.md](BACKEND/09_endpoints.md) | `endpoints/` — all HTTP handlers, SSE streaming, file upload |
| [BACKEND/10_stock_service.md](BACKEND/10_stock_service.md) | `stock_service.py` — yfinance, retry/backoff, TTL cache, technicals, scoring |
| [BACKEND/11_sentiment_service.md](BACKEND/11_sentiment_service.md) | `sentiment_service.py` — Bing News, og:description, ThreadPoolExecutor |
| [BACKEND/12_scraper_worker.md](BACKEND/12_scraper_worker.md) | `scraper.py` + `worker.py` — Playwright, Semaphore, PID singleton, crash recovery |

### Frontend (React.js)
| File | Covers |
|---|---|
| [FRONTEND/01_App_Routes.md](FRONTEND/01_App_Routes.md) | `App.jsx`, `routes/` — BrowserRouter, Outlet, PrivateRoute, RoleRoute |
| [FRONTEND/02_AuthContext.md](FRONTEND/02_AuthContext.md) | `AuthContext.jsx` + `authService.js` — Context API, useCallback, URLSearchParams |
| [FRONTEND/03_api_services.md](FRONTEND/03_api_services.md) | `services/api.js` + all service files — Axios, interceptors, FormData |
| [FRONTEND/04_hooks.md](FRONTEND/04_hooks.md) | `hooks/` — useSSE, usePagination, useSortFilter, useMenuAccess, useConfirm |
| [FRONTEND/05_StockDashboard.md](FRONTEND/05_StockDashboard.md) | `StockDashboard/` — tabs, lazy loading, Indian FY, financial tables, news |

---

## Quick Reference — Key Concepts

### Backend

| Concept | File | Line |
|---|---|---|
| App lifespan / startup | `main.py` | `@asynccontextmanager async def lifespan` |
| Settings / .env | `config.py` | `class Settings(BaseSettings)` |
| DB session per request | `db/session.py` | `def get_db(): yield db` |
| JWT creation | `core/security.py` | `def create_access_token` |
| Password hashing | `core/security.py` | `pwd_context = CryptContext(schemes=["bcrypt"])` |
| Role check dependency | `core/roles.py` | `def require_roles(*roles)` |
| Auth dependency chain | `dependencies.py` | `get_current_user → get_current_active_user` |
| Generic CRUD | `crud/base.py` | `class CRUDBase(Generic[ModelType])` |
| TTL cache | `stock_service.py` | `def _cached(key, fn, ttl)` |
| Retry + backoff | `stock_service.py` | `def _yf_info(symbol, retries=3)` |
| Parallel HTTP | `sentiment_service.py` | `ThreadPoolExecutor(max_workers=4)` |
| SSE streaming | `endpoints/scraping.py` | `StreamingResponse(event_gen())` |
| Singleton worker | `worker.py` | `def _acquire_singleton()` |
| Playwright scraping | `scraper.py` | `def scrape_amazon_asin(asin)` |

### Frontend

| Concept | File | Function/Component |
|---|---|---|
| JWT interceptor | `services/api.js` | `api.interceptors.request.use` |
| 401 global handler | `services/api.js` | `api.interceptors.response.use` |
| Global auth state | `context/AuthContext.jsx` | `AuthProvider`, `useAuth()` |
| Auth guard | `routes/PrivateRoute.jsx` | `PrivateRoute` |
| Role + menu guard | `routes/RoleRoute.jsx` | `RoleRoute` |
| SSE stream | `hooks/useSSE.js` | `useSSE(path, init)` |
| Pagination state | `hooks/usePagination.js` | `usePagination(pageSize)` |
| Sort + search | `hooks/useSortFilter.js` | `useSortFilter()`, `applySort()`, `applySearch()` |
| Per-page permissions | `hooks/useMenuAccess.js` | `useMenuAccess(path)` |
| Lazy load accordion | `StockDashboard/index.jsx` | `FinancialsSection` |
| Indian FY | `StockDashboard/index.jsx` | `getFY()`, `computePeriodGroups()` |
| Composite score bar | `StockDashboard/index.jsx` | `CompositeScore` |

---

## Interview Question Topics Covered in These Docs

### Python / FastAPI
- Pydantic BaseSettings and type coercion
- SQLAlchemy ORM — session lifecycle, flush vs commit, identity map
- Alembic migrations — autogenerate, upgrade, downgrade
- FastAPI Dependency Injection — Depends, chaining, caching within request
- JWT — HS256 vs RS256, payload structure, expiry, decode
- bcrypt — why slow hashing, salt, work factor
- HTTP status codes — 401 vs 403, 422, 502
- CORS — preflight, allow_origins, credentials
- ASGI vs WSGI
- Exponential backoff for rate limiting
- ThreadPoolExecutor — when to use threads vs asyncio
- Playwright — headless Chrome, anti-bot detection
- Server-Sent Events — vs WebSockets
- In-memory cache — TTL, single-process limitation, Redis alternative

### React.js
- Context API vs Redux — when to use each
- Custom hooks — useCallback, useRef vs useState
- React Router v6 — nested routes, Outlet, Navigate
- Axios interceptors — request/response, Promise.reject
- Promise.all vs Promise.allSettled
- Controlled vs uncontrolled components
- Optional chaining — `?.` with API error objects
- useCallback — preventing infinite loops, stable references
- useMemo — expensive derived calculations
- SSE with Fetch API — ReadableStream, AbortController
- `rel="noopener noreferrer"` — tab-napping security
- FormData for file uploads
- Loading states — preventing flash of wrong content

---

## File Size Summary

```
DOCS/
├── 00_PROJECT_OVERVIEW.md   ← Project goals, stack, directory tree, data flow
├── 01_ARCHITECTURE.md       ← 10 design patterns, technology choices, security, scalability
├── BACKEND/
│   ├── 01_main.md           ← Lifespan, ASGI, middleware ordering, CORS
│   ├── 02_config.md         ← BaseSettings, .env, DATABASE_URL, SECRET_KEY
│   ├── 03_database.md       ← Engine, session, get_db, Alembic, ORM concepts
│   ├── 04_models.md         ← User, Stock, Scraping models, Column types, relationships
│   ├── 05_schemas.md        ← Pydantic v2, validators, In/Out pattern, from_attributes
│   ├── 06_crud.md           ← Generic[T], Repository pattern, partial update
│   ├── 07_core.md           ← bcrypt, JWT, Enum RBAC, exception constants, logging
│   ├── 08_dependencies.md   ← DI graph, OAuth2PasswordBearer, chained deps
│   ├── 09_endpoints.md      ← All HTTP handlers, route ordering, SSE, file upload
│   ├── 10_stock_service.md  ← curl_cffi, retry/backoff, cache, 15+ technicals, composite score
│   ├── 11_sentiment_service.md ← Bing RSS, namespace bug fix, ThreadPoolExecutor, og:description
│   └── 12_scraper_worker.md ← Playwright, Semaphore, PID singleton, crash recovery
└── FRONTEND/
    ├── 01_App_Routes.md     ← App.jsx, BrowserRouter, Outlet, PrivateRoute, RoleRoute
    ├── 02_AuthContext.md    ← Context API, useCallback infinite loop, URLSearchParams
    ├── 03_api_services.md   ← Axios, interceptors, all service files, Promise.all
    ├── 04_hooks.md          ← useSSE (AbortController, ReadableStream), usePagination, useSortFilter
    └── 05_StockDashboard.md ← Tabs, lazy loading, Indian FY, FinTable, CompositeScore, News
```
