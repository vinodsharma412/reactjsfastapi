-- ================================================================
-- Migration V3: seed users with bcrypt-hashed passwords
--
-- Run AFTER V2 (menus + menu_access must exist first).
--
-- Passwords (bcrypt $2b$12$ rounds):
--   admin       → Admin@1234
--   manager1    → Manager@1234
--   manager2    → Manager@1234
--   jane.smith  → Jane@1234
--   viewer1     → Viewer@1234
--   viewer2     → Viewer@1234
--   john.doe    → John@1234
--
-- Run: psql -U <db_user> -d <db_name> -f migrations/V3__seed_users.sql
-- ================================================================

INSERT INTO users
    (username, hashed_password, full_name, email, role, is_admin, is_active)
VALUES
-- ── admin ──────────────────────────────────────────────────────────────────
(
    'admin',
    '$2b$12$znLdpbcfeHMTAbWvji.OFOaFwJc5sebaYGp96g0Q5kTCGld39wPXW',
    'System Administrator',
    'admin@example.com',
    'admin',
    TRUE,
    TRUE
),
-- ── managers ───────────────────────────────────────────────────────────────
(
    'manager1',
    '$2b$12$7t8q4EgumwDoKRjuO5J/Y.AGDU7SGEeR0o4qy2MfsctOzoUni.b9y',
    'Alice Johnson',
    'alice.johnson@example.com',
    'manager',
    FALSE,
    TRUE
),
(
    'manager2',
    '$2b$12$pR1gEskCsrLhLqDck5DIPeOsNFXf3vcFmnOwVtLJexWlTJEzclU.i',
    'Bob Williams',
    'bob.williams@example.com',
    'manager',
    FALSE,
    TRUE
),
(
    'jane.smith',
    '$2b$12$4Uw/qsXYXTgOCS4klE8LSO1lIfo7NMeVjlGUeLIktjpUB3E6dzUS2',
    'Jane Smith',
    'jane.smith@example.com',
    'manager',
    FALSE,
    TRUE
),
-- ── viewers ────────────────────────────────────────────────────────────────
(
    'viewer1',
    '$2b$12$/yBLd7q1EcUhQToHlBV72uykbqSEjSaseNXqtJwQgSvwA3ZNiBJIS',
    'Charlie Brown',
    'charlie.brown@example.com',
    'viewer',
    FALSE,
    TRUE
),
(
    'viewer2',
    '$2b$12$JjoJOapRun/z8paRV8RY3.kKJ.QRjIeuBkdlHM3R1rtHBl0jAUK9q',
    'Diana Prince',
    'diana.prince@example.com',
    'viewer',
    FALSE,
    TRUE
),
(
    'john.doe',
    '$2b$12$TJ4xqh2T39ZDYDbJd1PxHOJ6dEG1CDSWYTgOx.xUdU8RLGxVYZvEy',
    'John Doe',
    'john.doe@example.com',
    'viewer',
    FALSE,
    TRUE
)
ON CONFLICT (username) DO UPDATE
    SET full_name       = EXCLUDED.full_name,
        email           = EXCLUDED.email,
        role            = EXCLUDED.role,
        is_admin        = EXCLUDED.is_admin,
        is_active       = EXCLUDED.is_active;
        -- Note: hashed_password is NOT updated to preserve any existing password changes
