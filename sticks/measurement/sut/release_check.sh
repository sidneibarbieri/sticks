#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STICKS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE_ROOT="$(cd "$STICKS_ROOT/.." && pwd)"
MEAS_SCRIPTS="$STICKS_ROOT/measurement/sut/scripts"
PAPER_DIR="$WORKSPACE_ROOT/ACM CCS - Paper 2"

export STICKS_ROOT
export WORKSPACE_ROOT
export MEAS_SCRIPTS
export PAPER_DIR

log() { printf '[release-check] %s\n' "$*"; }
fail() { printf '[release-check][FAIL] %s\n' "$*" >&2; exit 1; }

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
python3 sut_measurement_pipeline.py >/tmp/measurement_pipeline_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_pipeline_release.log >&2
  fail "pipeline execution failed"
}

log "1b) Rendering TikZ figures from measured outputs"
python3 render_figures.py >/tmp/measurement_render_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_render_release.log >&2
  fail "figure rendering failed"
}

log "1c) Generating traceability appendix"
python3 generate_traceability.py >/tmp/measurement_traceability_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_traceability_release.log >&2
  fail "traceability generation failed"
}

log "1d) Evaluating compatibility manual-validation packet"
python3 evaluate_compatibility_validation.py >/tmp/measurement_validation_release.log 2>&1 || {
  tail -n 120 /tmp/measurement_validation_release.log >&2
  fail "compatibility validation summary generation failed"
}

log "1e) Synchronizing manuscript values from measured outputs"
python3 "$STICKS_ROOT/scripts/sync_manuscript_values.py" --paper paper2 >/tmp/measurement_sync_release.log 2>&1 || {
  cat /tmp/measurement_sync_release.log >&2
  fail "manuscript value synchronization failed"
}

log "2) Checking required output artifacts"
required=(
  "results/todo_values.json"
  "results/todo_values_latex.tex"
  "results/figures_data.json"
  "results/audit/all_cves.csv"
  "results/audit/campaign_cves.csv"
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

log "3) Validating key numeric invariants"
python3 - <<'PY'
import json, csv, sys
from pathlib import Path
base = Path('results')
with open(base/'todo_values.json') as f:
    d = json.load(f)

checks = []
checks.append((d['enterprise_platform_count'] == 691, 'enterprise_platform_count must be 691'))
checks.append((d['enterprise_campaigns_with_software_count'] == 47, 'campaigns_with_software_count must be 47'))
checks.append((d['enterprise_campaigns_with_platform_signal_count'] == 47, 'campaigns_with_platform_signal_count must be 47'))
checks.append((d['enterprise_campaigns_platform_unknown_count'] == 5, 'campaigns_platform_unknown_count must be 5'))
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

# Dataset table totals in main.tex are currently static and must stay aligned
# with local bundles used by the pipeline.
expected_bundle_totals = {
    'enterprise-attack.json': {'attack-pattern': 835, 'campaign': 52, 'intrusion-set': 187, 'malware': 696, 'tool': 91},
    'mobile-attack.json': {'attack-pattern': 190, 'campaign': 3, 'intrusion-set': 17, 'malware': 121, 'tool': 2},
    'ics-attack.json': {'attack-pattern': 95, 'campaign': 8, 'intrusion-set': 16, 'malware': 30, 'tool': 0},
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

log "3b) Validating static tables in manuscript against measured artifacts"
python3 - <<'PY'
import csv, re, sys
import os
from pathlib import Path

paper_dir = Path(os.environ["PAPER_DIR"])
meas_scripts = Path(os.environ["MEAS_SCRIPTS"])
main = (paper_dir / 'main.tex').read_text(encoding='utf-8')

required_dataset_rows = [
    (
        "Enterprise dataset row",
        [
            r"Enterprise & \enterprisetotalattackpatterncount{} & \enterpriseactivecampaigncount{}  & \enterprisetotalintrusionsetcount{} & \enterprisetotalmalwarecount{} & \enterprisetotaltoolcount{} \\",
            r"Enterprise & 835 & 52  & 187 & 696 & 91 \\",
        ],
    ),
    (
        "Mobile dataset row",
        [r"Mobile     & 190 & 3   & 17  & 121 & 2  \\"],
    ),
    (
        "ICS dataset row",
        [r"ICS        & 95  & 8   & 16  & 30  & 0  \\"],
    ),
    (
        "CAPEC dataset row",
        [r"CAPEC      & 615 & 0   & 0   & 0   & 0 \\"],
    ),
    (
        "FiGHT dataset row",
        [r"FiGHT      & 707 & 0   & 136 & 475 & 73 \\"],
    ),
]
for label, alternatives in required_dataset_rows:
    if not any(row in main for row in alternatives):
        print(f"[release-check][FAIL] dataset table row missing/mismatched: {label}")
        sys.exit(1)

expected = {}
with open(meas_scripts / 'results' / 'audit' / 'campaign_cves.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if int(row.get('cve_count','0')) > 0:
            cves = '; '.join(x.strip() for x in row['cves'].split(';') if x.strip())
            expected[row['campaign_name']] = cves

for name, cves in expected.items():
    latex_row = f"{name} & {cves} \\\\"
    if latex_row not in main:
        print(f"[release-check][FAIL] campaign CVE row missing/mismatched in main.tex: {latex_row}")
        sys.exit(1)

software_counts = {}
with open(meas_scripts / 'results' / 'audit' / 'campaign_software.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        software_counts[row['campaign_name']] = int(row['software_count'])

platform_signal = {}
with open(meas_scripts / 'results' / 'audit' / 'campaign_platforms_software_only.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        platform_signal[row['campaign_name']] = row['platform_signal'] == 'True'

profile_tiers = {}
with open(meas_scripts / 'results' / 'audit' / 'campaign_profile_completeness.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        profile_tiers[row['campaign_name']] = 'Exploit-pinned' if row['tier_t3_exploit_pinned'] == 'True' else 'Not anchored'

for name in [
    'APT28 Nearest Neighbor Campaign',
    'Operation MidnightEclipse',
    'Versa Director Zero Day Exploitation',
    'SharePoint ToolShell Exploitation',
    'ShadowRay',
]:
    latex_row = (
        f"{name} & "
        f"{'Yes' if software_counts[name] > 0 else 'No'} ({software_counts[name]}) & "
        f"{'Yes' if platform_signal[name] else 'No'} & "
        f"{profile_tiers[name]} \\\\"
    )
    if latex_row not in main:
        print(f"[release-check][FAIL] campaign CVE profile row missing/mismatched in main.tex: {latex_row}")
        sys.exit(1)

rule_label_map = {
    'R1_ID_PLATFORM_KEYWORD': r'Platform keyword (\texttt{Windows Domain}/identity/IaaS/SaaS)',
    'R3_ID_LATERAL_TACTIC': 'Lateral-movement tactic fallback',
    'R4_VMR_KERNEL_BOOT': 'Kernel or boot pattern',
    'R6_VMR_NAME_PATTERN': 'Privileged or kernel name pattern',
    'R7_CF_CONTAINER_COMPATIBLE': 'Container-compatible targets',
    'R8_DEFAULT_VMR': 'Conservative fallback',
}
with open(meas_scripts / 'results' / 'audit' / 'compatibility_rule_breakdown.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        label = rule_label_map[row['rule_id']]
        latex_row = (
            f"{label} & {row['class']} & {row['count']} & "
            f"{float(row['pct_all_techniques']):.1f}\\% \\\\"
        )
        if latex_row not in main:
            print(f"[release-check][FAIL] compatibility rule breakdown row missing/mismatched in main.tex: {latex_row}")
            sys.exit(1)

print('[release-check] static table checks OK')
PY

log "3c) Enforcing bibliography policy (no poster entries/citations)"
python3 "$MEAS_SCRIPTS/sanitize_bibliography_policy.py" \
  --input "$PAPER_DIR/references.bib" \
  --input "$PAPER_DIR/references_official_downloaded.bib" \
  --input "$PAPER_DIR/used_citations_only.bib" \
  --check >/tmp/measurement_bib_policy_check.log 2>&1 || {
    cat /tmp/measurement_bib_policy_check.log >&2
    fail "bibliography policy check failed"
  }

python3 - <<'PY'
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

poster_like_cites = sorted(k for k in cite_keys if re.search(r'(?i)(poster|asiaccs.*kurt|chen_2020)', k))
if poster_like_cites:
    print(f"[release-check][FAIL] poster-like citation keys found in main.tex: {', '.join(poster_like_cites)}")
    sys.exit(1)

print('[release-check] bibliography policy checks OK')
PY

log "4) Building manuscript PDF"
cd "$PAPER_DIR"
python3 "$STICKS_ROOT/scripts/build_manuscript.py" --paper-dir "$PAPER_DIR" >/tmp/measurement_paper_release.log 2>&1 || {
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
python3 "$STICKS_ROOT/scripts/check_paper_hygiene.py" --paper paper2 >/tmp/measurement_paper_hygiene.log 2>&1 || {
  cat /tmp/measurement_paper_hygiene.log >&2
  fail "paper directory hygiene check failed"
}

log "6) Ensuring manuscript imports generated measurement macros"
# Paper now uses results/values.tex (local copy of generated macros)
rg -n '\\input\{results/values\.tex\}' main.tex >/dev/null || \
  fail "main.tex is not importing results/values.tex"

log "6b) Ensuring rendered ablation figure template exists"
[[ -f "$PAPER_DIR/figures/ablation_template.tex" ]] || fail "missing ablation_template.tex"

log "6c) Ensuring rendered tier-collapse figure template exists"
[[ -f "$PAPER_DIR/figures/tier_collapse_template.tex" ]] || fail "missing tier_collapse_template.tex"

log "6d) Ensuring macro coverage report exists and is non-empty"
[[ -f "$MEAS_SCRIPTS/results/macro_coverage.json" ]] || fail "missing macro_coverage.json"
python3 - <<'PY'
import json, sys
import os
from pathlib import Path
meas_scripts = Path(os.environ["MEAS_SCRIPTS"])
p = meas_scripts / 'results' / 'macro_coverage.json'
d = json.loads(p.read_text(encoding='utf-8'))
used = int(d.get('manuscript_macro_count', 0))
generated = int(d.get('generated_macro_count', 0))
if used <= 0 or generated <= 0:
    print('[release-check][FAIL] macro coverage report indicates empty generated/used macro sets')
    sys.exit(1)
print('[release-check] macro coverage report OK')
PY

log "6e) Checking macro consistency (defined vs used)"
python3 - <<'PY'
import os
import re, sys
from pathlib import Path

paper_dir = Path(os.environ["PAPER_DIR"])
latex_file = paper_dir / 'results' / 'values.tex'
main_file  = paper_dir / 'main.tex'

if not latex_file.exists() or not main_file.exists():
    print('[release-check][WARN] cannot run macro consistency check (files missing)')
    sys.exit(0)

# Extract defined macros from todo_values_latex.tex
defined = set()
for line in latex_file.read_text(encoding='utf-8').splitlines():
    m = re.match(r'\\newcommand\{\\([A-Za-z]+)\}', line)
    if m:
        defined.add(m.group(1))

# Extract macro uses from main.tex (backslash + alphabetic name)
main_text = main_file.read_text(encoding='utf-8')
used_all = set(re.findall(r'\\([A-Za-z][A-Za-z0-9]+)', main_text))

# Only check against our generated macros
used_from_generated = used_all & defined
used_but_undefined = set()
# Well-known LaTeX/package commands that match our heuristic but are NOT pipeline macros
latex_builtins = {
    'includegraphics', 'definecolor', 'textcolor', 'resizebox',
    'raggedright', 'arraybackslash', 'shortstack', 'nolinkurl',
    'multicolumn', 'bibliography', 'bibliographystyle',
}
# Check if main.tex uses macros that LOOK like pipeline macros but aren't defined
# Heuristic: pipeline macros are camelCase starting with lowercase
for name in used_all:
    if name[0].islower() and len(name) > 8 and name not in defined and name not in latex_builtins:
        # Likely intended as a pipeline macro
        if any(keyword in name.lower() for keyword in [
            'enterprise', 'campaign', 'software', 'compatibility',
            'threshold', 'bootstrap', 'null', 'cve', 'sut', 'delta',
            'capec', 'fight', 'ics', 'mobile', 'jaccard', 'profile',
        ]):
            used_but_undefined.add(name)

defined_but_unused = defined - used_all

if used_but_undefined:
    print(f'[release-check][WARN] {len(used_but_undefined)} pipeline-like macros used in main.tex but NOT defined in todo_values_latex.tex:')
    for name in sorted(used_but_undefined):
        print(f'  \\{name}')

if defined_but_unused:
    print(f'[release-check][INFO] {len(defined_but_unused)} macros defined in todo_values_latex.tex but not used in main.tex (audit-only metrics)')

print(f'[release-check] macro consistency: {len(defined)} defined, {len(used_from_generated)} used in manuscript, {len(used_but_undefined)} potentially missing')
if used_but_undefined:
    sys.exit(1)
PY

log "7) Ensuring traceability appendix exists"
[[ -f "$STICKS_ROOT/measurement/sut/TRACEABILITY.md" ]] || fail "missing TRACEABILITY.md"

log "PASS: pipeline + data + paper build are consistent"
