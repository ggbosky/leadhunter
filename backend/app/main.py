"""FastAPI aplikace Project Two Lead Hunter."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import jobs  # noqa: F401
from .api import companies, system
from .api.deps import require_token
from .config import BACKEND_DIR, get_settings
from .db import SessionLocal
from .jobs import handlers  # noqa: F401 - registrace handlerů
from .jobs.queue import Worker
from .jobs.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("leadhunter")

WORKER: Worker | None = None


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # configparser interpoluje %, hesla v URL (např. %40) je nutné escapovat
    cfg.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def bootstrap() -> None:
    from .connectors.registry import ensure_data_sources

    with SessionLocal() as db:
        ensure_data_sources(db)
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global WORKER
    s = get_settings()
    run_migrations()
    bootstrap()
    if s.worker_enabled:
        WORKER = Worker()
        WORKER.start()
    if s.scheduler_enabled:
        start_scheduler()
    from sqlalchemy.engine import make_url

    log.info("Lead Hunter připraven (DB: %s)", make_url(s.sqlalchemy_url).render_as_string(hide_password=True))
    yield
    shutdown_scheduler()
    if WORKER:
        WORKER.stop()
        WORKER = None


app = FastAPI(title="Project Two Lead Hunter API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system.router, prefix="/api", dependencies=[Depends(require_token)])
app.include_router(companies.router, prefix="/api", dependencies=[Depends(require_token)])


@app.get("/screenshots/{path:path}", dependencies=[Depends(require_token)])
def screenshot(path: str) -> FileResponse:
    root = get_settings().screenshot_dir.resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file() or target.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise HTTPException(404, "Screenshot nenalezen")
    return FileResponse(target, headers={"Cache-Control": "private, max-age=86400"})


@app.get("/")
def root() -> dict:
    return {"app": "Project Two Lead Hunter", "docs": "/docs", "api": "/api"}


def _ensure_dirs() -> None:
    Path(get_settings().screenshot_dir).mkdir(parents=True, exist_ok=True)


_ensure_dirs()
