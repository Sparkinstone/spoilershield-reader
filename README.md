# SpoilerShield

AI-powered anti-spoiler reader. Upload an ebook, read it, comment on any
paragraph — a retrieval + LLM pipeline decides whether the comment spoils later
plot and hides it (or sends it to human review).

## Stack

FastAPI · Jinja2 + HTMX · SQLite · sentence-transformers (embeddings) ·
DeepSeek Flash via an OpenAI-compatible endpoint (default).

## Quick start

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
cp .env.example .env             # then set LLM_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On Windows, double-click `启动应用.bat` instead: it starts the server, waits
for `/ping` to answer, and only then opens the browser (no more "connection
refused" on the first load). The launcher also accepts `--port`, `--reload`,
`--no-browser` and `--host`:

```bash
python scripts/launch.py --port 8080
```

Open http://localhost:8000, upload a PDF / EPUB / TXT, click a paragraph, post a
comment. `/admin` is the moderation queue.

Verify the model connection before using the app:

```bash
python scripts/check_llm.py
```

## Configuration

All settings are read from `.env` (or the process environment). See
`.env.example` for the full list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | — | API key. Falls back to `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`. |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | Any OpenAI-compatible endpoint. Falls back to `OPENAI_API_BASE`. |
| `LLM_MODEL` | `deepseek-flash` | Model name sent to the endpoint. |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | `30` / `2` | Per-request timeout and retry budget (429 / 5xx / timeouts). |
| `LLM_SSL_VERIFY` | `true` | Set `false` only for a private gateway with a broken certificate. |
| `SPOILER_CONFIDENCE_THRESHOLD` | `0.7` | Below this the comment goes to `PENDING_REVIEW`. |
| `MAX_UPLOAD_MB` / `MAX_PARAGRAPHS` | `20` / `5000` | Upload guards. |
| `MAX_COMMENT_CHARS` | `500` | Comment length guard. |
| `EMBEDDING_ALLOW_DOWNLOAD` | `true` | Cache-first model loading; set `false` for air-gapped deployments. |
| `ADMIN_USER` / `ADMIN_PASSWORD` | `admin` / — | Basic auth for `/admin`. Unset = localhost-only access. |

Switching providers only needs env changes: `LLM_BASE_URL` + `LLM_MODEL` +
`LLM_API_KEY`. The Anthropic SDK is no longer used.

## Tests

```bash
python -m pytest
```

The suite (131 tests) runs fully offline: embeddings and the LLM are replaced
with fakes through FastAPI dependency overrides, so no model download and no API
key are needed. Coverage includes upload security (path traversal, size/type
limits), parsers (encoding, PDF line wrapping, EPUB TOC), the retrieval
pipeline, retry/error classification, comment moderation states, and admin
authentication.

## Project layout

```
app/
  config.py           env-driven settings
  database.py         engine, session, templates, indexes
  models.py           books / paragraphs / comments
  routers/            upload, reader, comments, admin
  services/parser.py  TXT/PDF/EPUB → paragraphs
  services/embedding.py  vector + keyword recall
  services/llm.py     OpenAI-compatible client, retries, JSON validation
  services/spoiler_detector.py  retrieval → future filter → LLM
  static/app.css      local design system (no CDN)
  static/app.js       vanilla JS: comment dialog, TOC, progress, spoilers
  templates/          Jinja2 pages (Chinese UI)
scripts/
  launch.py           start server, wait for /ping, then open the browser
  check_llm.py        live model connectivity check
  seed_test_comments.py  batch-generate labelled comments + accuracy report
```

## Offline behaviour

The app is fully self-contained: CSS, JavaScript, icons and fonts are local files
under `app/static/`, with no Tailwind CDN, htmx, or web fonts.

- The embedding model is loaded cache-first (`local_files_only`). With
  `all-MiniLM-L6-v2` cached, the first upload/comment is ready in ~0.1s even
  offline. Without a cache, the request fails within a couple of seconds with a
  503 that names the missing model instead of retrying HuggingFace for minutes.
- Verified with headless Chrome against a local server: zero external resource
  requests, no horizontal overflow at 390px, and the comment dialog, spoiler
  reveal and TOC drawer work with the local JS.
- Comment posting still needs the LLM endpoint. Offline it degrades to
  `PENDING_REVIEW` with an explicit "AI 审核暂不可用" notice instead of losing the
  comment.

## Deployment

This is a single-node app: one uvicorn worker, SQLite, ~1 GB RSS for the
embedding model. A 2 vCPU / 4 GB Linux VPS is the practical minimum.

- `Dockerfile` + `docker-compose.yml` + `deploy/Caddyfile`: app behind Caddy with
  automatic HTTPS, state in a named volume.
- `deploy/nginx.conf` + `deploy/spoilershield.service`: bare Ubuntu/Debian with
  systemd and Nginx.
- Set `ADMIN_PASSWORD` (the localhost bypass is refused behind a proxy), keep
  only 22/80/443 open, and set `ALLOW_UPLOADS=false` after seeding a demo book.

Full runbook, backup commands and security checklist:
[deploy/README.md](deploy/README.md). For 宝塔面板 / OpenCloudOS 9 (Nginx already
owns 80/443), use [deploy/BAOTA.md](deploy/BAOTA.md) instead.

## Known limitations

- The accuracy report in `spoiler_detection_report/` was measured on
  LLM-generated comments, so 98.8% is an optimistic upper bound, not a field
  metric; real-user precision/recall still needs a labelled sample.
- `all-MiniLM-L6-v2` is an English model used on Chinese text; vector recall is
  weak and the lexical path carries much of the load. Changing
  `EMBEDDING_MODEL` is supported (dimension mismatches are re-encoded on read).
- Single-node SQLite + local uploads; no queue, rate limiting, or CSRF token.
  Fine for a demo, not for public multi-user deployment without those.
