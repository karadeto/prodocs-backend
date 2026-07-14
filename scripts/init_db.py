"""Create extensions, tables, functional indexes, and the procrastinate schema.

Dev bootstrap: `uv run python scripts/init_db.py`
(For production, move to alembic once the schema stabilizes.)
"""

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.models import Base  # noqa: E402

EXTRA_DDL = [
    # Folder name uniqueness incl. NULL parents (root folders).
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_folders_user_parent_name
    ON folders (user_id,
                coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid),
                lower(name))
    """,
]


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        for ddl in EXTRA_DDL:
            await conn.execute(text(ddl))
    await engine.dispose()

    # procrastinate's own tables
    subprocess.run(
        ["procrastinate", "--app", "app.ingestion.worker.pq_app", "schema", "--apply"],
        check=True,
        env=None,
    )
    print(f"Database initialized: {get_settings().database_url}")


if __name__ == "__main__":
    asyncio.run(main())
