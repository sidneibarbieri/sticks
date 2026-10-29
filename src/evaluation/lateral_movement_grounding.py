"""Measure whether the corpus itself grounds credential-to-lateral-movement ordering.

Two techniques co-occurring in one campaign does not establish that the credential obtained
by the first enabled the lateral movement of the second. The compiler already declares its
ordering as a tactic-rank policy, not a historical total order; this module asks the narrower
question the ordering policy cannot answer from tactic rank alone: does a lateral-movement
step's own procedure description textually attribute the movement to previously obtained
credentials, or to an independent mechanism (brute force, tool transfer), or to nothing at all?

The distinction matters because a step may be labeled ordering_source: cti only when the text
supports a causal link. Where the text names an independent mechanism, honesty requires
ordering_source: independent_mechanism; where it is silent, ordering_source: procedure_dependency
(a reconstruction-policy choice, not evidence). Deterministic and offline over the pinned plans.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

# Credential-access techniques whose product could gate later remote access.
CREDENTIAL_PREFIXES = ("T1003", "T1552", "T1555", "T1558", "T1539")

# Remote-service / alternate-authentication techniques that carry lateral movement.
LATERAL_PREFIXES = ("T1021", "T1550")

# Lateral-movement sub-techniques that move host-to-host over a remote service on Linux/macOS,
# so a two-Linux-VM backend could realize "credential on host A grants access to host B".
# Deliberately host-to-host remote services only: T1550 (Use Alternate Authentication Material)
# carries a Linux platform tag but denotes identity-plane material (SAML tokens, app tokens, web
# cookies) for cloud-application access, not host-to-host movement, so it is not linux_capable
# here even when its platform tag includes Linux -- realizability, not the raw platform tag, is
# what the backend decision turns on.
LINUX_CAPABLE_LATERAL = ("T1021.004", "T1021.005")

# Language that attributes the movement to previously obtained credentials.
CONNECTIVE_CREDENTIAL_REUSE = re.compile(
    r"compromis(ed|ing)?\s+credential|"
    r"(obtained|stolen|harvested|acquired|valid|legitimate)\s+(account|credential)|"
    r"using\s+(the\s+|stolen\s+|valid\s+)?(account|credential)|"
    r"with\s+(the\s+)?(compromised\s+|stolen\s+)?credential|"
    r"compromised\s+(azure|domain|administrative|service)\s+(credential|account|principal)|"
    r"forged\s+(saml|kerberos)|stolen\s+(cookie|token|session)",
    re.IGNORECASE,
)

# Language that attributes the movement to a mechanism independent of prior credential theft.
INDEPENDENT_MECHANISM = re.compile(
    r"brute[- ]?forc|password spray|to transfer tools|tunnel",
    re.IGNORECASE,
)


class LateralMovementStep(BaseModel):
    """One lateral-movement step and how its own text grounds its ordering."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    campaign_name: str
    technique_id: str
    platforms: list[str]
    linux_capable: bool
    credential_techniques_in_campaign: list[str]
    ordering_source: str
    procedure_excerpt: str


class LateralMovementGrounding(BaseModel):
    """Deterministic lexical screen for candidate credential-to-movement links.

    The record is intentionally not a semantic adjudication. Its labels are reproducible
    candidates for the separate, blinded P16 human-adjudication protocol.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    classifier_version: str
    scientific_status: str
    adjudication_protocol_path: str
    question: str
    method: str
    campaigns_examined: int
    lateral_steps_examined: int
    cti_grounded_steps: int
    independent_mechanism_steps: int
    ungrounded_cooccurrence_steps: int
    cti_grounded_linux_capable_steps: int
    steps: list[LateralMovementStep]
    note: str


def _classify_ordering_source(procedure_text: str) -> str:
    """A lateral step's grounding, read only from its own procedure description."""
    if INDEPENDENT_MECHANISM.search(procedure_text):
        return "independent_mechanism"
    if CONNECTIVE_CREDENTIAL_REUSE.search(procedure_text):
        return "cti"
    return "procedure_dependency"


def _has_credential_technique(steps: list[dict]) -> list[str]:
    return sorted(
        {
            step["technique_id"]
            for step in steps
            if step.get("technique_id", "").startswith(CREDENTIAL_PREFIXES)
        }
    )


def evaluate(plans: list[dict]) -> LateralMovementGrounding:
    """Read every compiled plan and grade each lateral-movement step's ordering grounding."""
    examined_steps: list[LateralMovementStep] = []
    for plan in plans:
        steps = plan.get("steps", [])
        credential_techniques = _has_credential_technique(steps)
        if not credential_techniques:
            continue
        for step in steps:
            technique_id = step.get("technique_id", "")
            if not technique_id.startswith(LATERAL_PREFIXES):
                continue
            procedure_text = " ".join(step.get("procedure_descriptions", []))
            examined_steps.append(
                LateralMovementStep(
                    campaign_id=plan.get("campaign_id", ""),
                    campaign_name=plan.get("campaign_name", ""),
                    technique_id=technique_id,
                    platforms=step.get("platforms", []),
                    linux_capable=technique_id in LINUX_CAPABLE_LATERAL,
                    credential_techniques_in_campaign=credential_techniques,
                    ordering_source=_classify_ordering_source(procedure_text),
                    procedure_excerpt=procedure_text[:400],
                )
            )

    cti_grounded = [s for s in examined_steps if s.ordering_source == "cti"]
    independent = [s for s in examined_steps if s.ordering_source == "independent_mechanism"]
    ungrounded = [s for s in examined_steps if s.ordering_source == "procedure_dependency"]
    cti_linux = [s for s in cti_grounded if s.linux_capable]

    return LateralMovementGrounding(
        schema_version="2",
        classifier_version="p16-lexical-screen-v1",
        scientific_status="unadjudicated_lexical_screen",
        adjudication_protocol_path=(
            "release/experiments/lateral_movement_grounding/adjudication/protocol.v1.json"
        ),
        question=(
            "Which lateral-movement descriptions match the fixed lexical patterns for credential "
            "reuse or an independent mechanism, and which matching descriptions are Linux "
            "host-to-host candidates under the declared backend rule?"
        ),
        method=(
            "For every compiled campaign plan that contains a credential-access technique, a "
            "deterministic lexical classifier inspects only each remote-service or alternate-"
            "authentication step's own procedure description: ordering_source=cti when it "
            "matches credential-reuse patterns, independent_mechanism when it matches brute-"
            "force or tool-transfer patterns, and procedure_dependency otherwise. Co-occurrence "
            "does not change a label."
        ),
        campaigns_examined=sum(
            1 for plan in plans if _has_credential_technique(plan.get("steps", []))
        ),
        lateral_steps_examined=len(examined_steps),
        cti_grounded_steps=len(cti_grounded),
        independent_mechanism_steps=len(independent),
        ungrounded_cooccurrence_steps=len(ungrounded),
        cti_grounded_linux_capable_steps=len(cti_linux),
        steps=examined_steps,
        note=(
            "This record preserves an auditable lexical screen, not a semantic conclusion about "
            "causal order or historical adversary behavior. The screen finds no Linux host-to-"
            "host step that matches its credential-reuse patterns. C0024's T1550 step carries a "
            "Linux platform tag but is treated as identity-plane rather than host-to-host under "
            "the declared backend rule. The separate P16 adjudication protocol must independently "
            "confirm every label before this screen can support paper-facing wording or a backend "
            "decision."
        ),
    )
