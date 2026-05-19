# `backend/app/crud/` — Repository / CRUD Layer

## What Is CRUD?

CRUD stands for **Create, Read, Update, Delete** — the four fundamental database operations.
The `crud/` layer is a **Repository pattern**: it centralises all database access logic,
keeping endpoints thin and data access reusable.

```
HTTP Request → Endpoint → CRUD → SQLAlchemy → PostgreSQL
```

Endpoints call CRUD functions. CRUD functions call SQLAlchemy. SQLAlchemy talks to PostgreSQL.
**Endpoints never write raw SQL. CRUD functions never know about HTTP.**

---

## `crud/base.py` — Generic Base Class

```python
from sqlalchemy.orm import Session
from typing import TypeVar, Generic, Type

ModelType = TypeVar("ModelType")


class CRUDBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: int):
        return db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, db: Session, skip: int = 0, limit: int = 100):
        return db.query(self.model).offset(skip).limit(limit).all()

    def delete(self, db: Session, id: int):
        obj = self.get(db, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj
```

### Concept: Python Generics (`Generic[ModelType]`)

`TypeVar("ModelType")` creates a **type variable** — a placeholder for any type.
`Generic[ModelType]` makes `CRUDBase` a generic class — like Java's `List<T>` or C#'s `List<T>`.

```python
# CRUDBase without generics — no type safety
class CRUDBase:
    def get(self, db, id):
        return db.query(self.model).filter(self.model.id == id).first()
    # IDE doesn't know the return type — no autocomplete

# CRUDBase with generics — fully type-safe
class CRUDBase(Generic[ModelType]):
    def get(self, db: Session, id: int) -> Optional[ModelType]:
        ...
    # IDE knows: CRUDUser.get() returns Optional[User]
    # CRUDMenu.get() returns Optional[Menu]
```

### How `Generic` Works Here

```python
class CRUDUser(CRUDBase[User]):     # ModelType = User
    ...

crud_user = CRUDUser(User)          # self.model = User class

crud_user.get(db, 5)
# → db.query(User).filter(User.id == 5).first()
# → Returns: User object or None
```

When you write `CRUDBase[User]`, Python substitutes `ModelType` with `User` throughout.
The `get()` method effectively becomes `def get(self, db: Session, id: int) -> Optional[User]`.

### `get_all` with Pagination

```python
def get_all(self, db: Session, skip: int = 0, limit: int = 100):
    return db.query(self.model).offset(skip).limit(limit).all()
```

This generates:
```sql
SELECT * FROM users OFFSET 0 LIMIT 100;
```

`offset` = how many rows to skip (for page 2 with 10 per page: `offset=10`).
`limit` = max rows to return. Always use limit — never `SELECT * FROM users` on large tables.

---

## `crud/user.py` — User-Specific Operations

```python
from typing import Optional
from sqlalchemy.orm import Session
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password


class CRUDUser(CRUDBase[User]):

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def create(self, db: Session, user_in: UserCreate) -> User:
        user = User(
            username=user_in.username,
            email=user_in.email,
            full_name=user_in.full_name,
            role=user_in.role,
            hashed_password=hash_password(user_in.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def update(self, db: Session, user_id: int, user_in: UserUpdate) -> Optional[User]:
        user = self.get(db, user_id)
        if not user:
            return None
        update_data = user_in.dict(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = hash_password(update_data.pop("password"))
        for field, value in update_data.items():
            setattr(user, field, value)
        db.commit()
        db.refresh(user)
        return user


crud_user = CRUDUser(User)
```

### `get_by_username` — Used for Login

```python
user = crud_user.get_by_username(db, "vinod")
```

Generates:
```sql
SELECT * FROM users WHERE username = 'vinod' LIMIT 1;
```

The `index=True` on `username` column makes this O(log n) fast.
Used by `auth_service.login_user()` to look up the user during authentication.

### `create` — Password Hashing Pattern

```python
user = User(
    ...
    hashed_password=hash_password(user_in.password),  # ← hash BEFORE storing
)
```

`user_in.password` is the plain text from the request body.
`hash_password()` uses bcrypt with a random salt — two calls with the same password
produce different hashes.

**Critical**: The `User` ORM object never stores plain text password. The schema
field is named `password` (in Pydantic) but the model field is `hashed_password`
(in SQLAlchemy) — different names to make this explicit.

### `create` — `db.refresh()` Pattern

```python
db.add(user)
db.commit()
db.refresh(user)   # ← Re-reads the row from DB
return user
```

After `db.commit()`, the Python `user` object is "expired" — SQLAlchemy marks it as
stale. If you access `user.id` before `db.refresh()`, SQLAlchemy automatically runs
another SELECT (lazy load). `db.refresh()` explicitly reloads all attributes including
DB-generated ones (`id`, `created_at`).

Without `db.refresh()`, returning `user` from the endpoint would trigger lazy loading
AFTER the DB session is closed — raising `DetachedInstanceError`.

### `update` — Partial Update with `exclude_unset=True`

```python
update_data = user_in.dict(exclude_unset=True)
```

`exclude_unset=True` returns only fields that were **explicitly set** in the request,
not fields with default values. This enables PATCH semantics:

```python
# Request body: {"email": "new@example.com"}
# user_in.dict() → {"email": "new@example.com", "full_name": None, "role": "viewer", ...}
# user_in.dict(exclude_unset=True) → {"email": "new@example.com"}  ← Only what was sent
```

Without `exclude_unset=True`, updating email would overwrite `full_name` with `None`
even though the caller didn't intend to change it.

```python
for field, value in update_data.items():
    setattr(user, field, value)
```

`setattr(user, "email", "new@example.com")` is equivalent to `user.email = "new@example.com"`.
Using `setattr` lets us update any field dynamically without a chain of `if "email" in data: user.email = data["email"]`.

### Password Change in Update

```python
if "password" in update_data:
    update_data["hashed_password"] = hash_password(update_data.pop("password"))
```

If the update request includes `password`:
1. `pop("password")` removes the plain text from `update_data`
2. Hashes it and stores as `hashed_password`
3. The loop then calls `setattr(user, "hashed_password", hashed_value)`

This ensures plain text never accidentally gets set on the ORM object.

### Module-Level Instance

```python
crud_user = CRUDUser(User)
```

Created once at module import time. Stateless — it holds only `self.model = User`.
Every file imports this singleton: `from app.crud.user import crud_user`.

---

## How Endpoints Use CRUD

```python
# endpoints/users.py
@router.post("/", response_model=UserResponse)
def create_user(
    user_in: UserCreate,              # ← Pydantic validates request body
    db: Session = Depends(get_db),    # ← DB session injected
    _: User = Depends(require_roles(Role.ADMIN)),  # ← Auth check
):
    existing = crud_user.get_by_username(db, user_in.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    return crud_user.create(db, user_in)  # ← CRUD creates and returns User ORM object
    # FastAPI serialises via UserResponse.from_attributes = True
```

The endpoint:
1. Validates input (Pydantic)
2. Checks auth (Depends)
3. Delegates to CRUD (business logic + DB)
4. Returns ORM object (FastAPI serialises)

---

## Interview Questions

**Q: What is the Repository pattern and why use it?**

Repository pattern separates **data access logic** from **business logic**.
Benefits:
- **Testability**: mock the CRUD object in tests, no DB needed
- **Reusability**: multiple endpoints call the same CRUD function
- **Single responsibility**: endpoints handle HTTP, CRUD handles DB

**Q: What is `TypeVar` and `Generic` in Python?**

`TypeVar` creates a type placeholder. `Generic[T]` says "this class works with any type T."
When you write `CRUDBase[User]`, you specialise the generic — T becomes User.
This gives IDEs full type information: `CRUDUser.get()` → `Optional[User]`.

**Q: What is the difference between `db.add()` and `db.merge()`?**

`db.add()` — adds a **new** object to the session. Fails if the PK already exists.
`db.merge()` — upsert: if the object's PK exists in the session or DB, merge the state;
otherwise insert. Useful for syncing objects that may or may not exist.

**Q: What does `db.commit()` do if it fails?**

The transaction is rolled back automatically by SQLAlchemy. The DB is unchanged.
The Python exception propagates to the endpoint, which FastAPI converts to a 500 response.
If you want explicit rollback control: `try/except/db.rollback()`.
