# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Backend Overview

FastAPI + MongoDB backend for MissionControl. Uses Motor (async) for API routes and pymongo (sync) for Celery workers — never mix these two clients within the same code path.

## Commands

```bash
# Run dev server (from missioncontrol-be/)
uvicorn app.main:app --reload --port 8001

# Seed database (creates admin user + migrates pipeline agents)
python -m app.seed

# Celery worker
celery -A app.celery_app.celery worker --loglevel=info

# Celery beat (cron scheduler — run alongside worker)
celery -A app.celery_app.celery beat --loglevel=info

# Redis (required for Celery)
docker-compose up -d
```

No test suite exists yet. Verify behaviour via the OpenAPI docs at http://localhost:8001/docs.

## Architecture

### Entry point
`app/main.py` — Creates the FastAPI app, registers CORS middleware, includes all routers, and manages the Motor DB connection lifecycle via `lifespan`.

### Configuration
`app/config.py` — Single `Settings` (Pydantic BaseSettings) singleton at `settings`. All env vars loaded from `.env`. Key settings:
- `MONGODB_URL`, `DB_NAME` — MongoDB connection
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` — Redis URLs
- `AGENT_POLL_INTERVAL_SECONDS` — how often the beat task polls for agent work
- `RESEARCHER_CRON_HOUR/MINUTE` — UTC time for daily Content Researcher run

### Database clients
- **API routes** → `app/database.py` → `get_db()` returns an async Motor database handle (set during `lifespan`)
- **Celery tasks** → `app/worker/db.py` → `get_sync_db()` returns a synchronous pymongo handle (lazy singleton)

MongoDB `_id` (ObjectId) is always serialized to string `id` in API responses via the `serialize_*` helpers in `app/utils.py`. Every router calls the appropriate serializer before returning.

### Authentication
`app/auth.py` — JWT (HS256) bearer tokens. Token stored in `sub` claim = user `_id` string.
- `get_current_user` — FastAPI dependency that decodes token and returns the serialized user dict
- `require_admin` — wraps `get_current_user`; raises 403 if `role != "admin"`
- Roles: `admin`, `editor`, `viewer`

### Router structure
All routers live in `app/routers/`. URL prefixes:
- `/api/auth` — login, register, me
- `/api/users` — user management (admin-only mutations)
- `/api/orgs` — organization CRUD
- `/api/orgs/{org_id}/spaces` — space CRUD (also auto-seeds 4 pipeline agents + 4 default statuses on create)
- `/api/orgs/{org_id}/settings` — API keys and Notion config (admin-only writes; keys are masked on read)
- `/api/spaces/{space_id}/tasks` — tasks, task statuses, comments
- `/api/spaces/{space_id}/agents` — pipeline agent CRUD
- `/api/spaces/{space_id}/logs` — LLM call logs

### Models
`app/models/` contains Pydantic models (Create, Update, Response) for each entity — user, organization, space, task, agent, settings, llm_log. MongoDB documents are raw dicts; Pydantic only validates API input/output, not DB writes.

### Settings / org_settings collection
API keys (OpenAI, Gemini, Claude) and Notion credentials are stored in the `org_settings` collection, keyed by `org_id`. The `settings.py` router uses `upsert` so the doc is created on first save. Keys are masked on GET (shows only last 4 chars).

### Agent dispatch flow
When a task is created or reassigned to an agent via the API (`app/routers/tasks.py`), `_maybe_dispatch_agent_task()` checks the agent role and calls the matching Celery task with `.delay()`. The same dispatch also happens via the periodic `poll_agent_tasks` beat task.

Before dispatching, the task document gets `_agent_processing: True` set to prevent duplicate execution. It is cleared at the end of every Celery task (including on failure paths).

### LLM logging
Every LLM call is logged to the `llm_logs` collection directly inside `app/worker/llm.py` at the point of the API call. The logged `request` is the exact `**kwargs` dict sent to the provider SDK; `response` is raw text. Stored fields: `task_id`, `agent_id`, `space_id`, `provider`, `model`, `request` (dict), `response`, `duration_ms`, `requested_at`, `created_at`.

### Logging & retention (all ≤ 1 day)
- **Agent/LLM logs** (`llm_logs`): a **TTL index** on `created_at` (`LLM_LOG_TTL_SECONDS`, default 86400) is ensured in `main.py`'s lifespan; MongoDB auto-deletes entries older than 1 day.
- **Process logs** (backend / worker / beat): `app/logging_config.py` `setup_logging()` installs a `TimedRotatingFileHandler` (midnight UTC, `backupCount=LOG_BACKUP_DAYS=1`) writing to `${LOG_DIR}/${SERVICE_NAME}.log` plus a console handler. Wired into Celery via the `setup_logging` signal in `celery_app.py` and called at import in `main.py`. In Docker, `LOG_DIR=/var/log/missioncontrol` on a shared `app_logs` volume; each service sets a distinct `SERVICE_NAME`.
- **Container stdout**: the `x-logging` anchor in docker-compose caps every service's `json-file` driver (`max-size 10m`, `max-file 1`) as a size backstop.

### Thumbnail generation
`app/worker/thumbnail.py` — Generates an SVG file in `assets/` using a hardcoded gradient template. Called by Content Validator on approval; the file is uploaded to Notion then deleted locally.

## Key Invariants

- The four pipeline statuses **must** be named exactly `To Do`, `In Progress`, `In Review`, `Done` (case-insensitive match). The worker looks them up by name.
- Each space must have exactly one agent per pipeline role (`content_researcher`, `topic_validator`, `content_writer`, `content_validator`). The seed script and space-creation endpoint enforce this.
- `_agent_processing` is a soft lock — always `$unset` it at the end of every task code path, including exception handlers.
- Revision loop caps at 5 rounds (`_revision_count >= 5`) then escalates to the first active admin user.
- OpenAI prompt caching only activates for the writer/validator on **revision** turns (not first write/review), and only when `provider == "openai"` and prior messages exist on the task.
