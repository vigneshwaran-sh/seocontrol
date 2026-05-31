import re
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models.organization import OrgCreate, OrgUpdate, OrgResponse
from app.utils import serialize_org

router = APIRouter(prefix="/api/orgs", tags=["organizations"])


def _make_slug(name: str) -> str:
    slug = name.lower().strip().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug


@router.post("/", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgCreate, user: dict = Depends(get_current_user)):
    db = get_db()
    slug = _make_slug(body.name)

    existing = await db.organizations.find_one({"slug": slug})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization with this name already exists",
        )

    now = datetime.utcnow()
    doc = {
        "name": body.name,
        "slug": slug,
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.organizations.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_org(doc)


@router.get("/", response_model=list[OrgResponse])
async def list_orgs(user: dict = Depends(get_current_user)):
    db = get_db()
    orgs = await db.organizations.find().sort("created_at", 1).to_list(length=100)
    return [serialize_org(o) for o in orgs]


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org(org_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(org_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID")

    org = await db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return serialize_org(org)


@router.put("/{org_id}", response_model=OrgResponse)
async def update_org(org_id: str, body: OrgUpdate, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(org_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID")

    updates: dict = {"updated_at": datetime.utcnow()}
    if body.name is not None:
        updates["name"] = body.name
        updates["slug"] = _make_slug(body.name)

    result = await db.organizations.find_one_and_update(
        {"_id": ObjectId(org_id)},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return serialize_org(result)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(org_id: str, user: dict = Depends(require_admin)):
    db = get_db()
    if not ObjectId.is_valid(org_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID")

    result = await db.organizations.delete_one({"_id": ObjectId(org_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
