import re
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import hash_password, require_admin
from app.database import get_db
from app.models.user import UserCreate, UserResponse, UserUpdate
from app.utils import serialize_user

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    search: str | None = Query(None),
    _admin: dict = Depends(require_admin),
):
    db = get_db()
    query: dict = {}

    if search:
        pattern = re.compile(re.escape(search), re.IGNORECASE)
        query["$or"] = [
            {"full_name": {"$regex": pattern}},
            {"email": {"$regex": pattern}},
        ]

    cursor = db.users.find(query).sort("created_at", -1)
    users = await cursor.to_list(length=500)
    return [UserResponse(**serialize_user(u)) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    _admin: dict = Depends(require_admin),
):
    db = get_db()

    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    now = datetime.now(timezone.utc)
    user_doc = {
        "email": payload.email,
        "password": hash_password(payload.password),
        "full_name": payload.full_name,
        "role": payload.role.value,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return UserResponse(**serialize_user(user_doc))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _admin: dict = Depends(require_admin),
):
    db = get_db()

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    user = await db.users.find_one({"_id": oid})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(**serialize_user(user))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    _admin: dict = Depends(require_admin),
):
    db = get_db()

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    user = await db.users.find_one({"_id": oid})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        return UserResponse(**serialize_user(user))

    # Check for duplicate email if email is being changed
    if "email" in update_data and update_data["email"] != user.get("email"):
        existing = await db.users.find_one({"email": update_data["email"]})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

    # Convert enum to string value if present
    if "role" in update_data:
        update_data["role"] = update_data["role"].value

    update_data["updated_at"] = datetime.now(timezone.utc)

    await db.users.update_one({"_id": oid}, {"$set": update_data})
    updated_user = await db.users.find_one({"_id": oid})
    return UserResponse(**serialize_user(updated_user))


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: str,
    admin: dict = Depends(require_admin),
):
    db = get_db()

    if admin["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    user = await db.users.find_one({"_id": oid})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_active": False, "updated_at": now}},
    )

    updated_user = await db.users.find_one({"_id": oid})
    return UserResponse(**serialize_user(updated_user))
