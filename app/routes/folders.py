from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.db import get_session
from app.ingestion.routing import ensure_system_folders, get_or_create_folder
from app.models import Document, Folder

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("")
async def folder_tree(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    await ensure_system_folders(session, user_id)
    await session.commit()

    folders = (await session.execute(
        select(Folder).where(Folder.user_id == user_id).order_by(Folder.name)
    )).scalars().all()

    counts = dict((await session.execute(
        select(Document.folder_id, func.count())
        .where(Document.user_id == user_id, Document.folder_id.is_not(None))
        .group_by(Document.folder_id)
    )).all())

    nodes = {
        f.id: {
            "id": str(f.id), "name": f.name, "code": f.code, "icon": f.icon,
            "is_system": f.is_system, "document_count": counts.get(f.id, 0), "children": [],
        }
        for f in folders
    }
    roots = []
    for f in folders:
        node = nodes[f.id]
        if f.parent_id and f.parent_id in nodes:
            nodes[f.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


class CreateFolderIn(BaseModel):
    name: str
    parent_id: UUID | None = None


@router.post("", status_code=201)
async def create_folder(
    body: CreateFolderIn,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Folder name required")
    folder = await get_or_create_folder(session, user_id, body.parent_id, name)
    await session.commit()
    return {"id": str(folder.id), "name": folder.name,
            "parent_id": str(folder.parent_id) if folder.parent_id else None}
