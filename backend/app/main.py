"""FastAPI application factory and lifespan manager.

Creates the ASGI application, registers middleware, mounts the static-file
directory for avatar images, includes the versioned API router, and manages
the scraping worker subprocess lifecycle.
"""

import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.config import settings
from app.db.base import Base
from app.db.session import engine
from app.middleware.logging_middleware import LoggingMiddleware

# Register all ORM models with Base.metadata before create_all is called.
import app.models.email_action   # noqa: F401
import app.models.product_master  # noqa: F401
import app.models.scraping        # noqa: F401
import app.models.stock           # noqa: F401
import app.models.user            # noqa: F401

#: Directory that serves avatar images at ``/static/avatars/<filename>``.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "avatars").mkdir(exist_ok=True)

_WORKER_SCRIPT = Path(__file__).resolve().parent / "worker.py"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage startup and shutdown tasks.

    On startup:
    - Creates all DB tables that don't yet exist (idempotent).
    - Spawns the scraping worker as a separate OS process.

    On shutdown (``finally`` block):
    - Sends ``SIGTERM`` to the worker, giving it a chance to finish cleanly.

    The worker is launched via ``shell=True`` so that debugpy (the VS Code
    debugger) does not intercept and instrument the child process.
    """
    Base.metadata.create_all(bind=engine)
    cmd = f'exec "{sys.executable}" "{_WORKER_SCRIPT}"'
    worker = subprocess.Popen(cmd, shell=True, start_new_session=True)
    try:
        yield
    finally:
        worker.terminate()


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router, prefix="/api/v1")
