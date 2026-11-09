"""FastAPI backend that streams Claude responses to the Vue front end.

POST /api/chat with {"messages": [{"role": "user"|"assistant", "content": "..."}]}
returns a Server-Sent Events stream of JSON events:
    {"type": "text", "text": "..."}   - a chunk of the reply
    {"type": "error", "message": "..."} - something went wrong
    {"type": "done", "stop_reason": "..."} - the reply is complete
"""

import json
import logging
import os
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Load ANTHROPIC_API_KEY (and optional CLAUDE_* settings) from backend/.env.
# Must run before the settings below are read and before the client is created.
# Variables already set in the shell take precedence over the file.
load_dotenv(Path(__file__).resolve().parent / ".env")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "64000"))
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")  # low | medium | high | xhigh | max
SYSTEM_PROMPT = os.environ.get(
    "CLAUDE_SYSTEM_PROMPT",
    "You are a helpful assistant. Format answers in Markdown when it aids readability.",
)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

log = logging.getLogger("chat_agent")

# Reads ANTHROPIC_API_KEY from the environment (populated from .env above).
client = anthropic.AsyncAnthropic()
app = FastAPI(title="Claude Chat Agent")


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
            async with client.beta.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                output_config = {"effort": EFFORT},
                # If a safety classifier declines, the API retries on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[m.model_dump() for m in req.messages],
            ) as stream:
                async for text in stream.text_stream:
                    yield sse({"type": "text", "text": text})
                final = await stream.get_final_message()

            if final.stop_reason == "refusal":
                yield sse({"type": "error", "message": "Claude declined to answer this request."})
            elif final.stop_reason == "max_tokens":
                yield sse({"type": "error", "message": "Reply was cut off (max_tokens reached)."})
            yield sse({"type": "done", "stop_reason": final.stop_reason})

        except anthropic.AuthenticationError:
            yield sse({"type": "error", "message": "Invalid or missing ANTHROPIC_API_KEY."})
        except anthropic.RateLimitError:
            yield sse({"type": "error", "message": "Rate limited by the Claude API. Try again shortly."})
        except anthropic.APIStatusError as e:
            log.exception("Claude API error")
            yield sse({"type": "error", "message": f"Claude API error ({e.status_code}): {e.message}"})
        except anthropic.APIConnectionError:
            yield sse({"type": "error", "message": "Could not reach the Claude API."})
        except Exception as e:  # noqa: BLE001 - e.g. no credentials configured
            log.exception("Unexpected error while streaming")
            yield sse({"type": "error", "message": f"Server error: {e}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "model": MODEL}


# Serve the built Vue app (npm run build) when it exists; in dev, Vite serves it.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
