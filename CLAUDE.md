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

1. **Content Researcher** (`content_researcher`) — runs on daily cron; queries LLM for topic ideas; creates a task assigned to Topic Validator
2. **Topic Validator** (`topic_validator`) — validates/shortlists topics; creates individual tasks for Content Writer
3. **Content Writer** (`content_writer`) — writes blog post JSON via LLM; publishes to Notion as a Draft; moves to In Review
4. **Content Validator** (`content_validator`) — reads content from Notion; approves (→ Published + thumbnail) or rejects (→ back to writer). After 5 revision cycles, escalates to admin user.

Pipeline dispatch happens in two ways:
- **Periodic**: `poll_agent_tasks` beat task (every 30s) scans all agent-assigned tasks and dispatches
- **Immediate**: When a task is created or its assignee changes to an agent via the API, it dispatches directly

### Key Celery beat schedules
- `poll_agent_tasks` — every `AGENT_POLL_INTERVAL_SECONDS` (default: 30s)
- `run_content_researcher_all` — daily cron at `RESEARCHER_CRON_HOUR:RESEARCHER_CRON_MINUTE` UTC

### LLM provider support
- **OpenAI**, **Gemini**, **Claude** — configured per agent
- API keys stored in `org_settings` collection per org
- OpenAI gets a special cached path (`execute_with_llm_cached`) for the writer/validator revision loop: conversation history is persisted on the task doc (`_llm_messages_writer`, `_llm_messages_validator`) and replayed to benefit from OpenAI prefix caching

### MongoDB collections
`users`, `organizations`, `spaces`, `tasks`, `task_statuses`, `documents`, `folders`, `agents`, `comments`, `llm_logs`, `org_settings`

### Task internal fields (underscore-prefixed, not in API response)
- `_agent_processing` — lock flag; prevents duplicate Celery dispatches
- `_revision_count` — number of writer/validator revision rounds
- `_llm_messages_writer` / `_llm_messages_validator` — conversation history arrays for OpenAI caching
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
