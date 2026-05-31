"""
Celery tasks for the 4-agent content pipeline.

Pipeline:
1. Content Researcher — daily cron, discovers topics, creates tasks for Topic Validator
2. Topic Validator   — validates topics, creates individual tasks for Content Writer
3. Content Writer    — writes blog, publishes to Notion database, marks In Review
4. Content Validator — reviews content, publishes or sends back for revision
"""

import json
import logging
import re
import time
from datetime import datetime

from bson import ObjectId

from app.celery_app import celery
from app.config import settings
from app.worker.db import get_sync_db
from app.worker.llm import execute_with_llm

log = logging.getLogger(__name__)

# Agent roles
ROLE_RESEARCHER = "content_researcher"
ROLE_TOPIC_VALIDATOR = "topic_validator"
ROLE_CONTENT_WRITER = "content_writer"
ROLE_CONTENT_VALIDATOR = "content_validator"

_PROVIDER_KEY_MAP = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "claude": "claude_api_key",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_agent_by_role(db, space_id: str, role: str) -> dict | None:
    """Find an active agent by its pipeline role in a space."""
    return db.agents.find_one({
        "space_id": space_id,
        "role": role,
        "is_active": True,
    })


def _get_status_by_name(db, space_id: str, name: str) -> dict | None:
    """Get a task status by name (case-insensitive)."""
    return db.task_statuses.find_one({
        "space_id": space_id,
        "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
    })


def _get_status_by_position(db, space_id: str, position: str):
    """Get status by position — 'first' for todo, 'last' for done."""
    sort_dir = 1 if position == "first" else -1
    return db.task_statuses.find_one(
        {"space_id": space_id},
        sort=[("position", sort_dir)],
    )


def _get_org_settings(db, space_id: str) -> dict | None:
    """Resolve org settings from a space."""
    space = db.spaces.find_one({"_id": ObjectId(space_id)})
    if not space:
        return None
    org_id = space.get("org_id")
    if not org_id:
        return None
    return db.org_settings.find_one({"org_id": org_id})


def _get_api_key(org_settings: dict, provider: str) -> str:
    """Extract the API key for a provider."""
    key_field = _PROVIDER_KEY_MAP.get(provider, "")
    return (org_settings or {}).get(key_field, "")


def _get_notion_config(org_settings: dict) -> tuple[str, str]:
    """Return (notion_token, notion_database_id)."""
    token = (org_settings or {}).get("notion_token", "")
    db_id = (org_settings or {}).get("notion_database_id", "")
    return token, db_id


def _post_comment(
    db, task_id: str, agent_id: str, agent_name: str,
    content: str, mentions: list | None = None,
):
    """Insert a comment on a task."""
    now = datetime.utcnow()
    db.comments.insert_one({
        "task_id": task_id,
        "content": content,
        "mentions": mentions or [],
        "created_by": agent_id,
        "created_by_name": agent_name,
        "created_at": now,
        "updated_at": now,
    })


def _create_task(
    db, space_id: str, title: str, description: str,
    status_id: str, assignee_id: str, assignee_type: str = "agent",
    extra: dict | None = None,
) -> str:
    """Create a task and return its string ID."""
    now = datetime.utcnow()
    # Position at end
    last_task = db.tasks.find_one(
        {"space_id": space_id, "status_id": status_id},
        sort=[("position", -1)],
    )
    next_pos = (last_task["position"] + 1) if last_task else 0

    doc = {
        "space_id": space_id,
        "status_id": status_id,
        "title": title,
        "description": description,
        "priority": "medium",
        "assignee_id": assignee_id,
        "assignee_type": assignee_type,
        "due_date": None,
        "tags": [],
        "position": next_pos,
        "created_by": assignee_id,
        "created_at": now,
        "updated_at": now,
    }
    if extra:
        doc.update(extra)

    result = db.tasks.insert_one(doc)
    return str(result.inserted_id)


def _move_task(db, task_id: str, status_id: str):
    """Update a task's status."""
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status_id": status_id, "updated_at": datetime.utcnow()}},
    )


def _assign_task(db, task_id: str, agent_id: str):
    """Reassign a task to an agent."""
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {
            "assignee_id": agent_id,
            "assignee_type": "agent",
            "updated_at": datetime.utcnow(),
        }},
    )


def _build_agent_system_prompt(agent: dict, system_extra: str) -> str:
    """Build the full system prompt from agent config + role-specific instructions."""
    agent_name = agent.get("name", "Agent")
    skill_content = agent.get("skill_content", "")

    system_prompt = f"You are an AI agent named '{agent_name}'.\n"
    if skill_content:
        clean_skills = re.sub(r"<[^>]+>", "", skill_content)
        system_prompt += f"\nYour instructions:\n{clean_skills}\n"
    system_prompt += f"\n{system_extra}"
    return system_prompt


def _call_agent_llm(db, agent: dict, space_id: str, system_extra: str, user_prompt: str) -> str:
    """Build system prompt from agent config and call LLM (one-shot)."""
    provider = agent.get("provider", "")
    model = agent.get("model", "")
    agent_name = agent.get("name", "Agent")

    if not provider or not model:
        raise ValueError(f"Agent '{agent_name}' has no provider/model configured.")

    org_settings = _get_org_settings(db, space_id)
    api_key = _get_api_key(org_settings, provider)
    if not api_key:
        raise ValueError(f"No API key for {provider}. Add one in Settings.")

    system_prompt = _build_agent_system_prompt(agent, system_extra)

    return execute_with_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def _call_agent_llm_cached(
    db, agent: dict, space_id: str, messages: list[dict],
) -> tuple[str, list[dict]]:
    """
    Call LLM with a full messages array.
    For OpenAI the entire conversation is sent, enabling prompt caching on
    the prefix (system prompt + earlier turns).
    Returns (response_text, updated_messages_with_assistant_turn).
    """
    from app.worker.llm import execute_with_llm_cached

    provider = agent.get("provider", "")
    model = agent.get("model", "")
    agent_name = agent.get("name", "Agent")

    if not provider or not model:
        raise ValueError(f"Agent '{agent_name}' has no provider/model configured.")

    org_settings = _get_org_settings(db, space_id)
    api_key = _get_api_key(org_settings, provider)
    if not api_key:
        raise ValueError(f"No API key for {provider}. Add one in Settings.")

    return execute_with_llm_cached(
        provider=provider,
        model=model,
        api_key=api_key,
        messages=messages,
    )


def _find_admin_user(db) -> dict | None:
    """Find the first active admin user."""
    return db.users.find_one({"role": "admin", "is_active": True})


def _clear_processing_flag(db, task_id: str):
    """Remove the processing flag."""
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$unset": {"_agent_processing": ""}},
    )


def _log_llm_call(
    db,
    task_id: str,
    task_title: str,
    space_id: str,
    agent_id: str,
    agent_name: str,
    agent_role: str,
    provider: str,
    model: str,
    request: list[dict],
    response: str,
    is_cached: bool,
    duration_ms: int,
):
    """
    Persist an LLM call to the llm_logs collection.
    `request` is the full messages array sent to the LLM (system + all turns).
    `response` is the full text returned by the LLM.
    """
    try:
        db.llm_logs.insert_one({
            "task_id": task_id,
            "task_title": task_title,
            "space_id": space_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_role": agent_role,
            "provider": provider,
            "model": model,
            "request": request,
            "response": response,
            "is_cached": is_cached,
            "duration_ms": duration_ms,
            "created_at": datetime.utcnow(),
        })
    except Exception as exc:
        log.warning(f"Failed to persist LLM log: {exc}")


def _parse_json_from_llm(text: str) -> dict | list:
    """
    Extract JSON from LLM output.
    The output might be wrapped in ```json ... ``` or just raw JSON.
    """
    # Try to find JSON in code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    # Try parsing directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array or object in the text
        for pattern in [r"\[.*\]", r"\{.*\}"]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Could not parse JSON from LLM output: {text}")


# ---------------------------------------------------------------------------
# Beat task — daily cron for Content Researcher (all spaces)
# ---------------------------------------------------------------------------

@celery.task(name="run_content_researcher_all")
def run_content_researcher_all():
    """
    Daily cron: for every space that has a configured Content Researcher
    with provider/model set, run the researcher.
    """
    db = get_sync_db()
    researchers = list(db.agents.find({
        "role": ROLE_RESEARCHER,
        "is_active": True,
        "provider": {"$ne": ""},
        "model": {"$ne": ""},
    }))

    if not researchers:
        log.info("No active Content Researchers found.")
        return

    for agent in researchers:
        space_id = agent["space_id"]
        try:
            run_content_researcher.delay(space_id)
            log.info(f"Dispatched Content Researcher for space {space_id}")
        except Exception as exc:
            log.error(f"Failed to dispatch researcher for space {space_id}: {exc}")


# ---------------------------------------------------------------------------
# Beat task — poll for pipeline tasks
# ---------------------------------------------------------------------------

@celery.task(name="poll_agent_tasks")
def poll_agent_tasks():
    """
    Periodic: find tasks assigned to pipeline agents that are in actionable
    statuses and dispatch the appropriate pipeline step.
    """
    db = get_sync_db()
    log.info("Polling for pipeline agent tasks...")

    # Find all tasks assigned to agents
    agent_tasks = list(
        db.tasks.find({"assignee_type": "agent", "assignee_id": {"$ne": None}})
    )

    if not agent_tasks:
        return

    dispatched = 0
    for task in agent_tasks:
        task_id = str(task["_id"])
        space_id = task["space_id"]
        agent_id = task.get("assignee_id")

        # Skip if already processing
        if task.get("_agent_processing"):
            continue

        # Look up the agent to determine role
        agent = db.agents.find_one({"_id": ObjectId(agent_id)}) if agent_id else None
        if not agent:
            continue

        role = agent.get("role", "")
        status_id = task.get("status_id", "")

        # Determine which statuses trigger which roles
        todo_status = _get_status_by_name(db, space_id, "To Do")
        review_status = _get_status_by_name(db, space_id, "In Review")

        should_dispatch = False

        if role == ROLE_TOPIC_VALIDATOR and todo_status and status_id == str(todo_status["_id"]):
            should_dispatch = True
        elif role == ROLE_CONTENT_WRITER and todo_status and status_id == str(todo_status["_id"]):
            should_dispatch = True
        elif role == ROLE_CONTENT_VALIDATOR and review_status and status_id == str(review_status["_id"]):
            should_dispatch = True

        if not should_dispatch:
            continue

        # Mark as processing
        db.tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"_agent_processing": True}},
        )

        # Dispatch the right pipeline task
        if role == ROLE_TOPIC_VALIDATOR:
            run_topic_validator.delay(task_id, space_id)
        elif role == ROLE_CONTENT_WRITER:
            run_content_writer.delay(task_id, space_id)
        elif role == ROLE_CONTENT_VALIDATOR:
            run_content_validator.delay(task_id, space_id)

        dispatched += 1

    if dispatched:
        log.info(f"Dispatched {dispatched} pipeline task(s).")


# ---------------------------------------------------------------------------
# Pipeline step 1: Content Researcher
# ---------------------------------------------------------------------------

@celery.task(name="run_content_researcher", bind=True, max_retries=2)
def run_content_researcher(self, space_id: str):
    """
    Discover topics for the space's niche, then create a task
    assigned to the Topic Validator with the list of topics.
    Uses previous blog topics as context to avoid duplication.
    """
    db = get_sync_db()
    now = datetime.utcnow

    # Load researcher agent
    agent = _get_agent_by_role(db, space_id, ROLE_RESEARCHER)
    if not agent:
        log.warning(f"No active Content Researcher in space {space_id}")
        return

    agent_id = str(agent["_id"])
    agent_name = agent.get("name", "Content Researcher")

    # Load space config
    space = db.spaces.find_one({"_id": ObjectId(space_id)})
    if not space:
        log.error(f"Space {space_id} not found")
        return

    niche = space.get("niche", "")
    topic_count = space.get("topic_count", 5)

    if not niche:
        log.warning(f"Space {space_id} has no niche configured, skipping researcher.")
        return

    # ── Gather previous blog topics as context ──
    # Pull titles from all existing tasks in this space (writer tasks)
    writer = _get_agent_by_role(db, space_id, ROLE_CONTENT_WRITER)
    previous_topics = []
    if writer:
        writer_id = str(writer["_id"])
        past_tasks = list(
            db.tasks.find(
                {"space_id": space_id, "assignee_id": writer_id, "assignee_type": "agent"},
                {"title": 1},
            )
            .sort("created_at", -1)
            .limit(50)
        )
        previous_topics = [t["title"] for t in past_tasks if t.get("title")]

    # Also check tasks assigned to validators (those were topic batches)
    validator = _get_agent_by_role(db, space_id, ROLE_TOPIC_VALIDATOR)
    if validator:
        val_tasks = list(
            db.tasks.find(
                {"space_id": space_id, "assignee_id": str(validator["_id"]), "assignee_type": "agent"},
                {"description": 1},
            )
            .sort("created_at", -1)
            .limit(10)
        )
        for vt in val_tasks:
            desc = vt.get("description", "")
            # Extract topic titles from validator task descriptions
            for line in desc.split("\n"):
                line = line.strip().strip("-").strip("*").strip()
                if line and len(line) > 10 and "title" not in line.lower()[:10]:
                    previous_topics.append(line)

    # Deduplicate
    previous_topics = list(dict.fromkeys(previous_topics))[:50]

    # Build previous topics context
    previous_context = ""
    if previous_topics:
        topic_list = "\n".join(f"- {t}" for t in previous_topics)
        previous_context = (
            f"\n\n## Previously covered topics (DO NOT repeat these):\n{topic_list}\n"
        )

    # Call LLM
    system_extra = (
        "You are a content research specialist. Your job is to discover trending, "
        "engaging blog topics.\n\n"
        "IMPORTANT: Respond ONLY with a valid JSON array of topic objects. No extra text.\n"
        "Each topic object must have:\n"
        '- "title": a compelling blog title\n'
        '- "description": 2-3 sentence summary of what the blog should cover\n'
        '- "category": the content category\n'
        '- "focus_keyword": the primary SEO keyword\n'
    )

    user_prompt = (
        f"Research and suggest {topic_count} NEW trending blog topics in the niche: \"{niche}\".\n\n"
        f"The topics should be:\n"
        f"- Fresh and trending (as of today)\n"
        f"- SEO-friendly with clear search intent\n"
        f"- Suitable for a detailed blog post (1500-2500 words)\n"
        f"- Diverse within the niche\n"
        f"- NOT duplicate or overlap with previously covered topics\n"
        f"{previous_context}\n"
        f"Return ONLY a JSON array with {topic_count} topic objects."
    )

    try:
        t0 = time.time()
        output = _call_agent_llm(db, agent, space_id, system_extra, user_prompt)
        _log_llm_call(
            db, task_id="", task_title=f"Research: {niche}",
            space_id=space_id, agent_id=agent_id, agent_name=agent_name,
            agent_role=ROLE_RESEARCHER,
            provider=agent.get("provider", ""), model=agent.get("model", ""),
            request=[
                {"role": "system", "content": _build_agent_system_prompt(agent, system_extra)},
                {"role": "user", "content": user_prompt},
            ],
            response=output,
            is_cached=False, duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        log.exception(f"Content Researcher LLM failed for space {space_id}: {exc}")
        try:
            self.retry(countdown=120)
        except self.MaxRetriesExceededError:
            pass
        return

    # Find the Topic Validator to assign the task
    validator = _get_agent_by_role(db, space_id, ROLE_TOPIC_VALIDATOR)
    if not validator:
        log.error(f"No Topic Validator in space {space_id}")
        return

    validator_id = str(validator["_id"])
    todo_status = _get_status_by_name(db, space_id, "To Do")
    if not todo_status:
        log.error(f"No 'To Do' status in space {space_id}")
        return

    # Create task for Topic Validator
    task_id = _create_task(
        db,
        space_id=space_id,
        title=f"Validate topics for: {niche}",
        description=f"Review and validate the following topics discovered by Content Researcher:\n\n{output}",
        status_id=str(todo_status["_id"]),
        assignee_id=validator_id,
    )

    log.info(f"Content Researcher created task {task_id} for Topic Validator in space {space_id}")

    # Dispatch Topic Validator immediately
    run_topic_validator.delay(task_id, space_id)


# ---------------------------------------------------------------------------
# Pipeline step 2: Topic Validator
# ---------------------------------------------------------------------------

@celery.task(name="run_topic_validator", bind=True, max_retries=2)
def run_topic_validator(self, task_id: str, space_id: str):
    """
    Validate topics and create individual Content Writer tasks
    for each approved topic.
    """
    db = get_sync_db()
    now = datetime.utcnow

    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        log.error(f"Task {task_id} not found")
        return

    agent = _get_agent_by_role(db, space_id, ROLE_TOPIC_VALIDATOR)
    if not agent:
        log.error(f"No Topic Validator in space {space_id}")
        _clear_processing_flag(db, task_id)
        return

    agent_id = str(agent["_id"])
    agent_name = agent.get("name", "Topic Validator")

    # Move to In Progress
    in_progress = _get_status_by_name(db, space_id, "In Progress")
    if in_progress:
        _move_task(db, task_id, str(in_progress["_id"]))

    _post_comment(db, task_id, agent_id, agent_name, "Validating topics...")

    # Call LLM
    system_extra = (
        "You are a content strategy validator. Review topics and shortlist the best ones.\n\n"
        "IMPORTANT: Respond ONLY with a valid JSON array of approved topic objects.\n"
        "Each approved topic must have:\n"
        '- "title": the approved blog title (refined if needed)\n'
        '- "description": refined 2-3 sentence description\n'
        '- "category": content category\n'
        '- "focus_keyword": primary SEO keyword\n'
        '- "reason": brief reason why this topic was approved\n\n'
        "Only include topics that are strong enough to publish. Remove weak or duplicate topics."
    )

    task_description = task.get("description", "")
    user_prompt = (
        f"Review and validate these topics. Approve only the best ones:\n\n{task_description}"
    )

    try:
        t0 = time.time()
        output = _call_agent_llm(db, agent, space_id, system_extra, user_prompt)
        _log_llm_call(
            db, task_id=task_id, task_title=task.get("title", ""),
            space_id=space_id, agent_id=agent_id, agent_name=agent_name,
            agent_role=ROLE_TOPIC_VALIDATOR,
            provider=agent.get("provider", ""), model=agent.get("model", ""),
            request=[
                {"role": "system", "content": _build_agent_system_prompt(agent, system_extra)},
                {"role": "user", "content": user_prompt},
            ],
            response=output,
            is_cached=False, duration_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        log.exception(f"Topic Validator LLM failed: {exc}")
        _post_comment(db, task_id, agent_id, agent_name, f"Failed: {str(exc)}")
        _clear_processing_flag(db, task_id)
        try:
            self.retry(countdown=60)
        except self.MaxRetriesExceededError:
            pass
        return

    # Parse approved topics
    try:
        approved_topics = _parse_json_from_llm(output)
        if not isinstance(approved_topics, list):
            approved_topics = [approved_topics]
    except ValueError as exc:
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Could not parse validated topics: {str(exc)}",
        )
        _clear_processing_flag(db, task_id)
        return

    # Find Content Writer
    writer = _get_agent_by_role(db, space_id, ROLE_CONTENT_WRITER)
    if not writer:
        _post_comment(db, task_id, agent_id, agent_name, "No Content Writer agent found.")
        _clear_processing_flag(db, task_id)
        return

    writer_id = str(writer["_id"])
    todo_status = _get_status_by_name(db, space_id, "To Do")
    if not todo_status:
        _clear_processing_flag(db, task_id)
        return

    # Create individual tasks for Content Writer
    created_tasks = []
    for topic in approved_topics:
        title = topic.get("title", "Untitled Topic")
        desc = topic.get("description", "")
        category = topic.get("category", "")
        keyword = topic.get("focus_keyword", "")

        task_desc = (
            f"Write a comprehensive blog post on this topic.\n\n"
            f"**Title:** {title}\n"
            f"**Description:** {desc}\n"
            f"**Category:** {category}\n"
            f"**Focus Keyword:** {keyword}\n"
        )

        new_task_id = _create_task(
            db,
            space_id=space_id,
            title=title,
            description=task_desc,
            status_id=str(todo_status["_id"]),
            assignee_id=writer_id,
        )
        created_tasks.append(title)

        # Dispatch Content Writer immediately
        run_content_writer.delay(new_task_id, space_id)

    # Mark this validator task as Done
    done_status = _get_status_by_name(db, space_id, "Done")
    if done_status:
        _move_task(db, task_id, str(done_status["_id"]))

    _post_comment(
        db, task_id, agent_id, agent_name,
        f"Validated and approved {len(created_tasks)} topic(s). "
        f"Created tasks for Content Writer:\n" +
        "\n".join(f"- {t}" for t in created_tasks),
    )

    _clear_processing_flag(db, task_id)
    log.info(f"Topic Validator approved {len(created_tasks)} topics in space {space_id}")


# ---------------------------------------------------------------------------
# Pipeline step 3: Content Writer
# ---------------------------------------------------------------------------

@celery.task(name="run_content_writer", bind=True, max_retries=2)
def run_content_writer(self, task_id: str, space_id: str):
    """
    Write blog content and publish to Notion database.
    Handles both new content and revisions (when task has feedback comments).

    On OpenAI the conversation history is cached on the task so that
    revisions only send the new feedback — system prompt, skills, and
    previous turns are served from OpenAI's prompt cache.
    """
    db = get_sync_db()

    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        log.error(f"Task {task_id} not found")
        return

    agent = _get_agent_by_role(db, space_id, ROLE_CONTENT_WRITER)
    if not agent:
        log.error(f"No Content Writer in space {space_id}")
        _clear_processing_flag(db, task_id)
        return

    agent_id = str(agent["_id"])
    agent_name = agent.get("name", "Content Writer")
    provider = agent.get("provider", "")

    # Check if this is a revision (task has a notion_page_id)
    notion_page_id = task.get("notion_page_id")
    is_revision = bool(notion_page_id)

    # Move to In Progress
    in_progress = _get_status_by_name(db, space_id, "In Progress")
    if in_progress:
        _move_task(db, task_id, str(in_progress["_id"]))

    if is_revision:
        _post_comment(db, task_id, agent_id, agent_name, "Revising content based on feedback...")
    else:
        _post_comment(db, task_id, agent_id, agent_name, "Writing content...")

    # Get Notion config
    org_settings = _get_org_settings(db, space_id)
    notion_token, notion_database_id = _get_notion_config(org_settings)

    if not notion_token or not notion_database_id:
        _post_comment(
            db, task_id, agent_id, agent_name,
            "Notion is not configured. Please add token and database ID in Settings.",
        )
        _clear_processing_flag(db, task_id)
        return

    task_title = task.get("title", "")
    task_description = task.get("description", "")

    # ------------------------------------------------------------------
    # Build messages — cached path (OpenAI) vs full-context path (others)
    # ------------------------------------------------------------------

    # The system prompt is the same for first write and revisions.
    # On the cached path it is sent once and reused from cache.
    _WRITER_SYSTEM_EXTRA = (
        "You are a professional blog content writer. Write high-quality, SEO-optimized "
        "blog posts.\n"
        "When asked to revise, incorporate all feedback and return the complete updated content.\n\n"
        "IMPORTANT: Respond ONLY with valid JSON. No extra text.\n"
        "The JSON object must have these fields:\n"
        '- "title": the blog title\n'
        '- "slug": URL-friendly slug (lowercase, hyphens, no special chars)\n'
        '- "description": 1-2 sentence meta description for the blog\n'
        '- "category": content category\n'
        '- "tags": array of relevant tags (3-5 tags)\n'
        '- "focus_keyword": primary SEO keyword\n'
        '- "meta_title": SEO meta title (under 60 chars)\n'
        '- "meta_description": SEO meta description (under 160 chars)\n'
        '- "content": the full blog post in Markdown (aim for 1500-2500 words, '
        'well-structured with headings, subheadings, lists, and rich formatting)\n'
    )

    existing_messages = task.get("_llm_messages_writer", [])
    use_cache = provider == "openai" and is_revision and len(existing_messages) > 0

    if use_cache:
        # ── CACHED PATH (OpenAI only) ──
        # The assistant already has the full context from previous turns.
        # We only append the new reviewer feedback — no need to re-send
        # system prompt, skills, original task, or blog content.
        comments = list(
            db.comments.find({"task_id": task_id}).sort("created_at", -1).limit(5)
        )
        feedback = "\n".join(
            f"- {c.get('created_by_name', 'Reviewer')}: {c['content']}"
            for c in comments
            if c.get("created_by") != agent_id
        )

        revision_prompt = (
            f"The content validator has reviewed your blog post and requests revisions.\n\n"
            f"## Reviewer Feedback\n{feedback}\n\n"
            f"Revise the blog post addressing all the feedback above. "
            f"Return the complete revised JSON in the same format."
        )
        messages = existing_messages + [{"role": "user", "content": revision_prompt}]
        log.info(
            f"Writer using cached messages for task {task_id} "
            f"({len(existing_messages)} existing msgs)"
        )

    elif is_revision:
        # ── FULL-CONTEXT REVISION (non-OpenAI or no cached messages) ──
        comments = list(
            db.comments.find({"task_id": task_id}).sort("created_at", -1).limit(5)
        )
        feedback = "\n".join(
            f"- {c.get('created_by_name', 'Reviewer')}: {c['content']}"
            for c in comments
            if c.get("created_by") != agent_id
        )
        try:
            from app.worker.notion import read_page_content
            current_content = read_page_content(notion_token, notion_page_id)
        except Exception:
            current_content = "(Could not read current content)"

        system_prompt = _build_agent_system_prompt(agent, _WRITER_SYSTEM_EXTRA)
        user_prompt = (
            f"Revise this blog post based on the reviewer feedback.\n\n"
            f"## Original Task\n{task_title}\n{task_description}\n\n"
            f"## Current Content\n{current_content}\n\n"
            f"## Reviewer Feedback\n{feedback}\n\n"
            f"Apply all the feedback and improve the content. Return JSON only."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        log.info(f"Writer using full-context revision for task {task_id}")

    else:
        # ── FIRST WRITE ──
        system_prompt = _build_agent_system_prompt(agent, _WRITER_SYSTEM_EXTRA)
        user_prompt = (
            f"Write a comprehensive blog post for:\n\n"
            f"**Title:** {task_title}\n"
            f"**Details:** {task_description}\n\n"
            f"Write detailed, engaging, SEO-optimized content. Return JSON only."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        log.info(f"Writer building fresh messages for task {task_id}")

    # ── Call LLM ──
    try:
        t0 = time.time()
        output, updated_messages = _call_agent_llm_cached(
            db, agent, space_id, messages,
        )
        dur = int((time.time() - t0) * 1000)

        # Persist conversation for future cache hits
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_llm_messages_writer": updated_messages}},
        )

        # Log LLM call — store the full request messages + response
        _log_llm_call(
            db, task_id=task_id, task_title=task_title,
            space_id=space_id, agent_id=agent_id, agent_name=agent_name,
            agent_role=ROLE_CONTENT_WRITER,
            provider=provider, model=agent.get("model", ""),
            request=messages, response=output,
            is_cached=use_cache, duration_ms=dur,
        )
    except Exception as exc:
        log.exception(f"Content Writer LLM failed: {exc}")
        _post_comment(db, task_id, agent_id, agent_name, f"Failed: {str(exc)}")
        _clear_processing_flag(db, task_id)
        try:
            self.retry(countdown=60)
        except self.MaxRetriesExceededError:
            pass
        return

    # Parse JSON output
    try:
        blog_data = _parse_json_from_llm(output)
        if isinstance(blog_data, list):
            blog_data = blog_data[0]
    except ValueError as exc:
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Could not parse blog JSON: {str(exc)}",
        )
        _clear_processing_flag(db, task_id)
        return

    # Extract fields
    blog_title = blog_data.get("title", task_title)
    slug = blog_data.get("slug", "")
    description = blog_data.get("description", "")
    category = blog_data.get("category", "")
    tags = blog_data.get("tags", [])
    focus_keyword = blog_data.get("focus_keyword", "")
    meta_title = blog_data.get("meta_title", "")
    meta_description = blog_data.get("meta_description", "")
    content = blog_data.get("content", "")

    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    # Publish to Notion
    from app.worker.notion import create_blog_entry, update_blog_content

    try:
        if is_revision:
            # Update existing Notion page
            update_blog_content(
                token=notion_token,
                page_id=notion_page_id,
                content=content,
                properties={
                    "title": {"title": [{"text": {"content": blog_title}}]},
                    "slug": {"rich_text": [{"text": {"content": slug}}]},
                    "status": {"status": {"name": "Draft"}},
                    "description": {"rich_text": [{"text": {"content": description}}]},
                    "category": {"rich_text": [{"text": {"content": category}}]},
                    "tags": {"multi_select": [{"name": t} for t in tags if t]},
                    "focus_keyword": {"rich_text": [{"text": {"content": focus_keyword}}]},
                    "meta_title": {"rich_text": [{"text": {"content": meta_title}}]},
                    "meta_description": {"rich_text": [{"text": {"content": meta_description}}]},
                },
            )
            notion_url = f"https://notion.so/{notion_page_id.replace('-', '')}"
        else:
            # Create new Notion page
            result = create_blog_entry(
                token=notion_token,
                database_id=notion_database_id,
                title=blog_title,
                slug=slug,
                description=description,
                category=category,
                tags=tags,
                focus_keyword=focus_keyword,
                meta_title=meta_title,
                meta_description=meta_description,
                content=content,
                status="Draft",
            )
            notion_page_id = result["page_id"]
            notion_url = result["url"]

            # Store Notion page ID on the task for future reference
            db.tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {"notion_page_id": notion_page_id}},
            )

    except Exception as exc:
        log.exception(f"Notion publish failed: {exc}")
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Failed to publish to Notion: {str(exc)}",
        )
        _clear_processing_flag(db, task_id)
        return

    # Move task to "In Review" and assign to Content Validator
    review_status = _get_status_by_name(db, space_id, "In Review")
    if review_status:
        _move_task(db, task_id, str(review_status["_id"]))

    validator = _get_agent_by_role(db, space_id, ROLE_CONTENT_VALIDATOR)
    validator_id = str(validator["_id"]) if validator else None
    validator_name = validator.get("name", "Content Validator") if validator else None

    if validator_id:
        _assign_task(db, task_id, validator_id)

    # Comment with Notion link and @mention validator
    action = "Revised" if is_revision else "Written"
    comment_parts = [
        f"Blog {action.lower()} and published to Notion.",
        f"",
        f"Notion page: {notion_url}",
        f"",
        f"Please review the content at the above link.",
    ]
    mentions = []
    if validator_id and validator_name:
        comment_parts.insert(0, f"@{validator_name}")
        mentions.append({"id": validator_id, "type": "agent", "name": validator_name})

    _post_comment(
        db, task_id, agent_id, agent_name,
        "\n".join(comment_parts),
        mentions=mentions,
    )

    _clear_processing_flag(db, task_id)
    log.info(f"Content Writer {action.lower()} blog for task {task_id}")


# ---------------------------------------------------------------------------
# Pipeline step 4: Content Validator
# ---------------------------------------------------------------------------

@celery.task(name="run_content_validator", bind=True, max_retries=2)
def run_content_validator(self, task_id: str, space_id: str):
    """
    Review content from Notion. If OK → publish, if not → send back to writer.

    On OpenAI the conversation history is cached on the task so that
    subsequent reviews keep the system prompt + previous feedback in the
    prompt cache.  The revised content is always re-sent (it changed on
    Notion), but all prior turns are cached.
    """
    db = get_sync_db()

    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        log.error(f"Task {task_id} not found")
        return

    agent = _get_agent_by_role(db, space_id, ROLE_CONTENT_VALIDATOR)
    if not agent:
        log.error(f"No Content Validator in space {space_id}")
        _clear_processing_flag(db, task_id)
        return

    agent_id = str(agent["_id"])
    agent_name = agent.get("name", "Content Validator")
    provider = agent.get("provider", "")

    notion_page_id = task.get("notion_page_id")

    # Find the Notion URL from writer's comments
    notion_url_from_comment = ""
    if notion_page_id:
        comments = list(db.comments.find({"task_id": task_id}).sort("created_at", -1))
        for c in comments:
            url_match = re.search(r"(https?://(?:www\.)?notion\.so/\S+)", c.get("content", ""))
            if url_match:
                notion_url_from_comment = url_match.group(1)
                break

    if not notion_page_id:
        _post_comment(
            db, task_id, agent_id, agent_name,
            "No Notion page linked to this task. Cannot review.",
        )
        _clear_processing_flag(db, task_id)
        return

    notion_link = notion_url_from_comment or f"https://notion.so/{notion_page_id.replace('-', '')}"

    _post_comment(
        db, task_id, agent_id, agent_name,
        f"Reviewing content from Notion: {notion_link}",
    )

    # Get Notion config
    org_settings = _get_org_settings(db, space_id)
    notion_token, _ = _get_notion_config(org_settings)

    if not notion_token:
        _post_comment(db, task_id, agent_id, agent_name, "Notion token not configured.")
        _clear_processing_flag(db, task_id)
        return

    # Read the content from Notion (always needed — content changes each revision)
    from app.worker.notion import read_page_content, read_page_properties, update_blog_status

    try:
        content = read_page_content(notion_token, notion_page_id)
        properties = read_page_properties(notion_token, notion_page_id)
    except Exception as exc:
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Failed to read Notion page: {str(exc)}",
        )
        _clear_processing_flag(db, task_id)
        return

    blog_title = properties.get("title", task.get("title", ""))

    # ------------------------------------------------------------------
    # Build messages — cached path (OpenAI) vs full-context path (others)
    # ------------------------------------------------------------------

    _VALIDATOR_SYSTEM_EXTRA = (
        "You are a content quality reviewer. Evaluate blog posts for quality, accuracy, "
        "SEO optimization, readability, and completeness.\n\n"
        "IMPORTANT: Respond ONLY with valid JSON. No extra text.\n"
        "The JSON object must have:\n"
        '- "approved": true or false\n'
        '- "score": quality score from 1-10\n'
        '- "feedback": detailed feedback explaining your decision\n'
        '- "issues": array of specific issues found (empty if approved)\n'
        '- "suggestions": array of improvement suggestions\n'
    )

    existing_messages = task.get("_llm_messages_validator", [])
    use_cache = provider == "openai" and len(existing_messages) > 0

    if use_cache:
        # ── CACHED PATH (OpenAI only) ──
        # System prompt + skills + previous review turns are cached.
        # We only append the new review request with updated content.
        review_prompt = (
            f"The writer has revised the content based on your previous feedback. "
            f"Review the updated version below.\n\n"
            f"**Title:** {blog_title}\n"
            f"**Category:** {properties.get('category', '')}\n"
            f"**Focus Keyword:** {properties.get('focus_keyword', '')}\n"
            f"**Meta Title:** {properties.get('meta_title', '')}\n"
            f"**Meta Description:** {properties.get('meta_description', '')}\n\n"
            f"## Revised Content\n{content}\n\n"
            f"Evaluate the quality of the revised content. "
            f"Check whether your previous issues have been addressed. Return JSON only."
        )
        messages = existing_messages + [{"role": "user", "content": review_prompt}]
        log.info(
            f"Validator using cached messages for task {task_id} "
            f"({len(existing_messages)} existing msgs)"
        )
    else:
        # ── FRESH PATH (first review or non-OpenAI) ──
        system_prompt = _build_agent_system_prompt(agent, _VALIDATOR_SYSTEM_EXTRA)
        user_prompt = (
            f"Review this blog post for publication:\n\n"
            f"**Title:** {blog_title}\n"
            f"**Category:** {properties.get('category', '')}\n"
            f"**Focus Keyword:** {properties.get('focus_keyword', '')}\n"
            f"**Meta Title:** {properties.get('meta_title', '')}\n"
            f"**Meta Description:** {properties.get('meta_description', '')}\n\n"
            f"## Content\n{content}\n\n"
            f"Evaluate the quality. Approve only if the content is well-written, "
            f"accurate, properly structured, and SEO-optimized. Return JSON only."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        log.info(f"Validator building fresh messages for task {task_id}")

    # ── Call LLM ──
    try:
        t0 = time.time()
        output, updated_messages = _call_agent_llm_cached(
            db, agent, space_id, messages,
        )
        dur = int((time.time() - t0) * 1000)

        # Persist conversation for future cache hits
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_llm_messages_validator": updated_messages}},
        )

        # Log LLM call — store the full request messages + response
        _log_llm_call(
            db, task_id=task_id, task_title=blog_title,
            space_id=space_id, agent_id=agent_id, agent_name=agent_name,
            agent_role=ROLE_CONTENT_VALIDATOR,
            provider=provider, model=agent.get("model", ""),
            request=messages, response=output,
            is_cached=use_cache, duration_ms=dur,
        )
    except Exception as exc:
        log.exception(f"Content Validator LLM failed: {exc}")
        _post_comment(db, task_id, agent_id, agent_name, f"Review failed: {str(exc)}")
        _clear_processing_flag(db, task_id)
        try:
            self.retry(countdown=60)
        except self.MaxRetriesExceededError:
            pass
        return

    # Parse review result
    try:
        review = _parse_json_from_llm(output)
        if isinstance(review, list):
            review = review[0]
    except ValueError:
        # If we can't parse, treat as needing revision
        review = {"approved": False, "feedback": output, "issues": [], "suggestions": []}

    approved = review.get("approved", False)
    feedback = review.get("feedback", "")
    issues = review.get("issues", [])
    suggestions = review.get("suggestions", [])
    score = review.get("score", 0)

    if approved:
        # Generate thumbnail SVG, upload to Notion page, then clean up
        from app.worker.thumbnail import generate_thumbnail, delete_thumbnail
        from app.worker.notion import upload_image_to_page

        try:
            svg_path = generate_thumbnail(blog_title)
            upload_image_to_page(notion_token, notion_page_id, svg_path)
            # Extract just the filename (without extension) for deletion
            import os
            svg_filename = os.path.basename(svg_path)
            delete_thumbnail(svg_filename)
            log.info(f"Thumbnail uploaded and local file deleted for task {task_id}")
        except Exception as exc:
            log.warning(f"Thumbnail generation/upload failed for task {task_id}: {exc}")
            # Non-fatal — continue with publishing

        # Update Notion status to Published
        try:
            update_blog_status(notion_token, notion_page_id, "Published")
        except Exception as exc:
            log.error(f"Failed to update Notion status: {exc}")

        # Move task to Done
        done_status = _get_status_by_name(db, space_id, "Done")
        if done_status:
            _move_task(db, task_id, str(done_status["_id"]))

        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Content approved! (Score: {score}/10)\n\n"
            f"**Remarks:** {feedback}\n\n"
            f"Notion page: {notion_link}\n"
            f"Thumbnail uploaded. Status changed to **Published**. Task complete.",
        )

        # Notify admin
        admin = _find_admin_user(db)
        if admin:
            admin_name = admin.get("full_name", "Admin")
            admin_id = str(admin["_id"])
            _post_comment(
                db, task_id, agent_id, agent_name,
                f"@{admin_name} Blog \"{blog_title}\" has been reviewed and published.\n"
                f"Notion: {notion_link}",
                mentions=[{"id": admin_id, "type": "user", "name": admin_name}],
            )

    else:
        # Increment revision count
        revision_count = task.get("_revision_count", 0) + 1
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_revision_count": revision_count}},
        )

        # After 5 revision rounds, stop the loop and escalate to admin
        if revision_count >= 5:
            admin = _find_admin_user(db)
            admin_name = admin.get("full_name", "Admin") if admin else "Admin"
            admin_id = str(admin["_id"]) if admin else None

            _post_comment(
                db, task_id, agent_id, agent_name,
                f"@{admin_name} Content has gone through {revision_count} revision cycles "
                f"without approval (latest score: {score}/10). "
                f"Escalating to you for manual review.\n\n"
                f"Notion page: {notion_link}\n\n"
                f"**Last feedback:** {feedback}",
                mentions=[{"id": admin_id, "type": "user", "name": admin_name}] if admin_id else [],
            )

            # Assign to admin and move to To Do
            if admin_id:
                db.tasks.update_one(
                    {"_id": ObjectId(task_id)},
                    {"$set": {
                        "assignee_id": admin_id,
                        "assignee_type": "user",
                        "updated_at": datetime.utcnow(),
                    }},
                )
            todo_status = _get_status_by_name(db, space_id, "To Do")
            if todo_status:
                _move_task(db, task_id, str(todo_status["_id"]))

            _clear_processing_flag(db, task_id)
            log.info(f"Task {task_id} escalated to admin after {revision_count} revisions")
            return

        # Send back to Content Writer
        writer = _get_agent_by_role(db, space_id, ROLE_CONTENT_WRITER)
        if not writer:
            _post_comment(db, task_id, agent_id, agent_name, "No Content Writer to send back to.")
            _clear_processing_flag(db, task_id)
            return

        writer_id = str(writer["_id"])
        writer_name = writer.get("name", "Content Writer")

        # Build detailed feedback comment with Notion link
        feedback_parts = [
            f"@{writer_name} Content needs revision. (Score: {score}/10) — Revision {revision_count}/5",
            f"",
            f"Notion page: {notion_link}",
            f"",
        ]
        if feedback:
            feedback_parts.append(f"**Remarks:** {feedback}")
            feedback_parts.append("")
        if issues:
            feedback_parts.append("**Issues found:**")
            for issue in issues:
                feedback_parts.append(f"- {issue}")
            feedback_parts.append("")
        if suggestions:
            feedback_parts.append("**Suggestions:**")
            for suggestion in suggestions:
                feedback_parts.append(f"- {suggestion}")

        feedback_text = "\n".join(feedback_parts)

        _post_comment(
            db, task_id, agent_id, agent_name,
            feedback_text,
            mentions=[{"id": writer_id, "type": "agent", "name": writer_name}],
        )

        # Reassign to Content Writer and move to To Do
        _assign_task(db, task_id, writer_id)
        todo_status = _get_status_by_name(db, space_id, "To Do")
        if todo_status:
            _move_task(db, task_id, str(todo_status["_id"]))

    _clear_processing_flag(db, task_id)
    log.info(
        f"Content Validator {'approved' if approved else 'rejected'} "
        f"task {task_id} (score: {score})"
    )
