# `backend/app/config.py` — Application Settings

## What Is This File?

`config.py` is the **single source of truth for all configuration values**.
It reads from environment variables and the `.env` file using **Pydantic BaseSettings**.
Every other file imports `settings` from here — nothing reads `os.environ` directly.

---

## Full Code With Line-by-Line Explanation

```python
from pydantic_settings import BaseSettings
from urllib.parse import quote_plus

class Settings(BaseSettings):
    APP_NAME: str = "MyApp"
    APP_ENV: str = "development"
    DEBUG: bool = True

    SECRET_KEY: str                          # NO default = REQUIRED — app fails at startup if missing
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours (60 min × 24)

    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    GMAIL_USER:         str = ""
    GMAIL_APP_PASSWORD: str = ""

    OLLAMA_URL:   str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"

    @property
    def DATABASE_URL(self) -> str:
        password = quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Concept: Pydantic BaseSettings

### What It Is
`BaseSettings` is a special Pydantic class that reads values from:
1. Environment variables (highest priority)
2. `.env` file (fallback)
3. Default values in the class (lowest priority)

### How It Works — Reading Priority
```
1. os.environ["DB_HOST"] = "prod-server"      # wins if set
2. .env file:  DB_HOST=localhost               # used if env var not set
3. DB_HOST: str = "localhost"                  # used if neither above is set
```

### Why Use This Instead of `os.environ.get()`?
```python
# Without BaseSettings (fragile)
DB_PORT = int(os.environ.get("DB_PORT", "5432"))  # manual type conversion, error-prone

# With BaseSettings (safe)
DB_PORT: int = 5432  # Pydantic auto-converts str "5432" → int 5432, raises error on "abc"
```

---

## Each Setting Explained

### `SECRET_KEY: str`
**No default** — the app crashes at startup with `ValidationError` if this is missing.
This is intentional: a missing secret key means JWTs cannot be signed, which is a
security-critical failure that must be caught immediately.

Used in `core/security.py` to sign and verify JWT tokens.

**How to generate a strong secret key:**
```bash
openssl rand -hex 32
# output: a8f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1
```

### `ALGORITHM: str = "HS256"`
`HS256` = HMAC with SHA-256. A **symmetric** algorithm — the same `SECRET_KEY` is used
to both sign tokens (when logging in) and verify them (on every request).

Alternative: `RS256` (RSA-SHA256) is asymmetric — a private key signs, a public key verifies.
Better for microservices where multiple services verify tokens but only one signs them.

### `ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440`
1440 = 24 × 60. Tokens expire after 24 hours. After expiry, the user must log in again.
Changed from the default 30 minutes to improve user experience.

### `DB_PORT: int = 5432`
Pydantic automatically casts the string `"5432"` from the `.env` file to Python `int`.
If `.env` has `DB_PORT=abc`, Pydantic raises `ValidationError` at startup — fail fast.

### `GMAIL_USER: str = ""`
Optional. If empty string, the Gmail feature is disabled (checked in `gmail_service.py`).
Using empty string as the "disabled" sentinel avoids `Optional[str] = None` handling.

---

## The `DATABASE_URL` Property

```python
@property
def DATABASE_URL(self) -> str:
    password = quote_plus(self.DB_PASSWORD)
    return f"postgresql://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
```

### Why `quote_plus`?
SQLAlchemy's connection URL has the format:
```
postgresql://user:password@host:port/dbname
```

If the password contains special characters like `@`, `#`, `%`, `/`, they break URL parsing.
`quote_plus` encodes them: `p@ss#word` → `p%40ss%23word`.

Example:
```python
DB_PASSWORD = "my@secure#pass"
quote_plus("my@secure#pass")  # → "my%40secure%23pass"
# Final URL: postgresql://admin:my%40secure%23pass@localhost:5432/mydb
```

### Why `@property` and not just a field?
A `@property` is computed from other fields — it's derived, not stored. You can't set it
directly. It also means Pydantic won't try to read `DATABASE_URL` from the `.env` file.

---

## The `.env` File (Not Committed to Git)

```ini
# backend/.env
SECRET_KEY=your-32-char-random-secret-here
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myappdb
DB_USER=postgres
DB_PASSWORD=mypassword
DEBUG=True
APP_ENV=development
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=abcd-efgh-ijkl-mnop
```

The `.env` file should be in `.gitignore`. Never commit secrets.

---

## Module-Level Singleton

```python
settings = Settings()   # Created ONCE when Python imports this module
```

Python caches module imports — `Settings()` runs exactly once per process.
Every `from app.config import settings` gets the same object.

This is the **Singleton pattern** — one instance shared across the entire application.

---

## How to Override Settings in Tests

```python
# In a pytest test
import os
os.environ["DB_NAME"] = "test_db"
os.environ["SECRET_KEY"] = "test-secret"

from app.config import Settings
test_settings = Settings()   # reads the overridden env vars
```

Or use `pydantic_settings` features:
```python
settings = Settings(SECRET_KEY="test-key", DB_NAME="test_db")
```

---

## Interview Questions

**Q: What is the difference between `Optional[str] = None` and `str = ""`?**

`Optional[str] = None` means the value is truly absent — you must check `if value is not None`.
`str = ""` means the feature is disabled — you check `if value`. Both work; this project
uses `str = ""` for optional integrations (Gmail, Ollama) to avoid nullable type handling.

**Q: What happens if `SECRET_KEY` is missing?**

`pydantic_settings.BaseSettings` raises `pydantic.ValidationError` during `settings = Settings()`,
which runs at **import time**. The application fails to start — the process exits before
uvicorn can accept any requests. This is the correct "fail fast" behaviour.

**Q: Can you use multiple `.env` files?**

Yes: `class Config: env_file = ".env", ".env.local"` — Pydantic reads all listed files,
later files taking lower priority. Common pattern: `.env` for shared defaults, `.env.local`
for machine-specific overrides (both in `.gitignore`).
