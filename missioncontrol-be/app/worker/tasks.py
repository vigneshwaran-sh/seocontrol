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
from datetime import datetime

from bson import ObjectId

from app.celery_app import celery
from app.config import settings
from app.worker.db import get_sync_db

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

# Topic loop tuning
TOPIC_APPROVAL_TARGET = 3   # approved topics needed before the batch task is Done
TOPIC_MAX_REVISIONS = 5     # researcher↔validator rounds before escalating to admin
DEFAULT_TOPIC_COUNT = 10    # topics proposed per round when none is given


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


def _extract_revision_feedback(comment_content: str) -> str:
    """
    Extract only the Remarks and Suggestions sections from a validator
    feedback comment. Everything else (score header, Notion link, issues, etc.)
    is stripped so the writer only receives actionable guidance.

    Falls back to the full comment if neither section is found (e.g. plain-text
    comments posted by humans).
    """
    parts = []

    # **Remarks:** <single-line text>
    remarks_match = re.search(r'\*\*Remarks:\*\*\s*(.+)', comment_content)
    if remarks_match:
        text = remarks_match.group(1).strip()
        if text:
            parts.append(f"Remarks: {text}")

    # **Suggestions:** followed by bullet lines
    suggestions_match = re.search(
        r'\*\*Suggestions:\*\*[ \t]*\n((?:[ \t]*-[ \t]+.+\n?)*)',
        comment_content,
        re.MULTILINE,
    )
    if suggestions_match:
        bullets = suggestions_match.group(1).strip()
        if bullets:
            parts.append(f"Suggestions:\n{bullets}")

    if parts:
        return "\n\n".join(parts)

    # Fallback for plain-text / human comments: keep the text but drop any
    # line referencing a Notion page URL (e.g. the "Reviewing content from
    # Notion: https://notion.so/..." status comment) so it never reaches the LLM.
    cleaned_lines = [
        line
        for line in comment_content.splitlines()
        if not re.search(r"https?://(?:www\.)?notion\.so/\S+", line)
    ]
    return "\n".join(cleaned_lines).strip()


def _html_to_text(html: str) -> str:
    """Convert TipTap HTML to readable plain text preserving structure."""
    # Block-level tags → newline before their content
    html = re.sub(r"<(p|div|br|h[1-6])[^>]*>", "\n", html, flags=re.IGNORECASE)
    # List items → bullet prefix
    html = re.sub(r"<li[^>]*>", "\n- ", html, flags=re.IGNORECASE)
    # Closing block tags → newline
    html = re.sub(r"</(p|div|h[1-6]|ul|ol|li)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    # Collapse 3+ consecutive newlines to 2
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _build_agent_system_prompt(agent: dict, system_extra: str) -> str:
    """Build the full system prompt from agent config + role-specific instructions."""
    agent_name = agent.get("name", "Agent")
    skill_content = agent.get("skill_content", "")

    system_prompt = f"You are an AI agent named '{agent_name}'.\n"
    if skill_content:
        clean_skills = _html_to_text(skill_content)
        if clean_skills:
            system_prompt += f"\nYour instructions:\n{clean_skills}\n"
    system_prompt += f"\n{system_extra}"
    return system_prompt


def _call_agent_llm(
    db, agent: dict, space_id: str, system_extra: str, user_prompt: str,
    task_id: str = "",
) -> str:
    """Build system prompt from agent config and call LLM (one-shot)."""
    provider = agent.get("provider", "")
    model = agent.get("model", "")
    agent_name = agent.get("name", "Agent")
    agent_id = str(agent.get("_id", ""))

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
        task_id=task_id,
        agent_id=agent_id,
        space_id=space_id,
    )


def _call_agent_llm_cached(
    db, agent: dict, space_id: str, messages: list[dict],
    task_id: str = "",
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
    agent_id = str(agent.get("_id", ""))

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
        task_id=task_id,
        agent_id=agent_id,
        space_id=space_id,
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


def _due_reached(due_date) -> bool:
    """
    True if a task's due date has arrived (today or earlier), or if there is
    no due date at all. Future due dates (e.g. tomorrow) return False so the
    researcher waits until that day.
    """
    if not due_date:
        return True
    try:
        if hasattr(due_date, "date"):
            d = due_date.date()
        else:
            d = datetime.fromisoformat(str(due_date).replace("Z", "+00:00")).date()
    except Exception:
        return True
    return d <= datetime.utcnow().date()


def _parse_topic_count(text: str, default: int = DEFAULT_TOPIC_COUNT) -> int:
    """Extract the requested number of topics from a task title/description."""
    m = re.search(r"\b(\d{1,3})\b", text or "")
    if m:
        n = int(m.group(1))
        if 1 <= n <= 100:
            return n
    return default


def _norm_title(s: str) -> str:
    """Normalise a topic/title for exact-duplicate comparison."""
    return re.sub(r"\s+", " ", (s or "").strip().lower()).rstrip(".!?")


def _md_cell(text: str) -> str:
    """Sanitise a value for a Markdown table cell (escape pipes / newlines)."""
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def _topics_md_table(topics: list[dict]) -> str:
    """Render researcher topics as a | TOPIC | PURPOSE | Markdown table."""
    lines = ["| TOPIC | PURPOSE |", "| --- | --- |"]
    for t in topics:
        lines.append(f"| {_md_cell(t.get('topic'))} | {_md_cell(t.get('purpose'))} |")
    return "\n".join(lines)


def _validation_md_table(rows: list[dict]) -> str:
    """Render validator results as a | TOPIC | PURPOSE | STATUS | Remark | table."""
    lines = ["| TOPIC | PURPOSE | STATUS | REMARK |", "| --- | --- | --- | --- |"]
    for r in rows:
        lines.append(
            f"| {_md_cell(r.get('topic'))} | {_md_cell(r.get('purpose'))} "
            f"| {_md_cell(r.get('status'))} | {_md_cell(r.get('remark'))} |"
        )
    return "\n".join(lines)



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

DAILY_TOPIC_TASK_TITLE = (
    "Give me 10 new SEO blogs topic that attracts United States Restaurant Owners/Managers"
)


@celery.task(name="daily_cron")
def daily_cron():
    """
    Daily cron (04:00 IST / 22:30 UTC): for every space with an active Content
    Researcher, create a fresh topic-research task and assign it to that
    researcher. The researcher picks it up immediately (no due date set).
    """
    db = get_sync_db()
    researchers = list(db.agents.find({
        "role": ROLE_RESEARCHER,
        "is_active": True,
        "provider": {"$ne": ""},
        "model": {"$ne": ""},
    }))

    if not researchers:
        log.info("daily_cron: no active Content Researchers found.")
        return

    created = 0
    for agent in researchers:
        space_id = agent["space_id"]
        researcher_id = str(agent["_id"])

        todo_status = _get_status_by_name(db, space_id, "To Do")
        if not todo_status:
            log.warning(f"daily_cron: no 'To Do' status in space {space_id}, skipping.")
            continue

        new_task_id = _create_task(
            db,
            space_id=space_id,
            title=DAILY_TOPIC_TASK_TITLE,
            description="",
            status_id=str(todo_status["_id"]),
            assignee_id=researcher_id,
            # Hold the lock so the periodic poll won't also dispatch it.
            extra={"_agent_processing": True},
        )
        run_content_researcher.delay(new_task_id, space_id)
        created += 1
        log.info(f"daily_cron: created researcher task {new_task_id} in space {space_id}")

    log.info(f"daily_cron: created {created} researcher task(s).")


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
        is_todo = bool(todo_status) and status_id == str(todo_status["_id"])
        is_review = bool(review_status) and status_id == str(review_status["_id"])

        should_dispatch = False

        # Researcher works a topic task in To Do, but only once its due date
        # has arrived (today/empty → now; tomorrow → waits).
        if role == ROLE_RESEARCHER and is_todo and _due_reached(task.get("due_date")):
            should_dispatch = True
        # Topic Validator reviews the researcher's topics from In Review.
        elif role == ROLE_TOPIC_VALIDATOR and is_review:
            should_dispatch = True
        elif role == ROLE_CONTENT_WRITER and is_todo:
            should_dispatch = True
        elif role == ROLE_CONTENT_VALIDATOR and is_review:
            should_dispatch = True

        if not should_dispatch:
            continue

        # Mark as processing
        db.tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"_agent_processing": True}},
        )

        # Dispatch the right pipeline task
        if role == ROLE_RESEARCHER:
            run_content_researcher.delay(task_id, space_id)
        elif role == ROLE_TOPIC_VALIDATOR:
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
def run_content_researcher(self, task_id: str, space_id: str):
    """
    Work a "topic ideas" task assigned to the Content Researcher.

    Researches `topic + purpose` only, based on the agent's skills. Posts the
    topics as a Markdown table in the comments, then moves the task to In Review
    and assigns the Topic Validator.

    Already-approved topics (from prior revisions) persist and are NOT
    regenerated; this run produces fresh candidates that avoid those, the
    previously-declined ones, and existing Notion blog titles.
    """
    db = get_sync_db()

    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        log.error(f"Task {task_id} not found")
        return

    agent = _get_agent_by_role(db, space_id, ROLE_RESEARCHER)
    if not agent:
        log.warning(f"No active Content Researcher in space {space_id}")
        _clear_processing_flag(db, task_id)
        return

    agent_id = str(agent["_id"])
    agent_name = agent.get("name", "Content Researcher")

    space = db.spaces.find_one({"_id": ObjectId(space_id)})
    niche = (space or {}).get("niche", "")

    # Topic Validator must exist to hand off to.
    validator = _get_agent_by_role(db, space_id, ROLE_TOPIC_VALIDATOR)
    if not validator:
        _post_comment(db, task_id, agent_id, agent_name, "No Topic Validator agent found in this space.")
        _clear_processing_flag(db, task_id)
        return
    validator_id = str(validator["_id"])
    validator_name = validator.get("name", "Topic Validator")

    # How many topics to propose this round.
    topic_count = _parse_topic_count(
        f"{task.get('title', '')} {task.get('description', '')}",
        default=(space or {}).get("topic_count") or DEFAULT_TOPIC_COUNT,
    )

    # Move to In Progress while we work.
    in_progress = _get_status_by_name(db, space_id, "In Progress")
    if in_progress:
        _move_task(db, task_id, str(in_progress["_id"]))

    revision_count = task.get("_revision_count", 0)
    approved_topics = task.get("_approved_topics", [])      # [{topic, purpose}]
    declined_topics = task.get("_declined_topics", [])      # [{topic, purpose, remark}]
    suggestions = task.get("_topic_suggestions", "")
    needed = max(TOPIC_APPROVAL_TARGET - len(approved_topics), 0)

    _post_comment(
        db, task_id, agent_id, agent_name,
        f"Researching {topic_count} topic ideas..."
        + (f" (revision {revision_count}, {len(approved_topics)}/{TOPIC_APPROVAL_TARGET} approved so far)"
           if revision_count else ""),
    )

    # ── Build the "do not repeat" list: existing Notion titles + approved + declined ──
    org_settings = _get_org_settings(db, space_id)
    notion_token, notion_database_id = _get_notion_config(org_settings)
    existing_titles: list[str] = []
    if notion_token and notion_database_id:
        try:
            from app.worker.notion import list_blog_titles
            existing_titles = list_blog_titles(notion_token, notion_database_id)
        except Exception as exc:
            log.warning(f"Could not fetch existing Notion titles: {exc}")

    avoid = list(existing_titles)
    avoid += [t.get("topic", "") for t in approved_topics]
    avoid += [t.get("topic", "") for t in declined_topics]
    avoid = [a for a in dict.fromkeys(avoid) if a][:200]
    avoid_block = ""
    if avoid:
        avoid_block = (
            "\n\n## Do NOT repeat these existing/handled topics "
            "(exact duplicates only — contextual overlap is fine):\n"
            + "\n".join(f"- {a}" for a in avoid)
        )

    system_extra = (
        "You are a content research specialist. Discover blog topic ideas based on your "
        "instructions/skills above. For EACH idea provide only the topic and the purpose "
        "of the blog — nothing else.\n\n"
        "IMPORTANT: Respond ONLY with a valid JSON array. No extra text.\n"
        "Each array item must be an object with exactly:\n"
        '- "topic": a concise, compelling blog topic/title\n'
        '- "purpose": one or two sentences on what the blog should achieve for the reader\n'
    )

    niche_line = f' in the niche "{niche}"' if niche else ""

    existing_messages = task.get("_llm_messages_researcher", [])
    use_cache = agent.get("provider") == "openai" and len(existing_messages) > 0

    if use_cache and declined_topics:
        # ── Revision turn (cached) — only append what changed ──
        declined_block = "\n".join(
            f"- {d.get('topic')} — declined: {d.get('remark', 'no remark')}"
            for d in declined_topics
        )
        revision_prompt = (
            f"The Topic Validator reviewed your previous topics. "
            f"{len(approved_topics)} were approved and kept; {needed} more still need approval.\n\n"
            f"## Declined topics (do not propose these again):\n{declined_block}\n\n"
            + (f"## Overall suggestions from the validator:\n{suggestions}\n\n" if suggestions else "")
            + f"Propose {topic_count} NEW topic ideas{niche_line} that address the feedback and "
            f"avoid every topic already listed.{avoid_block}\n\n"
            f"Return ONLY a JSON array of {topic_count} objects with \"topic\" and \"purpose\"."
        )
        messages = existing_messages + [{"role": "user", "content": revision_prompt}]
    else:
        system_prompt = _build_agent_system_prompt(agent, system_extra)
        feedback_block = ""
        if declined_topics:
            declined_block = "\n".join(
                f"- {d.get('topic')} — declined: {d.get('remark', 'no remark')}"
                for d in declined_topics
            )
            feedback_block = f"\n\n## Previously declined (do not repeat):\n{declined_block}"
            if suggestions:
                feedback_block += f"\n\n## Validator suggestions:\n{suggestions}"
        user_prompt = (
            f"Suggest {topic_count} blog topic ideas{niche_line}. "
            f"For each, give only the topic and its purpose. "
            f"Make them distinct and aligned with your instructions."
            f"{feedback_block}{avoid_block}\n\n"
            f"Return ONLY a JSON array of {topic_count} objects with \"topic\" and \"purpose\"."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # ── Call LLM (cached thread persisted on the task) ──
    try:
        output, updated_messages = _call_agent_llm_cached(
            db, agent, space_id, messages, task_id=task_id,
        )
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_llm_messages_researcher": updated_messages}},
        )
    except Exception as exc:
        log.exception(f"Content Researcher LLM failed for task {task_id}: {exc}")
        try:
            self.retry(countdown=120)
        except self.MaxRetriesExceededError:
            _post_comment(db, task_id, agent_id, agent_name, f"Research failed: {str(exc)}")
            _clear_processing_flag(db, task_id)
        return

    # Parse topics → [{topic, purpose}]
    try:
        parsed = _parse_json_from_llm(output)
        if isinstance(parsed, dict):
            parsed = parsed.get("topics") or parsed.get("ideas") or [parsed]
    except ValueError as exc:
        _post_comment(db, task_id, agent_id, agent_name, f"Could not parse topics: {str(exc)}")
        _clear_processing_flag(db, task_id)
        return

    pending_topics = []
    for item in parsed if isinstance(parsed, list) else []:
        if not isinstance(item, dict):
            continue
        topic = (item.get("topic") or item.get("title") or "").strip()
        purpose = (item.get("purpose") or item.get("description") or "").strip()
        if topic:
            pending_topics.append({"topic": topic, "purpose": purpose})

    # Hard de-duplication: drop any candidate whose title exactly matches an
    # existing Notion blog or an already approved/declined topic. (Contextual
    # overlap is allowed — only exact/near-exact titles are removed.)
    avoid_norm = {_norm_title(a) for a in avoid}
    seen_norm: set[str] = set()
    deduped = []
    dropped = 0
    for t in pending_topics:
        n = _norm_title(t["topic"])
        if n in avoid_norm or n in seen_norm:
            dropped += 1
            continue
        seen_norm.add(n)
        deduped.append(t)
    if dropped:
        log.info(f"Researcher dropped {dropped} duplicate topic(s) for task {task_id}")
    pending_topics = deduped[:topic_count]

    if not pending_topics:
        _post_comment(
            db, task_id, agent_id, agent_name,
            "All generated topics duplicated existing/handled topics. Will retry with fresh ideas.",
        )
        _clear_processing_flag(db, task_id)
        return

    # Persist this round's candidates for the validator to read.
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"_pending_topics": pending_topics}},
    )

    # Post the topics table and @mention the Topic Validator.
    table = _topics_md_table(pending_topics)
    _post_comment(
        db, task_id, agent_id, agent_name,
        f"@{validator_name} Researched {len(pending_topics)} topic idea(s) for validation:\n\n{table}",
        mentions=[{"id": validator_id, "type": "agent", "name": validator_name}],
    )

    # Hand off to the Topic Validator: In Review + assign + keep the processing
    # lock so poll won't double-dispatch, then trigger the validator directly.
    review_status = _get_status_by_name(db, space_id, "In Review")
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {
            "assignee_id": validator_id,
            "assignee_type": "agent",
            "status_id": str(review_status["_id"]) if review_status else task.get("status_id"),
            "_agent_processing": True,
            "updated_at": datetime.utcnow(),
        }},
    )
    run_topic_validator.delay(task_id, space_id)
    log.info(f"Content Researcher proposed {len(pending_topics)} topics for task {task_id}")


# ---------------------------------------------------------------------------
# Pipeline step 2: Topic Validator
# ---------------------------------------------------------------------------

@celery.task(name="run_topic_validator", bind=True, max_retries=2)
def run_topic_validator(self, task_id: str, space_id: str):
    """
    Validate the researcher's proposed topics (read from `_pending_topics`).

    For every row: assign a status (approved/declined) and a remark, cross-
    checking Notion to avoid exact duplicates (contextual overlap is fine).
    Each approved topic immediately spawns a Content Writer task and is added
    to the persistent `_approved_topics` set.

    Completion rules:
      • ≥ TOPIC_APPROVAL_TARGET approved (cumulative) → task → Done.
      • otherwise → record declined topics + suggestions, send back to the
        Content Researcher (To Do) for another round.
      • after TOPIC_MAX_REVISIONS rounds without enough approvals → escalate
        the task to an admin user.
    """
    db = get_sync_db()

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

    pending_topics = task.get("_pending_topics", [])
    if not pending_topics:
        _post_comment(db, task_id, agent_id, agent_name, "No topics to validate.")
        _clear_processing_flag(db, task_id)
        return

    # Move to In Progress
    in_progress = _get_status_by_name(db, space_id, "In Progress")
    if in_progress:
        _move_task(db, task_id, str(in_progress["_id"]))

    _post_comment(db, task_id, agent_id, agent_name, "Validating topics...")

    # ── Existing Notion titles for the duplicate cross-check ──
    org_settings = _get_org_settings(db, space_id)
    notion_token, notion_database_id = _get_notion_config(org_settings)
    existing_titles: list[str] = []
    if notion_token and notion_database_id:
        try:
            from app.worker.notion import list_blog_titles
            existing_titles = list_blog_titles(notion_token, notion_database_id)
        except Exception as exc:
            log.warning(f"Could not fetch existing Notion titles: {exc}")
    existing_block = ""
    if existing_titles:
        existing_block = (
            "\n\n## Existing Notion blog titles (decline only EXACT/near-exact "
            "duplicates — contextual overlap is acceptable):\n"
            + "\n".join(f"- {t}" for t in existing_titles[:200])
        )

    topics_block = "\n".join(
        f'{i + 1}. topic: "{t.get("topic")}" | purpose: "{t.get("purpose")}"'
        for i, t in enumerate(pending_topics)
    )

    system_extra = (
        "You are a topic validator. Using your instructions/skills above, validate EACH "
        "topic and its purpose, deciding whether it is worth writing a blog about.\n\n"
        "IMPORTANT: Respond ONLY with valid JSON. No extra text. Shape:\n"
        "{\n"
        '  "rows": [\n'
        '    {"topic": "...", "purpose": "...", "status": "approved" | "declined", "remark": "short reason"}\n'
        "  ],\n"
        '  "overall_suggestions": "guidance for the researcher if not enough were approved"\n'
        "}\n\n"
        "Return one row for EVERY topic given, preserving topic and purpose text. "
        "Decline duplicates of existing blogs and weak/off-strategy ideas."
    )

    existing_messages = task.get("_llm_messages_topic_validator", [])
    use_cache = agent.get("provider") == "openai" and len(existing_messages) > 0

    review_request = (
        f"Validate these {len(pending_topics)} topics. Return one row per topic with "
        f"status and remark.\n\n{topics_block}{existing_block}"
    )
    if use_cache:
        messages = existing_messages + [{"role": "user", "content": review_request}]
    else:
        system_prompt = _build_agent_system_prompt(agent, system_extra)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": review_request},
        ]

    try:
        output, updated_messages = _call_agent_llm_cached(
            db, agent, space_id, messages, task_id=task_id,
        )
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_llm_messages_topic_validator": updated_messages}},
        )
    except Exception as exc:
        log.exception(f"Topic Validator LLM failed: {exc}")
        _post_comment(db, task_id, agent_id, agent_name, f"Validation failed: {str(exc)}")
        _clear_processing_flag(db, task_id)
        try:
            self.retry(countdown=60)
        except self.MaxRetriesExceededError:
            pass
        return

    # ── Parse the validation result ──
    try:
        parsed = _parse_json_from_llm(output)
    except ValueError as exc:
        _post_comment(db, task_id, agent_id, agent_name, f"Could not parse validation: {str(exc)}")
        _clear_processing_flag(db, task_id)
        return

    if isinstance(parsed, dict):
        rows = parsed.get("rows") or parsed.get("topics") or []
        overall_suggestions = parsed.get("overall_suggestions", "") or parsed.get("suggestions", "")
    elif isinstance(parsed, list):
        rows = parsed
        overall_suggestions = ""
    else:
        rows = []
        overall_suggestions = ""

    # Normalise rows; fall back to pending topic text when the model omits it.
    norm_rows = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        fallback = pending_topics[i] if i < len(pending_topics) else {}
        status_val = str(r.get("status", "")).strip().lower()
        status_val = "approved" if status_val.startswith("appro") else "declined"
        norm_rows.append({
            "topic": (r.get("topic") or fallback.get("topic") or "").strip(),
            "purpose": (r.get("purpose") or fallback.get("purpose") or "").strip(),
            "status": status_val,
            "remark": str(r.get("remark", "")).strip(),
        })

    if not norm_rows:
        _post_comment(db, task_id, agent_id, agent_name, "Validator returned no rows. Will retry.")
        _clear_processing_flag(db, task_id)
        return

    # Hard duplicate guard: regardless of the LLM's decision, force-decline any
    # topic whose title exactly matches an existing Notion blog. This enforces
    # the no-duplicate rule in code, not just via the prompt.
    existing_norm = {_norm_title(t) for t in existing_titles}
    forced = 0
    if existing_norm:
        for r in norm_rows:
            if r["status"] == "approved" and _norm_title(r["topic"]) in existing_norm:
                r["status"] = "declined"
                r["remark"] = (r["remark"] + " " if r["remark"] else "") + \
                    "(auto-declined: a blog with this title already exists in Notion)"
                forced += 1
    if forced:
        log.info(f"Validator auto-declined {forced} Notion-duplicate topic(s) for task {task_id}")

    # Post the validation table.
    _post_comment(
        db, task_id, agent_id, agent_name,
        f"Validation results:\n\n{_validation_md_table(norm_rows)}",
    )

    approved_now = [r for r in norm_rows if r["status"] == "approved"]
    declined_now = [r for r in norm_rows if r["status"] != "approved"]

    # ── Spawn a Content Writer task for each newly approved topic ──
    writer = _get_agent_by_role(db, space_id, ROLE_CONTENT_WRITER)
    todo_status = _get_status_by_name(db, space_id, "To Do")
    created = []
    if writer and todo_status and approved_now:
        writer_id = str(writer["_id"])
        for r in approved_now:
            new_task_id = _create_task(
                db,
                space_id=space_id,
                title=r["topic"],
                description=r["purpose"],
                status_id=str(todo_status["_id"]),
                assignee_id=writer_id,
                extra={"_agent_processing": True},
            )
            created.append(r["topic"])
            run_content_writer.delay(new_task_id, space_id)

    # ── Update persistent state on the batch task ──
    approved_topics = task.get("_approved_topics", [])
    approved_topics += [{"topic": r["topic"], "purpose": r["purpose"]} for r in approved_now]
    # Accumulate declined topics so the researcher avoids them next round.
    declined_topics = task.get("_declined_topics", [])
    declined_topics += [
        {"topic": r["topic"], "purpose": r["purpose"], "remark": r["remark"]}
        for r in declined_now
    ]

    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {
            "_approved_topics": approved_topics,
            "_declined_topics": declined_topics,
            "_topic_suggestions": overall_suggestions,
        }, "$unset": {"_pending_topics": ""}},
    )

    total_approved = len(approved_topics)

    if created:
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Approved {len(created)} topic(s) this round ({total_approved}/{TOPIC_APPROVAL_TARGET} total). "
            f"Created Content Writer task(s):\n" + "\n".join(f"- {t}" for t in created),
        )

    # ── Enough approved → Done ──
    if total_approved >= TOPIC_APPROVAL_TARGET:
        done_status = _get_status_by_name(db, space_id, "Done")
        if done_status:
            _move_task(db, task_id, str(done_status["_id"]))
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"Target reached — {total_approved} topic(s) approved and assigned to the Content Writer. "
            f"Marking this task as Done.",
        )
        _clear_processing_flag(db, task_id)
        log.info(f"Topic Validator completed task {task_id} with {total_approved} approved")
        return

    # ── Not enough yet → revision or escalation ──
    revision_count = task.get("_revision_count", 0) + 1
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"_revision_count": revision_count}},
    )

    if revision_count >= TOPIC_MAX_REVISIONS:
        admin = _find_admin_user(db)
        admin_name = admin.get("full_name", "Admin") if admin else "Admin"
        admin_id = str(admin["_id"]) if admin else None
        _post_comment(
            db, task_id, agent_id, agent_name,
            f"@{admin_name} After {revision_count} revision rounds only {total_approved}/"
            f"{TOPIC_APPROVAL_TARGET} topics were approved. Escalating for manual review.\n\n"
            + (f"**Overall suggestions:** {overall_suggestions}" if overall_suggestions else ""),
            mentions=[{"id": admin_id, "type": "user", "name": admin_name}] if admin_id else [],
        )
        todo_status = _get_status_by_name(db, space_id, "To Do")
        if admin_id:
            db.tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {
                    "assignee_id": admin_id,
                    "assignee_type": "user",
                    "status_id": str(todo_status["_id"]) if todo_status else task.get("status_id"),
                    "updated_at": datetime.utcnow(),
                }},
            )
        _clear_processing_flag(db, task_id)
        log.info(f"Topic task {task_id} escalated to admin after {revision_count} rounds")
        return

    # Send back to the Content Researcher for another round.
    researcher = _get_agent_by_role(db, space_id, ROLE_RESEARCHER)
    if not researcher:
        _post_comment(db, task_id, agent_id, agent_name, "No Content Researcher to send back to.")
        _clear_processing_flag(db, task_id)
        return

    researcher_id = str(researcher["_id"])
    researcher_name = researcher.get("name", "Content Researcher")
    needed = TOPIC_APPROVAL_TARGET - total_approved

    feedback_parts = [
        f"@{researcher_name} {total_approved}/{TOPIC_APPROVAL_TARGET} topics approved — "
        f"need {needed} more. Round {revision_count}/{TOPIC_MAX_REVISIONS}.",
    ]
    if declined_now:
        feedback_parts.append("")
        feedback_parts.append("**Declined this round:**")
        for r in declined_now:
            feedback_parts.append(f"- {r['topic']} — {r['remark']}")
    if overall_suggestions:
        feedback_parts.append("")
        feedback_parts.append(f"**Overall suggestions:** {overall_suggestions}")

    todo_status = _get_status_by_name(db, space_id, "To Do")
    # Reassign to researcher, move to To Do, keep the processing lock and
    # dispatch directly so the next round starts immediately (revisions ignore
    # the due date — only the initial trigger waits for it).
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {
            "assignee_id": researcher_id,
            "assignee_type": "agent",
            "status_id": str(todo_status["_id"]) if todo_status else task.get("status_id"),
            "_agent_processing": True,
            "updated_at": datetime.utcnow(),
        }},
    )
    _post_comment(
        db, task_id, agent_id, agent_name,
        "\n".join(feedback_parts),
        mentions=[{"id": researcher_id, "type": "agent", "name": researcher_name}],
    )
    run_content_researcher.delay(task_id, space_id)
    log.info(
        f"Topic Validator sent task {task_id} back to researcher "
        f"(round {revision_count}, {total_approved} approved)"
    )


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
        feedback_items = []
        for c in comments:
            if c.get("created_by") == agent_id:
                continue
            extracted = _extract_revision_feedback(c["content"])
            if extracted.strip():
                feedback_items.append(extracted)
        feedback = "\n\n---\n\n".join(feedback_items)

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
        feedback_items = []
        for c in comments:
            if c.get("created_by") == agent_id:
                continue
            extracted = _extract_revision_feedback(c["content"])
            if extracted.strip():
                feedback_items.append(extracted)
        feedback = "\n\n---\n\n".join(feedback_items)
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
        output, updated_messages = _call_agent_llm_cached(
            db, agent, space_id, messages, task_id=task_id,
        )

        # Persist conversation for future cache hits
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_llm_messages_writer": updated_messages}},
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
        output, updated_messages = _call_agent_llm_cached(
            db, agent, space_id, messages, task_id=task_id,
        )

        # Persist conversation for future cache hits
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"_llm_messages_validator": updated_messages}},
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
        from app.worker.notion import (
            upload_image_to_page, get_first_image_url, set_thumbnail_url,
        )

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

        # Copy the first image on the page (the thumbnail we just uploaded sits
        # at the top) into the database's `thumbnail_url` property — before the
        # status is flipped to Published.
        try:
            first_image_url = get_first_image_url(notion_token, notion_page_id)
            if first_image_url:
                set_thumbnail_url(notion_token, notion_page_id, first_image_url)
                log.info(f"Set thumbnail_url for task {task_id}: {first_image_url}")
            else:
                log.warning(f"No image found on page for task {task_id}; thumbnail_url not set")
        except Exception as exc:
            log.warning(f"Could not set thumbnail_url for task {task_id}: {exc}")
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
