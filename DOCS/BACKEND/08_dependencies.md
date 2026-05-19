# `backend/app/dependencies.py` — FastAPI Dependency Injection

## What Is This File?

`dependencies.py` contains **reusable dependency functions** that endpoints declare
as parameters. FastAPI's Dependency Injection (DI) system automatically resolves and
injects these dependencies before calling the endpoint function.

This file primarily implements **JWT authentication** — the mechanism that validates
every protected API request.

---

## Full Code With Explanation

```python
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_token
from app.core.exceptions import credentials_exception
from app.crud.user import crud_user
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = crud_user.get_by_username(db, username)
    if not user:
        raise credentials_exception
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_active:
        raise credentials_exception
    return current_user
```

---

## `OAuth2PasswordBearer` — Token Extraction

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
```

`OAuth2PasswordBearer` is a **FastAPI security utility** that:
1. Reads the `Authorization` header from every request
2. Expects the format: `Authorization: Bearer <token>`
3. Extracts and returns the token string
4. If the header is missing, automatically returns `HTTP 401`

```
Client Request Header:
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

oauth2_scheme extracts:
"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

`tokenUrl="/api/v1/auth/token"` is used only for **OpenAPI docs** (Swagger UI) — it
tells the "Authorize" button in Swagger where to get a token. It doesn't affect runtime behaviour.

---

## `get_current_user` — JWT Validation Dependency

```python
def get_current_user(
    token: str = Depends(oauth2_scheme),   # ← JWT string from Authorization header
    db: Session = Depends(get_db)          # ← PostgreSQL session
) -> User:
    try:
        payload = decode_token(token)      # ← Verify signature + expiry
        username: str = payload.get("sub") # ← Extract username from payload
        if not username:
            raise credentials_exception    # ← Malformed token (no "sub" claim)
    except JWTError:
        raise credentials_exception        # ← Invalid signature or expired
    user = crud_user.get_by_username(db, username)  # ← Look up in DB
    if not user:
        raise credentials_exception        # ← Username in token no longer exists
    return user
```

### Step-by-Step Flow

```
1. Client sends: GET /api/v1/stocks/analyse/TCS.NS
   Header: Authorization: Bearer <JWT>

2. oauth2_scheme extracts JWT string

3. decode_token(JWT):
   - Verifies HMAC signature with SECRET_KEY
   - Checks "exp" claim — raises JWTError if expired
   - Returns payload: {"sub": "vinod", "exp": 1234567890}

4. payload.get("sub") → "vinod"

5. crud_user.get_by_username(db, "vinod")
   → SELECT * FROM users WHERE username = 'vinod'
   → Returns User ORM object

6. Returns User object to the calling endpoint
```

### Why Three Separate Failure Points?

```python
# Failure 1: JWTError — token expired or tampered with
except JWTError:
    raise credentials_exception

# Failure 2: Malformed token — "sub" claim missing
if not username:
    raise credentials_exception

# Failure 3: User deleted after token was issued
if not user:
    raise credentials_exception
```

All three raise the same `credentials_exception` (HTTP 401). This is intentional —
**security through vagueness**: don't tell an attacker whether the token signature is
wrong or the user doesn't exist. Give the same generic error for all auth failures.

---

## `get_current_active_user` — Second-Level Dependency

```python
def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_active:
        raise credentials_exception
    return current_user
```

This **chains** onto `get_current_user`. FastAPI resolves the full dependency graph:

```
get_current_active_user
    └── get_current_user
            ├── oauth2_scheme → reads Authorization header
            └── get_db → creates DB session
```

**Why separate from `get_current_user`?**

Separation of concerns:
- `get_current_user` = "Is the token valid and does the user exist?"
- `get_current_active_user` = "Is the user allowed to use the system?"

Some internal/admin endpoints might allow inactive users (e.g., an admin tool that reactivates
accounts). They'd use `Depends(get_current_user)`. All regular user endpoints use
`Depends(get_current_active_user)`.

---

## Dependency Injection Graph

FastAPI builds a **dependency graph** (DAG — Directed Acyclic Graph) and resolves it
bottom-up before calling the endpoint:

```
Endpoint: def analyse(symbol: str, _: User = Depends(get_current_active_user))
                                                         │
                           ┌─────────────────────────────┘
                           ▼
              get_current_active_user(current_user = Depends(get_current_user))
                                                         │
                           ┌─────────────────────────────┘
                           ▼
              get_current_user(token = Depends(oauth2_scheme),
                                db    = Depends(get_db))
                                │                │
                                ▼                ▼
                      read Authorization    create DB session
                      header → JWT string   SessionLocal()
```

FastAPI resolves the graph once per request. If multiple endpoints on the same request
use `Depends(get_db)`, FastAPI calls `get_db()` **only once** and reuses the session
(dependency caching within a request).

---

## Usage Pattern in Endpoints

### Pattern 1: Auth but don't need the user object
```python
@router.get("/stocks/screener")
def screener(
    _: User = Depends(get_current_active_user),  # enforces auth, _ means unused
):
    return stock_service.screen_stocks()
```

The `_` convention signals to readers: "auth is required here, but we don't use
the user object itself."

### Pattern 2: Auth and use the user
```python
@router.get("/users/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_active_user),
):
    return current_user   # return the authenticated user's data
```

### Pattern 3: Role-restricted endpoint
```python
@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN)),  # only admins
):
    ...
```

`require_roles(Role.ADMIN)` is a factory that returns a dependency function that
itself depends on `get_current_active_user`. Role check runs after auth check.

---

## How FastAPI Dependency Caching Works

Within a single request, if the same dependency is declared multiple times, FastAPI
calls it **only once** and caches the result:

```python
@router.post("/portfolio/transactions")
def add_transaction(
    payload: TransactionIn,
    db: Session = Depends(get_db),           # get_db called once
    _: User = Depends(get_current_active_user),  # get_db also needed here
):
    ...
```

FastAPI sees `get_db` is needed by both the endpoint and `get_current_active_user`.
It calls `get_db()` once and passes the same session to both. This prevents double
connection borrow from the pool within one request.

---

## Interview Questions

**Q: What is Dependency Injection?**

DI is a design pattern where dependencies (objects a function needs) are provided
externally rather than created inside the function. Benefits:
- **Testability** — inject a mock DB session in tests
- **Decoupling** — function doesn't know how the DB session is created
- **Reusability** — same auth logic reused across dozens of endpoints

FastAPI's DI uses Python's `Depends()` — it inspects function signatures and
resolves all `Depends(...)` parameters automatically.

**Q: What happens if a client sends a valid JWT that's not yet expired, but the user was deleted from the DB?**

Step 5 in `get_current_user`: `crud_user.get_by_username(db, username)` returns `None`.
The dependency raises `credentials_exception` (HTTP 401). The token is valid cryptographically
but the referenced user no longer exists — access is denied. This is a key advantage of
**database-backed user lookup** on every request vs. trusting the token entirely.

**Q: How would you implement token refresh?**

Add a `refresh_token` field alongside `access_token` in the login response.
Set `refresh_token` expiry to 7 days, `access_token` to 1 hour.
Create a `POST /auth/refresh` endpoint that accepts a valid refresh token and
issues a new access token. The frontend calls `/auth/refresh` when it receives a 401.
This project uses a simple single-token approach (24h expiry).
