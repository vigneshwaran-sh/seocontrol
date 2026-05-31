from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import (
    ChangePassword,
    TokenResponse,
    UserLogin,
    UserResponse,
)
from app.utils import serialize_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    db = get_db()
    user = await db.users.find_one({"email": credentials.email})

    if user is None or not verify_password(credentials.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user["_id"])})
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(**serialize_user(user)),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)


@router.put("/change-password", response_model=UserResponse)
async def change_password(
    payload: ChangePassword,
    current_user: dict = Depends(get_current_user),
):
    db = get_db()
    from bson import ObjectId

    user = await db.users.find_one({"_id": ObjectId(current_user["id"])})

    if user is None or not verify_password(payload.current_password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": ObjectId(current_user["id"])},
        {"$set": {"password": hash_password(payload.new_password), "updated_at": now}},
    )

    updated_user = await db.users.find_one({"_id": ObjectId(current_user["id"])})
    return UserResponse(**serialize_user(updated_user))
