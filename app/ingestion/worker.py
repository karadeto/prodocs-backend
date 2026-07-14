"""Procrastinate app: Postgres-native job queue.

Jobs live in the same database as the data — transactional deferral, no
Hangfire-style lease juggling. Run the worker with:

    procrastinate --app app.ingestion.worker.pq_app worker
"""

import logging
from uuid import UUID

import procrastinate

from app.config import get_settings

logging.basicConfig(level=logging.INFO)

pq_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=get_settings().database_url),
    import_paths=["app.ingestion.worker"],
)


@pq_app.task(
    queue="ingestion",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=30, exponential_wait=True),
)
async def process_document(document_id: str) -> None:
    from app.ingestion.pipeline import run_pipeline

    await run_pipeline(UUID(document_id))


async def defer_ingestion(document_id: UUID) -> None:
    """Defer with a per-document lock so double-uploads can't double-process."""
    await process_document.configure(
        queueing_lock=f"ingest:{document_id}"
    ).defer_async(document_id=str(document_id))
