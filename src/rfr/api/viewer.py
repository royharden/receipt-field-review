"""Small immutable public viewer shell, separated from capability-protected receipt routes."""

import re
from pathlib import Path

from fastapi.responses import Response

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'none'"
)


class ViewerFiles:
    def __init__(self, root: Path, private_root: Path):
        root, private_root = Path(root).absolute(), Path(private_root).resolve(strict=True)
        for part in (root, *root.parents):
            if part.is_symlink() or part.is_junction():
                raise ValueError("viewer_symlink_refused")
        root = root.resolve(strict=True)
        if root.is_relative_to(private_root) or private_root.is_relative_to(root):
            raise ValueError("viewer_private_root_overlap")
        files = {}
        total = 0
        for path in root.rglob("*"):
            if path.is_symlink() or path.is_junction():
                raise ValueError("viewer_symlink_refused")
            if path.is_dir():
                if path != root / "assets":
                    raise ValueError("unexpected_viewer_directory")
                continue
            name = path.relative_to(root).as_posix()
            if name != "index.html" and not re.fullmatch(r"assets/[A-Za-z0-9_-]+\.(js|css)", name):
                raise ValueError("unexpected_viewer_file")
            if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("viewer_asset_limit")
            with path.open("rb") as reader:
                content = reader.read(2 * 1024 * 1024 + 1)
            total += len(content)
            if len(content) > 2 * 1024 * 1024 or total > 6 * 1024 * 1024 or len(files) >= 32:
                raise ValueError("viewer_asset_limit")
            media = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[
                path.suffix
            ]
            files["/" + name] = (content, media)
        if "/index.html" not in files:
            raise ValueError("viewer_index_required")
        files["/"] = files["/index.html"]
        self.files = files

    def response(self, method, path):
        if method not in {"GET", "HEAD"} or path not in self.files:
            return None
        content, media = self.files[path]
        return Response(
            content if method == "GET" else b"",
            media_type=media,
            headers={
                "Content-Security-Policy": CSP,
                "Referrer-Policy": "no-referrer",
                "Content-Length": str(len(content)),
            },
        )
