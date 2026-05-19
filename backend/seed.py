#!/usr/bin/env python3
"""
Database seed script.

Run from the backend/ directory with the venv active:
    cd backend
    source venv/bin/activate        # Linux / macOS
    venv\\Scripts\\activate           # Windows
    python seed.py

The script is idempotent — safe to run more than once.
Existing rows are updated in place; nothing is deleted.
"""
import sys
import os

# Ensure app package is on the path when run as a plain script
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.models.user import User          # noqa: F401  — needed for Base.metadata
from app.models.menu import Menu, MenuAccess
from app.core.security import hash_password


# ── helpers ───────────────────────────────────────────────────────────────────

def _upsert_user(db, *, username, password, full_name, email, role, is_admin=False):
    obj = db.query(User).filter(User.username == username).first()
    if obj:
        # update mutable fields only
        obj.full_name       = full_name
        obj.email           = email
        obj.role            = role
        obj.is_admin        = is_admin
        obj.is_active       = True
        db.commit()
        print(f"   ~ updated  user      '{username}'")
        return
    db.add(User(
        username=username,
        hashed_password=hash_password(password),
        full_name=full_name,
        email=email,
        role=role,
        is_admin=is_admin,
        is_active=True,
    ))
    db.commit()
    print(f"   + inserted user      '{username}'  (role: {role})")


def _upsert_menu(db, *, name, path, icon, sort_order, is_active=True):
    obj = db.query(Menu).filter(Menu.path == path).first()
    if obj:
        obj.name       = name
        obj.icon       = icon
        obj.sort_order = sort_order
        obj.is_active  = is_active
        db.commit()
        print(f"   ~ updated  menu      '{path}'")
        return obj
    obj = Menu(name=name, path=path, icon=icon,
               sort_order=sort_order, is_active=is_active)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    print(f"   + inserted menu      '{path}'  ({name})")
    return obj


def _upsert_access(db, *, menu_path, role,
                   can_view, can_insert, can_update, can_delete):
    menu = db.query(Menu).filter(Menu.path == menu_path).first()
    if not menu:
        print(f"   ! menu '{menu_path}' not found — skipping access rule for role={role}")
        return
    obj = db.query(MenuAccess).filter(
        MenuAccess.menu_id == menu.id,
        MenuAccess.role    == role,
    ).first()
    if obj:
        obj.can_view   = can_view
        obj.can_insert = can_insert
        obj.can_update = can_update
        obj.can_delete = can_delete
        db.commit()
        perms = _perm_str(can_view, can_insert, can_update, can_delete)
        print(f"   ~ updated  access    {role:<9} -> {menu_path:<16}  [{perms}]")
        return
    db.add(MenuAccess(
        menu_id=menu.id, role=role,
        can_view=can_view, can_insert=can_insert,
        can_update=can_update, can_delete=can_delete,
    ))
    db.commit()
    perms = _perm_str(can_view, can_insert, can_update, can_delete)
    print(f"   + inserted access    {role:<9} -> {menu_path:<16}  [{perms}]")


def _perm_str(v, i, u, d):
    return (
        ("view "   if v else "     ") +
        ("insert " if i else "       ") +
        ("update " if u else "       ") +
        ("delete"  if d else "      ")
    ).strip() or "no-access"


# ── seed data ─────────────────────────────────────────────────────────────────

USERS = [
    # username         password         full_name                   email                          role       is_admin
    ("admin",          "Admin@1234",    "System Administrator",     "admin@example.com",           "admin",   True),
    ("manager1",       "Manager@1234",  "Alice Johnson",            "alice.johnson@example.com",   "manager", False),
    ("manager2",       "Manager@1234",  "Bob Williams",             "bob.williams@example.com",    "manager", False),
    ("jane.smith",     "Jane@1234",     "Jane Smith",               "jane.smith@example.com",      "manager", False),
    ("viewer1",        "Viewer@1234",   "Charlie Brown",            "charlie.brown@example.com",   "viewer",  False),
    ("viewer2",        "Viewer@1234",   "Diana Prince",             "diana.prince@example.com",    "viewer",  False),
    ("john.doe",       "John@1234",     "John Doe",                 "john.doe@example.com",        "viewer",  False),
]

MENUS = [
    # name            path             icon  sort
    ("Dashboard",     "/",             "🏠",  1),
    ("Users",         "/users",        "👥",  2),
    ("Reports",       "/reports",      "📊",  3),
    ("Settings",      "/settings",     "⚙️",   4),
    ("Menus",         "/menus",        "📋",  5),
    ("Menu Access",   "/menu-access",  "🔑",  6),
    ("Scraper",       "/scraper",      "🛒",  7),
    ("Email Action",  "/email-action", "📧",  8),
    ("Product Master","/product-master","📦", 9),
    ("NSE Stocks",    "/stocks",       "📈",  10),
]

#
# Access matrix: (menu_path, role, can_view, can_insert, can_update, can_delete)
#
#  admin   → full CRUD on everything
#  manager → view+insert+update on Dashboard/Users/Reports/Settings; no access to admin pages
#  viewer  → view-only on Dashboard/Reports/Settings
#
ACCESS = [
    # ── Dashboard (/') ───────────────────────────────────────────────────────
    ("/",            "admin",   True,  True,  True,  True),
    ("/",            "manager", True,  False, False, False),
    ("/",            "viewer",  True,  False, False, False),

    # ── Users (/users) ───────────────────────────────────────────────────────
    ("/users",       "admin",   True,  True,  True,  True),
    ("/users",       "manager", True,  True,  True,  False),
    ("/users",       "viewer",  False, False, False, False),

    # ── Reports (/reports) ───────────────────────────────────────────────────
    ("/reports",     "admin",   True,  True,  True,  True),
    ("/reports",     "manager", True,  False, False, False),
    ("/reports",     "viewer",  True,  False, False, False),

    # ── Settings (/settings) ─────────────────────────────────────────────────
    ("/settings",    "admin",   True,  True,  True,  True),
    ("/settings",    "manager", True,  False, False, False),
    ("/settings",    "viewer",  True,  False, False, False),

    # ── Menus (/menus) — admin-only ──────────────────────────────────────────
    ("/menus",       "admin",   True,  True,  True,  True),
    ("/menus",       "manager", False, False, False, False),
    ("/menus",       "viewer",  False, False, False, False),

    # ── Menu Access (/menu-access) — admin-only ──────────────────────────────
    ("/menu-access",   "admin",   True,  True,  True,  True),
    ("/menu-access",   "manager", False, False, False, False),
    ("/menu-access",   "viewer",  False, False, False, False),

    # ── Scraper (/scraper) ────────────────────────────────────────────────────
    ("/scraper",       "admin",   True,  True,  True,  True),
    ("/scraper",       "manager", True,  True,  True,  False),
    ("/scraper",       "viewer",  True,  False, False, False),

    # ── Email Action (/email-action) ──────────────────────────────────────────
    ("/email-action",  "admin",   True,  True,  True,  True),
    ("/email-action",  "manager", True,  True,  True,  False),
    ("/email-action",  "viewer",  True,  False, False, False),

    # ── Product Master (/product-master) — admin/manager only ─────────────────
    ("/product-master","admin",   True,  True,  True,  True),
    ("/product-master","manager", True,  True,  True,  False),
    ("/product-master","viewer",  False, False, False, False),

    # ── NSE Stocks (/stocks) ──────────────────────────────────────────────────
    ("/stocks",        "admin",   True,  True,  True,  True),
    ("/stocks",        "manager", True,  True,  True,  False),
    ("/stocks",        "viewer",  True,  False, False, False),
]


# ── main ──────────────────────────────────────────────────────────────────────

def seed():
    print("\n╔══════════════════════════════════════════════╗")
    print("║           MyApp — Database Seeder            ║")
    print("╚══════════════════════════════════════════════╝")

    # Create tables that do not exist yet
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ── Users ────────────────────────────────────────
        print("\n▶ Users")
        for username, password, full_name, email, role, is_admin in USERS:
            _upsert_user(db,
                username=username, password=password,
                full_name=full_name, email=email,
                role=role, is_admin=is_admin)

        # ── Menus ────────────────────────────────────────
        print("\n▶ Menus")
        for name, path, icon, sort_order in MENUS:
            _upsert_menu(db,
                name=name, path=path,
                icon=icon, sort_order=sort_order)

        # ── Menu Access ──────────────────────────────────
        print("\n▶ Menu Access")
        for path, role, v, i, u, d in ACCESS:
            _upsert_access(db,
                menu_path=path, role=role,
                can_view=v, can_insert=i,
                can_update=u, can_delete=d)

        print("\n✅  Seed completed successfully!\n")
        print("── Login credentials ──────────────────────────")
        print("  admin       / Admin@1234   (admin)")
        print("  manager1    / Manager@1234 (manager)")
        print("  manager2    / Manager@1234 (manager)")
        print("  jane.smith  / Jane@1234    (manager)")
        print("  viewer1     / Viewer@1234  (viewer)")
        print("  viewer2     / Viewer@1234  (viewer)")
        print("  john.doe    / John@1234    (viewer)")
        print("───────────────────────────────────────────────\n")

    except Exception as exc:
        db.rollback()
        print(f"\n❌  Seed failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
