# `backend/app/api/v1/endpoints/` — HTTP Endpoint Layer

## What Is the Endpoints Layer?

Endpoints are **thin HTTP handlers**. They:
1. Declare what parameters/body they accept (Pydantic validates automatically)
2. Check authentication/authorization (via `Depends`)
3. Call the service or CRUD layer
4. Return the response (FastAPI serialises via `response_model`)

Endpoints contain **no business logic** — they delegate to services and CRUD.

---

## `api/v1/router.py` — Assembling All Routers

```python
from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, health, menu, scraping, email_action, stocks
from app.api.v1.endpoints.product_master import product_router, suggestion_router

api_router = APIRouter()
api_router.include_router(auth.router,         prefix="/auth",             tags=["Auth"])
api_router.include_router(users.router,        prefix="/users",            tags=["Users"])
api_router.include_router(menu.router,         prefix="/menus",            tags=["Menus"])
api_router.include_router(health.router,       prefix="/health",           tags=["Health"])
api_router.include_router(scraping.router,     prefix="/scraping",         tags=["Scraping"])
api_router.include_router(email_action.router, prefix="/email",            tags=["Email"])
api_router.include_router(product_router,      prefix="/products",         tags=["Products"])
api_router.include_router(suggestion_router,   prefix="/word-suggestions", tags=["WordSuggestions"])
api_router.include_router(stocks.router,       prefix="/stocks",           tags=["Stocks"])
```

The `api_router` itself is included in `main.py` with `prefix="/api/v1"`.
Full URL: `prefix of main.py` + `prefix of router.py` + `@router.get(path)`

Example:
```
/api/v1  +  /stocks  +  /analyse/{symbol}
= /api/v1/stocks/analyse/TCS.NS
```

`tags=["Stocks"]` groups endpoints in Swagger UI (http://localhost:9000/docs).

---

## `endpoints/auth.py` — Login Endpoint

```python
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.auth_service import login_user
from app.schemas.auth import Token

router = APIRouter()

@router.post("/token", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    token = login_user(db, form_data.username, form_data.password)
    return {"access_token": token, "token_type": "bearer"}
```

### `OAuth2PasswordRequestForm`

This reads the request body as **form data** (not JSON). The OAuth2 standard requires
form-encoded login data:
```
Content-Type: application/x-www-form-urlencoded
Body: username=vinod&password=mypass
```

**Why form data and not JSON for login?**

OAuth2 spec (RFC 6749) mandates form encoding for the password grant flow.
This allows using Swagger UI's built-in "Authorize" button and standard OAuth clients.

`form_data.username` and `form_data.password` are the extracted values.

### `auth_service.login_user()` — Business Logic Separation

The endpoint calls `login_user(db, username, password)`. This function is in
`services/auth_service.py`:

```python
def login_user(db: Session, username: str, password: str) -> str:
    user = crud_user.get_by_username(db, username)
    if not user or not verify_password(password, user.hashed_password):
        raise invalid_credentials_exception
    if not user.is_active:
        raise inactive_user_exception
    return create_access_token({"sub": user.username})
```

**Why a service function and not inline in the endpoint?**

Testable: you can call `login_user(mock_db, "vinod", "password")` in a unit test
without going through HTTP.

Reusable: if you add a mobile app API later, it can use the same `login_user()`.

---

## `endpoints/users.py` — User Management

### Full CRUD for Users

```python
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user
```

Any authenticated user can fetch their own profile. No role check needed.

```python
@router.get("/", response_model=List[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)),
):
    return crud_user.get_all(db, skip=skip, limit=limit)
```

`skip` and `limit` are **query parameters** (in the URL): `/users/?skip=10&limit=5`.
FastAPI extracts them from the URL automatically because they're declared as function
parameters without `Body(...)` or `Path(...)` annotation.

```python
@router.post("/", response_model=UserResponse)
def create_user(
    user_in: UserCreate,                        # Request body (JSON)
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),
):
    existing = crud_user.get_by_username(db, user_in.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    return crud_user.create(db, user_in)
```

The uniqueness check before create is belt-and-suspenders — the DB has a `UNIQUE` constraint
too. The endpoint check gives a friendly error message; the DB constraint is the last safety net.

### Avatar Upload

```python
@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only JPEG, PNG, WebP or GIF images allowed.")

    contents = await file.read()
    if len(contents) > MAX_SIZE:   # 3 MB limit
        raise HTTPException(400, "Image must be smaller than 3 MB.")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    filename = f"user_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    save_path = AVATARS_DIR / filename

    # Delete old avatar
    if current_user.avatar_url:
        old_file = AVATARS_DIR / Path(current_user.avatar_url).name
        old_file.unlink(missing_ok=True)

    save_path.write_bytes(contents)
    current_user.avatar_url = f"/static/avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user
```

**Security Validations:**
1. `content_type` check — prevents uploading `.php` files disguised as `.jpg`
2. 3 MB size limit — prevents disk exhaustion
3. `uuid.uuid4().hex[:8]` in filename — prevents filename collisions and path traversal attacks

**Note `async def`** — `await file.read()` is async I/O (reading the upload stream).
Regular endpoints use `def` (synchronous), avatar upload uses `async def`.

**`unlink(missing_ok=True)`** — Python 3.8+ feature. Deletes the file; if it doesn't exist,
silently succeeds. Without `missing_ok=True`, you'd need a `try/except FileNotFoundError`.

---

## `endpoints/stocks.py` — All Stock Endpoints

### Route Ordering Matters

```python
@router.get("/market/global")    # ← specific, defined FIRST
def global_markets(...):
    ...

@router.get("/{symbol}")         # ← catches anything with one path segment
def some_endpoint(symbol: str):
    ...
```

FastAPI matches routes **in order**. If `/market/global` was defined after `/{symbol}`,
`/market/global` would be captured as `symbol = "market"`. Always define more specific
routes first.

This project avoids the issue by using descriptive sub-paths:
`/basic/{symbol}`, `/analyse/{symbol}`, `/chart/{symbol}`, etc.

### Portfolio Endpoints — Multi-Step Logic

```python
@router.post("/portfolio/transactions", response_model=TransactionOut)
def add_transaction(
    payload: TransactionIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    sign         = -1 if payload.transaction_type == "sell" else 1
    total_amount = sign * payload.quantity * payload.price + payload.brokerage
    record = StockTransaction(
        symbol           = payload.symbol.upper(),
        company_name     = payload.company_name or
                           stock_service.NSE_UNIVERSE.get(payload.symbol.upper(), ""),
        transaction_type = payload.transaction_type,
        quantity         = payload.quantity,
        price            = payload.price,
        total_amount     = abs(total_amount),
        brokerage        = payload.brokerage,
        notes            = payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
```

**`sign = -1 if sell else 1`** — sells reduce the invested amount.

**`payload.symbol.upper()`** — normalise: "tcs" → "TCS.NS" (after `.upper()`).
Prevents duplicates like "tcs.ns" and "TCS.NS" being treated as different symbols.

**`stock_service.NSE_UNIVERSE.get(symbol, "")`** — auto-fills company name from the
built-in NSE universe dict if the user didn't provide it.

### Screener Endpoint

```python
@router.get("/screener")
def screener(
    min_yield: float = Query(0.03, ge=0.0, le=0.20),
    max_pe:    float = Query(50.0, ge=0.0),
    min_score: int   = Query(0),
    _: User = Depends(get_current_active_user),
):
    results = stock_service.screen_stocks(min_yield, max_pe, min_score)
    if min_score:
        results = [r for r in results if (r.get('score') or 0) >= min_score]
    return results
```

`Query(0.03, ge=0.0, le=0.20)` declares:
- Default value: `0.03`
- Validation: `ge=0.0` (≥ 0), `le=0.20` (≤ 0.20)
- If client sends `min_yield=-0.1`, FastAPI returns 422 automatically

URL: `/stocks/screener?min_yield=0.05&max_pe=30&min_score=5`

### Error Handling Pattern

```python
@router.get("/analyse/{symbol}")
def analyse(symbol: str, _: User = Depends(get_current_active_user)):
    sym  = symbol.upper()
    sent = sentiment_service.analyze_sentiment(sym)
    data = stock_service.get_stock_analysis(sym, sent.get('score', 0.0))
    if data.get('error'):
        raise HTTPException(status_code=502, detail=data['error'])
    return data
```

`502 Bad Gateway` — the correct status when YOUR server called an upstream service
(Yahoo Finance) and it failed. `500` means YOUR code crashed. `502` means an upstream
dependency failed. This distinction helps with monitoring and debugging.

`sent.get('score', 0.0)` — safe dict access with default. If sentiment analysis fails
(no news found), score defaults to 0.0 (neutral) and analysis continues.

---

## `endpoints/scraping.py` — Server-Sent Events

```python
@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    async def event_gen():
        while True:
            job = db.query(ScrapingJob).filter(ScrapingJob.id == job_id).first()
            if not job:
                break
            yield f"data: {json.dumps(_job_to_dict(job))}\n\n"
            if job.pending == 0 and job.running == 0:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

**Server-Sent Events (SSE)** — the server keeps the HTTP connection open and pushes
updates to the client. The client (React `useSSE` hook) reads the stream.

`media_type="text/event-stream"` — tells the browser this is an SSE stream.

SSE frame format:
```
data: {"id": 5, "completed": 12, "pending": 8}\n\n
```

Each frame ends with `\n\n`. The client splits frames on `\n\n` and parses the `data:` line.

`await asyncio.sleep(1.0)` — yield control back to the event loop for 1 second between polls.
Without `await`, the loop would block the entire server. `async def` functions can `await`.

---

## Interview Questions

**Q: What is the difference between `def` and `async def` in FastAPI endpoints?**

`def` — FastAPI runs this in a **thread pool** so it doesn't block the event loop.
`async def` — FastAPI runs this in the **event loop** directly. You must `await` any I/O.

Use `async def` when using async libraries (`asyncio.sleep`, `aiofiles`, `asyncpg`).
Use `def` (synchronous) for endpoints using synchronous libraries (SQLAlchemy, yfinance, httpx sync).

**Q: What is the difference between `Path`, `Query`, and `Body` parameters?**

```python
@router.get("/stocks/{symbol}")          # Path: required, in URL
def get_stock(
    symbol: str,                          # ← Path param (matches {symbol})
    period: str = Query("1y"),            # ← Query param (?period=6m)
    payload: SomeModel = Body(...)        # ← Request body (JSON)
):
```

FastAPI infers the type automatically:
- Function param matches `{name}` in path → Path parameter
- Function param not in path + simple type → Query parameter
- Function param has Pydantic model type → Request body

**Q: What is `StreamingResponse` and when would you use it?**

`StreamingResponse` streams data to the client incrementally without buffering the
full response in memory. Use cases:
- Server-Sent Events (real-time updates)
- Large file downloads (CSV exports, video streaming)
- Progressive data loading

Without streaming, you'd have to wait for all data before sending anything.
