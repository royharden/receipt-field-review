"""Bounded ASGI-message accumulator. Cancellable transport deadlines remain caller work."""

from typing import Never

from pydantic import JsonValue

from ..shared.execution.callledger.models import decode_wire_json
from .security import RequestGuard, RequestRefused


class JsonBody:
    """Authorize before feeding messages; never trust Content-Length as the actual byte bound."""

    def __init__(self, guard: RequestGuard, method, raw_headers, *, max_messages=1024):
        headers = tuple(raw_headers) if type(raw_headers) in (tuple, list) else raw_headers
        guard.authorize(method, headers)
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            raise RequestRefused(405, "json_body_method_required")
        if type(max_messages) is not int or not 1 <= max_messages <= 4096:
            raise ValueError("bounded_message_count_required")
        self.maximum = guard.max_body_bytes
        self.max_messages = max_messages
        self.expected = next(
            (int(value) for key, value in headers if key.lower() == b"content-length"), None
        )
        self.messages = 0
        self.complete = False
        self.failed = False
        self._body = bytearray()

    def _refuse(self, status, code) -> Never:
        self.failed = True
        self._body.clear()
        raise RequestRefused(status, code)

    def feed(self, message: dict[str, object]) -> bool:
        if self.failed:
            self._refuse(400, "body_already_refused")
        if self.complete:
            self._refuse(400, "body_already_complete")
        if type(message) is not dict:
            self._refuse(400, "invalid_body_message")
        if message.get("type") == "http.disconnect":
            self._refuse(400, "body_disconnected")
        if message.get("type") != "http.request" or set(message) - {"type", "body", "more_body"}:
            self._refuse(400, "invalid_body_message")
        part, more = message.get("body", b""), message.get("more_body", False)
        if type(part) is not bytes or type(more) is not bool:
            self._refuse(400, "invalid_body_message")
        self.messages += 1
        if self.messages > self.max_messages:
            self._refuse(413, "body_message_limit")
        size = len(self._body) + len(part)
        if size > self.maximum:
            self._refuse(413, "request_body_limit")
        if self.expected is not None and size > self.expected:
            self._refuse(400, "content_length_mismatch")
        self._body.extend(part)
        if not more:
            if self.expected is not None and size != self.expected:
                self._refuse(400, "content_length_mismatch")
            self.complete = True
        return self.complete

    def value(self) -> JsonValue:
        if self.failed:
            self._refuse(400, "body_already_refused")
        if not self.complete:
            self._refuse(400, "body_incomplete")
        try:
            return decode_wire_json(self._body.decode("utf-8"), max_bytes=self.maximum)
        except (UnicodeError, ValueError, RecursionError):
            self._refuse(400, "invalid_json_body")
