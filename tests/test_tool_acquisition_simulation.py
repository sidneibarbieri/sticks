"""A synthetic acquisition record must not become acquired-tool evidence."""

from pathlib import Path

import pytest

from executors.executor_registry import ExecutionMode, registry
from executors.registry_initializer import initialize_registry


@pytest.mark.parametrize("campaign", ["0.c0010", "0.operation_midnighteclipse", "0.salesforce_data_exfiltration"])
def test_generic_tool_acquisition_is_declared_simulation(campaign):
    initialize_registry(force=True)
    metadata = registry.get_metadata("T1588.002", campaign)
    assert metadata.execution_mode is ExecutionMode.NAIVE_SIMULATED
    assert metadata.produces == ["simulation:tool_acquisition_recorded"]
    assert "resources:tool_acquired" not in metadata.produces


def test_generic_tool_acquisition_records_only_the_simulated_operation(monkeypatch, tmp_path):
    initialize_registry(force=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    result = registry.get_executor("T1588.002", "0.c0010")("0.c0010", "0.c0010")
    assert result[0] is True
    assert "Simulation" in result[1]
    assert "Tool acquired successfully" not in result[1]
    assert len(result[3]) == 2
    assert all(Path(path).is_file() for path in result[3])
    assert "simulation" in Path(result[3][1]).read_text().lower()


def test_simulation_write_error_propagates(monkeypatch, tmp_path):
    initialize_registry(force=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/artifacts").write_text("not a directory")
    with pytest.raises(FileExistsError):
        registry.get_executor("T1588.002", "0.c0010")("0.c0010", "0.c0010")


def test_scoped_guest_tool_preparation_keeps_its_distinct_contract():
    initialize_registry(force=True)
    metadata = registry.get_metadata("T1588.002", "0.costaricto")
    assert metadata.execution_mode is ExecutionMode.NAIVE_SIMULATED
    assert metadata.produces == ["simulation:guest_tool_staged"]
    assert registry.get_executor("T1588.002", "0.costaricto").__name__ == "execute_costaricto_target_tool_staging"


def test_campaign_expectations_do_not_describe_simulation_as_real():
    import json
    root = Path(__file__).resolve().parents[1]
    campaign = json.loads((root / "campaigns/0.c0010.json").read_text())
    step = next(step for step in campaign["techniques"] if step["technique_id"] == "T1588.002")
    assert step["expected_mode"] == "naive_simulated"
    assert step["expected_fidelity"] == "inspired"
    assert step["produces"] == ["simulation:tool_acquisition_recorded"]
    import yaml
    profile = yaml.safe_load((root / "data/sut_profiles/0.c0010.yml").read_text())
    assert profile["fidelity_expectations"]["T1588.002"] == "INSPIRED"
