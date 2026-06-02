# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MissionControl is an AI-powered SEO content pipeline management panel for ReviewHandy. It consists of two sub-projects:

- `missioncontrol-be/` — FastAPI + MongoDB backend with Celery workers
- `missioncontrol-fe/` — React 19 + TypeScript + Vite frontend

The central feature is a **4-agent autonomous content pipeline** that researches topics, validates them, writes blog posts to Notion, and reviews them — all triggered by Celery beat tasks and direct API-triggered dispatches.

## Architecture

### Data model hierarchy
```
Organization → Spaces → (Tasks, Documents/Folders, Agents)
               ↓
          org_settings (API keys, Notion credentials — per org)
```

### Content pipeline (the core feature)
Four fixed pipeline agents are auto-created when a Space is made. They execute in sequence as Celery tasks:

1. **Content Researcher** (`content_researcher`) — triggered when a "Give me N topic ideas" task is assigned to it, **on a due-date basis** (today/empty → now, future → waits). Researches topic + purpose only (count parsed from the title), posts a `| TOPIC | PURPOSE |` table in comments, then moves the task to In Review and assigns the Topic Validator.
2. **Topic Validator** (`topic_validator`) — reads the researcher's topics; validates every row (approved/declined + remark) in a `| TOPIC | PURPOSE | STATUS | REMARK |` table, cross-checking Notion for duplicates. Each approved topic immediately spawns a Content Writer task. Loops back to the researcher (the same batch task) until **3 topics are approved cumulatively** (→ Done) or **5 rounds** elapse (→ escalate to admin). Approved topics persist across rounds; only the shortfall is regenerated.
3. **Content Writer** (`content_writer`) — writes blog post JSON via LLM; publishes to Notion as a Draft; moves to In Review
4. **Content Validator** (`content_validator`) — reads content from Notion; approves (→ Published + thumbnail) or rejects (→ back to writer). After 5 revision cycles, escalates to admin user.

Pipeline dispatch happens in two ways:
- **Periodic**: `poll_agent_tasks` beat task (every 30s) scans all agent-assigned tasks and dispatches
- **Immediate**: When a task is created or its assignee changes to an agent via the API, it dispatches directly

### Key Celery beat schedules
- `poll_agent_tasks` — every `AGENT_POLL_INTERVAL_SECONDS` (default: 30s). Also the backstop that fires the researcher when a deferred (future due-date) task becomes due.
- `daily_cron` — daily at `DAILY_CRON_HOUR:DAILY_CRON_MINUTE` UTC (default **22:30 UTC = 04:00 IST**). Creates the static daily topic task ("Give me 10 new SEO blogs topic that attracts United States Restaurant Owners/Managers") in every space with an active Content Researcher and assigns it to that researcher.

### LLM provider support
- **OpenAI**, **Gemini**, **Claude** — configured per agent
- API keys stored in `org_settings` collection per org
- All four agents use the cached path (`execute_with_llm_cached`): each task keeps a persisted conversation thread (`_llm_messages_researcher`, `_llm_messages_topic_validator`, `_llm_messages_writer`, `_llm_messages_validator`) so the full request/response is logged per task and (on OpenAI) the prefix is served from prompt cache across revisions

### MongoDB collections
`users`, `organizations`, `spaces`, `tasks`, `task_statuses`, `agents`, `comments`, `llm_logs`, `org_settings`

### Task internal fields (underscore-prefixed, not in API response)
- `_agent_processing` — lock flag; prevents duplicate Celery dispatches. Held `True` for the whole researcher↔validator loop (each stage hands off directly); cleared only on a terminal state
- `_revision_count` — number of revision rounds (writer/validator loop AND researcher/validator topic loop)
- `_llm_messages_researcher` / `_llm_messages_topic_validator` / `_llm_messages_writer` / `_llm_messages_validator` — per-task conversation threads (logged + OpenAI caching)
- `_pending_topics` — topics the researcher proposed this round, awaiting validation (unset after the validator reads them)
- `_approved_topics` / `_declined_topics` — persistent topic state across revisions; `_topic_suggestions` — validator's overall guidance for the next researcher round
- `notion_page_id` — Notion page ID stored once the writer publishes

### Default task statuses per space
`To Do` → `In Progress` → `In Review` → `Done`
The pipeline keyed on these names (case-insensitive lookup). Renaming them breaks routing.

## Development Setup

### Services required
- MongoDB (local or Atlas)
- Redis (for Celery broker/backend — `docker-compose up` starts Redis)

### Running the backend
```bash
cd missioncontrol-be
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in MONGODB_URL, SECRET_KEY, etc.
uvicorn app.main:app --reload --port 8001
```

API docs: http://localhost:8001/docs

### Seeding the database
```bash
cd missioncontrol-be
python -m app.seed    # creates admin@reviewhandy.com / admin123456 and migrates pipeline agents
```

### Running Celery workers
```bash
cd missioncontrol-be
# Worker
celery -A app.celery_app.celery worker --loglevel=info

# Beat scheduler (runs alongside worker in dev)
celery -A app.celery_app.celery beat --loglevel=info
```

### Running the frontend
```bash
cd missioncontrol-fe
npm install
npm run dev    # http://localhost:5173
```

### Redis via Docker
```bash
cd missioncontrol-be
docker-compose up -d   # starts Redis on port 6379
```
