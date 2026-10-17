"""Real in-process ASGI request path; authored input, no TCP/OCR/model or human Gold claim."""

import asyncio
import csv
import io
import json
import socket

import pytest
from fastapi.testclient import TestClient

from rfr.api.app import create_app
from rfr.api.models import CreateBatch, DraftRequest, RecognizedImport
from rfr.receipt.models import CurrencyPolicy

ORIGIN = "http://127.0.0.1:24002"
TOKEN = "synthetic-test-capability-0000000000"
HEADERS = {"X-RFR-Token": TOKEN, "Origin": ORIGIN}


def client(root, **options):
    return TestClient(
        create_app(root, origin=ORIGIN, capability=TOKEN, **options),
        base_url=ORIGIN,
        headers=HEADERS,
    )


def post(c, path, model, status=200):
    result = c.post(path, json=model.model_dump(mode="json"))
    assert result.status_code == status, result.text
    return result.json()


def imported(c, bundle):
    batch = post(c, "/api/batches", CreateBatch(currency=CurrencyPolicy()), 201)["batch_id"]
    result = post(c, f"/api/batches/{batch}/recognized", RecognizedImport(bundle=bundle), 201)
    return f"/api/batches/{batch}", result["revision"]


def decide(c, base, item, view, field, action, *, value=None, issues=()):
    detail = view["fields"][field]
    request = DraftRequest(
        field_id=field,
        action=action,
        value=value,
        expected_item_revision=view["revision"],
        expected_prior_event_id=detail["head_event_id"],
        actor="synthetic-http-control",
        reason="Authored HTTP control; no human Gold claim",
        waive_issues=tuple(issues),
        issue_reason="Explicit synthetic waiver" if issues else None,
    )
    draft = post(c, f"{base}/items/{item}/draft", request)
    response = c.post(f"{base}/items/{item}/decisions", json=draft)
    assert response.status_code == 200, response.text
    return draft, response.json()


def test_real_http_correction_retry_restart_and_explicit_clean_exports(tmp_path, bundle_factory):
    bundle = bundle_factory(["TEST SHOP", "TOTAL 99.00"])
    item = bundle.document.document_id
    with client(tmp_path) as c:
        status = c.get("/api/status")
        assert status.status_code == 200
        caps = status.json()["capabilities"]
        assert caps["recognized_import"] and caps["review_persistence"]
        assert caps["source_images"]
        assert not any(caps[k] for k in ("image_upload", "local_b0", "jev", "vision"))
        base, revision = imported(c, bundle)
        before = c.get(f"{base}/items/{item}").json()
        assert before["image_available"] is False
        assert "retained_artifact_base64" not in before["review"]
        view = before["review"]
        assert not view["clean"] and view["unresolved_issues"]
        assert c.get(f"{base}/exports/clean/receipts.csv").status_code == 409
        draft, outcome = decide(c, base, item, view, "merchant_name", "correct", value="HTTP Shop")
        assert outcome["outcome"] == "appended"
        retry = c.post(f"{base}/items/{item}/decisions", json=draft)
        assert retry.json()["outcome"] == "exact_retry"
        stale = dict(draft["intent"])
        stale["event_id"] = "synthetic-stale-event"
        conflict = c.post(f"{base}/items/{item}/decisions", json={**draft, "intent": stale})
        assert conflict.status_code == 409

    # New app + client replay the durable journal, rather than reusing process-local state.
    with client(tmp_path) as c:
        view = c.get(f"{base}/items/{item}").json()["review"]
        assert view["fields"]["merchant_name"]["effective_value"] == "HTTP Shop"
        assert c.get(f"{base}/exports/clean/receipts.jsonl").status_code == 409
        for field in bundle.receipt.all_fields():
            view = c.get(f"{base}/items/{item}").json()["review"]
            if view["fields"][field.field_id]["review_state"] == "needs_review":
                decide(
                    c,
                    base,
                    item,
                    view,
                    field.field_id,
                    "waive_absent" if field.proposal is None else "confirm",
                )
        view = c.get(f"{base}/items/{item}").json()["review"]
        assert not view["unfinished_fields"] and view["unresolved_issues"]
        decide(c, base, item, view, "merchant_name", "confirm", issues=view["unresolved_issues"])
        final = c.get(f"{base}/items/{item}").json()["review"]
        assert final["clean"]
        for field in bundle.receipt.all_fields():
            assert final["fields"][field.field_id]["machine"] == field.model_dump(mode="json")
            assert final["fields"][field.field_id]["label"]["label_source"] == "agent_provisional"
        response = c.get(f"{base}/exports/clean/receipts.jsonl")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"] == 'attachment; filename="receipts.jsonl"'
        row = json.loads(response.text)
        assert row["fields"]["merchant_name"]["effective_value"] == "HTTP Shop"
        assert row["retained_artifact_base64"] == bundle.artifact_base64
        rows = list(csv.DictReader(io.StringIO(c.get(f"{base}/exports/clean/receipts.csv").text)))
        assert len(rows) == 1 and "HTTP Shop" in rows[0].values()
        assert c.get(f"{base}/exports/review/line_items.csv").status_code == 200
        assert c.get(f"{base}/items").json()[0]["revision"] == revision


@pytest.mark.parametrize(
    "payload",
    [
        b'{"currency":null,"currency":null}',
        b'{"currency":NaN}',
        b'{"currency":',
        b'{"currency":"private-sentinel"}',
        b"\xff",
    ],
)
def test_malformed_http_json_has_no_echo_or_storage_effect(tmp_path, payload):
    with client(tmp_path) as c:
        response = c.post(
            "/api/batches", content=payload, headers={"content-type": "application/json"}
        )
        assert response.status_code == 400
        assert "private-sentinel" not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert not list(tmp_path.iterdir())


def test_http_wrong_route_item_and_unsafe_download_paths(tmp_path, bundle_factory):
    with client(tmp_path) as c:
        bundle = bundle_factory()
        base, revision = imported(c, bundle)
        req = DraftRequest(
            field_id="merchant_name",
            action="confirm",
            value=None,
            expected_item_revision=revision,
            expected_prior_event_id=None,
            actor="synthetic-http-control",
            reason="Authored control",
        )
        draft = post(c, f"{base}/items/{bundle.document.document_id}/draft", req)
        response = c.post(f"{base}/items/different-item/decisions", json=draft)
        assert response.status_code == 400
        assert not list(tmp_path.rglob("rulings.jsonl"))
        for path, status in [
            ("other/receipts.csv", 400),
            ("review/private.txt", 404),
            ("review/%2E%2E%2Fprivate.txt", 404),
        ]:
            assert c.get(f"{base}/exports/{path}").status_code == status
        assert c.get("/openapi.json").status_code == 404


def asgi_call(app, headers, messages, *, method="POST", path="/api/batches", stall=False):
    received = 0
    sent = []

    async def receive():
        nonlocal received
        received += 1
        if stall:
            await asyncio.Event().wait()
        if received > len(messages):
            raise AssertionError("adapter read beyond terminal body or admission")
        return messages[received - 1]

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 10),
        "server": ("127.0.0.1", 24002),
    }
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"], json.loads(b"".join(m.get("body", b"") for m in sent[1:])), received


RAW_HEADERS = [
    (b"host", b"127.0.0.1:24002"),
    (b"x-rfr-token", TOKEN.encode()),
    (b"origin", ORIGIN.encode()),
    (b"content-type", b"application/json"),
]


def test_network_canary_survives_stdlib_control_pair():
    for _ in range(2):
        with pytest.raises(AssertionError, match="forbid application network"):
            socket.create_connection(("127.0.0.1", 1))
        with socket.socket() as sock:
            with pytest.raises(AssertionError, match="forbid application network"):
                sock.connect(("127.0.0.1", 1))
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b"control")
            assert right.recv(7) == b"control"


def test_unexpected_server_error_has_private_headers_and_no_exception_echo(tmp_path):
    app = create_app(tmp_path, origin=ORIGIN, capability=TOKEN)

    async def broken():
        raise RuntimeError("private-sentinel-not-for-response")

    app.add_api_route("/api/test-failure", broken)
    with TestClient(app, base_url=ORIGIN, headers=HEADERS, raise_server_exceptions=False) as c:
        response = c.get("/api/test-failure")
    assert response.status_code == 500 and response.json() == {"error": "internal_error"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "headers,status",
    [
        (RAW_HEADERS[:1], 401),
        ([(b"host", b"attacker.test"), *RAW_HEADERS[1:]], 403),
        (RAW_HEADERS + [(b"X-RFR-Token", TOKEN.encode())], 400),
        (RAW_HEADERS[:2] + [RAW_HEADERS[3]], 403),
        (RAW_HEADERS + [(b"content-length", b"9999")], 413),
        (RAW_HEADERS + [(b"transfer-encoding", b"chunked")], 400),
        (RAW_HEADERS + [(b"sec-fetch-site", b"cross-site")], 403),
    ],
)
def test_real_middleware_refuses_before_reading_any_body(tmp_path, headers, status):
    app = create_app(tmp_path, origin=ORIGIN, capability=TOKEN, max_body_bytes=100)
    actual, _, reads = asgi_call(app, headers, [])
    assert actual == status and reads == 0 and not list(tmp_path.iterdir())


def test_actual_fragmented_body_count_disconnect_and_deadline(tmp_path):
    app = create_app(
        tmp_path, origin=ORIGIN, capability=TOKEN, max_body_bytes=200, body_timeout_s=0.02
    )

    def message(body, more=False):
        return {"type": "http.request", "body": body, "more_body": more}

    status, value, reads = asgi_call(
        app, RAW_HEADERS, [message(b"x" * 120, True), message(b"x" * 120)]
    )
    assert (status, value["error"], reads) == (413, "request_body_limit", 2)
    status, _, reads = asgi_call(app, RAW_HEADERS, [{"type": "http.disconnect"}])
    assert status == 400 and reads == 1
    status, value, reads = asgi_call(app, RAW_HEADERS, [], stall=True)
    assert (status, value["error"], reads) == (408, "request_body_timeout", 1)
    assert not list(tmp_path.iterdir())
    payload = CreateBatch(currency=CurrencyPolicy()).model_dump_json().encode()
    assert len(payload) <= 200
    status, value, reads = asgi_call(
        app, RAW_HEADERS, [message(payload[:5], True), message(payload[5:])]
    )
    assert status == 201 and value["item_count"] == 0 and reads == 2
