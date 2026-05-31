from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_db, close_db
from app.routers import health, auth, users, organizations, spaces, tasks, documents, agents, llm_logs
from app.routers import settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
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
app.include_router(documents.router)
app.include_router(agents.router)
app.include_router(llm_logs.router)
app.include_router(settings_router.router)


@app.get("/")
async def root():
    return {"message": "MissionControl API"}
