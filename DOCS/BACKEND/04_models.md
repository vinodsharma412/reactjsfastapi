# `backend/app/models/` — SQLAlchemy ORM Models

## What Are Models?

Models are **Python classes that map to database tables**.
Each class attribute using `Column(...)` becomes a column in the table.
SQLAlchemy uses these classes to:
- Generate `CREATE TABLE` SQL
- Build `SELECT`, `INSERT`, `UPDATE`, `DELETE` queries
- Map database rows ↔ Python objects

---

## `models/user.py` — The Users Table

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(100), unique=True, nullable=False, index=True)
    email           = Column(String(150), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(200), nullable=True)
    is_active       = Column(Boolean, default=True)
    is_admin        = Column(Boolean, default=False)
    role            = Column(String(50), nullable=False, default="viewer")
    avatar_url      = Column(String(255), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())
```

### Column-by-Column Explanation

| Column | Type | Constraint | Why |
|---|---|---|---|
| `id` | Integer | PK, indexed | Auto-increment surrogate key. `index=True` creates a B-tree index for fast PK lookups. |
| `username` | String(100) | unique, not null, indexed | Used for login — must be unique. `index=True` makes `WHERE username = ?` fast (O(log n) vs O(n)). |
| `email` | String(150) | unique, nullable | Users may not provide email. Still unique when provided. |
| `hashed_password` | String(255) | not null | bcrypt hashes are 60 chars; 255 gives room for future algorithms. Never store plain text. |
| `role` | String(50) | not null, default "viewer" | RBAC role: admin/manager/viewer. String instead of Enum for flexibility. |
| `is_active` | Boolean | default True | Soft-disable users without deleting their data. Deleted data is unrecoverable. |
| `created_at` | DateTime(timezone=True) | server_default | DB-generated timestamp. `timezone=True` stores UTC. |
| `updated_at` | DateTime(timezone=True) | onupdate | Auto-set by SQLAlchemy on any UPDATE. Null until first update. |

### `server_default=func.now()` vs `default=datetime.utcnow`

```python
# server_default — runs in the DATABASE
created_at = Column(DateTime, server_default=func.now())
# → INSERT INTO users (...) VALUES (...) -- PostgreSQL fills in NOW()

# Python default — runs in PYTHON
created_at = Column(DateTime, default=datetime.utcnow)
# → INSERT INTO users (..., created_at) VALUES (..., '2024-01-15 10:30:00')
```

`server_default` is more accurate — it's the DB server's clock, consistent across
multiple app servers (no timezone drift between pods in a cluster).

### `onupdate=func.now()`

SQLAlchemy automatically adds `updated_at = NOW()` to any `UPDATE` statement touching this row.
You never call `user.updated_at = datetime.utcnow()` manually.

---

## `models/stock.py` — Stock Transactions and Watchlist

```python
class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id               = Column(Integer, primary_key=True, index=True)
    symbol           = Column(String(30), nullable=False, index=True)
    company_name     = Column(String(200))
    transaction_type = Column(String(10), nullable=False)   # buy | sell | dividend
    quantity         = Column(Float, nullable=False)
    price            = Column(Float, nullable=False)
    total_amount     = Column(Float, nullable=False)
    brokerage        = Column(Float, default=0.0)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=False), server_default=func.now())
```

### Design Decisions

**`transaction_type` as String, not Enum:**

PostgreSQL has a native ENUM type. SQLAlchemy supports it via `Enum('buy','sell','dividend')`.
Using String is more flexible — you can add new types without an Alembic migration.
Validation happens in the Pydantic schema (`@field_validator`), not the DB.

**`total_amount` is stored even though it's derived:**

`total_amount = quantity × price ± brokerage`. We store it to avoid recomputation and to
preserve the exact amount at the time of the transaction (price might change).

**`Float` for financial values:**

In production, `Numeric(15, 4)` is recommended for money to avoid floating-point rounding.
For a personal portfolio tracker, `Float` is acceptable.

**`index=True` on `symbol`:**

The screener and portfolio queries filter/group by symbol heavily.
Without an index, `WHERE symbol = 'TCS.NS'` would scan all rows.

---

```python
class StockWatchlist(Base):
    __tablename__ = "stock_watchlist"

    id           = Column(Integer, primary_key=True, index=True)
    symbol       = Column(String(30), unique=True, nullable=False, index=True)
    company_name = Column(String(200))
    target_price = Column(Float, nullable=True)
    stop_loss    = Column(Float, nullable=True)
    notes        = Column(Text, nullable=True)
    added_at     = Column(DateTime(timezone=False), server_default=func.now())
```

**`unique=True` on `symbol`:**

A symbol can only appear once in the watchlist. The endpoint checks for duplicates
in Python too (`db.query(StockWatchlist).filter(symbol == sym).first()`), but the DB
constraint is the final safety net — it prevents race conditions where two requests
add the same symbol simultaneously.

---

## `models/scraping.py` — Job Queue Tables

```python
class ScrapingJob(Base):
    __tablename__ = "scraping_jobs"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    total      = Column(Integer, default=0)
    pending    = Column(Integer, default=0)
    running    = Column(Integer, default=0)
    completed  = Column(Integer, default=0)
    failed     = Column(Integer, default=0)

    user  = relationship("User")
    tasks = relationship("ScrapingTask", back_populates="job", cascade="all, delete-orphan")
```

### Three-Table Relationship

```
ScrapingJob (1) ──────────< ScrapingTask (many)
                                   │
                                   └──────────── ProductData (1)
                                                 (scraped result)
```

One **Job** = one batch request (e.g., user uploads 50 ASINs).
Each **Task** = one ASIN to scrape.
Each **ProductData** = the scraped result of one Task (0 or 1 per task).

### `ForeignKey("users.id")`

```python
user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
```

Creates a FK constraint in PostgreSQL: `user_id` must exist in `users.id`.
This prevents orphaned jobs (jobs with no owner user).

`"users.id"` — note it's the **table name** (lowercase), not the **class name** (`User`).

### `relationship()` — Object-Level Navigation

```python
user  = relationship("User")
tasks = relationship("ScrapingTask", back_populates="job", cascade="all, delete-orphan")
```

`relationship` lets you navigate between objects without writing SQL:
```python
job = db.query(ScrapingJob).filter(ScrapingJob.id == 1).first()
print(job.user.username)   # → SQLAlchemy runs SELECT on users table automatically
print(len(job.tasks))      # → SQLAlchemy runs SELECT on scraping_tasks
```

**`back_populates="job"`** creates a bidirectional relationship:
```python
task.job          # → the ScrapingJob object
job.tasks         # → list of ScrapingTask objects
```

**`cascade="all, delete-orphan"`** means:
When you `db.delete(job)` and `db.commit()`, all related `ScrapingTask` and `ProductData`
rows are automatically deleted too. Without cascade, you'd get a FK constraint violation.

### `uselist=False` on ProductData

```python
product = relationship("ProductData", back_populates="task", uselist=False)
```

By default, `relationship()` returns a list. `uselist=False` means it returns a single
object (or `None`). Correct here because each task produces exactly one product row.

```python
task.product        # → ProductData object (not a list)
task.product.title  # → "Samsung Galaxy S24"
```

---

## How `create_all` Creates These Tables

When `Base.metadata.create_all(bind=engine)` runs:

1. SQLAlchemy reads all registered classes (User, StockTransaction, etc.)
2. For each class, it generates a `CREATE TABLE IF NOT EXISTS` statement
3. It creates foreign key constraints and indexes
4. It sends all SQL to PostgreSQL in dependency order (referenced tables first)

Generated SQL for `users` table:
```sql
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL UNIQUE,
    email           VARCHAR(150) UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(200),
    is_active       BOOLEAN DEFAULT TRUE,
    is_admin        BOOLEAN DEFAULT FALSE,
    role            VARCHAR(50) NOT NULL DEFAULT 'viewer',
    avatar_url      VARCHAR(255),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
```

---

## Interview Questions

**Q: What is the difference between `nullable=True` and `nullable=False`?**

`nullable=False` → `NOT NULL` in SQL. PostgreSQL will reject any INSERT/UPDATE that
doesn't provide a value. `nullable=True` (default) → the column accepts NULL.

**Q: Why is `hashed_password` stored as String(255) not Text?**

bcrypt hashes are always exactly 60 characters. `String(255)` has a length limit which
PostgreSQL indexes more efficiently than `Text` (unlimited). Using 255 instead of 60
leaves room for longer hash algorithms in the future.

**Q: What is `index=True` doing at the database level?**

`index=True` creates a **B-tree index** — a balanced binary search tree. Without it,
`SELECT * FROM users WHERE username = 'vinod'` scans all rows (O(n)).
With the index, PostgreSQL finds the row in O(log n) — milliseconds on millions of rows.

**Q: What is a cascade delete and when would you NOT use it?**

Cascade delete automatically removes child records when the parent is deleted.
You would NOT use it for audit logs — you want to keep transaction history even if
a user deletes their account. In that case, use `SET NULL` on the FK instead.
