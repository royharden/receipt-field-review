"""Authored ASGI messages test admission state, not an HTTP server or cancellable transport."""

import pytest

from rfr.api.body import JsonBody
from rfr.api.security import RequestGuard, RequestRefused

ORIGIN = "http://127.0.0.1:23456"  # Message-only test context; no listener is bound.
TOKEN = "a" * 40  # Authored test capability, not a provider key.


def decoder(*, maximum=1024, length=None, **kwargs):
    headers = [
        (b"host", b"127.0.0.1:23456"),
        (b"origin", ORIGIN.encode()),
        (b"x-rfr-token", TOKEN.encode()),
        (b"content-type", b"application/json"),
    ]
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    return JsonBody(RequestGuard(ORIGIN, TOKEN, maximum), "POST", headers, **kwargs)


def message(body=b"", more=False):
    return {"type": "http.request", "body": body, "more_body": more}


def test_fragmented_utf8_body_is_admitted_only_after_complete_and_exact_length():
    raw = '{"merchant":"Café"}'.encode()
    body = decoder(length=len(raw))
    split = raw.index(b"\xc3") + 1
    assert body.feed(message(raw[:split], True)) is False
    assert body.feed(message(raw[split:])) is True
    assert body.value() == {"merchant": "Café"}


def test_actual_bytes_are_bounded_with_no_declared_length():
    body = decoder(maximum=8)
    assert body.feed(message(b"1234", True)) is False
    with pytest.raises(RequestRefused) as error:
        body.feed(message(b"56789"))
    assert error.value.status == 413 and error.value.code == "request_body_limit"
    with pytest.raises(RequestRefused, match="body_already_refused"):
        body.value()


@pytest.mark.parametrize("length", [1, 3])
def test_length_mismatch_refuses_without_a_value(length):
    body = decoder(length=length)
    with pytest.raises(RequestRefused, match="content_length_mismatch"):
        body.feed(message(b"{}"))


def test_zero_byte_message_flood_is_bounded():
    body = decoder(max_messages=2)
    assert not body.feed(message(more=True))
    assert not body.feed(message(more=True))
    with pytest.raises(RequestRefused) as error:
        body.feed(message(more=True))
    assert error.value.status == 413 and error.value.code == "body_message_limit"


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "http.disconnect"},
        {"type": "websocket.receive", "body": b"{}"},
        {"type": "http.request", "body": "{}"},
        {"type": "http.request", "body": b"{}", "more_body": "false"},
        {"type": "http.request", "body": b"{}", "unexpected": True},
    ],
)
def test_disconnect_and_invalid_messages_fail_closed(payload):
    body = decoder()
    with pytest.raises(RequestRefused):
        body.feed(payload)
    with pytest.raises(RequestRefused, match="body_already_refused"):
        body.value()


@pytest.mark.parametrize(
    "payload", [b'{"private":1,"private":2}', b'{"private":NaN}', b"\xff", b"{"]
)
def test_malformed_json_has_closed_diagnostics(payload):
    body = decoder()
    body.feed(message(payload))
    with pytest.raises(RequestRefused) as error:
        body.value()
    assert error.value.code == "invalid_json_body" and str(error.value) == "invalid_json_body"


def test_incomplete_and_extra_messages_never_supply_a_reusable_value():
    partial = decoder()
    partial.feed(message(b"{", True))
    with pytest.raises(RequestRefused, match="body_incomplete"):
        partial.value()
    complete = decoder()
    complete.feed(message(b"{}"))
    with pytest.raises(RequestRefused, match="body_already_complete"):
        complete.feed(message(b"{}"))
    with pytest.raises(RequestRefused, match="body_already_refused"):
        complete.value()


def test_header_admission_rejects_before_body_state_is_created():
    with pytest.raises(RequestRefused) as error:
        JsonBody(RequestGuard(ORIGIN, TOKEN), "POST", [(b"host", b"127.0.0.1:23456")])
    assert error.value.status == 401
