# `backend/app/db/` — Database Layer

## Files in This Layer

| File | Purpose |
|---|---|
| `db/base.py` | Creates the SQLAlchemy `Base` — the parent class all models inherit |
| `db/session.py` | Creates the database engine, session factory, and `get_db()` dependency |
| `alembic/env.py` | Alembic migration runner — knows which models and DB URL to use |

---

## `db/base.py`

```python
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

### What Is `declarative_base()`?

`declarative_base()` creates a **base class** that SQLAlchemy uses as a registry.
When you write `class User(Base)`, SQLAlchemy:
1. Reads the `__tablename__` attribute
2. Reads each `Column(...)` definition
3. Registers the mapping between Python class ↔ database table

`Base.metadata` is the object that holds all this table information.
When `create_all(bind=engine)` is called, it reads `Base.metadata` to know what
tables to create.

### Why Is It in Its Own File?

`Base` is imported by:
- `db/session.py` — to pass `Base.metadata` to Alembic and `create_all`
- Every model file — to inherit from

If `Base` was in `session.py`, importing `session.py` from a model file would create a
circular import (`session.py → model → session.py`). Keeping `Base` separate breaks the cycle.

---

## `db/session.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### `create_engine(settings.DATABASE_URL)`

Creates a **connection pool** to PostgreSQL. SQLAlchemy keeps a pool of open connections
(default: 5 connections). Each request borrows a connection, uses it, then returns it.

The `DATABASE_URL` format:
```
postgresql://user:password@host:port/dbname
```

### `sessionmaker` Parameters

```python
SessionLocal = sessionmaker(
    autocommit=False,   # You must call db.commit() explicitly
    autoflush=False,    # SQLAlchemy won't auto-flush before queries
    bind=engine,        # Use our PostgreSQL engine
)
```

**`autocommit=False`** — The most important setting.

In `autocommit=True` mode, every query is immediately committed. You can't roll back.
With `autocommit=False`, you work in a **transaction** until you call `db.commit()`.
If an error occurs before commit, you can call `db.rollback()` to undo all changes.

Example:
```python
# autocommit=False (this project's setting)
db.add(user)
db.add(role)
db.commit()   # Both user and role are saved atomically
              # If commit fails, neither is saved
```

**`autoflush=False`** — SQLAlchemy has a "pending queue" of changes not yet sent to DB.
With `autoflush=True`, it automatically sends these to the DB before every query
(within the same transaction). With `autoflush=False`, you control when this happens.
This prevents surprising implicit DB calls and speeds up batch operations.

### `get_db()` — The Dependency Generator

```python
def get_db():
    db = SessionLocal()   # Create a new session (borrow a connection from pool)
    try:
        yield db          # Hand it to the endpoint function
    finally:
        db.close()        # Always return connection to pool, even on exception
```

This is a **Python generator** used as a FastAPI dependency.

**How FastAPI uses it:**
```python
@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    # FastAPI calls next(get_db()) → gets db
    users = db.query(User).all()
    # FastAPI calls next(get_db()) again after endpoint finishes → hits finally
    return users
```

**Why `finally`?**

If the endpoint raises an `HTTPException` or any unhandled exception, Python still
executes the `finally` block. Without `finally`, an exception would leak the connection —
the pool would eventually run out of connections and the app would hang.

---

## Session vs Connection — What's the Difference?

| | Connection | Session |
|---|---|---|
| What | Raw TCP connection to PostgreSQL | Higher-level SQLAlchemy object |
| Manages | Network protocol | Transaction, identity map, unit-of-work |
| Lifetime | Lives in pool (reused across requests) | Created per request, closed after |
| Operations | Raw SQL | `db.query()`, `db.add()`, `db.commit()` |

The **Session** borrows a **Connection** from the pool during a transaction.
When you call `db.close()`, the Connection is returned to the pool (not closed).

---

## `alembic/env.py` — Database Migrations

```python
from app.config import settings
from app.db.base import Base
import app.models.user  # noqa — registers User with Base.metadata

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(...)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

### What Is Alembic?

Alembic is a **database migration tool** for SQLAlchemy. It tracks schema changes
(adding columns, renaming tables, etc.) as versioned Python scripts.

### Migration Workflow

```bash
# 1. Make a change to a model (e.g., add a new column)
# users.py: add  phone = Column(String(20), nullable=True)

# 2. Generate a migration script automatically
alembic revision --autogenerate -m "add phone to users"
# Creates: alembic/versions/abc123_add_phone_to_users.py

# 3. Apply the migration to the database
alembic upgrade head

# 4. Roll back if something is wrong
alembic downgrade -1
```

### Why `target_metadata = Base.metadata`?

Alembic compares `Base.metadata` (what your models say the schema should look like)
against the actual database schema. The difference becomes the migration.

### Why Import Models in `env.py`?

Same reason as in `main.py` — models must be imported so they register themselves with
`Base.metadata`. Without the import, `Base.metadata` is empty and Alembic would think
all tables need to be dropped.

---

## Understanding the ORM — How Python Objects Map to Database Rows

```python
# Python code               # What SQLAlchemy does
user = User(                # → Creates a Python object (not yet in DB)
    username="vinod",
    email="v@example.com",
)
db.add(user)               # → Adds to session's "pending" queue
db.flush()                 # → Sends INSERT to DB (within transaction, not committed)
db.commit()                # → Commits transaction — row is permanently saved
db.refresh(user)           # → Re-reads row from DB (to get server-generated id, created_at)

# Querying
users = db.query(User).filter(User.is_active == True).all()
# → SELECT * FROM users WHERE is_active = true

user = db.query(User).filter(User.id == 5).first()
# → SELECT * FROM users WHERE id = 5 LIMIT 1

# Updating
user.email = "new@example.com"
db.commit()
# → UPDATE users SET email = 'new@example.com' WHERE id = 5

# Deleting
db.delete(user)
db.commit()
# → DELETE FROM users WHERE id = 5
```

---

## Connection Pooling Explained

```
FastAPI Requests:   Req1  Req2  Req3  Req4  Req5  Req6
                     │     │     │     │     │     │
                     ▼     ▼     ▼     ▼     ▼     │
Pool (5 conns): [conn1][conn2][conn3][conn4][conn5] │
                                                     │
                Req6 waits until one is returned ◄───┘
```

SQLAlchemy's default pool size is 5. When all connections are in use, new requests
wait (up to `pool_timeout` seconds, default 30s) for one to be returned.

For high-traffic apps, increase pool size:
```python
engine = create_engine(settings.DATABASE_URL, pool_size=20, max_overflow=10)
```

---

## Interview Questions

**Q: What is the difference between `db.flush()` and `db.commit()`?**

`flush()` sends pending SQL statements to the DB server within the current transaction.
Other connections cannot see the changes yet. Good for getting auto-generated IDs before commit.

`commit()` makes the transaction permanent — visible to all connections. After commit,
there's no rollback possible.

**Q: What is the SQLAlchemy identity map?**

The Session maintains an **identity map** — a dictionary of `{(ModelClass, primary_key): object}`.
If you query the same user twice in one request, you get the same Python object (not two copies).
This prevents stale data inconsistencies within a single request.

**Q: Why not use `async` SQLAlchemy?**

AsyncSQLAlchemy exists (`asyncpg` driver) but requires all ORM operations to be awaited.
This project chose synchronous SQLAlchemy because:
1. Most endpoints are not I/O-bound on the DB — they're CPU-bound (calculations)
2. Simpler code — no `async`/`await` throughout CRUD functions
3. yfinance is synchronous — the bottleneck is external API calls, not DB
