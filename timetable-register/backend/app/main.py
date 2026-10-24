import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import Base, engine
from .routers import admin, auth, dashboard, public, resources, timetables

log = logging.getLogger("timetable")
_init_lock = threading.Lock()
_initialised = False


def ensure_initialised() -> None:
    """Create tables and (optionally) load demo data once per process.

    Runs lazily on the first request as well as at startup, because serverless
    platforms do not always deliver ASGI lifespan events.
    """
    global _initialised
    if _initialised:
        return
    with _init_lock:
        if _initialised:
            return
        s = get_settings()
        try:
            if s.auto_create_tables:
                Base.metadata.create_all(bind=engine)
            if s.seed_demo:
                from . import seed

                seed.run(reset=False)
        except Exception:  # noqa: BLE001 - another instance may be seeding at the same moment
            log.exception("Startup initialisation failed")
        _initialised = True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_initialised()
    yield


app = FastAPI(
    title="Timetable Management System API",
    version="1.0.0",
    description=(
        "Multi-institution timetable management: configure schedules, teachers, rooms, subjects, "
        "classes and curriculum, then generate conflict-free timetables with a constraint-satisfaction "
        "engine, edit them with live conflict checks, publish, export and share."
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def _lazy_init(request: Request, call_next):
    if not _initialised:
        ensure_initialised()
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_origin_regex=get_settings().cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for r in (auth.router, admin.router, resources.router, timetables.router, dashboard.router, public.router):
    app.include_router(r)


@app.get("/", include_in_schema=False)
def root():
    return {"name": "Timetable Register API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", tags=["meta"])
def health():
    s = get_settings()
    return {"status": "ok", "database": s.database_url.split(":", 1)[0].split("+")[0]}
