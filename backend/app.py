"""FastAPI backend for Baseball GPT.

POST /api/chat with {"messages": [{"role": "user"|"assistant", "content": "..."}]}
returns a Server-Sent Events stream of JSON events (see agent.run_turn):
    {"type": "text", "text": "..."}                     a chunk of the reply
    {"type": "query", "id", "purpose", "sql"}           Claude ran a SQL query
    {"type": "query_result", "id", "rows", "truncated", "error"}
    {"type": "error", "message": "..."}                 something went wrong
    {"type": "done", "stop_reason": "..."}              the reply is complete
"""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Settings: ANTHROPIC_API_KEY and CLAUDE_* in backend/.env; database settings
# (READER_DATABASE_URL) in the repo-root .env. Must load before the modules
# below read them. Variables already set in the shell take precedence.
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

import anthropic  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import agent  # noqa: E402
import db  # noqa: E402
from schema import schema_prompt  # noqa: E402

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

log = logging.getLogger("baseball_gpt")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await db.close_pool()


# Reads ANTHROPIC_API_KEY from the environment (populated from .env above).
client = anthropic.AsyncAnthropic()
app = FastAPI(title="Baseball GPT", lifespan=lifespan)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/api/chat")
async def chat(req: ChatRequest):
    async def generate():
        try:
            async for event in agent.run_turn(client, [m.model_dump() for m in req.messages]):
                yield sse(event)
        except anthropic.AuthenticationError:
            yield sse({"type": "error", "message": "Invalid or missing ANTHROPIC_API_KEY."})
        except anthropic.RateLimitError:
            yield sse({"type": "error", "message": "Rate limited by the Claude API. Try again shortly."})
        except anthropic.APIStatusError as e:
            log.exception("Claude API error")
            yield sse({"type": "error", "message": f"Claude API error ({e.status_code}): {e.message}"})
        except anthropic.APIConnectionError:
            yield sse({"type": "error", "message": "Could not reach the Claude API."})
        except Exception as e:  # noqa: BLE001 - e.g. database down, no credentials
            log.exception("Unexpected error while streaming")
            yield sse({"type": "error", "message": f"Server error: {e}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    try:
        await schema_prompt()
        database = "ok"
    except Exception as e:  # noqa: BLE001
        database = f"error: {e}"
    return {"status": "ok", "model": agent.MODEL, "database": database}


# Serve the built Vue app (npm run build) when it exists; in dev, Vite serves it.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
