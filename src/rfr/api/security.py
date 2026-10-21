"""Pure request admission, not an HTTP server, capability issuer or Windows ACL claim."""

import hmac
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

IMAGE_BODY_LIMIT = 20 * 1024 * 1024


def image_upload_route(method, path):
    return (
        method == "PUT"
        and type(path) is str
        and re.fullmatch(r"/api/batches/[0-9a-f]{32}/images/[0-9a-f]{64}", path) is not None
    )


class RequestRefused(RuntimeError):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RequestGuard:
    origin: str
    capability: str = field(repr=False)
    max_body_bytes: int = 8 * 1024 * 1024 + 4096

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or self.origin != "http://" + parsed.netloc
        ):
            raise ValueError("exact_loopback_origin_required")
        # Accessing port also rejects malformed/out-of-range explicit ports before serving.
        port = parsed.port
        expected_host = parsed.hostname + (f":{port}" if port is not None else "")
        if parsed.netloc != expected_host or port == 0:
            raise ValueError("canonical_loopback_host_required")
        if type(self.capability) is not str or not 32 <= len(self.capability) <= 256:
            raise ValueError("bounded_start_capability_required")
        self.capability.encode("ascii")
        if type(self.max_body_bytes) is not int or not 1 <= self.max_body_bytes <= 25 * 1024 * 1024:
            raise ValueError("bounded_body_policy_required")

    def body_limit(self, method, path=None):
        return IMAGE_BODY_LIMIT if image_upload_route(method, path) else self.max_body_bytes

    def authorize(self, method, raw_headers, *, capability_required=True, path=None):
        if type(capability_required) is not bool:
            raise ValueError("explicit_capability_policy_required")
        if type(raw_headers) not in (tuple, list) or len(raw_headers) > 64:
            raise RequestRefused(400, "header_count_limit")
        headers = {}
        security_headers = {
            "host",
            "origin",
            "x-rfr-token",
            "content-length",
            "content-type",
            "sec-fetch-site",
            "transfer-encoding",
        }
        for raw_key, raw_value in raw_headers:
            if type(raw_key) is not bytes or type(raw_value) is not bytes:
                raise RequestRefused(400, "invalid_headers")
            if len(raw_key) > 128 or len(raw_value) > 2048:
                raise RequestRefused(400, "header_limit")
            try:
                key, value = raw_key.decode("ascii").lower(), raw_value.decode("ascii")
            except UnicodeError:
                raise RequestRefused(400, "invalid_headers") from None
            if "\r" in value or "\n" in value:
                raise RequestRefused(400, "invalid_headers")
            if key in security_headers:
                if key in headers:
                    raise RequestRefused(400, "duplicate_security_header")
                headers[key] = value
        if headers.get("host") != urlsplit(self.origin).netloc:
            raise RequestRefused(403, "host_refused")
        supplied = headers.get("x-rfr-token", "")
        if capability_required and not hmac.compare_digest(
            supplied.encode("ascii"), self.capability.encode("ascii")
        ):
            raise RequestRefused(401, "capability_required")
        origin = headers.get("origin")
        if origin is not None and origin != self.origin:
            raise RequestRefused(403, "origin_refused")
        if headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
            raise RequestRefused(403, "fetch_site_refused")
        if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            raise RequestRefused(405, "method_refused")
        if method not in {"GET", "HEAD"}:
            if origin != self.origin:
                raise RequestRefused(403, "mutation_origin_required")
            expected_type = (
                "application/octet-stream"
                if image_upload_route(method, path)
                else "application/json"
            )
            if headers.get("content-type", "").split(";", 1)[0].strip() != expected_type:
                raise RequestRefused(
                    415,
                    "binary_content_type_required"
                    if image_upload_route(method, path)
                    else "json_content_type_required",
                )
        if "transfer-encoding" in headers:
            raise RequestRefused(400, "transfer_encoding_refused")
        if "content-length" in headers:
            length = headers["content-length"]
            if not length.isascii() or not length.isdecimal() or len(length) > 10:
                raise RequestRefused(400, "invalid_content_length")
            if int(length) > self.body_limit(method, path):
                raise RequestRefused(413, "request_body_limit")
        # The eventual transport MUST also count actual streamed bytes; Content-Length is not proof.
