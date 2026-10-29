from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.substitution import (
    StepClass,
    analyze_campaign,
    analyze_corpus,
    classify_step,
)


def _template(template_id, technique_ids, domain, evidence, produces, fidelity="adapted"):
    return {
        "template_id": template_id,
        "technique_ids": technique_ids,
        "execution_domain": domain,
        "evidence_predicates": evidence,
        "produces": produces,
        "fidelity_ceiling": fidelity,
    }


CATALOG = [
    _template("only-one", ["T1000"], "target", ["e1"], ["f1"]),
    # two templates for T2000 with DIFFERENT certified evidence
    _template("run-key", ["T2000"], "target", ["registry_write"], ["persist_runkey"]),
    _template("wmi-sub", ["T2000"], "target", ["wmi_subscription"], ["persist_wmi"]),
    # two templates for T3000 with the SAME evidence signature but different produces:
    # the choice cannot change what is certified, only downstream fact-plumbing.
    _template("dup-a", ["T3000"], "target", ["e3"], ["transfer.target.payload"]),
    _template("dup-b", ["T3000"], "target", ["e3"], ["payload.target.staged"]),
]


def test_single_applicable_template_is_determined():
    assert classify_step("T1000", "target", CATALOG) is StepClass.determined


def test_distinct_evidence_alternatives_are_divergent():
    # the CTI says "T2000"; the proposer must choose run-key vs wmi-sub, which certify
    # different evidence -- a choice over the observable effect not in the intelligence
    assert classify_step("T2000", "target", CATALOG) is StepClass.evidence_divergent


def test_same_evidence_different_produces_is_equivalent_not_divergent():
    # This is the real T1105 case: identical evidence signature, differing only in the
    # produced-fact name. It must NOT count as a behavioral choice.
    assert classify_step("T3000", "target", CATALOG) is StepClass.evidence_equivalent


def test_no_applicable_template_is_unsupported():
    assert classify_step("T9999", "target", CATALOG) is StepClass.unsupported
    assert classify_step("T1000", "attacker", CATALOG) is StepClass.unsupported  # domain mismatch


def test_campaign_rollup_rates():
    steps = [
        {"technique_id": "T1000", "execution_domain": "target"},   # determined
        {"technique_id": "T2000", "execution_domain": "target"},   # evidence_divergent
        {"technique_id": "T3000", "execution_domain": "target"},   # evidence_equivalent
    ]
    result = analyze_campaign("CTEST", steps, CATALOG)
    assert result.total_steps == 3
    assert result.determined == 1
    assert result.evidence_divergent == 1
    assert result.evidence_equivalent == 1
    # two of three steps offer a menu; only one of those changes the certified effect
    assert result.multiplicity_rate == 2 / 3
    assert result.evidence_divergence_rate == 1 / 3


def test_corpus_rollup_aggregates_campaigns():
    campaigns = {
        "CA": [
            {"technique_id": "T1000", "execution_domain": "target"},  # determined
            {"technique_id": "T2000", "execution_domain": "target"},  # evidence_divergent
        ],
        "CB": [
            {"technique_id": "T9999", "execution_domain": "target"},  # unsupported
            {"technique_id": "T3000", "execution_domain": "target"},  # evidence_equivalent
        ],
    }
    corpus = analyze_corpus(campaigns, CATALOG)
    assert corpus.total_campaigns == 2
    assert corpus.total_steps == 4
    assert corpus.determined == 1
    assert corpus.evidence_equivalent == 1
    assert corpus.evidence_divergent == 1
    assert corpus.unsupported == 1
    # three of four steps are catalog-supported
    assert corpus.catalog_supported_steps == 3
    assert corpus.catalog_coverage_rate == 3 / 4
    assert corpus.evidence_divergence_rate_over_supported == 1 / 3


def test_real_corpus_has_no_proposer_divergent_mechanism():
    plans_dir = PROJECT_ROOT / "release" / "plans" / "enterprise"
    templates = json.loads(
        (PROJECT_ROOT / "data" / "concretization" / "action_templates.json").read_text(
            encoding="utf-8"
        )
    )["templates"]
    campaigns = {
        json.loads(path.read_text(encoding="utf-8"))["campaign_id"]: json.loads(
            path.read_text(encoding="utf-8")
        )["steps"]
        for path in sorted(plans_dir.glob("*.procedural-plan.json"))
    }
    corpus = analyze_corpus(campaigns, templates)
    assert corpus.total_campaigns == 55
    # Corpus-wide Gate-1: no catalog-supported step offers a proposer-chosen mechanism.
    assert corpus.evidence_divergent == 0
    # Catalog coverage is partial and honestly reported, not hidden.
    assert 0.0 < corpus.catalog_coverage_rate < 1.0


def test_every_technique_reaching_campaign_is_compiled():
    """The corpus omits exactly the campaigns whose relationships reach no technique."""
    bundle = json.loads(
        (PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json").read_text(
            encoding="utf-8"
        )
    )
    campaign_ids = {
        reference["external_id"]: item["id"]
        for item in bundle["objects"]
        if item.get("type") == "campaign"
        and not item.get("revoked")
        and not item.get("x_mitre_deprecated")
        for reference in item.get("external_references", [])
        if reference.get("source_name") == "mitre-attack"
    }
    reaches_technique = {
        relationship["source_ref"]
        for relationship in bundle["objects"]
        if relationship.get("relationship_type") == "uses"
        and relationship.get("target_ref", "").startswith("attack-pattern--")
    }
    expected = {
        external_id
        for external_id, stix_id in campaign_ids.items()
        if stix_id in reaches_technique
    }
    compiled = {
        path.name.split(".")[0]
        for path in (PROJECT_ROOT / "release" / "plans" / "enterprise").glob(
            "*.procedural-plan.json"
        )
    }
    assert compiled == expected
