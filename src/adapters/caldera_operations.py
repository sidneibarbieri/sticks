"""Minimal operation API for the laboratory's pinned CALDERA 5.3 runtime."""

import json
from collections.abc import Callable
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from adapters.caldera_command_result import CalderaCommandResult, verify_completed_result

from adapters.caldera_dispatch import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    CalderaDispatchExpectation,
    CalderaDispatchReceipt,
    verify_completed_dispatch,
)


class CalderaCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    executor: str = Field(min_length=1)
    command: str = Field(min_length=1)
    timeout_seconds: int = Field(default=DEFAULT_COMMAND_TIMEOUT_SECONDS, strict=True, gt=0, le=300)


JsonTransport = Callable[[str, str, dict[str, object] | None], object]


class CalderaOperations:
    def __init__(self, transport: JsonTransport) -> None:
        self._transport = transport

    def create_operation(self, name: str, group: str) -> str:
        if not name.strip() or not group.strip():
            raise ValueError("operation name and isolated agent group are required")
        response = self._transport("POST", "/operations", {
            "name": name, "group": group, "state": "running",
            "autonomous": 1, "auto_close": False, "jitter": "0/0",
        })
        if not isinstance(response, dict) or not isinstance(response.get("id"), str) or not response["id"]:
            raise ValueError("CALDERA returned no operation identity")
        return response["id"]

    def submit_command(self, operation_id: str, command: CalderaCommand) -> str:
        response = self._transport(
            "POST", f"/operations/{quote(operation_id, safe='')}/potential-links",
            {
                "paw": command.agent_id,
                "executor": {
                    "name": command.executor, "platform": command.platform,
                    "command": command.command,
                    "timeout": command.timeout_seconds,
                },
            },
        )
        if not isinstance(response, dict) or not isinstance(response.get("id"), str) or not response["id"]:
            raise ValueError("CALDERA returned no link identity")
        return response["id"]

    def link(self, operation_id: str, link_id: str) -> dict[str, object]:
        response = self._transport(
            "GET",
            f"/operations/{quote(operation_id, safe='')}/links/{quote(link_id, safe='')}",
            None,
        )
        if not isinstance(response, dict) or response.get("id") != link_id:
            raise ValueError("CALDERA link identity differs from the submitted link")
        if type(response.get("status")) is not int:
            raise ValueError("CALDERA link status must be an integer")
        if response.get("finish") is not None and not isinstance(response["finish"], str):
            raise ValueError("CALDERA link finish must be a string or null")
        return response

    def completed_dispatch(
        self, expected: CalderaDispatchExpectation
    ) -> CalderaDispatchReceipt:
        operation = self._transport(
            "GET", f"/operations/{quote(expected.operation_id, safe='')}", None
        )
        return verify_completed_dispatch(expected, operation)

    def completed_command(
        self, expected: CalderaDispatchExpectation
    ) -> CalderaCommandResult:
        operation_path = f"/operations/{quote(expected.operation_id, safe='')}"
        operation = self._transport("GET", operation_path, None)
        result = self._transport(
            "GET", operation_path + f"/links/{quote(expected.link_id, safe='')}/result", None
        )
        return verify_completed_result(expected, operation, result)

    def finish_operation(self, operation_id: str) -> None:
        self._transport(
            "PATCH", f"/operations/{quote(operation_id, safe='')}", {"state": "finished"}
        )


def http_transport(base_url: str, api_key: SecretStr) -> JsonTransport:
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("CALDERA base URL must be an HTTP origin")
    if parsed.username or parsed.password or parsed.path not in ("", "/"):
        raise ValueError("CALDERA base URL must not contain credentials or a path")

    def request_json(method: str, path: str, payload: dict[str, object] | None) -> object:
        request = Request(
            base_url.rstrip("/") + "/api/v2" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"KEY": api_key.get_secret_value(), "Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request, timeout=45) as response:
            return json.load(response)

    return request_json
