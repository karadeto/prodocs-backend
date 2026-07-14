import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat.routes import router as chat_router
from app.config import get_settings
from app.ingestion.worker import pq_app
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router
from app.routes.folders import router as folders_router
from app.routes.review import router as review_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the procrastinate connector so API request handlers can defer jobs.
    async with pq_app.open_async():
        worker_task: asyncio.Task | None = None
        if get_settings().embedded_worker:
            worker_task = asyncio.create_task(
                pq_app.run_worker_async(concurrency=2, install_signal_handlers=False),
                name="procrastinate-worker",
            )
            worker_task.add_done_callback(_log_worker_exit)
            logger.info("Embedded ingestion worker started (EMBEDDED_WORKER=false to disable)")
        try:
            yield
        finally:
            if worker_task is not None:
                worker_task.cancel()  # first cancel = graceful stop
                with suppress(asyncio.CancelledError):
                    await worker_task


def _log_worker_exit(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Embedded worker crashed — uploads will queue but not process", exc_info=exc)


app = FastAPI(title="ProDocs API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth_router, documents_router, folders_router, review_router, chat_router):
    app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
