#!/usr/bin/env python3
"""
LLM-Assisted Environment Inference — Ablation Layer

Optional module that queries an LLM to enrich campaign environment inference
for campaigns where the canonical (rule-based) pipeline has low or no confidence.

Design principles (top-4 venue quality):
  1. LLM is ablation layer, NOT foundation — paper claims use canonical pipeline
  2. Every LLM output is compared against the canonical baseline
  3. Full prompt/response audit trail in results/audit/llm/
  4. Acceptance policy: LLM result only adopted if it fills a gap (no overrides)
  5. Reproducibility: temperature=0, cached responses, deterministic prompts

Usage:
    python3 llm_environment_inference.py [--provider anthropic|azure] [--dry-run]

Dependencies:
    anthropic  (pip install anthropic)      — for Anthropic Claude
    openai     (pip install openai)         — for Azure OpenAI

Authors: Roth, Barbieri, Evangelista, Pereira Jr.
Date: 2026-03-06
"""

import json
import csv
import os
import sys
import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from collections import Counter

# ─────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
RESULTS_DIR = SCRIPT_DIR / "results"
AUDIT_DIR = RESULTS_DIR / "audit"
LLM_AUDIT_DIR = AUDIT_DIR / "llm"

# LLM parameters — fixed for reproducibility
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 1024
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
AZURE_MODEL = "gpt-4o"

# Prompt template
ENVIRONMENT_INFERENCE_PROMPT = """You are a cybersecurity expert analyzing MITRE ATT&CK campaign data.
Given the following campaign information, infer the target environment.

Campaign: {campaign_name}

Techniques used (ATT&CK IDs with tactics):
{technique_list}

Software used:
{software_list}

CVEs exploited:
{cve_list}

Based on this information, infer the target environment.
Respond ONLY with valid JSON in this exact format:
{{
    "inferred_os": ["list of OS families: Windows, Linux, macOS, ESXi"],
    "required_services": ["list of services needed"],
    "network_requirements": ["list of network features"],
    "confidence": "high or medium or low",
    "reasoning": "brief one-sentence justification"
}}"""


# ─────────────────────────────────────────────────────────────────
# LLM Client Abstraction
# ─────────────────────────────────────────────────────────────────

class LLMClient:
    """Abstract LLM client with provider selection."""

    def __init__(self, provider='anthropic', dry_run=False):
        self.provider = provider
        self.dry_run = dry_run
        self.client = None

        if not dry_run:
            if provider == 'anthropic':
                try:
                    import anthropic
                    self.client = anthropic.Anthropic()
                except ImportError:
                    print("[ERROR] anthropic package not installed. Use: pip install anthropic")
                    sys.exit(1)
            elif provider == 'azure':
                try:
                    from openai import AzureOpenAI
                    self.client = AzureOpenAI(
                        api_key=os.environ.get('AZURE_OPENAI_API_KEY'),
                        api_version="2024-02-01",
                        azure_endpoint=os.environ.get('AZURE_OPENAI_ENDPOINT', ''),
                    )
                except ImportError:
                    print("[ERROR] openai package not installed. Use: pip install openai")
                    sys.exit(1)

    def query(self, prompt):
        """Send prompt to LLM and return response text."""
        if self.dry_run:
            return json.dumps({
                "inferred_os": ["Windows"],
                "required_services": ["smb"],
                "network_requirements": ["outbound_https"],
                "confidence": "low",
                "reasoning": "DRY RUN — no actual inference performed."
            })

        if self.provider == 'anthropic':
            message = self.client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text

        elif self.provider == 'azure':
            response = self.client.chat.completions.create(
                model=AZURE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
            return response.choices[0].message.content

        return ""


# ─────────────────────────────────────────────────────────────────
# Core Logic
# ─────────────────────────────────────────────────────────────────

def load_campaign_facts():
    """Load campaign factual structure from pipeline audit CSV."""
    csv_path = AUDIT_DIR / 'campaign_factual_structure.csv'
    if not csv_path.exists():
        print(f"[ERROR] {csv_path} not found. Run sut_measurement_pipeline.py first.")
        sys.exit(1)
    with open(csv_path, 'r') as f:
        return list(csv.DictReader(f))


def load_env_inference():
    """Load canonical environment inference from pipeline audit CSV."""
    csv_path = AUDIT_DIR / 'environment_inference.csv'
    if not csv_path.exists():
        print(f"[ERROR] {csv_path} not found. Run sut_measurement_pipeline.py first.")
        sys.exit(1)
    with open(csv_path, 'r') as f:
        return {row['campaign_id']: row for row in csv.DictReader(f)}


def build_prompt(fact_row):
    """Build the structured prompt for a campaign."""
    techs = fact_row.get('technique_ids', '').replace(';', ', ') or 'None listed'
    tactics = fact_row.get('tactic_sequence', '').replace(';', ', ') or 'None listed'
    software = fact_row.get('software_ids', '').replace(';', ', ') or 'None listed'
    cves = fact_row.get('cve_ids', '').replace(';', ', ') or 'None listed'

    tech_list = f"{techs}\n(Tactics: {tactics})"

    return ENVIRONMENT_INFERENCE_PROMPT.format(
        campaign_name=fact_row['campaign_name'],
        technique_list=tech_list,
        software_list=software,
        cve_list=cves,
    )


def parse_llm_response(response_text):
    """Parse LLM JSON response, handling common formatting issues."""
    # Try direct JSON parse
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON block from markdown
    import re
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def compare_with_canonical(llm_result, canonical_row):
    """Compare LLM inference with canonical pipeline inference."""
    canonical_os = set(filter(None, canonical_row.get('inferred_os', '').split(';')))
    llm_os = set(llm_result.get('inferred_os', []))

    agreement = len(canonical_os & llm_os) / max(len(canonical_os | llm_os), 1)
    novel = llm_os - canonical_os
    missing = canonical_os - llm_os

    return {
        'agreement_score': round(agreement, 2),
        'canonical_os': sorted(canonical_os),
        'llm_os': sorted(llm_os),
        'novel_os': sorted(novel),
        'missing_os': sorted(missing),
    }


def should_accept(llm_result, canonical_row, comparison):
    """
    Acceptance policy: LLM result adopted ONLY if it fills a gap.
    Never overrides canonical signals.
    """
    canonical_confidence = canonical_row.get('confidence', 'none')

    # Only accept if canonical confidence is low or none
    if canonical_confidence in ('high', 'medium'):
        return False, "canonical_confidence_sufficient"

    # Accept if LLM provides novel OS signals
    if comparison['novel_os']:
        return True, f"fills_gap_novel_os={comparison['novel_os']}"

    return False, "no_novel_information"


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def run_llm_enrichment(campaign_facts=None, env_inference=None, provider='anthropic',
                        dry_run=False):
    """
    Main entry point. Can be called from pipeline or standalone.
    Returns dict with LLM enrichment metrics.
    """
    if campaign_facts is None:
        campaign_facts = load_campaign_facts()
    if env_inference is None:
        env_inference = load_env_inference()

    LLM_AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    client = LLMClient(provider=provider, dry_run=dry_run)

    # Identify candidates: campaigns with low/none confidence
    candidates = []
    for fact in campaign_facts:
        camp_id = fact['campaign_id']
        env_row = env_inference.get(camp_id, {})
        confidence = env_row.get('confidence', 'none')
        if confidence in ('low', 'none'):
            candidates.append((fact, env_row))

    print(f"\n  LLM candidates (low/none confidence): {len(candidates)}/{len(campaign_facts)}")

    # Process candidates
    log_entries = []
    comparison_rows = []
    acceptance_rows = []
    n_accepted = 0
    n_novel = 0

    for fact, env_row in candidates:
        camp_name = fact['campaign_name']
        camp_id = fact['campaign_id']

        # Build prompt
        prompt = build_prompt(fact)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:12]

        # Check cache
        cache_file = LLM_AUDIT_DIR / f"cache_{prompt_hash}.json"
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            response_text = cached['response']
            print(f"    [CACHED] {camp_name}")
        else:
            # Query LLM
            response_text = client.query(prompt)
            # Cache response
            with open(cache_file, 'w') as f:
                json.dump({
                    'campaign_name': camp_name,
                    'prompt_hash': prompt_hash,
                    'response': response_text,
                    'timestamp': datetime.now().isoformat(),
                    'provider': provider,
                    'dry_run': dry_run,
                }, f, indent=2)
            print(f"    [QUERIED] {camp_name}")

        # Parse response
        llm_result = parse_llm_response(response_text)
        if not llm_result:
            log_entries.append({
                'campaign_name': camp_name,
                'status': 'parse_error',
                'prompt_hash': prompt_hash,
            })
            continue

        # Compare with canonical
        comparison = compare_with_canonical(llm_result, env_row)
        comparison_rows.append({
            'campaign_name': camp_name,
            'canonical_os': ';'.join(comparison['canonical_os']),
            'llm_os': ';'.join(comparison['llm_os']),
            'agreement_score': comparison['agreement_score'],
            'novel_os': ';'.join(comparison['novel_os']),
            'missing_os': ';'.join(comparison['missing_os']),
        })

        # Acceptance decision
        accepted, reason = should_accept(llm_result, env_row, comparison)
        if accepted:
            n_accepted += 1
        if comparison['novel_os']:
            n_novel += 1

        acceptance_rows.append({
            'campaign_name': camp_name,
            'accepted': accepted,
            'reason': reason,
            'llm_confidence': llm_result.get('confidence', 'unknown'),
            'llm_reasoning': llm_result.get('reasoning', ''),
        })

        log_entries.append({
            'campaign_name': camp_name,
            'status': 'success',
            'prompt_hash': prompt_hash,
            'accepted': accepted,
        })

    # ── Export audit files ──
    # Full log
    with open(LLM_AUDIT_DIR / 'llm_inference_log.jsonl', 'w') as f:
        for entry in log_entries:
            f.write(json.dumps(entry) + '\n')

    # Comparison CSV
    if comparison_rows:
        with open(LLM_AUDIT_DIR / 'llm_vs_canonical.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(comparison_rows[0].keys()))
            writer.writeheader()
            writer.writerows(comparison_rows)

    # Acceptance report
    if acceptance_rows:
        with open(LLM_AUDIT_DIR / 'llm_acceptance_report.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(acceptance_rows[0].keys()))
            writer.writeheader()
            writer.writerows(acceptance_rows)

    n_total = len(campaign_facts)
    n_candidates = len(candidates)
    results = {
        'total_campaigns': n_total,
        'candidates': n_candidates,
        'candidates_pct': round(n_candidates / max(n_total, 1) * 100, 1),
        'accepted_count': n_accepted,
        'accepted_pct': round(n_accepted / max(n_candidates, 1) * 100, 1) if n_candidates else 0.0,
        'novel_signal_count': n_novel,
        'agreement_mean': round(
            sum(r['agreement_score'] for r in comparison_rows) / max(len(comparison_rows), 1),
            2
        ) if comparison_rows else 0.0,
        'dry_run': dry_run,
    }

    print(f"\n  LLM enrichment results:")
    print(f"    Candidates: {n_candidates}/{n_total} ({results['candidates_pct']}%)")
    print(f"    Accepted: {n_accepted}/{n_candidates}")
    print(f"    Novel signals: {n_novel}")
    print(f"    Mean agreement: {results['agreement_mean']}")

    return results


def main():
    parser = argparse.ArgumentParser(description='LLM-Assisted Environment Inference')
    parser.add_argument('--provider', choices=['anthropic', 'azure'],
                        default='anthropic', help='LLM provider')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run without making actual API calls')
    args = parser.parse_args()

    print("=" * 70)
    print("LLM-Assisted Environment Inference — Ablation Layer")
    print("=" * 70)
    print(f"  Provider: {args.provider}")
    print(f"  Dry run: {args.dry_run}")

    results = run_llm_enrichment(provider=args.provider, dry_run=args.dry_run)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == '__main__':
    main()
