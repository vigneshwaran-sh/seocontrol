def serialize_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "is_active": user.get("is_active", True),
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
    }


def serialize_org(org: dict) -> dict:
    return {
        "id": str(org["_id"]),
        "name": org["name"],
        "slug": org["slug"],
        "created_by": org["created_by"],
        "created_at": org["created_at"],
        "updated_at": org["updated_at"],
    }


def serialize_space(space: dict) -> dict:
    return {
        "id": str(space["_id"]),
        "org_id": space["org_id"],
        "name": space["name"],
        "slug": space["slug"],
        "icon": space.get("icon", "\U0001f4c1"),
        "color": space.get("color", "#C4956A"),
        "description": space.get("description"),
        "niche": space.get("niche", ""),
        "topic_count": space.get("topic_count", 5),
        "created_by": space["created_by"],
        "created_at": space["created_at"],
        "updated_at": space["updated_at"],
    }


def serialize_task_status(status: dict) -> dict:
    return {
        "id": str(status["_id"]),
        "space_id": status["space_id"],
        "name": status["name"],
        "color": status["color"],
        "position": status["position"],
        "is_default": status.get("is_default", False),
    }


def serialize_task(task: dict) -> dict:
    return {
        "id": str(task["_id"]),
        "space_id": task["space_id"],
        "status_id": task["status_id"],
        "title": task["title"],
        "description": task.get("description", ""),
        "priority": task.get("priority", "none"),
        "assignee_id": task.get("assignee_id"),
        "assignee_type": task.get("assignee_type"),
        "due_date": task.get("due_date"),
        "tags": task.get("tags", []),
        "position": task.get("position", 0),
        "revision_count": task.get("_revision_count", 0),
        "created_by": task["created_by"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }



def serialize_comment(comment: dict) -> dict:
    return {
        "id": str(comment["_id"]),
        "task_id": comment["task_id"],
        "content": comment["content"],
        "mentions": comment.get("mentions", []),
        "created_by": comment["created_by"],
        "created_by_name": comment.get("created_by_name", ""),
        "created_at": comment["created_at"],
        "updated_at": comment["updated_at"],
    }


def serialize_llm_log(log: dict) -> dict:
    # Normalise request: new docs store a dict, old docs stored a list or plain string.
    request = log.get("request")
    if isinstance(request, list):
        # Legacy format — wrap the messages list under a "messages" key
        request = {"messages": request}
    elif not isinstance(request, dict):
        raw = log.get("input_prompt", "")
        request = {"prompt": raw} if raw else {}

    response = log.get("response") or log.get("output_response", "")

    return {
        "id": str(log["_id"]),
        "task_id": log.get("task_id", ""),
        "agent_id": log.get("agent_id", ""),
        "space_id": log.get("space_id", ""),
        "provider": log.get("provider", ""),
        "model": log.get("model", ""),
        "request": request,
        "response": response,
        "duration_ms": log.get("duration_ms", 0),
        "requested_at": log.get("requested_at", log.get("created_at")),
        "created_at": log["created_at"],
    }


def serialize_agent(agent: dict) -> dict:
    return {
        "id": str(agent["_id"]),
        "space_id": agent["space_id"],
        "name": agent["name"],
        "avatar": agent.get("avatar", "\U0001f916"),
        "description": agent.get("description", ""),
        "role": agent.get("role", ""),
        "provider": agent.get("provider", ""),
        "model": agent.get("model", ""),
        "skill_content": agent.get("skill_content", ""),
        "is_active": agent.get("is_active", True),
        "created_by": agent["created_by"],
        "created_at": agent["created_at"],
        "updated_at": agent["updated_at"],
    }
