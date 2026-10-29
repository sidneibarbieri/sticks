"""Campaign-specific procedures must not replace generic technique executors."""

import sys
import base64
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from executors.executor_registry import (
    ExecutionMode,
    ExecutorMetadata,
    ExecutorRegistry,
)


def _metadata(technique_id: str, description: str) -> ExecutorMetadata:
    return ExecutorMetadata(
        technique_id=technique_id,
        technique_name=description,
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=[],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
    )


def test_campaign_specific_executor_does_not_override_generic() -> None:
    registry = ExecutorRegistry()

    def generic_executor(campaign_id: str, sut_profile_id: str):
        return True, "generic", "", []

    def specialized_executor(campaign_id: str, sut_profile_id: str):
        return True, "specialized", "", []

    registry.register("T1588.002", _metadata("T1588.002", "generic"), generic_executor)
    registry.register(
        "T1588.002",
        _metadata("T1588.002", "specialized"),
        specialized_executor,
        campaign_id="0.shadowray",
    )

    assert registry.get_executor("T1588.002", "0.c0010") is generic_executor
    assert registry.get_metadata("T1588.002", "0.c0010").technique_name == "generic"
    assert registry.get_executor("T1588.002", "0.shadowray") is specialized_executor
    assert registry.get_metadata("T1588.002", "0.shadowray").technique_name == "specialized"


def test_specialized_only_executor_fails_closed_for_other_campaign() -> None:
    registry = ExecutorRegistry()

    def specialized_executor(campaign_id: str, sut_profile_id: str):
        return True, "specialized", "", []

    registry.register(
        "T1546.004",
        _metadata("T1546.004", "specialized"),
        specialized_executor,
        campaign_id="0.shadowray",
    )

    assert registry.get_executor("T1546.004", "0.c0010") is None
    assert registry.get_executor("T1546.004", "0.shadowray") is specialized_executor


def test_generic_encoded_fixture_is_inert_and_campaign_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from executors import executor_registry

    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)
    success, message, error, artifacts = executor_registry.execute_t1027_013_generic(
        "0.outer_space", "0.outer_space"
    )

    assert success and not error
    assert "no target execution" in message
    assert artifacts == [str(tmp_path / "0.outer_space" / "encoded_fixture.txt")]
    assert base64.b64decode(Path(artifacts[0]).read_bytes()) == (
        b"STICKS inert encoding fixture for 0.outer_space\n"
    )
    with pytest.raises(ValueError, match="Invalid campaign ID"):
        executor_registry.execute_t1027_013_generic("../outside", "0.outer_space")
