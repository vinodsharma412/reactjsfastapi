# `backend/app/core/` — Security, RBAC, Exceptions, Logging

## Files in This Layer

| File | Purpose |
|---|---|
| `security.py` | bcrypt password hashing + JWT token creation/decoding |
| `roles.py` | Role enum + `require_roles()` dependency factory |
| `exceptions.py` | Pre-built `HTTPException` instances |
| `logging.py` | Centralised logger factory |

---

## `core/security.py` — Passwords and JWT

```python
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
```

---

### bcrypt — How Password Hashing Works

`CryptContext(schemes=["bcrypt"])` creates a hashing context using the **bcrypt** algorithm.

**Why bcrypt and not MD5/SHA256?**

| Algorithm | Speed | Salt | Designed For |
|---|---|---|---|
| MD5 / SHA256 | Extremely fast | No | Data integrity (checksums) |
| bcrypt | Intentionally slow | Yes (auto) | Password storage |

bcrypt is **deliberately slow** (configurable work factor). Hashing one password takes
~100-200ms on purpose. This makes brute-force attacks impractical:
- SHA256: attacker can try 10 billion passwords/second
- bcrypt: attacker can try ~50 passwords/second

**What the hash looks like:**
```
$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/n0IUXgGiO
 ↑   ↑  ↑
 |   |  └── salt (22 chars) + hash (31 chars)
 |   └── cost factor (2^12 = 4096 iterations)
 └── bcrypt version
```

Every `hash_password()` call generates a **different salt** → different hash even for
the same password. This prevents rainbow table attacks.

**`deprecated="auto"`** means if you later add a newer algorithm (e.g., Argon2), bcrypt
hashes are automatically flagged as deprecated on next login — you can rehash them transparently.

**`verify_password`:**
```python
verify_password("mypassword", "$2b$12$...")
```
bcrypt extracts the salt from the stored hash, re-hashes the input with that salt, and
compares. **Never compare hashes directly** — always use `pwd_context.verify()`.

---

### JWT — How Token Auth Works

**Step 1 — Login (create token):**
```python
token = create_access_token({"sub": "vinod"})
```

Internally:
```python
payload = {
    "sub": "vinod",                          # "sub" = subject (standard JWT claim)
    "exp": datetime(2024,1,15,10,30,0),      # expiry timestamp
}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
# → "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ2aW5vZCJ9.abc123"
```

A JWT has 3 parts separated by `.`:
```
header.payload.signature
  ↑       ↑        ↑
base64  base64   HMAC-SHA256(header + "." + payload, SECRET_KEY)
```

The payload is base64-encoded, **not encrypted** — anyone can decode it.
The signature guarantees nobody tampered with the payload.

**Step 2 — Every request (decode token):**
```python
payload = decode_token(token)
# python-jose: 1) verifies signature, 2) checks exp, 3) returns payload dict
username = payload["sub"]   # "vinod"
```

If the token is expired or signature is wrong, `decode_token()` raises `JWTError`.

**HS256 vs RS256:**

| | HS256 (this project) | RS256 |
|---|---|---|
| Algorithm | HMAC-SHA256 | RSA-SHA256 |
| Key type | Symmetric (same key signs + verifies) | Asymmetric (private signs, public verifies) |
| Best for | Single service | Microservices |
| Key sharing | Keep secret, share with no one | Public key can be shared safely |

---

## `core/roles.py` — Role-Based Access Control (RBAC)

```python
from enum import Enum
from fastapi import Depends, HTTPException, status
from app.models.user import User


class Role(str, Enum):
    ADMIN   = "admin"
    MANAGER = "manager"
    VIEWER  = "viewer"


def require_roles(*roles: Role):
    """Returns a FastAPI dependency that allows only the specified roles."""
    from app.dependencies import get_current_active_user

    def checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {[r.value for r in roles]}",
            )
        return current_user

    return checker
```

### `Role(str, Enum)` — String Enum

`str, Enum` dual inheritance makes `Role.ADMIN` equal to `"admin"` (the string).
```python
Role.ADMIN == "admin"   # True
Role.ADMIN.value        # "admin"
str(Role.ADMIN)         # "Role.ADMIN" (use .value for plain string)
```

This allows comparison: `user.role not in [r.value for r in roles]`
translates to: `user.role not in ["admin", "manager"]`.

### `require_roles()` — Dependency Factory Pattern

`require_roles()` is a **function that returns a function**. This is the
**Factory pattern** and **Higher-Order Function** concept.

```python
# Usage in endpoint
@router.get("/users")
def list_users(
    _: User = Depends(require_roles(Role.ADMIN, Role.MANAGER))
):
    ...
```

What happens:
1. `require_roles(Role.ADMIN, Role.MANAGER)` is called at **import time** when the
   route is registered. It captures `roles = (Role.ADMIN, Role.MANAGER)` in a closure.
2. It returns the `checker` function.
3. FastAPI calls `checker(current_user=...)` on **every request**.

The `_: User` means the dependency is required (auth enforced) but the user object
isn't used in this endpoint.

### Why Import `get_current_active_user` Inside the Function?

```python
def require_roles(*roles: Role):
    from app.dependencies import get_current_active_user   # ← import INSIDE
    def checker(...):
        ...
```

This is a **lazy import** to break a circular dependency:
- `dependencies.py` imports from `core/roles.py` (for RBAC)
- `core/roles.py` would import from `dependencies.py` (for `get_current_active_user`)
- Circular → ImportError

Importing inside the function means `dependencies.py` is only loaded when `checker()`
is first called, not at module load time — breaking the cycle.

---

## `core/exceptions.py` — Pre-Built HTTP Exceptions

```python
from fastapi import HTTPException, status

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

invalid_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect username or password",
    headers={"WWW-Authenticate": "Bearer"},
)

inactive_user_exception = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Inactive user",
)

not_found_exception = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found",
)
```

### Why Pre-Build Exception Instances?

Without this pattern:
```python
# In dependencies.py
raise HTTPException(status_code=401, detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"})

# In auth_service.py
raise HTTPException(status_code=401, detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"})
```

Repeated code. If you want to change the message, you find and update every occurrence.

With this pattern:
```python
raise credentials_exception   # 3 words, consistent everywhere
```

### `headers={"WWW-Authenticate": "Bearer"}`

This header is required by the **OAuth2/RFC 6750 standard** for 401 responses.
It tells the client "to access this resource, send a Bearer token."
Browsers and API clients use this header to determine the auth scheme.

### HTTP Status Codes Used

| Exception | Status | Meaning |
|---|---|---|
| `credentials_exception` | 401 | Token missing, invalid, or expired |
| `invalid_credentials_exception` | 401 | Wrong username/password at login |
| `inactive_user_exception` | 400 | User exists but `is_active=False` |
| `not_found_exception` | 404 | Resource doesn't exist |

---

## `core/logging.py` — Logger Factory

```python
import logging
import sys
from app.config import settings


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    return logger
```

### How Python Logging Works

```
Logger("app.services.stock_service")
    ↓
Handler (StreamHandler → stdout)
    ↓
Formatter ("2024-01-15 10:30:00 | INFO | app.services.stock_service | ...")
```

`logging.getLogger(name)` — Python's logging module maintains a **global registry** of loggers by name.
`getLogger("myapp.stocks")` and `getLogger("myapp.stocks")` return the **same object**.
The hierarchy is `.`-separated: `myapp.stocks` inherits from `myapp` inherits from root.

### Why `if not logger.handlers`?

`getLogger()` returns the same logger object every time. If you add a handler each time
`get_logger()` is called (e.g., once per module), you'd get duplicate log entries:
```
2024-01-15 INFO | Got TCS.NS data
2024-01-15 INFO | Got TCS.NS data   ← duplicate
2024-01-15 INFO | Got TCS.NS data   ← triplicate
```

`if not logger.handlers` ensures handlers are only added once.

### Log Format

```
2024-01-15 10:30:45,123 | INFO | app.services.stock_service | Rate-limited for TCS.NS — sleeping 3s
↑                          ↑     ↑                             ↑
timestamp                level  logger name                   message
```

Named loggers tell you exactly which file/module produced the log — essential for debugging.

### Usage in Services

```python
# In stock_service.py
logger = logging.getLogger(__name__)
# __name__ = "app.services.stock_service"

logger.info("Fetched data for %s", symbol)
logger.warning("Rate-limited for %s — sleeping %.0fs", symbol, delay)
logger.error("yf_info failed for %s: %s", symbol, exc)
```

Using `%s` formatting (not f-strings) in log calls is a Python best practice — the
string is only formatted if the log level is enabled, saving CPU.

---

## Interview Questions

**Q: What is the difference between 401 and 403?**

401 = **Unauthenticated** — "I don't know who you are. Please log in."
403 = **Unauthorised** — "I know who you are, but you don't have permission."

In this project:
- Invalid/missing token → 401 (`credentials_exception`)
- Valid token but wrong role → 403 (`require_roles` checker)

**Q: Why does bcrypt hash the same password differently each time?**

bcrypt generates a random 16-byte **salt** for each hash. The salt is embedded in the
hash string alongside the computed hash. `verify_password` extracts this salt from the
stored hash to re-hash the input consistently. Different salts = different hashes for
the same input — making precomputed rainbow tables useless.

**Q: Can you decode a JWT without the secret key?**

Yes — the payload is base64-encoded, not encrypted. Anyone can decode:
`base64.decode("eyJzdWIiOiJ2aW5vZCJ9") → {"sub": "vinod"}`.
But they cannot **forge** a token — creating a valid signature requires `SECRET_KEY`.
Never put sensitive data in JWT payloads.
