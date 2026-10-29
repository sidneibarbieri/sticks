#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STICKS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MEAS_SCRIPTS="$STICKS_ROOT/measurement/sut/scripts"
WORKSPACE_ROOT="$(cd "$STICKS_ROOT/.." && pwd)"
source "$STICKS_ROOT/scripts/python_env.sh"

PAPER_DIR_SOURCE="none"
if [[ "${PAPER_DIR+x}" == "x" ]]; then
  if [[ ! -d "$PAPER_DIR" ]]; then
    printf '[release-check][FAIL] explicit PAPER_DIR is not a directory: %s\n' \
      "$PAPER_DIR" >&2
    exit 1
  fi
  PAPER_DIR="$(cd "$PAPER_DIR" && pwd -P)"
  if [[ ! -f "$PAPER_DIR/main.tex" ]]; then
    printf '[release-check][FAIL] explicit PAPER_DIR has no main.tex: %s\n' \
      "$PAPER_DIR" >&2
    exit 1
  fi
  PAPER_DIR_SOURCE="explicit"
else
  PAPER_DIR=""
fi

HAS_MANUSCRIPT_DIR=0
if [[ -f "$PAPER_DIR/main.tex" ]]; then
  HAS_MANUSCRIPT_DIR=1
fi

export STICKS_ROOT
export WORKSPACE_ROOT
export MEAS_SCRIPTS
export PAPER_DIR
export PAPER_DIR_SOURCE
export HAS_MANUSCRIPT_DIR

log() { printf '[release-check] %s\n' "$*"; }
fail() { printf '[release-check][FAIL] %s\n' "$*" >&2; exit 1; }

PYTHON_BIN="$(sticks_resolve_python "$STICKS_ROOT" "$STICKS_ROOT/requirements.txt")"

if [[ "$HAS_MANUSCRIPT_DIR" == "1" ]]; then
  log "Manuscript directory ($PAPER_DIR_SOURCE): $PAPER_DIR"
else
  log "No manuscript directory selected; running standalone artifact checks"
fi

log "0) Verifying required input bundles"
required_inputs=(
  "data/enterprise-attack.json"
  "data/mobile-attack.json"
  "data/ics-attack.json"
  "data/stix-capec.json"
  "data/fight-enterprise-10.1.json"
)
for f in "${required_inputs[@]}"; do
  [[ -f "$MEAS_SCRIPTS/$f" ]] || fail "missing input bundle: $MEAS_SCRIPTS/$f"
done

log "1) Running measurement pipeline"
cd "$MEAS_SCRIPTS"
"$PYTHON_BIN" sut_measurement_pipeline.py >/tmp/measurement_pipeline_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_pipeline_release.log >&2
  fail "pipeline execution failed"
}

log "1b) Rendering TikZ figures from measured outputs"
"$PYTHON_BIN" render_figures.py >/tmp/measurement_render_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_render_release.log >&2
  fail "figure rendering failed"
}

log "1c) Generating traceability appendix"
"$PYTHON_BIN" generate_traceability.py >/tmp/measurement_traceability_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_traceability_release.log >&2
  fail "traceability generation failed"
}

log "1d) Evaluating compatibility manual-validation packet"
"$PYTHON_BIN" evaluate_compatibility_validation.py >/tmp/measurement_validation_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_validation_release.log >&2
  fail "compatibility validation summary generation failed"
}

log "1e) Generating deterministic CVE resolution report"
"$PYTHON_BIN" "$STICKS_ROOT/scripts/generate_cve_resolution_report.py" >/tmp/measurement_cve_resolution_release.log 2>&1 || {
  cat /tmp/measurement_cve_resolution_release.log >&2
  fail "CVE resolution report generation failed"
}

log "1ea) Generating infrastructure and SUT automation coverage report"
"$PYTHON_BIN" "$STICKS_ROOT/scripts/generate_infra_automation_report.py" >/tmp/measurement_infra_automation_release.log 2>&1 || {
  cat /tmp/measurement_infra_automation_release.log >&2
  fail "infrastructure automation report generation failed"
}

log "1eb) Generating compatibility rule surface report"
"$PYTHON_BIN" "$STICKS_ROOT/scripts/generate_compatibility_rule_surface.py" >/tmp/measurement_rule_surface_release.log 2>&1 || {
  cat /tmp/measurement_rule_surface_release.log >&2
  fail "compatibility rule surface generation failed"
}

if [[ "$HAS_MANUSCRIPT_DIR" == "1" ]]; then
  log "1f) Checking the manuscript's generated inputs against released evidence"
  "$PYTHON_BIN" "$STICKS_ROOT/scripts/sync_sticks_manuscript.py" \
    --paper-dir "$PAPER_DIR" --check >/tmp/measurement_sync_release.log 2>&1 || {
    cat /tmp/measurement_sync_release.log >&2
    fail "manuscript inputs are stale; run scripts/sync_sticks_manuscript.py"
  }
  cat /tmp/measurement_sync_release.log
else
  log "1f) No manuscript tree detected; skipping manuscript input check"
fi

log "2) Checking required output artifacts"
required=(
  "results/todo_values.json"
  "results/todo_values_latex.tex"
  "results/figures_data.json"
  "results/audit/all_cves.csv"
  "results/audit/campaign_cves.csv"
  "results/audit/cve_resolution_candidates.csv"
  "results/audit/campaign_software.csv"
  "results/audit/campaign_platforms_software_only.csv"
  "results/audit/campaign_os_family_counts.csv"
  "results/audit/campaign_non_os_platform_counts.csv"
  "results/audit/campaign_platform_unknown.csv"
  "results/audit/is_cves.csv"
  "results/audit/is_software.csv"
  "results/audit/initial_access_campaigns.csv"
  "results/audit/initial_access_techniques.csv"
  "results/audit/profile_specificity_software_only.csv"
  "results/audit/profile_ablation_summary.csv"
  "results/audit/evidence_threshold_curve.csv"
  "results/audit/delta_sensitivity.csv"
  "results/audit/bootstrap_confusion_distribution.csv"
  "results/audit/platform_distribution.csv"
  "results/audit/cve_validation.csv"
  "results/audit/technique_compatibility.csv"
  "results/audit/compatibility_rule_breakdown.csv"
  "results/audit/compatibility_validation_sample.csv"
  "results/compatibility_validation_summary.json"
  "results/audit/compatibility_validation_confusion.csv"
  "results/audit/compatibility_validation_disagreements.csv"
)
for f in "${required[@]}"; do
  [[ -f "$f" ]] || fail "missing artifact: $MEAS_SCRIPTS/$f"
done
[[ -f "$STICKS_ROOT/results/cve_resolution_candidates.json" ]] || fail "missing artifact: $STICKS_ROOT/results/cve_resolution_candidates.json"
[[ -f "$STICKS_ROOT/results/CVE_RESOLUTION_CANDIDATES.md" ]] || fail "missing artifact: $STICKS_ROOT/results/CVE_RESOLUTION_CANDIDATES.md"
[[ -f "$STICKS_ROOT/release/cve_resolution_candidates.json" ]] || fail "missing artifact: $STICKS_ROOT/release/cve_resolution_candidates.json"
[[ -f "$STICKS_ROOT/release/CVE_RESOLUTION_CANDIDATES.md" ]] || fail "missing artifact: $STICKS_ROOT/release/CVE_RESOLUTION_CANDIDATES.md"
[[ -f "$STICKS_ROOT/results/infra_automation_coverage.json" ]] || fail "missing artifact: $STICKS_ROOT/results/infra_automation_coverage.json"
[[ -f "$STICKS_ROOT/results/INFRA_AUTOMATION_COVERAGE.md" ]] || fail "missing artifact: $STICKS_ROOT/results/INFRA_AUTOMATION_COVERAGE.md"
[[ -f "$STICKS_ROOT/results/infra_automation_coverage.csv" ]] || fail "missing artifact: $STICKS_ROOT/results/infra_automation_coverage.csv"
[[ -f "$STICKS_ROOT/release/infra_automation_coverage.json" ]] || fail "missing artifact: $STICKS_ROOT/release/infra_automation_coverage.json"
[[ -f "$STICKS_ROOT/release/INFRA_AUTOMATION_COVERAGE.md" ]] || fail "missing artifact: $STICKS_ROOT/release/INFRA_AUTOMATION_COVERAGE.md"
[[ -f "$STICKS_ROOT/results/compatibility_rule_surface.json" ]] || fail "missing artifact: $STICKS_ROOT/results/compatibility_rule_surface.json"
[[ -f "$STICKS_ROOT/results/COMPATIBILITY_RULE_SURFACE.md" ]] || fail "missing artifact: $STICKS_ROOT/results/COMPATIBILITY_RULE_SURFACE.md"
[[ -f "$STICKS_ROOT/release/compatibility_rule_surface.json" ]] || fail "missing artifact: $STICKS_ROOT/release/compatibility_rule_surface.json"
[[ -f "$STICKS_ROOT/release/COMPATIBILITY_RULE_SURFACE.md" ]] || fail "missing artifact: $STICKS_ROOT/release/COMPATIBILITY_RULE_SURFACE.md"

log "3) Validating key numeric invariants"
"$PYTHON_BIN" - <<'PY'
import json, csv, os, sys
from pathlib import Path
base = Path('results')
with open(base/'todo_values.json') as f:
    d = json.load(f)

checks = []
checks.append((d['enterprise_platform_count'] == 697, 'enterprise_platform_count must be 697'))
checks.append((d['enterprise_campaigns_with_software_count'] == 50, 'campaigns_with_software_count must be 50'))
checks.append((d['enterprise_campaigns_with_platform_signal_count'] == 50, 'campaigns_with_platform_signal_count must be 50'))
checks.append((d['enterprise_campaigns_platform_unknown_count'] == 6, 'campaigns_platform_unknown_count must be 6'))
checks.append((d['ent_campaigns_with_cve_count'] == 5, 'campaigns_with_cve_count must be 5'))
checks.append((d['compatibility_container_feasible_count'] + d['compatibility_vm_required_count'] + d['compatibility_infrastructure_dependent_count'] == d['enterprise_platform_count'], 'CF+VMR+ID must equal enterprise_platform_count'))
checks.append((d['threshold_k_one_confusion_pct'] >= d['threshold_k_three_confusion_pct'], 'confusion should not increase from k>=1 to k>=3'))
checks.append((d['threshold_k_one_confusion_pct'] >= d['threshold_k_two_confusion_pct'], 'confusion should not increase from k>=1 to k>=2'))
checks.append((d['threshold_k_two_confusion_pct'] >= d['threshold_k_three_confusion_pct'], 'confusion should not increase from k>=2 to k>=3'))
checks.append((d['threshold_k_three_confusion_pct'] >= d['threshold_k_five_confusion_pct'], 'confusion should not increase from k>=3 to k>=5'))
checks.append((d['threshold_k_two_sample'] > 0, 'threshold_k_two_sample must be > 0'))
checks.append((d['delta_zero_zero_five_confusion_pct'] <= d['delta_zero_ten_confusion_pct'], 'confusion should not decrease when delta goes 0.05 -> 0.10'))
checks.append((d['delta_zero_ten_confusion_pct'] <= d['delta_zero_fifteen_confusion_pct'], 'confusion should not decrease when delta goes 0.10 -> 0.15'))
checks.append((d['enterprise_campaigns_with_software_ci_low'] <= d['enterprise_campaigns_with_software_percentage'] <= d['enterprise_campaigns_with_software_ci_high'], 'campaign software CI must bound point estimate'))
checks.append((d['ent_campaigns_with_cve_ci_low'] <= d['ent_campaigns_with_cve_pct'] <= d['ent_campaigns_with_cve_ci_high'], 'campaign CVE CI must bound point estimate'))
checks.append((d['campaigns_with_initial_access_ci_low'] <= d['campaigns_with_initial_access_pct'] <= d['campaigns_with_initial_access_ci_high'], 'initial access CI must bound point estimate'))
checks.append((d['bootstrap_confusion_ci_low'] <= d['bootstrap_confusion_pct'] <= d['bootstrap_confusion_ci_high'], 'bootstrap confusion CI must bound point estimate'))
checks.append((d['bootstrap_unique_ci_low'] <= d['bootstrap_unique_pct'] <= d['bootstrap_unique_ci_high'], 'bootstrap unique CI must bound point estimate'))
checks.append((0.0 <= d['sut_profile_confusion_software_platform_percentage'] <= 100.0, 'software+platform confusion pct out of range'))
checks.append((0.0 <= d['sut_profile_confusion_software_cve_platform_percentage'] <= 100.0, 'software+cve+platform confusion pct out of range'))
checks.append((0.0 <= d['sut_profile_confusion_software_family_only_percentage'] <= 100.0, 'software+family confusion pct out of range'))
checks.append((0.0 <= d['sut_profile_confusion_software_compat_percentage'] <= 100.0, 'software+compat confusion pct out of range'))
checks.append((d['capec_platform_percentage'] == 0.0, 'CAPEC platform percentage must be 0.0 for this bundle'))
checks.append((d['capec_software_link_pct'] == 0.0, 'CAPEC software-link percentage must be 0.0 for this bundle'))
checks.append((d['capec_cve_link_pct'] == 0.0, 'CAPEC CVE-link percentage must be 0.0 for this bundle'))

with open(base/'compatibility_validation_summary.json', encoding='utf-8') as f:
    validation = json.load(f)
checks.append((validation['total_sample_rows'] == d['compatibility_validation_sample_size'], 'compatibility validation sample size mismatch'))
checks.append((validation['status'] in {'pending_manual_labels', 'ready'}, 'unexpected compatibility validation status'))

unknown_names = []
with open(base/'audit'/'campaign_platform_unknown.csv', newline='', encoding='utf-8') as f:
    r = csv.DictReader(f)
    unknown_names = sorted(row['campaign_name'] for row in r if row.get('campaign_name'))
expected_unknown = sorted([
    'Anthropic AI-orchestrated Campaign',
    'FrostyGoop Incident',
    'KV Botnet Activity',
    'Leviathan Australian Intrusions',
    'SPACEHOP Activity',
    'ShadowRay'
])
checks.append((unknown_names == expected_unknown, 'unknown campaign list mismatch'))

campaign_cve_map = {}
with open(base/'audit'/'campaign_cves.csv', newline='', encoding='utf-8') as f:
    r = csv.DictReader(f)
    for row in r:
        try:
            if int(row.get('cve_count', '0')) > 0:
                cves = '; '.join(c.strip() for c in row.get('cves', '').split(';') if c.strip())
                campaign_cve_map[row['campaign_name']] = cves
        except ValueError:
            continue
expected_campaign_cve_map = {
    'APT28 Nearest Neighbor Campaign': 'CVE-2022-38028',
    'ShadowRay': 'CVE-2023-48022',
    'Operation MidnightEclipse': 'CVE-2024-3400',
    'Versa Director Zero Day Exploitation': 'CVE-2024-39717',
    'SharePoint ToolShell Exploitation': 'CVE-2025-49704; CVE-2025-49706; CVE-2025-53770; CVE-2025-53771',
}
checks.append((campaign_cve_map == expected_campaign_cve_map, 'campaign-linked CVE table source map mismatch'))

with open(Path(os.environ['STICKS_ROOT'])/'results'/'cve_resolution_candidates.json', encoding='utf-8') as f:
    resolution = json.load(f)
resolution_totals = resolution['totals']
checks.append((resolution_totals['total_cve_positive_campaigns'] == 5, 'CVE resolution campaign count mismatch'))
checks.append((resolution_totals['total_campaign_cve_pairs'] == 8, 'CVE resolution pair count mismatch'))
checks.append((resolution_totals['automatic_candidate_pairs'] == 1, 'automatic CVE candidate pair count mismatch'))
checks.append((resolution_totals['automatic_candidate_campaigns'] == 1, 'automatic CVE candidate campaign count mismatch'))
checks.append((resolution_totals['direct_attck_binding_pairs'] == 0, 'direct ATT&CK target-product binding count mismatch'))
checks.append((resolution_totals['open_package_pairs'] == 1, 'open-package CVE pair count mismatch'))
checks.append((resolution_totals['open_package_campaigns'] == 1, 'open-package CVE campaign count mismatch'))

shadowray_resolution = next(
    row
    for row in resolution['rows']
    if row['campaign_name'] == 'ShadowRay' and row['cve_id'] == 'CVE-2023-48022'
)
checks.append((shadowray_resolution['resolution_kind'] == 'open_package', 'ShadowRay resolution kind mismatch'))
checks.append((shadowray_resolution['ecosystem'] == 'pip', 'ShadowRay ecosystem mismatch'))
checks.append((shadowray_resolution['package_name'] == 'ray', 'ShadowRay package name mismatch'))
checks.append((shadowray_resolution['automatic_sut_support'] is True, 'ShadowRay automatic support mismatch'))
checks.append((shadowray_resolution['attck_binding_status'] == 'cve_only_curated_binding', 'ShadowRay binding status mismatch'))
checks.append((shadowray_resolution['source_basis'] == 'NVD CVE record plus PyPI package metadata and release tags', 'ShadowRay source basis mismatch'))
checks.append(('https://pypi.org/project/ray/' in shadowray_resolution['evidence_sources'], 'ShadowRay evidence sources missing PyPI URL'))

with open(Path(os.environ['STICKS_ROOT'])/'results'/'compatibility_rule_surface.json', encoding='utf-8') as f:
    rule_surface = json.load(f)
checks.append((rule_surface['default_fallback_class'] == 'VMR', 'compatibility rule surface fallback mismatch'))
checks.append(('Windows Domain' in rule_surface['id_platform_keywords'], 'compatibility rule surface missing Windows Domain keyword'))
checks.append(('kerberos' in rule_surface['lateral_software_keywords'], 'compatibility rule surface missing kerberos keyword'))
checks.append(('boot|firmware|kernel' in rule_surface['kernel_boot_regex'], 'compatibility rule surface missing kernel regex fragment'))
checks.append(('lsass' in rule_surface['vmr_name_regex'], 'compatibility rule surface missing lsass regex fragment'))

with open(Path(os.environ['STICKS_ROOT'])/'results'/'infra_automation_coverage.json', encoding='utf-8') as f:
    infra = json.load(f)
infra_totals = infra['totals']
evidence_root = Path(os.environ['STICKS_ROOT']) / 'release' / 'evidence'
expected_evidence_campaigns = 0
if evidence_root.exists():
    expected_evidence_campaigns = sum(
        1
        for campaign_id in {row['campaign_id'] for row in infra['rows']}
        if any(
            candidate.is_dir() and candidate.name.startswith(f"{campaign_id}_")
            for candidate in evidence_root.iterdir()
        )
    )
checks.append((infra_totals['published_campaigns'] == 14, 'infra coverage published campaign count mismatch'))
checks.append((infra_totals['campaigns_with_strict_pair_validation'] == 12, 'infra coverage pair-valid count mismatch'))
checks.append((infra_totals['campaigns_with_base_weaknesses'] == 14, 'infra coverage base-weakness count mismatch'))
checks.append((infra_totals['campaigns_with_step_overlays'] == 1, 'infra coverage overlay count mismatch'))
checks.append((infra_totals['campaigns_with_latest_evidence'] == expected_evidence_campaigns, 'infra coverage evidence count mismatch'))
checks.append((infra_totals['campaigns_with_single_target_host'] == 14, 'infra coverage single-target count mismatch'))
checks.append((infra_totals['campaigns_with_multi_target_host'] == 0, 'infra coverage multi-target count mismatch'))
checks.append((infra_totals['campaigns_with_multi_vm_runtime'] == 14, 'infra coverage multi-VM count mismatch'))

# Dataset table totals in main.tex are currently static and must stay aligned
# with local bundles used by the pipeline.
expected_bundle_totals = {
    'enterprise-attack.json': {'attack-pattern': 858, 'campaign': 56, 'intrusion-set': 191, 'malware': 733, 'tool': 95},
    'mobile-attack.json': {'attack-pattern': 190, 'campaign': 3, 'intrusion-set': 22, 'malware': 125, 'tool': 2},
    'ics-attack.json': {'attack-pattern': 118, 'campaign': 9, 'intrusion-set': 16, 'malware': 30, 'tool': 0},
    'stix-capec.json': {'attack-pattern': 615, 'campaign': 0, 'intrusion-set': 0, 'malware': 0, 'tool': 0},
    'fight-enterprise-10.1.json': {'attack-pattern': 707, 'campaign': 0, 'intrusion-set': 136, 'malware': 475, 'tool': 73},
}
for fname, exp in expected_bundle_totals.items():
    with open(Path('data')/fname, encoding='utf-8') as f:
        bundle = json.load(f).get('objects', [])
    counts = {'attack-pattern': 0, 'campaign': 0, 'intrusion-set': 0, 'malware': 0, 'tool': 0}
    for o in bundle:
        t = o.get('type')
        if t in counts:
            counts[t] += 1
    checks.append((counts == exp, f'bundle total count mismatch for {fname}: {counts} != {exp}'))

bad = [msg for ok, msg in checks if not ok]
if bad:
    for msg in bad:
        print('[release-check][FAIL]', msg)
    sys.exit(1)
print('[release-check] numeric invariants OK')
PY

if [[ "$HAS_MANUSCRIPT_DIR" == "1" ]]; then
log "3b) Validating static tables in manuscript against measured artifacts"
"$PYTHON_BIN" - <<'PY'
import csv, re, sys
import os
from pathlib import Path

paper_dir = Path(os.environ["PAPER_DIR"])
meas_scripts = Path(os.environ["MEAS_SCRIPTS"])
main = (paper_dir / 'main.tex').read_text(encoding='utf-8')

# STICKS scopes its measured claims to the pinned Enterprise bundle, so this manuscript
# carries no multi-domain dataset table; that surface belongs to the companion measurement
# paper, whose own release check validates its rows. Asserting the absence keeps the scope
# decision enforced instead of leaving a silent gap here.
OUT_OF_SCOPE_DATASET_ROWS = ("Mobile     &", "ICS        &", "CAPEC      &", "FiGHT      &")
present = [row for row in OUT_OF_SCOPE_DATASET_ROWS if row in main]
if present:
    print(
        "[release-check][FAIL] manuscript carries out-of-scope dataset rows "
        f"({', '.join(row.strip(' &') for row in present)}); STICKS declares Enterprise-only "
        "scope, so a multi-domain table must be validated by the measurement paper's check"
    )
    sys.exit(1)

# The per-campaign CVE, profile-completeness, and routing-rule tables are surfaces of the
# companion measurement paper, not of this manuscript. Its release check validates them
# against the same measured CSVs in a format-agnostic way, so duplicating an older,
# format-bound copy here would only drift.

print('[release-check] static table checks OK')
PY
else
  log "3b) No manuscript tree detected; skipping static table checks"
fi

if [[ "$HAS_MANUSCRIPT_DIR" == "1" ]]; then
log "3c) Enforcing bibliography policy (no poster entries/citations)"
bib_policy_args=()
for bibliography_file in "$PAPER_DIR"/*.bib; do
  [[ -f "$bibliography_file" ]] || continue
  bib_policy_args+=(--input "$bibliography_file")
done
(( ${#bib_policy_args[@]} > 0 )) || fail "no BibTeX files found in $PAPER_DIR"
"$PYTHON_BIN" "$MEAS_SCRIPTS/sanitize_bibliography_policy.py" \
  "${bib_policy_args[@]}" \
  --check >/tmp/measurement_bib_policy_check.log 2>&1 || {
    cat /tmp/measurement_bib_policy_check.log >&2
    fail "bibliography policy check failed"
  }

"$PYTHON_BIN" - <<'PY'
import os
import re
import sys
from pathlib import Path

paper_dir = Path(os.environ["PAPER_DIR"])
main_tex = paper_dir / 'main.tex'
tex = main_tex.read_text(encoding='utf-8')
cite_keys = set()
for group in re.findall(r'\\cite[a-zA-Z*]*\{([^}]*)\}', tex):
    for raw in group.split(','):
        key = raw.strip()
        if key:
            cite_keys.add(key)

poster_like_cites = sorted(k for k in cite_keys if re.search(r'(?i)(poster|kurt|chen_2020)', k))
if poster_like_cites:
    print(f"[release-check][FAIL] poster-like citation keys found in main.tex: {', '.join(poster_like_cites)}")
    sys.exit(1)

print('[release-check] bibliography policy checks OK')
PY
else
  log "3c) No manuscript tree detected; skipping bibliography policy checks"
fi

if [[ "$HAS_MANUSCRIPT_DIR" == "1" ]]; then
log "4) Building manuscript PDF"
cd "$PAPER_DIR"
"$PYTHON_BIN" "$STICKS_ROOT/scripts/build_manuscript.py" --paper-dir "$PAPER_DIR" >/tmp/measurement_paper_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_paper_release.log >&2
  fail "latex build failed"
}

log "5) Ensuring no active TODO placeholders in manuscript body"
# Ignore macro definition line; fail if TODO/TBD markers appear elsewhere.
if rg -n 'TODO\{|\[TBD\]' main.tex | rg -v '^87:' >/tmp/measurement_todo_hits.log; then
  cat /tmp/measurement_todo_hits.log >&2
  fail "found unresolved TODO/TBD markers"
fi

log "5b) Enforcing paper-directory hygiene"
"$PYTHON_BIN" "$STICKS_ROOT/scripts/check_paper_hygiene.py" \
  --paper-dir "$PAPER_DIR" >/tmp/measurement_paper_hygiene.log 2>&1 || {
  cat /tmp/measurement_paper_hygiene.log >&2
  fail "paper directory hygiene check failed"
}

log "6) Ensuring the manuscript loads every generated input"
"$PYTHON_BIN" - <<'PY'
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.environ["STICKS_ROOT"])
from scripts.sync_sticks_manuscript import GENERATED_INPUTS

paper_dir = Path(os.environ["PAPER_DIR"])
main_text = (paper_dir / "main.tex").read_text(encoding="utf-8")
loaded = set(re.findall(r"\\input\{([^}]+)\}", main_text))

missing = sorted(
    f"results/{name}" for name in GENERATED_INPUTS.values() if f"results/{name}" not in loaded
)
for relative in missing:
    print(f"[release-check][FAIL] manuscript does not load generated input: {relative}")
if missing:
    sys.exit(1)
print(f"[release-check] manuscript loads all {len(GENERATED_INPUTS)} generated inputs")
PY

# A named-figure existence check is superseded by the hygiene audit in 5b, which resolves
# every file the manuscript loads and reports any figure it does not.
else
  log "4-6) No manuscript tree detected; skipping manuscript build and hygiene checks"
fi

log "6d) Ensuring macro coverage report exists and is non-empty"
[[ -f "$MEAS_SCRIPTS/results/macro_coverage.json" ]] || fail "missing macro_coverage.json"
"$PYTHON_BIN" - <<'PY'
import json, sys
import os
from pathlib import Path
meas_scripts = Path(os.environ["MEAS_SCRIPTS"])
p = meas_scripts / 'results' / 'macro_coverage.json'
d = json.loads(p.read_text(encoding='utf-8'))
used = int(d.get('manuscript_macro_count', 0))
generated = int(d.get('generated_macro_count', 0))
if generated <= 0:
    print('[release-check][FAIL] macro coverage report produced no generated macros')
    sys.exit(1)
# These macros describe the multi-domain bundle census and feed the companion measurement
# manuscript, which asserts their consumption in its own release check. This manuscript is
# scoped to the Enterprise procedural question and consumes none of them, so requiring a
# non-zero count here would only encourage importing numbers it does not report.
print(f'[release-check] macro coverage report OK: {generated} generated, {used} used here')
PY

log "6e) Checking macro consistency (defined vs used)"
"$PYTHON_BIN" - <<'PY'
import os
import re
import sys
from pathlib import Path

paper_dir = Path(os.environ["PAPER_DIR"])
main_file = paper_dir / "main.tex"

if not main_file.exists():
    print("[release-check][WARN] cannot run macro consistency check (main.tex missing)")
    sys.exit(0)

main_text = main_file.read_text(encoding="utf-8")

# The manuscript is the authority on which generated files are in scope. Checking a file the
# manuscript never inputs would report on macros LaTeX does not load.
definition_sources = []
for relative in re.findall(r"\\input\{(results/[^}]+)\}", main_text):
    candidate = paper_dir / relative
    if candidate.exists():
        definition_sources.append(candidate)

if not definition_sources:
    print("[release-check][WARN] manuscript inputs no generated results file")
    sys.exit(0)

DEFINITION_PATTERN = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}\s*$")

definitions = {}
conflicts = []
CONDITIONAL_OPEN = re.compile(r"^\\if[a-zA-Z@]*\b")
CONDITIONAL_CLOSE = re.compile(r"^\\fi\b")
for source in definition_sources:
    # Two definitions in opposite branches of a conditional are alternatives, not drift, so
    # only definitions made outside every branch can conflict.
    depth = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if CONDITIONAL_OPEN.match(stripped):
            depth += 1
        elif CONDITIONAL_CLOSE.match(stripped):
            depth = max(0, depth - 1)
        match = DEFINITION_PATTERN.match(stripped)
        if not match:
            continue
        name, value = match.group(1), match.group(2)
        previous = definitions.get(name)
        if depth == 0 and previous is not None and previous[1] != value:
            conflicts.append(f"{name}: {previous[0].name}={previous[1]} vs {source.name}={value}")
        definitions[name] = (source, value)

defined = set(definitions)
used_all = set(re.findall(r"\\([A-Za-z][A-Za-z0-9]+)", main_text))
used_from_generated = used_all & defined

latex_builtins = {
    "includegraphics", "definecolor", "textcolor", "resizebox",
    "raggedright", "arraybackslash", "shortstack", "nolinkurl",
    "multicolumn", "bibliography", "bibliographystyle", "providecolor",
}
PIPELINE_KEYWORDS = (
    "enterprise", "campaign", "software", "compatibility", "threshold",
    "bootstrap", "null", "cve", "sut", "delta", "capec", "fight", "ics",
    "mobile", "jaccard", "profile", "technique", "corpus", "admitted",
    "catalog", "binding", "fidelity",
)
used_but_undefined = {
    name
    for name in used_all - defined
    if name[0].islower()
    and len(name) > 8
    and name not in latex_builtins
    and any(keyword in name.lower() for keyword in PIPELINE_KEYWORDS)
}

defined_but_unused = defined - used_all

for name in sorted(used_but_undefined):
    print(f"[release-check][FAIL] pipeline-like macro used but never defined: \\{name}")
for conflict in sorted(conflicts):
    print(f"[release-check][FAIL] macro defined twice with different values: {conflict}")
if defined_but_unused:
    print(
        f"[release-check][INFO] {len(defined_but_unused)} generated macros are defined "
        "but unused in the manuscript"
    )

print(
    f"[release-check] macro consistency: {len(definition_sources)} inputted sources, "
    f"{len(defined)} defined, {len(used_from_generated)} used, "
    f"{len(used_but_undefined)} undefined, {len(conflicts)} conflicting"
)
if used_but_undefined or conflicts:
    sys.exit(1)
PY

log "7) Ensuring traceability appendix exists"
[[ -f "$STICKS_ROOT/measurement/sut/TRACEABILITY.md" ]] || fail "missing TRACEABILITY.md"

if [[ "$HAS_MANUSCRIPT_DIR" == "1" ]]; then
  log "PASS: pipeline + data + manuscript checks are consistent"
else
  log "PASS: pipeline + data + released output checks are consistent"
fi
