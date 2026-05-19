-- ================================================================
-- Migration V2: menus, menu_access tables + full seed data
--
-- Run from psql:
--   psql -U <db_user> -d <db_name> -f migrations/V2__menus_and_access.sql
--
-- NOTE: User passwords require bcrypt hashing (Python).
--       Use seed.py for users. This file handles menus + access only.
-- ================================================================


-- ── 1. Tables ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS menus (
    id         SERIAL       PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    path       VARCHAR(200) NOT NULL UNIQUE,
    icon       VARCHAR(100),
    parent_id  INTEGER      REFERENCES menus(id) ON DELETE SET NULL,
    sort_order INTEGER      NOT NULL DEFAULT 0,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_access (
    id         SERIAL      PRIMARY KEY,
    menu_id    INTEGER     NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    role       VARCHAR(50) NOT NULL,
    can_view   BOOLEAN     NOT NULL DEFAULT FALSE,
    can_insert BOOLEAN     NOT NULL DEFAULT FALSE,
    can_update BOOLEAN     NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (menu_id, role)
);

CREATE INDEX IF NOT EXISTS idx_menu_access_role    ON menu_access(role);
CREATE INDEX IF NOT EXISTS idx_menu_access_menu_id ON menu_access(menu_id);


-- ── 2. Seed menus ────────────────────────────────────────────────

INSERT INTO menus (name, path, icon, sort_order, is_active) VALUES
  ('Dashboard',   '/',            '🏠', 1, TRUE),
  ('Users',       '/users',       '👥', 2, TRUE),
  ('Reports',     '/reports',     '📊', 3, TRUE),
  ('Settings',    '/settings',    '⚙️',  4, TRUE),
  ('Menus',       '/menus',       '📋', 5, TRUE),
  ('Menu Access', '/menu-access', '🔑', 6, TRUE)
ON CONFLICT (path) DO UPDATE
  SET name       = EXCLUDED.name,
      icon       = EXCLUDED.icon,
      sort_order = EXCLUDED.sort_order,
      is_active  = EXCLUDED.is_active;


-- ── 3. Seed menu_access ──────────────────────────────────────────
--
--  Role matrix:
--    admin   → full CRUD on all pages
--    manager → view+insert+update on Dashboard/Users/Reports/Settings
--    viewer  → view-only on Dashboard/Reports/Settings
--

-- admin — full access to everything
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'admin', TRUE, TRUE, TRUE, TRUE
FROM menus
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view   = TRUE,
      can_insert = TRUE,
      can_update = TRUE,
      can_delete = TRUE;

-- manager — Dashboard: view only
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'manager', TRUE, FALSE, FALSE, FALSE
FROM menus WHERE path = '/'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- manager — Users: view + insert + update (no delete)
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'manager', TRUE, TRUE, TRUE, FALSE
FROM menus WHERE path = '/users'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=TRUE, can_update=TRUE, can_delete=FALSE;

-- manager — Reports: view only
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'manager', TRUE, FALSE, FALSE, FALSE
FROM menus WHERE path = '/reports'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- manager — Settings: view only
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'manager', TRUE, FALSE, FALSE, FALSE
FROM menus WHERE path = '/settings'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- manager — Menus & Menu-Access: no access
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'manager', FALSE, FALSE, FALSE, FALSE
FROM menus WHERE path IN ('/menus', '/menu-access')
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=FALSE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- viewer — Dashboard: view only
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'viewer', TRUE, FALSE, FALSE, FALSE
FROM menus WHERE path = '/'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- viewer — Reports: view only
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'viewer', TRUE, FALSE, FALSE, FALSE
FROM menus WHERE path = '/reports'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- viewer — Settings: view only
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'viewer', TRUE, FALSE, FALSE, FALSE
FROM menus WHERE path = '/settings'
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=TRUE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;

-- viewer — Users, Menus, Menu-Access: no access
INSERT INTO menu_access (menu_id, role, can_view, can_insert, can_update, can_delete)
SELECT id, 'viewer', FALSE, FALSE, FALSE, FALSE
FROM menus WHERE path IN ('/users', '/menus', '/menu-access')
ON CONFLICT (menu_id, role) DO UPDATE
  SET can_view=FALSE, can_insert=FALSE, can_update=FALSE, can_delete=FALSE;
