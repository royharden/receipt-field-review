"""Serve the local recognized-bundle app on an explicitly selected loopback port."""

import argparse
import os
from pathlib import Path

import uvicorn

from .api.app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, required=True, help="Existing owner-private batch root"
    )
    parser.add_argument("--viewer", type=Path, required=True, help="Built dist/web directory")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("valid_explicit_port_required")
    capability = os.environ.get("RFR_LOCAL_CAPABILITY", "")
    try:
        app = create_app(
            args.root,
            origin=f"http://127.0.0.1:{args.port}",
            capability=capability,
            viewer_root=args.viewer,
        )
    except (ValueError, OSError, RuntimeError):
        parser.error(
            "local_setup_refused: verify private root, built viewer and RFR_LOCAL_CAPABILITY"
        )
    # No reload, wildcard bind, capability echo or receipt-path access log.
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
