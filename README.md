# React js + FastAPI Full-Stack Application

A full-stack business management application with role-based access control, user management, dynamic menus, a real-time Amazon product scraper, and an AI-powered email action centre.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [API Overview](#api-overview)
- [Role-Based Access Control](#role-based-access-control)
- [Amazon Scraper](#amazon-scraper)
- [Email Action Centre](#email-action-centre)
- [Real-Time Updates (SSE)](#real-time-updates-sse)
- [Database Schema](#database-schema)
- [Database Setup on a New Machine](#database-setup-on-a-new-machine)

---

## Features

| Feature | Description |
|---|---|
| **Authentication** | JWT-based login with automatic token refresh |
| **User Management** | Create, update, and deactivate users; avatar upload/remove |
| **Role-Based Access Control** | admin / manager / viewer roles; per-menu permission matrices |
| **Dynamic Menus** | Sidebar driven by the database; permissions enforced per role |
| **Amazon Scraper** | Submit ASIN batches; headless Playwright scraping with live progress |
| **Email Action Centre** | Sync Gmail inbox via IMAP; AI analysis by Ollama; team response tracking |
| **Smart Summary** | Per-email AI card showing building, flat, occupant, date, and reason |
| **Real-Time Updates** | Server-Sent Events (SSE) — zero polling, live job tracking |
| **Frozen Table Columns** | Sticky first/second columns and sticky headers on all data tables |
| **Pagination & Filters** | Client-side pagination and filter bar on every table |
| **Responsive Layout** | Works on desktop and tablets |

---

## Demo Credentials

After running `python seed.py`, the following accounts are available:

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@1234` | admin — full access |
| `manager1` | `Manager@1234` | manager |
| `viewer1` | `Viewer@1234` | viewer — read-only |

---

## Tech Stack

### Backend

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 |
| Server | Uvicorn |
| ORM | SQLAlchemy 2.0 (sync) |
| Database | PostgreSQL 14+ |
| Migrations | Alembic |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Scraping | Playwright (headless Chromium) |
| Email fetch | Python stdlib `imaplib` — IMAP over SSL |
| AI analysis | Ollama via `httpx` (local LLM, no cloud) |
| Config | pydantic-settings + python-dotenv |

### Frontend

| Layer | Technology |
|---|---|
| Framework | React 18 |
| Routing | React Router v6 |
| HTTP client | Axios |
| Real-time | Fetch-based SSE (custom `useSSE` hook) |
| State | React Context API |

---

## Project Structure

```
reactjsfastapi/
├── erp_database.sql              ← Full DB export — run on a new machine to restore
│
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   └── endpoints/
│   │   │       ├── auth.py           # Login → JWT token
│   │   │       ├── users.py          # User CRUD + avatar upload
│   │   │       ├── menu.py           # Menu & access-rule management
│   │   │       ├── scraping.py       # Scraper jobs + SSE streams
│   │   │       ├── email_action.py   # Gmail sync, AI analysis, responses
│   │   │       └── health.py
│   │   ├── core/
│   │   │   ├── security.py           # Password hashing, JWT encode/decode
│   │   │   └── roles.py              # RBAC decorator
│   │   ├── crud/                     # Generic + model-specific CRUD helpers
│   │   ├── db/
│   │   │   ├── base.py               # SQLAlchemy declarative base
│   │   │   └── session.py            # Engine, SessionLocal, get_db
│   │   ├── middleware/
│   │   │   └── logging_middleware.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── menu.py               # Menu, MenuAccess
│   │   │   ├── scraping.py           # ScrapingJob, ScrapingTask, ProductData
│   │   │   └── email_action.py       # EmailMessage, EmailSyncState
│   │   ├── schemas/                  # Pydantic request/response models
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── menu.py
│   │   │   ├── scraping.py
│   │   │   └── email_action.py
│   │   ├── services/
│   │   │   ├── scraper.py            # Playwright Amazon scraper
│   │   │   ├── scraping_queue.py     # In-process task enqueue
│   │   │   ├── gmail_service.py      # IMAP fetch with UID tracking
│   │   │   └── email_analyzer.py     # Ollama LLM prompt + JSON parsing
│   │   ├── config.py                 # All settings from .env
│   │   ├── dependencies.py           # FastAPI dependency: get_current_user
│   │   ├── main.py                   # App factory, lifespan, CORS
│   │   └── worker.py                 # Standalone scraper worker process
│   ├── alembic/                      # Alembic migration scripts
│   ├── static/avatars/               # Uploaded user avatars
│   ├── requirements.txt
│   └── run.py                        # Uvicorn entry point
│
└── frontend/
    └── src/
        ├── components/
        │   ├── common/               # Pagination, SortTh, ConfirmModal, Toggle …
        │   └── layout/               # Layout, Sidebar, TopPanel
        ├── context/
        │   └── AuthContext.jsx       # User, menus, login/logout
        ├── hooks/
        │   ├── useSSE.js             # Fetch-based SSE with auto-reconnect
        │   ├── usePagination.js
        │   ├── useSortFilter.js
        │   └── useMenuAccess.js
        ├── pages/
        │   ├── Dashboard/
        │   ├── Login/
        │   ├── Users/
        │   ├── Menus/
        │   ├── MenuAccess/           # Permission matrix editor
        │   ├── AmazonScraper/        # Batch ASIN scraper
        │   └── EmailAction/          # Gmail inbox + AI analysis + responses
        ├── routes/
        │   ├── index.jsx
        │   ├── PrivateRoute.jsx
        │   └── RoleRoute.jsx
        ├── services/
        │   ├── api.js                # Axios instance + JWT interceptor
        │   ├── authService.js
        │   ├── userService.js
        │   ├── menuService.js
        │   ├── scrapingService.js
        │   └── emailActionService.js
        └── utils/
            └── constants.js          # API_URL, TOKEN_KEY
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.9+ |
| Node.js | 18+ |
| PostgreSQL | 14+ |
| Playwright Chromium | installed via `playwright install chromium` |
| Ollama | optional — needed for AI email analysis |

---

## Getting Started

### 1. Clone the repository

```bash
git clone <repo-url>
cd reactjsfastapi
```

### 2. Backend setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (needed for Amazon scraper)
playwright install chromium

# Copy environment file and fill in values
cp .env.example .env
```

### 3. Database setup

**Option A — fresh database with demo data (recommended)**

```bash
# Create the PostgreSQL database
createdb ERP

# Start the backend once so SQLAlchemy creates all tables
cd backend && python run.py   # Ctrl-C after you see "Application startup complete"

# Seed demo users, menus, and access rules
python seed.py
```

**Option B — restore from the full export (includes all data)**

```bash
# Create the database first
createdb ERP

# Run the export script
PGPASSWORD='yourpassword' psql -h localhost -U postgres -d ERP -f erp_database.sql
```

### 4. Frontend setup

```bash
cd ../frontend
npm install
```

---

## Environment Variables

`backend/.env` — copy from `.env.example` and fill in all values:

```env
# ── Application ───────────────────────────────────────────────
APP_NAME=MyApp
APP_ENV=development
DEBUG=true

# ── Auth ──────────────────────────────────────────────────────
# Generate with: openssl rand -hex 32
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ── PostgreSQL ────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ERP
DB_USER=postgres
DB_PASSWORD=your_db_password

# ── Gmail IMAP (Email Action Centre) ─────────────────────────
# Use a Google App Password — not your account password.
# Enable at: https://myaccount.google.com/apppasswords
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# ── Ollama (AI email analysis) ────────────────────────────────
# Install Ollama: https://ollama.com
# Pull a model:  ollama pull llama3.2
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

**Frontend** — create `frontend/.env` only if the backend runs on a non-default port:

```env
REACT_APP_API_URL=http://localhost:9000/api/v1
```

---

## Running the Application

Open two terminals:

**Terminal 1 — Backend**

```bash
cd backend
source venv/bin/activate          # Windows: venv\Scripts\activate
python run.py
```

- API: `http://localhost:9000`
- API docs: `http://localhost:9000/docs`
- The scraping worker process starts automatically as a subprocess.

**Terminal 2 — Frontend**

```bash
cd frontend
npm start
```

- App: `http://localhost:3000`

---

## API Overview

All endpoints are prefixed with `/api/v1`.

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token` | Login — returns JWT access token |

### Users

| Method | Path | Description |
|---|---|---|
| GET | `/users/me` | Current user profile |
| GET | `/users` | List all users (admin / manager) |
| POST | `/users` | Create user (admin) |
| PUT | `/users/{id}` | Update user (admin) |
| DELETE | `/users/{id}` | Delete user (admin) |
| POST | `/users/{id}/avatar` | Upload avatar |
| DELETE | `/users/{id}/avatar` | Remove avatar |

### Menus

| Method | Path | Description |
|---|---|---|
| GET | `/menus` | All menus with user's permissions |
| POST | `/menus` | Create menu item (admin) |
| PUT | `/menus/{id}` | Update menu item (admin) |
| DELETE | `/menus/{id}` | Delete menu item (admin) |
| GET | `/menus/access` | List access rules |
| POST | `/menus/access` | Create access rule |
| PUT | `/menus/access/{id}` | Update access rule |
| DELETE | `/menus/access/{id}` | Delete access rule |

### Amazon Scraper

| Method | Path | Description |
|---|---|---|
| POST | `/scraping/jobs` | Submit a batch of ASINs |
| GET | `/scraping/jobs` | List jobs (role-filtered) |
| GET | `/scraping/jobs/{id}` | Job detail with all tasks and product data |
| GET | `/scraping/events` | **SSE** — live jobs list stream |
| GET | `/scraping/jobs/{id}/events` | **SSE** — live single-job stream |

### Email Action

| Method | Path | Description |
|---|---|---|
| POST | `/email/sync` | Fetch new Gmail messages and analyse with Ollama |
| GET | `/email/messages` | List messages (filterable by category / priority / status) |
| GET | `/email/messages/{id}` | Full message detail |
| PATCH | `/email/messages/{id}` | Update status, assignment, or response |
| GET | `/email/dashboard` | Summary stats — totals, by category, by priority, by status |

---

## Role-Based Access Control

| Role | Capabilities |
|---|---|
| `admin` | Full access — manage users, menus, access rules; see all scraping jobs and emails |
| `manager` | Read user list; view all scraping jobs and emails; cannot manage users or menus |
| `viewer` | Sees only their own scraping jobs and emails |

Menu visibility and CRUD permissions (view / insert / update / delete) are configured per-role in the **Menu Access** admin page and stored in the `menu_access` table.

---

## Amazon Scraper

### How it works

1. A user submits one or more 10-character ASINs (up to 50 per request).
2. The backend creates a `ScrapingJob` with one `ScrapingTask` per ASIN.
3. A standalone **worker process** (`worker.py`) runs alongside the FastAPI server. It polls the database every 2 seconds for `pending` tasks.
4. Up to **2 tasks run concurrently** (controlled by a `threading.Semaphore`). All other tasks wait and start automatically as slots free up.
5. Each task launches a headless Chromium browser via Playwright, navigates to `amazon.in/dp/{ASIN}`, and extracts title, brand, price, rating, review count, availability, and hero image URL.
6. Results are written to the `product_data` table. Task status becomes `completed` or `failed`.
7. On server restart the worker recovers any tasks that were `running`, resetting them to `pending`.
8. A PID file (`worker.pid`) prevents duplicate worker processes on hot-reload.

### Job status progression

| Status | Meaning |
|---|---|
| Queued | All tasks pending, none running yet |
| Running | At least one task in progress |
| Done | All tasks completed successfully |
| Partial | Mix of completed and failed tasks |
| Failed | All tasks failed |

### ASIN input format

One per line, or comma / space separated:

```
B0D324VJ6G
B09G3HRMVB, B0B7CM33XX
```

---

## Email Action Centre

A single-page inbox management tool that reads Gmail, classifies each email with a local LLM, and lets your team track responses.

### How it works

1. Click **Sync Gmail** — the backend connects to Gmail via IMAP and fetches all messages since the last sync (first run: most recent 50).
2. Each new email is sent to **Ollama** (running locally) for analysis. The LLM returns a structured JSON object with the fields below.
3. The email and its analysis are stored in `email_messages`. The IMAP UID of the last synced message is stored in `email_sync_state` so future syncs are incremental.
4. The page displays a live dashboard, category distribution bar, and filterable email table.
5. Team members open an email, read the AI summary, and log a response on the **Respond / Assign** tab.

### AI-extracted fields

| Field | Values |
|---|---|
| Category | request · issue · sales · inquiry · escalation · complaint · other |
| Priority | fatal · critical · medium · low |
| Sentiment | positive · neutral · negative |
| Summary | 2–3 sentence overview |
| Project / Zone | extracted if mentioned |
| Key Points | 3–5 bullet points |
| Action Items | required follow-up tasks |
| **Building Name** | name of the society / tower / complex |
| **Flat / Unit** | flat name and number (e.g. A-101) |
| **Occupant Type** | owner · tenant · visitor |
| **Visit / Complaint Date** | date extracted as text |
| **Reason / Purpose / Issue** | core problem in 1–2 sentences |

### Smart Summary tab

Each email detail modal has a **Smart Summary** tab that shows the structured fields above as quick-reference cards — designed for fast triage without reading the full email body.

### Gmail setup

1. Enable IMAP in Gmail: **Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP**.
2. Create an App Password: **Google Account → Security → 2-Step Verification → App Passwords**.
3. Set `GMAIL_USER` and `GMAIL_APP_PASSWORD` in `backend/.env`.

### Ollama setup

```bash
# Install Ollama (Linux/Mac)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2

# Ollama runs at http://localhost:11434 by default
```

Set `OLLAMA_MODEL=llama3.2` (or any model you have pulled) in `backend/.env`. If Ollama is not running, emails are still stored — AI fields will be blank.

---

## Real-Time Updates (SSE)

The scraper uses **Server-Sent Events** — no client polling.

| Connection | Endpoint | Behaviour |
|---|---|---|
| Jobs list page | `GET /scraping/events` | One persistent connection; sends JSON array on any change |
| Job detail modal | `GET /scraping/jobs/{id}/events` | Streams single-job updates; auto-closes when job finishes |

The server sends a frame only when data actually changes:
- **Active jobs** — DB queried every 1 second
- **Idle (no active jobs)** — DB queried every 5 seconds

The `useSSE` React hook (fetch-based, not `EventSource`) passes the `Authorization: Bearer` header and auto-reconnects after 3 seconds on any network error.

---

## Database Schema

```
users
  id, username, email, hashed_password, full_name,
  role (admin|manager|viewer), is_active,
  avatar_url, created_at, updated_at

menus
  id, name, path, icon, sort_order, is_active,
  parent_id → menus, created_at

menu_access
  id, menu_id → menus, role,
  can_view, can_insert, can_update, can_delete

scraping_jobs
  id, user_id → users,
  total, pending, running, completed, failed, created_at

scraping_tasks
  id, job_id → scraping_jobs,
  asin, status (pending|running|completed|failed),
  error, queued_at, started_at, completed_at

product_data
  id, task_id → scraping_tasks (unique), asin,
  title, brand, price, rating, review_count,
  availability, image_url, scraped_at

email_messages
  id, message_uid (IMAP UID, unique),
  subject, sender, received_at, body_text,
  category, priority, sentiment,
  ai_summary, project_name, zone,
  key_points (JSON), action_items (JSON),
  building_name, flat_info, occupant_type,
  event_date, reason_purpose,
  status (new|in_progress|resolved|closed),
  assigned_to, response_text, response_by, responded_at,
  created_at, updated_at

email_sync_state
  id, last_uid, last_sync_at
```

---

## Database Setup on a New Machine

A full export of the database (schema + all data) is included in `erp_database.sql`.

```bash
# 1. Install PostgreSQL
sudo apt install postgresql postgresql-client   # Ubuntu/Debian

# 2. Create the database
sudo -u postgres psql -c 'CREATE DATABASE "ERP";'

# 3. Restore the export
PGPASSWORD='your-postgres-password' psql -h localhost -U postgres -d ERP -f erp_database.sql

# 4. Copy backend/.env and adjust DB_HOST / DB_PASSWORD if needed
```

**Windows:**

```cmd
set PGPASSWORD=your-postgres-password
psql -h localhost -U postgres -d ERP -f erp_database.sql
```

The export contains all 8 tables, all rows, and sequence resets so that auto-increment IDs continue from the correct value.
