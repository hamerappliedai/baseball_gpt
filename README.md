# Claude Chat Agent

A web chat app: a Vue 3 front end posts the conversation to a Python (FastAPI)
backend, which calls Claude and streams the reply back token by token.

```
chat_agent/
├── backend/          FastAPI app (app.py) — POST /api/chat streams Server-Sent Events
└── frontend/         Vue 3 + Vite app (src/App.vue, src/api.js)
```

## Setup

You need an Anthropic API key and Node 18+ (Vite 5 is pinned so Node 21 works).

Backend:

```bash
cd backend && uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
```

Put your key in `backend/.env` (git-ignored), which the backend loads at startup with python-dotenv:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and set `ANTHROPIC_API_KEY=sk-ant-...`. A variable
already exported in your shell takes precedence over the file.

Frontend:

```bash
cd frontend && npm install
```

## Run (development, with hot reload)

Terminal 1, the API on :8000:

```bash
cd backend && .venv/bin/uvicorn app:app --reload --port 8000
```

Terminal 2, the UI on :5173 (it forwards `/api` to :8000):

```bash
cd frontend && npm run dev
```

Open http://localhost:5173.

## Run (single server)

```bash
cd frontend && npm run build
```

```bash
cd backend && .venv/bin/python app.py
```

FastAPI serves the built UI from `frontend/dist`. Open http://localhost:8000.

## Configuration (environment variables or `backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-5-5` | e.g. `claude-sonnet-5-5` for lower cost |
| `CLAUDE_EFFORT` | `medium` | `low` / `medium` / `high` / `xhigh` / `max`; `low` is often enough for chat |
| `CLAUDE_MAX_TOKENS` | `64000` | per-reply output cap |
| `CLAUDE_SYSTEM_PROMPT` | helpful assistant | |

## How the streaming works

- The backend uses `AsyncAnthropic().beta.messages.stream(...)` and relays each
  text chunk as an SSE event: `{"type": "text"}`, then `{"type": "done"}`. If something
  fails, it sends `{"type": "error"}` instead.
- Server-side refusal fallback (`fallbacks="default"`) is enabled. If a safety
  classifier declines a request, the API re-runs it on a fallback model.
- The front end uses `fetch` and reads the response body as a stream (`EventSource`
  can't send a POST body). Replies are rendered as Markdown and sanitized with DOMPurify.
- The conversation history lives in the browser and is sent with every request.
  Nothing is stored on the server.
