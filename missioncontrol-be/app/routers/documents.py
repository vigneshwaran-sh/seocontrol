from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.database import get_db
from app.models.document import (
    DocCreate,
    DocUpdate,
    DocResponse,
    FolderCreate,
    FolderUpdate,
    FolderResponse,
)
from app.utils import serialize_doc, serialize_folder

router = APIRouter(prefix="/api/spaces/{space_id}/docs", tags=["documents"])


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(
    space_id: str,
    parent_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    query: dict = {"space_id": space_id, "parent_id": parent_id}
    folders = await db.folders.find(query).sort("position", 1).to_list(length=200)
    return [serialize_folder(f) for f in folders]


@router.post("/folders", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    space_id: str, body: FolderCreate, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    # Determine next position
    last = await db.folders.find_one(
        {"space_id": space_id, "parent_id": body.parent_id},
        sort=[("position", -1)],
    )
    next_pos = (last["position"] + 1) if last else 0

    now = datetime.utcnow()
    doc = {
        "space_id": space_id,
        "parent_id": body.parent_id,
        "name": body.name,
        "position": next_pos,
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.folders.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_folder(doc)


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    space_id: str,
    folder_id: str,
    body: FolderUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(folder_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates: dict = {"updated_at": datetime.utcnow()}
    if body.name is not None:
        updates["name"] = body.name
    if body.parent_id is not None:
        updates["parent_id"] = body.parent_id
    if body.position is not None:
        updates["position"] = body.position

    result = await db.folders.find_one_and_update(
        {"_id": ObjectId(folder_id), "space_id": space_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return serialize_folder(result)


async def _delete_folder_recursive(db, space_id: str, folder_id: str) -> None:
    """Delete a folder, its sub-folders (recursively), and all documents inside."""
    # Find child folders
    children = await db.folders.find(
        {"space_id": space_id, "parent_id": folder_id}
    ).to_list(length=500)

    for child in children:
        await _delete_folder_recursive(db, space_id, str(child["_id"]))

    # Delete documents in this folder
    await db.documents.delete_many({"space_id": space_id, "folder_id": folder_id})

    # Delete the folder itself
    await db.folders.delete_one({"_id": ObjectId(folder_id), "space_id": space_id})


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    space_id: str, folder_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(folder_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    folder = await db.folders.find_one(
        {"_id": ObjectId(folder_id), "space_id": space_id}
    )
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    await _delete_folder_recursive(db, space_id, folder_id)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[DocResponse])
async def list_docs(
    space_id: str,
    folder_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    query: dict = {"space_id": space_id, "folder_id": folder_id}
    docs = await db.documents.find(query).sort("created_at", 1).to_list(length=200)
    return [serialize_doc(d) for d in docs]


@router.post("/", response_model=DocResponse, status_code=status.HTTP_201_CREATED)
async def create_doc(
    space_id: str, body: DocCreate, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    now = datetime.utcnow()
    doc = {
        "space_id": space_id,
        "folder_id": body.folder_id,
        "title": body.title,
        "content": body.content,
        "created_by": user["id"],
        "updated_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.documents.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_doc(doc)


@router.get("/{doc_id}", response_model=DocResponse)
async def get_doc(
    space_id: str, doc_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    doc = await db.documents.find_one({"_id": ObjectId(doc_id), "space_id": space_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return serialize_doc(doc)


@router.put("/{doc_id}", response_model=DocResponse)
async def update_doc(
    space_id: str,
    doc_id: str,
    body: DocUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates: dict = {
        "updated_at": datetime.utcnow(),
        "updated_by": user["id"],
    }
    if body.title is not None:
        updates["title"] = body.title
    if body.folder_id is not None:
        updates["folder_id"] = body.folder_id
    if body.content is not None:
        updates["content"] = body.content

    result = await db.documents.find_one_and_update(
        {"_id": ObjectId(doc_id), "space_id": space_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return serialize_doc(result)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    space_id: str, doc_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    result = await db.documents.delete_one({"_id": ObjectId(doc_id), "space_id": space_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
