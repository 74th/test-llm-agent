"""Starlette API exposing thread CRUD and an AG-UI compatible SSE endpoint."""
from __future__ import annotations
import asyncio
import os
import uuid
from pathlib import Path
from typing import Any
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from poc.adapter import ClaudeAgUiAdapter, event, sse
from poc.claude_runner import sdk_messages
from poc.repository import ThreadRepository
from poc.session_titles import resolve_session_title


def create_app(database: str | Path | None = None, adapter: ClaudeAgUiAdapter | None = None) -> Starlette:
    repository = ThreadRepository(database or os.getenv("POC_DATABASE", "poc.sqlite3"))
    agent = adapter or ClaudeAgUiAdapter(sdk_messages)

    async def list_threads(_: Request) -> JSONResponse:
        return JSONResponse(repository.list_threads())

    async def create_thread(request: Request) -> JSONResponse:
        body = await request.json() if request.headers.get("content-length") not in {None, "0"} else {}
        return JSONResponse(repository.create_thread(body.get("title", "新しいセッション")), status_code=201)

    async def get_thread(request: Request) -> JSONResponse:
        try:
            return JSONResponse(repository.get_thread(request.path_params["thread_id"]))
        except KeyError:
            return JSONResponse({"error": "thread not found"}, status_code=404)

    async def patch_thread(request: Request) -> JSONResponse:
        try:
            return JSONResponse(repository.update_thread(request.path_params["thread_id"], title=(await request.json()).get("title")))
        except KeyError:
            return JSONResponse({"error": "thread not found"}, status_code=404)

    async def run_agent(request: Request):
        body = await request.json()
        thread_id = body.get("threadId")
        run_id = body.get("runId") or str(uuid.uuid4())
        if not thread_id:
            return JSONResponse({"error": "threadId is required"}, status_code=422)
        try:
            thread = repository.get_thread(thread_id)
            repository.begin_run(thread_id, run_id)
        except KeyError:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        incoming = body.get("messages", [])
        user = next((item for item in reversed(incoming) if item.get("role") == "user"), None)
        if not user:
            repository.finish_run(thread_id, run_id, "error")
            return JSONResponse({"error": "a user message is required"}, status_code=422)
        content = user.get("content", "")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if part.get("type") == "text")
        repository.add_message(thread_id, "user", content, message_id=user.get("id"))

        async def generate():
            final_status = "interrupted"
            tool_names: dict[str, str] = {}
            try:
                async for item in agent.stream(content, thread_id=thread_id, run_id=run_id, session_id=thread.get("agentSessionId")):
                    if item["type"] == "TOOL_CALL_START":
                        tool_names[item["toolCallId"]] = item["toolCallName"]
                    elif item["type"] == "TOOL_CALL_ARGS":
                        repository.add_message(thread_id, "assistant", {"type": "tool_call", "toolCallId": item["toolCallId"], "name": tool_names.get(item["toolCallId"], "unknown"), "arguments": item["delta"]}, message_id=f"call-{item['toolCallId']}")
                    elif item["type"] == "TOOL_CALL_RESULT":
                        repository.add_message(thread_id, "tool", {"type": "tool_result", "toolCallId": item["toolCallId"], "content": item["content"]}, message_id=item["messageId"])
                    elif item["type"] == "RUN_FINISHED":
                        result = item.get("result", {})
                        repository.add_message(thread_id, "assistant", result.get("text", ""), message_id=result.get("messageId"))
                        repository.finish_run(thread_id, run_id, "completed", session_id=result.get("sessionId"), state={"lastRunId": run_id})
                        if result.get("sessionId"):
                            title = await asyncio.to_thread(resolve_session_title, result["sessionId"], content)
                            repository.set_generated_title(thread_id, title)
                        final_status = "completed"
                    elif item["type"] == "RUN_ERROR":
                        repository.finish_run(thread_id, run_id, "error")
                        final_status = "error"
                    yield sse(item)
            finally:
                if final_status == "interrupted":
                    try:
                        repository.finish_run(thread_id, run_id, "interrupted")
                    except RuntimeError:
                        pass
        return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    routes = [
        Route("/threads", list_threads, methods=["GET"]), Route("/threads", create_thread, methods=["POST"]),
        Route("/threads/{thread_id}", get_thread, methods=["GET"]), Route("/threads/{thread_id}", patch_thread, methods=["PATCH"]),
        Route("/agent/run", run_agent, methods=["POST"]),
    ]
    app = Starlette(routes=routes, middleware=[Middleware(CORSMiddleware, allow_origins=[os.getenv("WEB_ORIGIN", "http://localhost:3000")], allow_methods=["*"], allow_headers=["*"])])
    app.state.repository = repository
    return app

app = create_app()
