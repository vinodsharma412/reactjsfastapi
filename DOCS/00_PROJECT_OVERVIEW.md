# Project Overview — NSE Stock Dashboard

## What Is This Project?

A full-stack web application built for analysing NSE (National Stock Exchange of India) stocks.
It combines a **React.js Single Page Application** (SPA) frontend with a **FastAPI** Python backend,
backed by a **PostgreSQL** relational database.

---

## What Can It Do?

| Feature | Description |
|---|---|
| **Stock Analyser** | Search any NSE symbol, get real-time price, fundamental ratios, technical indicators, composite buy/sell signal |
| **News & Sentiment** | Bing News RSS aggregation, article summary enrichment via og:description, keyword-based bullish/bearish scoring |
| **Detailed Financials** | Balance sheet, P&L (annual/quarterly/half-yearly/nine-month), cash flows, ratios, capital structure — all in Crores (INR) |
| **Stock Screener** | Filter NSE universe by PE, dividend yield, composite score; add to watchlist in one click |
| **Portfolio Tracker** | Log buy/sell/dividend transactions, see P&L per holding and total |
| **Watchlist** | Track symbols with target price and stop-loss |
| **Global Markets** | Live prices for major world indices (Nifty 50, S&P 500, Nasdaq, etc.) |
| **Amazon Scraper** | Bulk scrape Amazon.in product data by ASIN using Playwright (headless Chrome) |
| **Email Actions** | Process Gmail inbox with automated actions |
| **User Management** | Role-based access: admin, manager, viewer |
| **Menu Access Control** | DB-driven per-menu read/insert/update/delete permissions |

---

## Technology Stack

### Backend
| Library | Version | Purpose |
|---|---|---|
| **FastAPI** | 0.100+ | Async REST API framework |
| **SQLAlchemy** | 2.x | ORM for PostgreSQL |
| **Alembic** | 1.x | Database schema migrations |
| **Pydantic v2** | 2.x | Request/response validation, settings |
| **python-jose** | 3.x | JWT encoding/decoding |
| **passlib[bcrypt]** | 1.7 | Password hashing |
| **yfinance** | 0.2.48 | Yahoo Finance stock data |
| **curl_cffi** | latest | Browser-impersonating HTTP session (bypasses 429) |
| **httpx** | 0.27 | Async-capable HTTP client (news fetching) |
| **Playwright** | 1.x | Headless Chrome for Amazon scraping |
| **pandas** | 2.x | Financial data manipulation |

### Frontend
| Library | Version | Purpose |
|---|---|---|
| **React** | 18.x | UI component framework |
| **React Router v6** | 6.x | Client-side routing |
| **Axios** | 1.x | HTTP client with interceptors |
| **Recharts** | 2.x | Candlestick and line charts |

### Infrastructure
| Component | Technology |
|---|---|
| Database | PostgreSQL |
| Migrations | Alembic |
| Process model | Uvicorn (ASGI) + separate worker process |
| Static files | FastAPI StaticFiles mount |

---

## Directory Structure

```
reactjsfastapi/
├── backend/
│   ├── alembic/              ← Database migration scripts
│   │   └── versions/         ← Each migration = one .py file
│   ├── alembic.ini           ← Alembic configuration
│   └── app/
│       ├── main.py           ← FastAPI app creation, lifespan, middleware
│       ├── config.py         ← Pydantic settings (reads .env)
│       ├── dependencies.py   ← JWT auth dependency (get_current_user)
│       ├── worker.py         ← Standalone scraping worker process
│       ├── api/v1/
│       │   ├── router.py     ← Assembles all sub-routers
│       │   └── endpoints/
│       │       ├── auth.py           ← POST /auth/token (login)
│       │       ├── users.py          ← CRUD + avatar upload
│       │       ├── stocks.py         ← All stock analysis endpoints
│       │       ├── scraping.py       ← Amazon scraping jobs
│       │       ├── email_action.py   ← Gmail integration
│       │       ├── menu.py           ← Menu management
│       │       └── product_master.py ← Product catalog
│       ├── core/
│       │   ├── security.py    ← bcrypt + JWT helpers
│       │   ├── roles.py       ← RBAC Enum + require_roles() factory
│       │   ├── exceptions.py  ← Pre-built HTTPException instances
│       │   └── logging.py     ← Logger factory function
│       ├── crud/
│       │   ├── base.py        ← Generic CRUDBase[Model]
│       │   └── user.py        ← CRUDUser (login lookup, create, update)
│       ├── db/
│       │   ├── base.py        ← SQLAlchemy declarative Base
│       │   └── session.py     ← Engine + SessionLocal + get_db()
│       ├── middleware/
│       │   └── logging_middleware.py ← Request/response timing logger
│       ├── models/
│       │   ├── user.py        ← users table
│       │   ├── stock.py       ← stock_transactions, stock_watchlist tables
│       │   ├── scraping.py    ← scraping_jobs, scraping_tasks, product_data tables
│       │   └── email_action.py, product_master.py
│       ├── schemas/
│       │   ├── auth.py        ← Token, TokenData
│       │   ├── user.py        ← UserCreate, UserUpdate, UserResponse
│       │   └── stock.py       ← All stock-related Pydantic models
│       └── services/
│           ├── stock_service.py      ← yfinance, technicals, scoring (~1400 lines)
│           ├── sentiment_service.py  ← Bing/Google News, og:description enrichment
│           ├── auth_service.py       ← login_user() business logic
│           ├── scraper.py            ← Playwright Amazon scraping
│           ├── scraping_queue.py     ← Thread-based task queue
│           ├── gmail_service.py      ← Gmail IMAP reader
│           └── email_analyzer.py    ← Email categorisation logic
│
└── frontend/src/
    ├── App.jsx               ← Root component: BrowserRouter + AuthProvider
    ├── index.js              ← ReactDOM.render entry point
    ├── routes/
    │   ├── index.jsx         ← All route definitions
    │   ├── PrivateRoute.jsx  ← Redirect to /login if not authenticated
    │   └── RoleRoute.jsx     ← Redirect to /unauthorized if wrong role
    ├── context/
    │   └── AuthContext.jsx   ← Global auth state (user, menus, login, logout)
    ├── hooks/
    │   ├── useAuth.js        ← Re-exports useAuth from AuthContext
    │   ├── useSSE.js         ← Server-Sent Events stream reader
    │   ├── usePagination.js  ← Page/pageSize state + paginate() helper
    │   ├── useSortFilter.js  ← Sort column/direction + search + filters
    │   ├── useMenuAccess.js  ← Per-path can_view/insert/update/delete flags
    │   └── useConfirm.js     ← Modal confirmation dialog hook
    ├── services/
    │   ├── api.js            ← Axios instance with JWT + 401 interceptors
    │   ├── authService.js    ← login, logout, getMe, isAuthenticated
    │   ├── stockService.js   ← All stock API calls
    │   ├── userService.js    ← User CRUD API calls
    │   ├── menuService.js    ← Menu + access API calls
    │   ├── scrapingService.js← Scraping job API calls
    │   └── productService.js ← Product master API calls
    ├── pages/
    │   ├── StockDashboard/   ← The main feature page (tabs: Analyser/Screener/Portfolio...)
    │   ├── Login/            ← Login form
    │   ├── Dashboard/        ← Home dashboard
    │   ├── Users/            ← User management table
    │   ├── AmazonScraper/    ← Scraping UI with SSE live updates
    │   └── ...
    ├── components/
    │   ├── layout/Layout.jsx ← Sidebar + Header shell
    │   └── common/           ← Loader, Modal, ConfirmDialog, etc.
    ├── utils/
    │   └── constants.js      ← API_URL, TOKEN_KEY
    └── assets/styles/
        └── global.css        ← All CSS variables, component styles
```

---

## Data Flow — Login to Authenticated API Call

```
Browser                     React                    FastAPI              PostgreSQL
  │                            │                         │                    │
  │── enter username/pass ──>  │                         │                    │
  │                    authService.login()               │                    │
  │                    POST /auth/token (form-encoded)   │                    │
  │                            │ ────────────────────>   │                    │
  │                            │                   login_user()               │
  │                            │                   crud_user.get_by_username()│
  │                            │                         │ ─── SELECT ──────> │
  │                            │                         │ <── user row ────  │
  │                            │                   verify_password (bcrypt)   │
  │                            │                   create_access_token (JWT)  │
  │                            │ <── {access_token} ─── │                    │
  │                    localStorage.setItem(token)       │                    │
  │                            │                         │                    │
  │── any page action ──────>  │                         │                    │
  │                    stockService.analyse('TCS.NS')    │                    │
  │                    GET /stocks/analyse/TCS.NS        │                    │
  │                    Header: Authorization: Bearer JWT │                    │
  │                            │ ────────────────────>   │                    │
  │                            │              Depends(get_current_active_user)│
  │                            │              decode_token(JWT)               │
  │                            │              crud_user.get_by_username()     │
  │                            │                         │ ─── SELECT ──────> │
  │                            │                         │ <── user ────────  │
  │                            │              stock_service.get_stock_analysis│
  │                            │              yfinance.Ticker('TCS.NS')       │
  │                            │ <── JSON response ───── │                    │
  │ <── render charts ──────   │                         │                    │
```

---

## How Docs Are Organised

```
DOCS/
├── 00_PROJECT_OVERVIEW.md       ← This file
├── 01_ARCHITECTURE.md           ← Patterns, decisions, trade-offs
├── BACKEND/
│   ├── 01_main.md               ← App entry point
│   ├── 02_config.md             ← Settings management
│   ├── 03_database.md           ← SQLAlchemy engine, session, Base
│   ├── 04_models.md             ← All ORM models explained
│   ├── 05_schemas.md            ← All Pydantic schemas explained
│   ├── 06_crud.md               ← Repository pattern
│   ├── 07_core.md               ← Security, RBAC, exceptions, logging
│   ├── 08_dependencies.md       ← FastAPI DI, JWT flow
│   ├── 09_api_router.md         ← Router assembly
│   ├── 10_endpoints.md          ← All HTTP endpoints
│   ├── 11_stock_service.md      ← yfinance, technicals, scoring
│   ├── 12_sentiment_service.md  ← News aggregation, scoring
│   ├── 13_scraper.md            ← Playwright Amazon scraping
│   └── 14_worker.md             ← Background process architecture
└── FRONTEND/
    ├── 01_App_Routes.md         ← Entry point and routing
    ├── 02_AuthContext.md        ← Global state management
    ├── 03_api_services.md       ← Axios, interceptors, service layer
    ├── 04_hooks.md              ← Custom hooks explained
    └── 05_StockDashboard.md     ← Feature page deep dive
```
