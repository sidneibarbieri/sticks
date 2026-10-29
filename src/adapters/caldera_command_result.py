"""Read the pinned native result envelope without inventing absent output."""

import base64
import json
from typing import Literal

from pydantic import StrictInt, StrictStr

from adapters.caldera_dispatch import (
    CalderaDispatchExpectation,
    CalderaDispatchReceipt,
    Identity,
    NativeLink,
    NativeOperation,
    NativeRecord,
    verify_completed_dispatch,
)


class NativeResultEnvelope(NativeRecord):
    link: NativeLink
    result: Identity


class NativeProcessOutput(NativeRecord):
    stdout: StrictStr
    stderr: StrictStr
    exit_code: StrictInt | Literal["", "0"]


class CalderaCommandResult(NativeRecord):
    schema_version: Literal["caldera-command-result/v1"] = "caldera-command-result/v1"
    dispatch: CalderaDispatchReceipt
    stdout: StrictStr
    stderr: StrictStr
    process_exit_code: StrictInt | None


def verify_completed_result(
    expected: CalderaDispatchExpectation, operation_payload: object, result_payload: object
) -> CalderaCommandResult:
    dispatch = verify_completed_dispatch(expected, operation_payload)
    operation = NativeOperation.model_validate(operation_payload)
    envelope = NativeResultEnvelope.model_validate(result_payload)
    selected = next(link for link in operation.chain if link.id == expected.link_id)
    if envelope.link != selected:
        raise ValueError("CALDERA native result link differs from the operation ledger")
    decoded = base64.b64decode(envelope.result, validate=True).decode("utf-8")
    output = NativeProcessOutput.model_validate(json.loads(decoded))
    if output.exit_code not in (0, "", "0"):
        raise ValueError("CALDERA native process exit contradicts successful completion")
    return CalderaCommandResult(
        dispatch=dispatch, stdout=output.stdout, stderr=output.stderr,
        process_exit_code=None if output.exit_code == "" else 0,
    )
