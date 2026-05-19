# `backend/app/schemas/` — Pydantic Schemas (Request/Response Models)

## What Are Schemas?

Schemas are **Pydantic models that define the shape and validation rules for data
entering or leaving the API**. They are different from SQLAlchemy models:

| | SQLAlchemy Model (models/) | Pydantic Schema (schemas/) |
|---|---|---|
| Purpose | Maps Python ↔ Database | Validates HTTP request/response |
| Lives in | `models/` | `schemas/` |
| Inherits from | `Base` (SQLAlchemy) | `BaseModel` (Pydantic) |
| Does DB queries | Yes | No |
| Validates data | No | Yes (type, length, custom) |
| Used in | `crud/`, `services/` | Endpoint function signatures |

---

## `schemas/auth.py`

```python
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type:   str

class TokenData(BaseModel):
    username: Optional[str] = None
```

### `Token` — What the Login Endpoint Returns

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

FastAPI uses `response_model=Token` on the login endpoint. This tells FastAPI:
- Serialize the response using these fields only
- Validate the return value matches this shape
- Generate accurate OpenAPI docs

`token_type: "bearer"` is the OAuth2 standard — tells clients how to send the token.

### `TokenData` — What's Decoded From the JWT

```python
payload = decode_token(token)   # Returns dict {"sub": "vinod", "exp": 1234567890}
username = payload.get("sub")   # "sub" is the JWT standard claim for subject
```

`TokenData` is a clean container for the decoded payload. `sub` (subject) holds the username.

---

## `schemas/user.py`

```python
class UserBase(BaseModel):
    username:  str
    email:     Optional[str] = None
    full_name: Optional[str] = None
    role:      str = "viewer"

class UserCreate(UserBase):
    password: str             # Plain text — hashed in CRUD before storing

class UserUpdate(BaseModel):
    email:     Optional[str]  = None
    full_name: Optional[str]  = None
    role:      Optional[str]  = None
    is_active: Optional[bool] = None
    password:  Optional[str]  = None   # Only set if changing password

class UserResponse(UserBase):
    id:         int
    is_active:  bool
    is_admin:   bool
    role:       str
    avatar_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
```

### Pattern: Base → Create → Update → Response

This is the standard Pydantic schema hierarchy:

```
UserBase          ← Shared fields (username, email, full_name, role)
  ├── UserCreate  ← Adds `password` (only needed at creation)
  ├── UserUpdate  ← All Optional (PATCH semantics — update only what's provided)
  └── UserResponse ← Adds DB-generated fields (id, is_active, created_at)
```

**Why separate Create and Update?**

`UserCreate` requires `password`. `UserUpdate` makes it Optional — you don't need to
re-send the password just to update an email address.

**Why `UserUpdate` doesn't extend `UserBase`?**

All fields in `UserUpdate` are `Optional` (PATCH, not PUT). If `UserUpdate` extended
`UserBase`, it would inherit `username: str` (required, not optional). You'd have to
re-send username every time. Using a flat class with all-Optional fields is cleaner.

### `from_attributes = True`

```python
class Config:
    from_attributes = True   # Previously called orm_mode = True in Pydantic v1
```

Pydantic normally reads data from a **dict**. With `from_attributes = True`,
it can read from any object's **attributes** (including SQLAlchemy ORM instances):

```python
# Without from_attributes: works with dict
UserResponse(**{"id": 1, "username": "vinod", ...})

# With from_attributes: works with ORM object
user_orm = db.query(User).first()   # SQLAlchemy User object
UserResponse.model_validate(user_orm)  # ✅ Reads id, username, etc. via getattr()
```

FastAPI automatically validates the return value with `response_model`:
```python
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user   # SQLAlchemy User object — Pydantic converts it
```

---

## `schemas/stock.py`

### `TransactionIn` — Request Body for Adding a Trade

```python
class TransactionIn(BaseModel):
    symbol:           str
    company_name:     Optional[str] = None
    transaction_type: str           # buy | sell | dividend
    quantity:         float
    price:            float
    brokerage:        float = 0.0
    notes:            Optional[str] = None

    @field_validator('transaction_type')
    @classmethod
    def validate_type(cls, v):
        if v not in ('buy', 'sell', 'dividend'):
            raise ValueError("transaction_type must be buy, sell, or dividend")
        return v
```

### `@field_validator` — Custom Validation

`@field_validator('transaction_type')` runs **after** Pydantic's type check.
If `transaction_type` is not one of the allowed values, FastAPI returns:

```json
HTTP 422 Unprocessable Entity
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "transaction_type"],
      "msg": "Value error, transaction_type must be buy, sell, or dividend"
    }
  ]
}
```

`@classmethod` is required in Pydantic v2 — validators are class methods, not instance methods.

### `TransactionOut` — Response Body

```python
class TransactionOut(TransactionIn):
    id:           int        # DB-generated
    total_amount: float      # Computed in endpoint
    created_at:   Optional[datetime] = None  # DB-generated

    class Config: from_attributes = True
```

`TransactionOut` extends `TransactionIn` (inherits all request fields) and adds
DB-generated fields that only exist after the record is saved.

---

### `TechnicalIndicators` — Nested Schema

```python
class TechnicalIndicators(BaseModel):
    rsi:             Optional[float] = None
    sma_50:          Optional[float] = None
    sma_200:         Optional[float] = None
    macd:            Optional[float] = None
    macd_signal:     Optional[float] = None
    bb_upper:        Optional[float] = None
    bb_lower:        Optional[float] = None
    price_vs_sma50:  Optional[str]   = None   # "above" | "below"
    price_vs_sma200: Optional[str]   = None
    week_52_high:    Optional[float] = None
    week_52_low:     Optional[float] = None
    week_52_pct:     Optional[float] = None   # % from 52-week high
```

All fields `Optional` because yfinance may not have data for every symbol.
Nested inside `StockAnalysis`:

```python
class StockAnalysis(BaseModel):
    symbol:         str
    current_price:  Optional[float] = None
    pe_ratio:       Optional[float] = None
    technicals:     Optional[TechnicalIndicators] = None   # ← nested
    recommendation: Optional[Recommendation] = None        # ← nested
```

FastAPI serialises this to:
```json
{
  "symbol": "TCS.NS",
  "current_price": 3450.5,
  "technicals": {
    "rsi": 58.3,
    "sma_50": 3280.0,
    "price_vs_sma50": "above"
  }
}
```

---

### `PortfolioSummary` — Complex Aggregated Response

```python
class PortfolioSummary(BaseModel):
    total_invested: float
    current_value:  float
    total_pnl:      float
    pnl_pct:        float
    holdings:       List[dict] = []         # list of per-stock summaries
    transactions:   List[TransactionOut] = [] # full list of trade history
```

`holdings` uses `List[dict]` instead of a typed schema because the portfolio calculation
produces variable-shape dicts (different stocks have different available data).
`List[TransactionOut]` is fully typed — each element is validated by Pydantic.

---

## How Pydantic Validation Works at Runtime

```python
# Request body arrives as JSON string
# FastAPI parses it and passes to Pydantic
payload = {
    "symbol": "TCS",
    "transaction_type": "BUY",   # wrong case
    "quantity": "50",             # string, not int
    "price": 3450.50,
}

# Pydantic processes:
# 1. symbol: str → "TCS" ✅
# 2. transaction_type: str → "BUY" → @field_validator → ❌ ValueError
# 3. quantity: float → "50" → Pydantic coerces "50" → 50.0 ✅
# 4. price: float → 3450.50 ✅

# FastAPI returns:
# HTTP 422 Unprocessable Entity
# {"detail": [{"loc": ["body", "transaction_type"], "msg": "..."}]}
```

---

## Interview Questions

**Q: What is the difference between Pydantic v1 `orm_mode = True` and Pydantic v2 `from_attributes = True`?**

They are the same feature, renamed in Pydantic v2. Both allow Pydantic to construct
a model from an ORM object by reading attributes instead of requiring a dict.

**Q: What HTTP status code does FastAPI return for validation errors?**

`422 Unprocessable Entity` — defined by RFC 9110. FastAPI automatically returns this
with a detailed list of which fields failed and why, from Pydantic's validation errors.

**Q: Why use `Optional[float] = None` instead of just `float` for stock fields?**

yfinance data is incomplete — some stocks don't have `pe_ratio`, `dividend_yield`, etc.
If you declare `pe_ratio: float` (required), any stock missing this data would cause
a Pydantic validation error. `Optional[float] = None` means "this field might not exist."

**Q: How does Pydantic handle extra fields in the request body?**

By default in v2, extra fields are **ignored**. If a client sends `{"symbol": "TCS", "hacker_field": "value"}`,
Pydantic silently drops `hacker_field`. You can change this with `model_config = ConfigDict(extra='forbid')`
to reject requests with unknown fields (stricter API).
