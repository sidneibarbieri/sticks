"""Retained external-procedure evidence must reject altered outcomes and identities."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/atomic_hostname"
SPEC = importlib.util.spec_from_file_location("atomic_hostname_qualification", EXAMPLE / "qualify.py")
assert SPEC is not None and SPEC.loader is not None
qualification = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qualification
SPEC.loader.exec_module(qualification)


def test_external_qualification_replays_pinned_contract_and_three_observed_cells():
    qualification.verify_qualification(EXAMPLE / "qualified", qualification.load_source())


@pytest.mark.parametrize("mutation", (
    "missing_cell", "reused_target", "false_success", "substituted_command", "changed_binding",
))
def test_external_qualification_rejects_mutated_evidence(tmp_path: Path, mutation: str):
    retained = tmp_path / "retained"
    shutil.copytree(EXAMPLE / "qualified", retained)
    path = retained / "qualification.json"
    receipt = json.loads(path.read_text())
    if mutation == "missing_cell":
        receipt["cells"].pop()
    elif mutation == "reused_target":
        receipt["cells"][1]["container_id"] = receipt["cells"][0]["container_id"]
    elif mutation == "false_success":
        receipt["cells"][1]["predicate_passed"] = True
    elif mutation == "substituted_command":
        receipt["cells"][2]["executed_command"] = "echo another-unplanned-command"
    else:
        binding_path = retained / "upstream_command/binding-catalog.json"
        catalog = json.loads(binding_path.read_text())
        catalog["bindings"][0]["value"] = "lab://another-target"
        binding_path.write_text(json.dumps(catalog))
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        qualification.verify_qualification(retained, qualification.load_source())
