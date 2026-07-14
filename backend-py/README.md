# ProDocs Backend (Python)

Python rewrite of `ProdocsBackend/` (.NET). Same product — scan a document, it files
itself into the right folder; ask questions across your documents — rebuilt around the
lessons from the first implementation: **fewer LLM decision points, deterministic-first
routing, verifiable evidence instead of self-reported confidence, and evals from day one.**

## Stack & why

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI + uvicorn | Standard, typed, async |
| DB | PostgreSQL + pgvector (unchanged) | The .NET app's best decision — kept |
| ORM | SQLAlchemy 2.0 async + asyncpg | Typed models, one schema definition |
| Jobs | procrastinate | Postgres-native queue: jobs are transactional with data, no lease juggling |
| LLM | pydantic-ai | Strict structured outputs (no JSON-repair prompts), provider-agnostic (`openai:` / `azure:`) |
| Parsing | docling (optional extra) + pypdf fallback | Layout-aware, handles scans; full document, not page 1 |
| Embeddings | text-embedding-3-small, 1536 dims | Cheap, multilingual |
| Storage | Cloudflare R2 via boto3 (local disk in dev) | Unchanged |
| Auth | Supabase JWT (HS256), unchanged | Existing Flutter/React clients keep working |

## Architecture

```
upload ──> blob store ──> procrastinate job
                              │
              ┌───────────────┴────────────────┐
              │  ingestion pipeline (worker)   │
              │  1. parse   (docling, full doc)│
              │  2. extract (ONE structured    │
              │     LLM pass -> DocumentRecord)│
              │  3. facts   (party + fact row) │
              │  4. route   (cascade, below)   │
              │  5. chunk & embed              │
              └────────────────────────────────┘

routing cascade:                       chat:
  1. RoutingRule (user-taught) ──auto    one pydantic-ai agent, 4 tools:
  2. vendor history ──────────auto         search_documents (hybrid RRF)
  3. LLM code + evidence ──review          query_facts      (SQL)
  4. fallback Sonstiges ───review          get_document     (full text)
                                           list_folders
  review confirm/move ──> new RoutingRule
```

Design rules carried over from the post-mortem of the .NET version:

- **The LLM classifies; it never decides.** Its output is a taxonomy code from a
  closed enum — folder resolution, vendor folders, year folders are deterministic code
  (`app/ingestion/routing.py`), unit-tested, with a DB uniqueness constraint against
  duplicate folders.
- **Evidence over confidence.** A classification only counts if ≥2 verbatim quotes
  from the model actually appear in the document text (`extract.py`). Self-reported
  confidence scores are not used anywhere.
- **Corrections are permanent.** Confirming/moving a document in the review inbox
  writes a `RoutingRule`; that vendor is never LLM-routed again. The system converges
  per user instead of being frozen at prompt quality.
- **No silent Sonstiges.** Everything not routed by a rule or history lands in the
  review inbox (`GET /api/v1/review`), visibly.
- **No intent router.** The chat agent decides per turn which tool answers the
  question; ambiguity = the model asks back. ~200 lines replace ~2,000.
- **Every decision is auditable.** `GET /api/v1/documents/{id}/events` shows each
  pipeline stage including the full extracted record.
- **Language-neutral.** English prompts (documents may be any language, answers follow
  the user's language), `simple` FTS config + multilingual embeddings instead of
  German-only stemming/keywords.

## Getting started

```bash
cd backend-py
cp .env.example .env       # fill in OPENAI_API_KEY (or Azure), SUPABASE_JWT_SECRET
make install               # uv sync --extra dev
make db-up                 # local pgvector via docker compose
make db-init               # tables + indexes + procrastinate schema
make api                   # http://localhost:5275  (same port the frontends expect)
make worker                # in a second terminal
```

Scanned documents/images need docling: `uv sync --extra parse` (large install).

## Evals — run these before shipping any prompt/model/taxonomy change

```bash
make test    # pure-logic unit tests (routing cascade, evidence, chunking, vendor matching)
make eval    # real LLM classification against evals/golden/folders.sample.jsonl
```

The golden set ships with 8 synthetic documents to demonstrate the format.
**Replace/extend it with real anonymized documents** — especially every document the
system ever misfiles. That file is the project's most valuable asset: it is the
difference between "I think the prompt is better" and "accuracy went 71% → 84% with
two regressions, here they are".

## API surface (all under `/api/v1`, Supabase bearer auth)

| Endpoint | Purpose |
|---|---|
| `POST /documents` (multipart) | Upload; returns immediately, pipeline runs async |
| `GET /documents?folder_id=&status=` | List |
| `GET /documents/{id}` | Detail incl. extracted facts |
| `GET /documents/{id}/file` | Presigned R2 URL (or bytes in dev) |
| `GET /documents/{id}/events` | Ingestion audit trail |
| `POST /documents/{id}/reprocess` | Re-run pipeline |
| `GET /folders`, `POST /folders` | Tree with counts; create |
| `GET /review` | Documents awaiting confirmation |
| `POST /review/{id}` `{action: confirm\|move, folder_id?}` | Resolve; learns a rule |
| `POST /chat/stream` `{message, thread_id?}` | SSE: `token`, `sources`, `done` |
| `GET /chat/threads`, `GET /chat/threads/{id}/messages` | History |

## Deliberately not ported (yet)

Tax categorization/Elster/SKR export, calendar events, contract cancellation, sharing,
push/SignalR realtime (clients poll `GET /documents/{id}` for status; add Supabase
Realtime later). Each should return only once the core loop's eval numbers are healthy,
and each gets its own golden set first.

Schema management is `scripts/init_db.py` (create_all) for now — move to alembic once
the schema stabilizes.
