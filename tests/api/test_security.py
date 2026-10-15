"""Independent admission vectors. No listener, HTTP integration or Windows ACL claim."""

import pytest

from rfr.api.security import RequestGuard, RequestRefused

ORIGIN = "http://127.0.0.1"
TOKEN = "literal-test-capability-not-a-real-secret"


def headers(**changes):
    values = {
        "host": "127.0.0.1",
        "x-rfr-token": TOKEN,
        "origin": ORIGIN,
        "content-type": "application/json",
    }
    values.update(changes)
    return [(k.encode("ascii"), v.encode("ascii")) for k, v in values.items() if v is not None]


def test_same_origin_mutation_and_authenticated_read_do_not_echo_capability():
    guard = RequestGuard(ORIGIN, TOKEN)
    assert guard.authorize("POST", headers()) is None
    assert guard.authorize("GET", headers(origin=None)) is None
    assert TOKEN not in repr(guard)


@pytest.mark.parametrize(
    "method,change,code,status",
    [
        ("GET", {"host": "evil.example"}, "host_refused", 403),
        ("GET", {"host": "127.0.0.1.evil.example"}, "host_refused", 403),
        ("GET", {"host": "localhost"}, "host_refused", 403),
        ("GET", {"x-rfr-token": None}, "capability_required", 401),
        ("GET", {"x-rfr-token": "wrong"}, "capability_required", 401),
        ("GET", {"origin": "https://evil.example"}, "origin_refused", 403),
        ("POST", {"origin": None}, "mutation_origin_required", 403),
        ("POST", {"content-type": "text/plain"}, "json_content_type_required", 415),
        ("POST", {"content-type": None}, "json_content_type_required", 415),
        ("POST", {"sec-fetch-site": "cross-site"}, "fetch_site_refused", 403),
        ("OPTIONS", {}, "method_refused", 405),
        ("POST", {"content-length": "99999999"}, "request_body_limit", 413),
        ("POST", {"content-length": "-1"}, "invalid_content_length", 400),
        ("POST", {"content-length": "1,1"}, "invalid_content_length", 400),
        ("POST", {"transfer-encoding": "chunked"}, "transfer_encoding_refused", 400),
    ],
)
def test_foreign_rebinding_capability_origin_content_and_length_refusals(
    method, change, code, status
):
    with pytest.raises(RequestRefused) as caught:
        RequestGuard(ORIGIN, TOKEN).authorize(method, headers(**change))
    assert caught.value.code == code and caught.value.status == status
    assert TOKEN not in str(caught.value) and "evil.example" not in str(caught.value)


@pytest.mark.parametrize(
    "extra",
    [
        (b"Host", b"127.0.0.1"),
        (b"Origin", ORIGIN.encode()),
        (b"X-RFR-Token", TOKEN.encode()),
        (b"content-type", b"application/json"),
    ],
)
def test_duplicate_security_headers_refuse_even_when_identical(extra):
    with pytest.raises(RequestRefused, match="duplicate_security_header"):
        RequestGuard(ORIGIN, TOKEN).authorize("POST", [*headers(), extra])


@pytest.mark.parametrize(
    "raw",
    [
        [(b"host", b"127.0.0.1\r\nevil")],
        [(b"x-rfr-token", b"\xff")],
        [(b"x-rfr-token", b"a" * 2049)],
        [(b"x", b"x")] * 65,
    ],
)
def test_malformed_and_unbounded_headers_fail_closed(raw):
    with pytest.raises(RequestRefused):
        RequestGuard(ORIGIN, TOKEN).authorize("POST", raw)


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:",
        "http://user@localhost",
        "http://127.0.0.1/path",
    ],
)
def test_server_guard_itself_requires_exact_canonical_loopback_configuration(origin):
    with pytest.raises(ValueError):
        RequestGuard(origin, TOKEN)
