import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_db, close_db, get_db
from app.logging_config import setup_logging
from app.routers import health, auth, users, organizations, spaces, tasks, agents, llm_logs
from app.routers import settings as settings_router

setup_logging("backend")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    # Auto-expire agent (LLM) call logs after LLM_LOG_TTL_SECONDS (1 day).
    # MongoDB's TTL monitor deletes documents once `created_at` is older than
    # the threshold — keeps the llm_logs collection to ~1 day of history.
    try:
        await get_db().llm_logs.create_index(
            "created_at", expireAfterSeconds=settings.LLM_LOG_TTL_SECONDS,
        )
        log.info("Ensured llm_logs TTL index (%ss)", settings.LLM_LOG_TTL_SECONDS)
    except Exception as exc:
        log.warning("Could not create llm_logs TTL index: %s", exc)
    yield
    await close_db()


app = FastAPI(title="MissionControl API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(organizations.router)
app.include_router(spaces.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(llm_logs.router)
app.include_router(settings_router.router)


@app.get("/")
async def root():
    return {"message": "MissionControl API"}
