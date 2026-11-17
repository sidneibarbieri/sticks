"""Admission of one campaign from a user-supplied STIX bundle.

This is the service behind ``scripts/emulate.py`` and the workbench's
"Your STIX bundle" panel, so both interfaces produce the same result for the
same bundle and campaign. It compiles the campaign into a procedural plan,
derives the declared lab environment from the template catalog, and runs the
finite-domain concretizer offline. A step with no admissible realization is
reported as unresolved; nothing is executed.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field

from contracts.procedural_ir import ProceduralPlan

from .lab_environment import derive_lab_environment
from .models import ActionTemplate, StrictModel

CAMPAIGN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SUBPROCESS_TIMEOUT_SECONDS = 600


class AdmittedStep(StrictModel):
    technique_id: str
    template_id: str


class BundleAdmissionResult(StrictModel):
    schema_version: Literal["1"] = "1"
    campaign_id: str
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposer: Literal["finite_domain_solver_offline", "configured_model"]
    plan_step_count: int = Field(ge=0)
    admitted_steps: list[AdmittedStep]
    unresolved_technique_ids: list[str]
    causal_certificate_valid: bool | None
    operational_status: Literal["not_run"] = "not_run"


class BundleAdmissionError(ValueError):
    """The bundle or campaign could not be admitted; the message is user-facing."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], project_root: Path, failure: str) -> None:
    try:
        subprocess.run(
            command,
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise BundleAdmissionError(f"{failure}: timed out") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"exit status {error.returncode}"
        raise BundleAdmissionError(f"{failure}: {message}") from error


def admit_campaign(
    project_root: Path,
    campaign_id: str,
    bundle_path: Path,
    workdir: Path,
    config: Path | None = None,
) -> tuple[ProceduralPlan, dict, BundleAdmissionResult]:
    """Compile, derive the lab and concretize one campaign; write artifacts in ``workdir``."""
    if not CAMPAIGN_ID_PATTERN.fullmatch(campaign_id):
        raise BundleAdmissionError(
            "Campaign identifier must be 1-64 letters, digits, '.', '_' or '-', for example C0045"
        )
    if not bundle_path.is_file():
        raise BundleAdmissionError(f"STIX bundle not found: {bundle_path}")
    workdir.mkdir(parents=True, exist_ok=True)
    plan_path = workdir / f"{campaign_id}.procedural-plan.json"
    bindings_path = workdir / f"{campaign_id}.binding-catalog.json"
    result_path = workdir / f"{campaign_id}.concretized-plan.json"
    templates_path = project_root / "data" / "concretization" / "action_templates.json"

    _run(
        [
            sys.executable,
            str(project_root / "scripts" / "compile_stix_campaign.py"),
            campaign_id,
            "--bundle",
            str(bundle_path),
            "--output",
            str(plan_path),
        ],
        project_root,
        f"Campaign {campaign_id} could not be compiled from the bundle",
    )
    plan = ProceduralPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    payload = json.loads(templates_path.read_text(encoding="utf-8"))
    templates = [ActionTemplate.model_validate(item) for item in payload["templates"]]
    environment = derive_lab_environment(f"{campaign_id}-lab", templates, plan)
    bindings_path.write_text(environment.model_dump_json(indent=2) + "\n", encoding="utf-8")

    command = [
        sys.executable,
        str(project_root / "scripts" / "concretize_procedural_plan.py"),
        "--plan", str(plan_path),
        "--bindings", str(bindings_path),
        "--templates", str(templates_path),
        "--output", str(result_path),
        "--allow-unresolved",
    ]
    if config is not None:
        command += ["--config", str(config)]
    _run(command, project_root, "Concretization failed")
    concretized = json.loads(result_path.read_text(encoding="utf-8"))

    certificate = concretized.get("planning_certificate", {})
    result = BundleAdmissionResult(
        campaign_id=campaign_id,
        bundle_sha256=file_sha256(bundle_path),
        proposer="configured_model" if config is not None else "finite_domain_solver_offline",
        plan_step_count=len(plan.steps),
        admitted_steps=[
            AdmittedStep(technique_id=step["technique_id"], template_id=step["template_id"])
            for step in concretized.get("steps", [])
        ],
        unresolved_technique_ids=list(concretized.get("unresolved_technique_ids", [])),
        causal_certificate_valid=certificate.get("valid"),
    )
    return plan, concretized, result
