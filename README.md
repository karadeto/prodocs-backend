# ProDocs

AI document management: scan a document, it files itself into the right folder; ask
questions across everything you've filed.

This is the Python/React rewrite of the original .NET + Flutter app, rebuilt around the
lessons from that first implementation: **fewer LLM decision points, deterministic-first
routing, verifiable evidence instead of self-reported confidence, and evals from day one.**

## Repo layout

| Package | Stack | What it is |
|---|---|---|
| [`backend/`](backend/README.md) | FastAPI · SQLAlchemy 2.0 async · PostgreSQL + pgvector · procrastinate · pydantic-ai | API, ingestion pipeline, routing cascade, hybrid retrieval, chat agent |
| [`web/`](web/README.md) | Vite · React 19 · TanStack Router/Query · Tailwind 4 | SPA client: library, document detail, review inbox, streaming chat |

Each package has its own README with the design rationale; this file only covers how they
fit together and how to get both running.

## How it fits together

```
web (localhost:3000)  ──/api──>  backend API (localhost:5275)  ──>  Postgres + pgvector
      Vite proxy                        │                              (data + job queue)
                                        │
                                  procrastinate worker
                                        │
                      parse → extract → facts → route → chunk & embed
```

The upload endpoint returns immediately and enqueues a job; the worker runs the pipeline;
the web client polls documents in `processing` until they settle. Jobs live in the same
Postgres as the data, so enqueueing is transactional with the write that caused it.

Routing is a cascade, not a prompt: a user-taught rule wins first, then vendor history,
then an LLM taxonomy code that only counts if its quotes are verbatim in the document —
and anything that falls through lands in the review inbox rather than a silent `Sonstiges`
folder. Confirming or moving a document there writes a rule, so the system converges per
user instead of being frozen at prompt quality.

## Getting started

Prerequisites: Docker (for Postgres), [uv](https://docs.astral.sh/uv/), Node 20+, and an
OpenAI or Azure OpenAI key.

```bash
# 1. Backend — three terminals' worth, in order
cd backend
cp .env.example .env       # fill in OPENAI_API_KEY (or Azure), SUPABASE_JWT_SECRET
make install               # uv sync --extra dev
make db-up                 # pgvector via docker compose
make db-init               # tables, indexes, procrastinate schema
make api                   # http://localhost:5275
make worker                # second terminal

# 2. Web
cd web
npm install
npm run dev                # http://localhost:3000, proxies /api -> :5275
```

Without `SUPABASE_URL` configured on the backend, auth runs in dev mode: any
email/password works. Scanned documents and images need docling
(`uv sync --extra parse` in `backend/` — large install, pulls torch); text PDFs work
without it via the pypdf fallback.

## Before you ship a prompt, model, or taxonomy change

```bash
cd backend
make test    # pure-logic unit tests: routing cascade, evidence check, chunking, vendor matching
make eval    # real LLM classification against evals/golden/folders.sample.jsonl
```

The golden set ships with 8 synthetic documents to demonstrate the format. Replace and
extend it with real anonymized documents — especially every document the system ever
misfiles. It's the difference between "I think the prompt is better" and "accuracy went
71% → 84%, with two regressions, here they are."

## Status

The core loop (upload → file → review → chat) is complete. Tax categorization/Elster
export, calendar events, contract cancellation, sharing, and realtime push are
deliberately not ported yet — each returns once the core loop's eval numbers are healthy,
and each gets its own golden set first. Schema management is `scripts/init_db.py`
(`create_all`) until the schema stabilizes; alembic after that.
