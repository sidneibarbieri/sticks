"""Minimal local HTTP interface for the causal-realization workbench."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from .workbench import RealizationWorkbench, WorkbenchEnumerationRequest

_MAXIMUM_REQUEST_BYTES = 64 * 1024
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/sticks-mark.svg": ("sticks-mark.svg", "image/svg+xml"),
}


def build_handler(
    workbench: RealizationWorkbench,
    web_root: Path,
) -> type[BaseHTTPRequestHandler]:
    """Bind immutable application dependencies to a request handler class."""

    resolved_web_root = web_root.resolve()

    class WorkbenchRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ready",
                        "interface_scope": "planning_only",
                        "operational_status": "not_run",
                    },
                )
                return
            if path == "/api/campaigns":
                inventory = workbench.campaign_inventory()
                self._send_json(HTTPStatus.OK, inventory.model_dump(mode="json"))
                return
            static_file = _STATIC_FILES.get(path)
            if static_file is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            filename, content_type = static_file
            self._send_static(resolved_web_root / filename, content_type)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/api/enumerate":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json_body()
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_request", "detail": str(error)},
                )
                return
            try:
                request = WorkbenchEnumerationRequest.model_validate(payload)
                response = workbench.enumerate_campaign(request)
            except ValidationError as error:
                self._send_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    {"error": "validation_failed", "detail": error.errors()},
                )
                return
            except (FileNotFoundError, ValueError) as error:
                self._send_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    {"error": "enumeration_rejected", "detail": str(error)},
                )
                return
            self._send_json(HTTPStatus.OK, response.model_dump(mode="json"))

        def _read_json_body(self) -> object:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length is required")
            content_length = int(raw_length)
            if content_length < 1 or content_length > _MAXIMUM_REQUEST_BYTES:
                raise ValueError(f"request body must contain 1..{_MAXIMUM_REQUEST_BYTES} bytes")
            return json.loads(self.rfile.read(content_length).decode("utf-8"))

        def _send_json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, path: Path, content_type: str) -> None:
            resolved = path.resolve()
            if not resolved.is_relative_to(resolved_web_root) or not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = resolved.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return WorkbenchRequestHandler


def serve_workbench(
    workbench: RealizationWorkbench,
    web_root: Path,
    *,
    host: str,
    port: int,
) -> None:
    """Serve one local, serial planning process until interrupted."""

    server = HTTPServer((host, port), build_handler(workbench, web_root))
    print(f"Realization workbench: http://{host}:{server.server_port}")
    print("Scope: planning only; operational status remains not_run")
    try:
        server.serve_forever()
    finally:
        server.server_close()
