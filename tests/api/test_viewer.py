"""Actual public-shell/private-API separation and immutable bounded viewer assets."""

import pytest
from fastapi.testclient import TestClient

from rfr.api.app import create_app

ORIGIN = "http://127.0.0.1:20601"
TOKEN = "synthetic-browser-capability-00000000"


def setup(tmp_path):
    data, viewer = tmp_path / "data", tmp_path / "viewer"
    data.mkdir()
    viewer.mkdir()
    (viewer / "assets").mkdir()
    (viewer / "index.html").write_text('<html><script src="/assets/index-abcd.js"></script></html>')
    (viewer / "assets/index-abcd.js").write_text('console.log("public-shell")')
    return data, viewer


def test_shell_is_public_but_all_receipt_routes_remain_protected(tmp_path):
    data, viewer = setup(tmp_path)
    app = create_app(data, origin=ORIGIN, capability=TOKEN, viewer_root=viewer)
    (viewer / "assets/index-abcd.js").write_text("changed after snapshot")
    with TestClient(app, base_url=ORIGIN) as c:
        page = c.get("/")
        assert page.status_code == 200 and "<html>" in page.text
        assert TOKEN not in page.text
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        assert "script-src 'self'" in page.headers["content-security-policy"]
        assert page.headers["cache-control"] == "no-store"
        assert page.headers["x-content-type-options"] == "nosniff"
        assert page.headers["referrer-policy"] == "no-referrer"
        assert "public-shell" in c.get("/assets/index-abcd.js").text
        head = c.head("/")
        assert head.status_code == 200 and head.content == b""
        assert head.headers["content-length"] == str(len(page.content))
        for route in [
            "/api/status",
            "/api/batches/arbitrary/items",
            "/assets/private.txt",
            "/.env",
        ]:
            assert c.get(route).status_code == 401
        assert c.post("/", json={}).status_code == 401
        assert c.get("/api/status", headers={"X-RFR-Token": TOKEN}).status_code == 200
        assert c.get("/", headers={"Host": "foreign.test"}).status_code == 403
        assert c.get("/", headers={"Origin": "http://foreign.test"}).status_code == 403
        assert c.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not list(data.iterdir())


@pytest.mark.parametrize(
    "extra", [".env", "assets/source.map", "assets/private.json", "other/file.js"]
)
def test_unexpected_static_content_refuses_before_serving(tmp_path, extra):
    data, viewer = setup(tmp_path)
    path = viewer / extra
    path.parent.mkdir(exist_ok=True)
    path.write_text("private sentinel")
    with pytest.raises(ValueError, match="unexpected_viewer"):
        create_app(data, origin=ORIGIN, capability=TOKEN, viewer_root=viewer)


def test_static_private_overlap_and_file_size_fail_closed(tmp_path):
    data, viewer = setup(tmp_path)
    with pytest.raises(ValueError, match="viewer_private_root_overlap"):
        create_app(viewer, origin=ORIGIN, capability=TOKEN, viewer_root=viewer)
    (viewer / "assets/index-abcd.js").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="viewer_asset_limit"):
        create_app(data, origin=ORIGIN, capability=TOKEN, viewer_root=viewer)
