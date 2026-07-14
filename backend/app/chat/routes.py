import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth import get_current_user_id
from app.chat.agent import ChatDeps, get_chat_agent
from app.db import get_session
from app.models import ChatMessage, ChatThread

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_HISTORY_MESSAGES = 30


class ChatIn(BaseModel):
    message: str
    thread_id: UUID | None = None


@router.post("/stream")
async def chat_stream(
    body: ChatIn,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    thread = await _get_or_create_thread(session, user_id, body)

    history = None
    if thread.model_messages:
        msgs = ModelMessagesTypeAdapter.validate_json(thread.model_messages)
        history = msgs[-MAX_HISTORY_MESSAGES:]

    session.add(ChatMessage(thread_id=thread.id, user_id=user_id, role="user", content=body.message))
    await session.commit()

    deps = ChatDeps(user_id=user_id, session=session)
    agent = get_chat_agent()

    async def event_generator():
        yield {"event": "thread", "data": json.dumps({"thread_id": str(thread.id)})}
        try:
            async with agent.run_stream(body.message, deps=deps, message_history=history) as stream:
                async for delta in stream.stream_text(delta=True):
                    yield {"event": "token", "data": json.dumps({"text": delta})}
                answer = await stream.get_output()
                all_messages_json = stream.all_messages_json()
        except Exception as e:  # surface the failure to the client instead of a dead stream
            yield {"event": "error", "data": json.dumps({"error": str(e)[:500]})}
            return

        thread.model_messages = (
            all_messages_json.decode()
            if isinstance(all_messages_json, bytes) else all_messages_json
        )
        session.add(ChatMessage(thread_id=thread.id, user_id=user_id, role="assistant",
                                content=answer, sources=deps.sources))
        await session.commit()
        yield {"event": "sources", "data": json.dumps({"sources": deps.sources})}
        yield {"event": "done", "data": json.dumps({"thread_id": str(thread.id)})}

    return EventSourceResponse(event_generator())


@router.get("/threads")
async def list_threads(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    threads = (await session.execute(
        select(ChatThread).where(ChatThread.user_id == user_id)
        .order_by(ChatThread.created_at.desc()).limit(50)
    )).scalars().all()
    return [{"id": str(t.id), "title": t.title, "created_at": t.created_at.isoformat()}
            for t in threads]


@router.get("/threads/{thread_id}/messages")
async def thread_messages(
    thread_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    msgs = (await session.execute(
        select(ChatMessage).where(
            ChatMessage.thread_id == thread_id, ChatMessage.user_id == user_id
        ).order_by(ChatMessage.created_at)
    )).scalars().all()
    return [{"id": str(m.id), "role": m.role, "content": m.content,
             "sources": m.sources, "created_at": m.created_at.isoformat()} for m in msgs]


async def _get_or_create_thread(session: AsyncSession, user_id: UUID, body: ChatIn) -> ChatThread:
    if body.thread_id is not None:
        thread = (await session.execute(
            select(ChatThread).where(
                ChatThread.id == body.thread_id, ChatThread.user_id == user_id
            )
        )).scalar_one_or_none()
        if thread is None:
            raise HTTPException(404, "Thread not found")
        return thread
    thread = ChatThread(user_id=user_id, title=body.message[:80])
    session.add(thread)
    await session.commit()
    return thread
