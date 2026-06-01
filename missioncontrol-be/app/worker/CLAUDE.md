# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Worker Overview

Celery task package for the 4-stage AI content pipeline. All code here is **synchronous** — Motor (async) cannot be used inside Celery tasks. Use `get_sync_db()` from `app/worker/db.py` for all database access.

## Files

| File | Purpose |
|---|---|
| `db.py` | Lazy pymongo client singleton (`get_sync_db()`) |
| `llm.py` | LLM execution layer: `execute_with_llm()` (one-shot) and `execute_with_llm_cached()` (multi-turn) for OpenAI, Gemini, Claude |
| `notion.py` | Notion API integration: create/update/read blog pages, upload images |
| `thumbnail.py` | SVG thumbnail generator; saves to `assets/` then caller uploads + deletes |
| `tasks.py` | All Celery task definitions — the 4 pipeline steps + beat tasks |

## Beat Tasks (registered in `app/celery_app.py`)

**`poll_agent_tasks`** — periodic (every `AGENT_POLL_INTERVAL_SECONDS`):
- Finds all tasks with `assignee_type: "agent"` that are not already `_agent_processing`
- Checks the agent role + current task status to determine if a dispatch is needed
- Topic Validator + Content Writer trigger on `To Do` status
- Content Validator triggers on `In Review` status
- Sets `_agent_processing: True` before dispatching

**`run_content_researcher_all`** — daily cron:
- Finds all active Content Researcher agents with provider/model set
- Dispatches `run_content_researcher.delay(space_id)` for each

## Pipeline Task Sequence

### Step 1: `run_content_researcher(space_id)`
- Fetches space `niche` and `topic_count` config
- Builds a previous-topics context from the last 50 writer tasks and last 10 validator task descriptions
- Calls LLM via `_call_agent_llm()` (one-shot); expects JSON array of `{title, description, category, focus_keyword}`
- Creates a task assigned to the Topic Validator with the raw LLM output as description
- Dispatches `run_topic_validator.delay()` immediately

### Step 2: `run_topic_validator(task_id, space_id)`
- Moves task to In Progress, posts a comment
- Calls LLM to shortlist/refine topics; parses approved topics from JSON
- Creates individual tasks for each approved topic, assigned to Content Writer
- Dispatches `run_content_writer.delay()` for each immediately
- Marks the validator task as Done

### Step 3: `run_content_writer(task_id, space_id)`
Three paths based on whether this is a first write or a revision, and whether caching is active:
- **First write** — builds fresh `[system, user]` messages array
- **Revision (OpenAI cached)** — reads `_llm_messages_writer` from the task, appends only the new feedback as a user turn, calls `execute_with_llm_cached()`; prior turns served from OpenAI cache
- **Revision (non-OpenAI)** — reads current Notion content via `read_page_content()`, rebuilds full context

After LLM call, persists updated messages to `tasks._llm_messages_writer`.

Publishes to Notion via `create_blog_entry()` (first write) or `update_blog_content()` (revision). Stores `notion_page_id` on the task. Moves task to `In Review`, assigns to Content Validator, posts a comment with the Notion URL.

### Step 4: `run_content_validator(task_id, space_id)`
Two paths (same caching pattern as writer, stored in `_llm_messages_validator`):
- Reads current Notion page content/properties every time (content changes each revision)
- If **approved**: generates thumbnail SVG → uploads to Notion → deletes local file → updates Notion status to Published → moves task to Done → notifies admin
- If **rejected**: increments `_revision_count`; posts structured feedback comment @mentioning the writer; reassigns to writer, moves to To Do
- After 5 rejection rounds: escalates to admin user (reassigns task to admin, posts @mention comment, stops the loop)

## Helper Functions (internal to `tasks.py`)

- `_get_agent_by_role(db, space_id, role)` — finds active agent by pipeline role string
- `_get_status_by_name(db, space_id, name)` — case-insensitive lookup of task status; these lookups drive all pipeline routing
- `_get_org_settings(db, space_id)` — resolves org via space's `org_id`, returns the `org_settings` doc
- `_get_api_key(org_settings, provider)` — extracts the right key field from org_settings
- `_call_agent_llm(db, agent, space_id, system_extra, user_prompt)` — one-shot LLM call for researcher and validator
- `_call_agent_llm_cached(db, agent, space_id, messages)` — multi-turn call; returns `(response_text, updated_messages)`
- `_post_comment(db, task_id, agent_id, agent_name, content, mentions)` — inserts a comment on behalf of an agent
- `_create_task(...)` — inserts a task, auto-positions at end of the status column
- `_parse_json_from_llm(text)` — extracts JSON from LLM output; handles ````json` code blocks and raw JSON
- `_clear_processing_flag(db, task_id)` — `$unset` the `_agent_processing` lock; **must be called on all exit paths**
- `_build_agent_system_prompt(agent, system_extra)` — prepends agent name + strips HTML tags from `skill_content` + appends role instructions

## LLM Layer (`llm.py`)

Two public functions (both accept keyword-only `task_id=""`, `agent_id=""`, `space_id=""`):
- `execute_with_llm(provider, model, api_key, system_prompt, user_prompt) → str` — one-shot; researcher and topic validator use this
- `execute_with_llm_cached(provider, model, api_key, messages) → (str, list[dict])` — sends full messages array; writer and validator use this; returns updated messages with assistant turn appended

Logging is done inside `llm.py` at the point of the actual API call via `_write_log()`. The logged `request` is the exact `**kwargs` dict passed to the provider SDK (raw messages array, model, etc.); `response` is the raw text returned. Each log entry also captures `requested_at`, `duration_ms`, `task_id`, `agent_id`, and `space_id`.

OpenAI notes:
- Tries `max_completion_tokens=16384` first (for reasoning models); falls back to `max_tokens=4096`
- Logs cache hit stats when `prompt_tokens_details.cached_tokens` is set
- Raises if content is empty and finish_reason is `"length"` (reasoning token exhaustion)

For Gemini and Claude on the cached path, only the last user message is extracted and sent (no real multi-turn caching — they use the one-shot path internally).

## Notion Layer (`notion.py`)

- Uses `notion-client` SDK for database/page operations and `httpx` directly for file uploads (the SDK doesn't support the file upload API)
- `_normalize_id()` accepts Notion page IDs in URL form, UUID form, or raw 32-char hex
- `_markdown_to_blocks()` converts the LLM's Markdown output to Notion block objects; handles headings, bullets, numbered lists, code blocks, blockquotes, bold/italic/code inline formatting
- Notion API limits: 100 blocks per append request, 2000 chars per rich_text content item — both limits are handled

## Critical Rules

1. **Never use `async`/`await` or Motor in this package.** Celery workers are sync. Use `get_sync_db()` only.
2. **Always call `_clear_processing_flag()`** before returning from any Celery task — on success, failure, and retry paths. Forgetting this permanently locks the task.
3. **Status name lookups are case-insensitive** but the expected names are `To Do`, `In Progress`, `In Review`, `Done`. The pipeline breaks if these statuses don't exist in a space.
4. **LLM output must be parsed with `_parse_json_from_llm()`** — never call `json.loads()` directly on LLM output; models wrap JSON in code fences.
5. **OpenAI caching is only effective when messages from prior turns are already on the task.** First writes/reviews always go through the non-cached path.
