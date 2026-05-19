# `backend/app/main.py` — Application Entry Point

## What Is This File?

`main.py` is the **root of the FastAPI application**. Every HTTP request enters here.
It creates the `app` object, registers middleware, mounts static files, includes routers,
and manages the application **lifespan** (startup and shutdown logic).

---

## Full Code With Explanation

```python
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.api.v1.router import api_router
from app.middleware.logging_middleware import LoggingMiddleware
from app.db.session import engine
from app.db.base import Base
import app.models.user          # noqa — register models with Base
import app.models.scraping       # noqa — register scraping models with Base
import app.models.email_action   # noqa — register email models with Base
import app.models.product_master # noqa — register product models with Base
import app.models.stock          # noqa — register stock models with Base
```

### Why Import Models With `# noqa`?

SQLAlchemy needs to know about every model class **before** calling `Base.metadata.create_all()`.
When Python imports a model file (e.g., `app.models.user`), the `User` class definition
runs and registers itself with `Base.metadata`.

If you skip these imports, `create_all()` will not create those tables — it won't error,
it will silently do nothing. The `# noqa` comment tells linters "this import appears unused
but it has a side effect — keep it."

---

```python
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "avatars").mkdir(exist_ok=True)
```

### Why `Path(__file__).resolve().parent.parent`?

`__file__` is the path to `main.py`. `.parent` goes up to `app/`. `.parent` again goes up to
`backend/`. So `STATIC_DIR = backend/static/`. Using `Path` (not string concatenation) works
on both Linux and Windows.

`mkdir(exist_ok=True)` creates the directory only if it doesn't exist. No error if it already exists.

---

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)  # ← Step 1: Create DB tables
    cmd = f'exec "{sys.executable}" "{_WORKER_SCRIPT}"'
    worker = subprocess.Popen(cmd, shell=True, start_new_session=True)  # ← Step 2: Start worker
    try:
        yield   # ← Application runs here (handles all requests)
    finally:
        worker.terminate()  # ← Step 3: Kill worker on shutdown
```

### What Is `@asynccontextmanager`?

A **context manager** defines what happens when entering and exiting a block.
`@asynccontextmanager` wraps a generator function so it can be used as an `async with` block.

FastAPI's `lifespan` parameter expects exactly this pattern:
- Code **before** `yield` = startup logic
- Code **after** `yield` (in `finally`) = shutdown logic

### Why `Base.metadata.create_all()`?

This is a shortcut that creates all tables in PostgreSQL if they don't already exist.
In development, it means you never need to run migrations manually.
In production, you would use **Alembic migrations** for schema changes (safer, versioned).

### Why `subprocess.Popen` for the Worker?

The scraping worker runs **blocking** code (Playwright browser). If run in an `asyncio.Task`,
it would freeze the FastAPI event loop. Options considered:

| Option | Problem |
|---|---|
| `asyncio.create_task` | Blocking code freezes event loop |
| `threading.Thread` | Works, but shares memory space — crash in thread can corrupt app |
| `multiprocessing.Process` | Good, but harder to start/stop cleanly |
| **`subprocess.Popen`** | ✅ True OS process, isolated memory, clean start/stop |

`start_new_session=True` detaches the worker from the parent's process group — a SIGTERM
to uvicorn won't cascade to the worker. We call `worker.terminate()` explicitly in `finally`.

`shell=True` with `exec` is used so debugpy (VSCode debugger) doesn't intercept the spawn.

---

```python
app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)
```

`debug=True` in development adds detailed tracebacks to error responses.
`lifespan=lifespan` wires in the startup/shutdown function.

---

## Middleware Stack (Order Is Critical)

```python
app.add_middleware(LoggingMiddleware)   # Added second → runs INNER
app.add_middleware(                     # Added first → runs OUTER
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### How Middleware Ordering Works

FastAPI wraps middleware like an onion. The **last `add_middleware` call wraps all others**.

```
Request enters:  CORSMiddleware → LoggingMiddleware → Endpoint
Response exits:  Endpoint → LoggingMiddleware → CORSMiddleware
```

This order is intentional:
- **CORS** must be outermost to handle browser `OPTIONS` preflight requests before any
  auth or logging runs.
- **Logging** sits inside CORS so it sees the actual response status code (not the CORS wrapper).

### What Does CORS Do?

Browser's Same-Origin Policy blocks JavaScript from calling APIs on a different domain/port.
When React (port 3000) calls the backend (port 9000), the browser first sends a preflight
`OPTIONS` request. `CORSMiddleware` responds with `Access-Control-Allow-*` headers that
tell the browser "this API is allowed to be called from any origin."

`allow_origins=["*"]` allows all origins. In production, replace with your domain:
`allow_origins=["https://yourapp.com"]`.

`allow_credentials=False` — set to `False` because `allow_origins=["*"]` and credentials
(cookies) cannot both be true. We use Bearer tokens in headers instead of cookies.

---

## Static Files

```python
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```

`/static/avatars/user_1_abc123.jpg` is served directly from disk — FastAPI does not
process these through Python. The `name="static"` allows generating URLs with
`request.url_for("static", path="avatars/filename.jpg")`.

---

## Router

```python
app.include_router(api_router, prefix="/api/v1")
```

All API endpoints are grouped under `/api/v1/`. This versioning prefix means if you ever
release a breaking API change, you add `/api/v2/` routes without removing v1.

---

## `LoggingMiddleware` — How It Works

```python
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)   # ← calls the actual endpoint
        ms = round((time.time() - start) * 1000, 2)
        logger.info(f"{request.method} {request.url.path} → {response.status_code} ({ms}ms)")
        return response
```

`call_next(request)` passes the request to the next middleware/endpoint and waits.
After the response is back, we log: `GET /api/v1/stocks/analyse/TCS.NS → 200 (342.5ms)`.

---

## Interview Questions

**Q: What is ASGI and why does FastAPI use it?**

ASGI = Asynchronous Server Gateway Interface. It's the Python standard for async web servers.
WSGI (used by Flask/Django) handles one request per thread — slow for I/O-heavy workloads.
ASGI uses an event loop — one process can handle thousands of concurrent requests if they
await I/O. FastAPI is ASGI-native; it runs on Uvicorn (ASGI server).

**Q: Why use `lifespan` instead of `@app.on_event("startup")`?**

`@app.on_event` is deprecated in FastAPI 0.93+. `lifespan` is the modern pattern.
It's more Pythonic (context manager), keeps startup and shutdown in one place, and plays
better with testing frameworks (you can override lifespan in tests).

**Q: What would happen if `Base.metadata.create_all()` was not called?**

If tables don't exist, the first API call that tries to query them would raise
`ProgrammingError: relation "users" does not exist`. You'd see a 500 error.
