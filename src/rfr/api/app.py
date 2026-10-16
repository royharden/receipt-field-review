"""Local recognized-bundle FastAPI adapter. Factory only; no listener or live-model fallback."""

import asyncio
import json
import math
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from ..pipeline.files import BatchError
from ..receipt.models import MINOR_UNITS
from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.store import GenerationConflict, JournalError, PriorConflict
from .body import JsonBody
from .models import (
    ApiStatus,
    Capabilities,
    CreateBatch,
    DecisionDraft,
    DraftRequest,
    RecognizedImport,
)
from .operations import ReviewOperations
from .security import RequestGuard, RequestRefused


class Admission:
    def __init__(self, app: ASGIApp, *, guard: RequestGuard):
        self.app, self.guard = app, guard

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return

        async def private_response(message):
            if message["type"] == "http.response.start":
                headers = [
                    h
                    for h in message.get("headers", [])
                    if h[0].lower() not in {b"cache-control", b"x-content-type-options"}
                ]
                message = {
                    **message,
                    "headers": [
                        *headers,
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ],
                }
            await send(message)

        try:
            self.guard.authorize(scope["method"], scope["headers"])
        except RequestRefused as error:
            await JSONResponse({"error": error.code}, status_code=error.status)(
                scope, receive, private_response
            )
            return
        await self.app(scope, receive, private_response)


def create_app(
    data_root: Path,
    *,
    origin: str,
    capability: str,
    max_body_bytes: int = 8 * 1024 * 1024 + 4096,
    body_timeout_s: float = 5.0,
) -> FastAPI:
    if (
        type(body_timeout_s) not in (int, float)
        or not math.isfinite(body_timeout_s)
        or not 0 < body_timeout_s <= 30
    ):
        raise ValueError("bounded_body_deadline_required")
    guard = RequestGuard(origin, capability, max_body_bytes)
    operations = ReviewOperations(data_root)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, debug=False)
    app.add_middleware(Admission, guard=guard)

    async def body(request, model):
        accumulator = JsonBody(guard, request.method, request.scope["headers"])
        try:
            async with asyncio.timeout(body_timeout_s):
                while not accumulator.complete:
                    accumulator.feed(await request.receive())
        except TimeoutError:
            raise RequestRefused(408, "request_body_timeout") from None
        except (OSError, RuntimeError) as error:
            if isinstance(error, RequestRefused):
                raise
            raise RequestRefused(400, "body_stream_refused") from None
        return model.model_validate_json(canonical_bytes(accumulator.value()))

    async def request_refused(request, error):
        return JSONResponse({"error": error.code}, status_code=error.status)

    async def conflict(request, error):
        return JSONResponse({"error": "revision_conflict"}, status_code=409)

    async def invalid(request, error):
        return JSONResponse({"error": "invalid_request_or_state"}, status_code=400)

    async def missing(request, error):
        return JSONResponse({"error": "not_found"}, status_code=404)

    async def journal(request, error):
        return JSONResponse({"error": "journal_refused"}, status_code=409)

    async def storage(request, error):
        return JSONResponse({"error": "storage_unavailable"}, status_code=503)

    async def unexpected(request, error):
        # Starlette's outer server-error middleware sends this response outside Admission.
        return JSONResponse(
            {"error": "internal_error"},
            status_code=500,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    for error_type, handler in [
        (RequestRefused, request_refused),
        (GenerationConflict, conflict),
        (PriorConflict, conflict),
        (RequestValidationError, invalid),
        (ValueError, invalid),
        (BatchError, invalid),
        (FileNotFoundError, missing),
        (JournalError, journal),
        (OSError, storage),
        (Exception, unexpected),
    ]:
        app.add_exception_handler(error_type, handler)

    @app.get("/api/status")
    async def status():
        return ApiStatus(
            mode="local",
            stage="recognized-http/1",
            currencies=tuple(MINOR_UNITS),
            capabilities=Capabilities(
                recognized_import=True,
                image_upload=False,
                source_images=False,
                review_persistence=True,
                local_b0=False,
                jev=False,
                vision=False,
            ),
        )

    @app.post("/api/batches", status_code=201)
    async def create_batch(request: Request):
        return await run_in_threadpool(operations.create, await body(request, CreateBatch))

    @app.get("/api/batches/{batch_id}/items")
    async def items(batch_id: str):
        return await run_in_threadpool(operations.items, batch_id)

    @app.post("/api/batches/{batch_id}/recognized", status_code=201)
    async def import_recognized(batch_id: str, request: Request):
        supplied = await body(request, RecognizedImport)
        revision = await run_in_threadpool(operations.import_recognized, batch_id, supplied)
        return {"item_id": supplied.bundle.document.document_id, "revision": revision}

    @app.get("/api/batches/{batch_id}/items/{item_id}")
    async def detail(batch_id: str, item_id: str):
        return await run_in_threadpool(operations.detail, batch_id, item_id)

    @app.post("/api/batches/{batch_id}/items/{item_id}/draft")
    async def draft(batch_id: str, item_id: str, request: Request):
        supplied = await body(request, DraftRequest)
        return await run_in_threadpool(operations.draft, batch_id, item_id, supplied)

    @app.post("/api/batches/{batch_id}/items/{item_id}/decisions")
    async def apply(batch_id: str, item_id: str, request: Request):
        supplied = await body(request, DecisionDraft)
        return await run_in_threadpool(operations.apply, batch_id, item_id, supplied)

    @app.get("/api/batches/{batch_id}/exports/{mode}/{filename}")
    async def export(batch_id: str, mode: Literal["review", "clean"], filename: str):
        types = {
            "receipts.csv": "text/csv",
            "line_items.csv": "text/csv",
            "receipts.jsonl": "application/x-ndjson",
            "omitted.json": "application/json",
        }
        if filename not in types:
            return JSONResponse({"error": "not_found"}, status_code=404)
        files = await run_in_threadpool(operations.export, batch_id, mode=mode)
        omissions = json.loads(files["omitted.json"])
        if mode == "clean" and not omissions["exported_N"] and filename != "omitted.json":
            return JSONResponse(
                {"error": "clean_export_empty", "omissions": omissions}, status_code=409
            )
        return Response(
            files[filename],
            media_type=types[filename],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
