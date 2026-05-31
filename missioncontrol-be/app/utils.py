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


def serialize_folder(folder: dict) -> dict:
    return {
        "id": str(folder["_id"]),
        "space_id": folder["space_id"],
        "parent_id": folder.get("parent_id"),
        "name": folder["name"],
        "position": folder.get("position", 0),
        "created_by": folder["created_by"],
        "created_at": folder["created_at"],
        "updated_at": folder["updated_at"],
    }


def serialize_doc(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "space_id": doc["space_id"],
        "folder_id": doc.get("folder_id"),
        "title": doc["title"],
        "content": doc.get("content", ""),
        "created_by": doc["created_by"],
        "updated_by": doc["updated_by"],
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
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
    return {
        "id": str(log["_id"]),
        "task_id": log["task_id"],
        "task_title": log.get("task_title", ""),
        "space_id": log["space_id"],
        "agent_id": log["agent_id"],
        "agent_name": log.get("agent_name", ""),
        "agent_role": log.get("agent_role", ""),
        "provider": log.get("provider", ""),
        "model": log.get("model", ""),
        "request": log.get("request", []),
        "response": log.get("response", ""),
        "is_cached": log.get("is_cached", False),
        "duration_ms": log.get("duration_ms", 0),
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
