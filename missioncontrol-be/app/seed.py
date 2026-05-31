"""Seed script — creates default admin user and pipeline agents.

Run with:  python -m app.seed
"""

import asyncio
from datetime import datetime, timezone

from app.auth import hash_password
from app.config import settings
from app.database import connect_db, close_db, get_db

PIPELINE_AGENTS = [
    {
        "role": "content_researcher",
        "name": "Content Researcher",
        "avatar": "\U0001f50d",
        "description": "Discovers trending topics and content ideas based on your niche. Runs daily.",
    },
    {
        "role": "topic_validator",
        "name": "Topic Validator",
        "avatar": "✅",
        "description": "Validates and shortlists topics for content creation.",
    },
    {
        "role": "content_writer",
        "name": "Content Writer",
        "avatar": "✍️",
        "description": "Writes blog content and publishes to Notion database.",
    },
    {
        "role": "content_validator",
        "name": "Content Validator",
        "avatar": "\U0001f4cb",
        "description": "Reviews content quality and approves or requests changes.",
    },
]


async def seed():
    await connect_db()
    db = get_db()

    # ── 1. Admin user ────────────────────────────────────────────
    email = "admin@reviewhandy.com"
    existing = await db.users.find_one({"email": email})

    if existing:
        print(f"Admin user '{email}' already exists. Skipping.")
    else:
        now = datetime.now(timezone.utc)
        user_doc = {
            "email": email,
            "password": hash_password("admin123456"),
            "full_name": "Admin",
            "role": "admin",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(user_doc)
        print(f"Created admin user: {email}")

    # ── 2. Migrate agents — delete old, seed pipeline ────────────
    await migrate_agents(db)

    await close_db()


async def migrate_agents(db):
    """
    For every space:
    - Delete any agents without a pipeline role (legacy agents)
    - Ensure all 4 pipeline agents exist
    """
    spaces = await db.spaces.find({}).to_list(length=1000)
    if not spaces:
        print("No spaces found. Pipeline agents will be created when a space is added.")
        return

    admin = await db.users.find_one({"role": "admin", "is_active": True})
    admin_id = str(admin["_id"]) if admin else "system"

    for space in spaces:
        space_id = str(space["_id"])
        space_name = space.get("name", space_id)

        # Delete non-pipeline agents
        old_result = await db.agents.delete_many({
            "space_id": space_id,
            "$or": [
                {"role": {"$exists": False}},
                {"role": ""},
                {"role": None},
                {"role": {"$nin": [a["role"] for a in PIPELINE_AGENTS]}},
            ],
        })
        if old_result.deleted_count:
            print(f"  [{space_name}] Deleted {old_result.deleted_count} legacy agent(s).")

        # Seed missing pipeline agents
        now = datetime.now(timezone.utc)
        seeded = 0
        for tmpl in PIPELINE_AGENTS:
            exists = await db.agents.find_one({
                "space_id": space_id,
                "role": tmpl["role"],
            })
            if exists:
                continue

            await db.agents.insert_one({
                "space_id": space_id,
                "role": tmpl["role"],
                "name": tmpl["name"],
                "avatar": tmpl["avatar"],
                "description": tmpl["description"],
                "provider": "",
                "model": "",
                "skill_content": "",
                "is_active": True,
                "created_by": admin_id,
                "created_at": now,
                "updated_at": now,
            })
            seeded += 1

        if seeded:
            print(f"  [{space_name}] Seeded {seeded} pipeline agent(s).")
        else:
            print(f"  [{space_name}] All 4 pipeline agents already exist.")

        # Ensure space has niche/topic_count fields
        update_fields = {}
        if "niche" not in space:
            update_fields["niche"] = ""
        if "topic_count" not in space:
            update_fields["topic_count"] = 5
        if update_fields:
            await db.spaces.update_one(
                {"_id": space["_id"]},
                {"$set": update_fields},
            )

        # Ensure "Review" status is renamed to "In Review"
        await db.task_statuses.update_many(
            {"space_id": space_id, "name": "Review"},
            {"$set": {"name": "In Review"}},
        )


if __name__ == "__main__":
    asyncio.run(seed())
