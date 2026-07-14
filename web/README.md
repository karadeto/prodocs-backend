# ProDocs Web

Web client for the Python backend (`backend-py/`). Replaces `frontend/` (which targeted the
old .NET API and is now reference-only).

## Stack

- **Vite + React 19** — plain SPA, no SSR server. An authenticated SaaS tool gains nothing
  from SSR; the build is static files you can host anywhere.
- **TanStack Router** — type-safe file-based routing (`src/routes/`, tree auto-generated).
- **TanStack Query** — server state, cache invalidation, and status polling
  (documents in `processing` refetch every 2.5 s until they settle).
- **Tailwind CSS 4** — design tokens live in `@theme` in `src/styles.css`.

## Design system

The visual language borrows from physical filing (binder registers, spine labels):

- **Palette**: paper `#F5F5F1`, ink `#22262F` (text *and* primary buttons), hairlines,
  and a signature binder-amber `#E29A1D` reserved for identity moments — the active
  register-tab in the sidebar, the brand glyph, selection states.
- **Type**: Archivo (display), IBM Plex Sans (body), IBM Plex Mono for all data —
  amounts, dates, codes, status chips, eyebrow labels.
- **Signature**: active sidebar items are register tabs — tab-shaped, flush to the
  content edge, 3 px amber spine.
- Statuses: `Filing` (blue, pulsing) → `Filed` (green) / `Review` (amber) / `Failed` (red).

## Screens

| Route | What it does |
|---|---|
| `/login` | Sign in / create account (via backend `/auth/*`; dev mode needs no Supabase) |
| `/` | Library: folder tree, ledger-style rows (vendor · date · amount), drag-drop upload, live filing status |
| `/documents/:id` | Extracted facts, filed-in path with reasoning, processing log (audit trail), download/move/reprocess |
| `/review` | Review inbox: "Looks right" / "Move to…" — every answer teaches a routing rule |
| `/chat` | Streaming chat (SSE) with per-answer source citations linking to documents |

## Run

```bash
cd web
npm install
npm run dev        # http://localhost:3000, proxies /api -> http://127.0.0.1:5275
```

Backend must be running (see `backend-py/README.md`). Without `SUPABASE_URL` configured
on the backend, any email/password works (local dev tokens).

`npm run build` outputs static files to `dist/` and typechecks.
