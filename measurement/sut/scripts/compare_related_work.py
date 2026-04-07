#!/usr/bin/env python3
"""
Related Work Comparison: Jin et al. NDSS 2024 vs Our Work

This script compares our findings with Jin et al. NDSS 2024 paper:
"Sharing cyber threat intelligence: Does it really help?"

Key metrics from Jin et al.:
- 10,392,889 STIX objects analyzed
- 61.22% unique (38.78% duplicate)
- 2,063 unique objects per day
- Timeliness: 10-50 days for malware variants

Our contributions:
- Procedural semantics gap measurement
- Environment semantics gap measurement
- Confidence intervals (not in Jin et al.)
"""

from datetime import datetime


def main():
    """Main comparison function."""
    print("=" * 70)
    print("RELATED WORK COMPARISON")
    print("=" * 70)
    
    print("\n" + "=" * 70)
    print("Jin et al. NDSS 2024: 'Sharing CTI: Does it really help?'")
    print("=" * 70)
    
    jin_findings = {
        "volume": {
            "total_objects": "10,392,889",
            "unique_percentage": "61.22%",
            "duplicate_percentage": "38.78%",
            "daily_unique": "2,063"
        },
        "timeliness": {
            "malware_variants": "10-50 days",
            "initial_samples": "43-109 days",
            "causality": "2-4 days increase after incidents"
        },
        "coverage": {
            "period": "Oct 2014 - Apr 2023"
        }
    }
    
    print("\n[Volume]")
    print(f"  Total STIX objects: {jin_findings['volume']['total_objects']}")
    print(f"  Unique: {jin_findings['volume']['unique_percentage']}")
    print(f"  Duplicates: {jin_findings['volume']['duplicate_percentage']}")
    print(f"  Daily unique: {jin_findings['volume']['daily_unique']}")
    
    print("\n[Timeliness]")
    print(f"  Malware variants: {jin_findings['timeliness']['malware_variants']}")
    print(f"  Initial samples: {jin_findings['timeliness']['initial_samples']}")
    print(f"  Causality: {jin_findings['timeliness']['causality']}")
    
    print("\n" + "=" * 70)
    print("OUR WORK: Procedural & Environment Semantics Gap")
    print("=" * 70)
    
    our_findings = {
        "paper1": {
            "focus": "Procedural Semantics Gap in Structured CTI",
            "methodology": "STIX to Caldera translation pipeline",
            "case_studies": "ShadowRay, Soft Cell",
            "key_metric": "Silhouette score ~0 (no clusters)"
        },
        "paper2": {
            "focus": "Environment Semantics Gap in Structured CTI",
            "methodology": "SUT requirements measurement",
            "campaigns": "52 ATT&CK campaigns",
            "key_metric": "32.7% explicit compatibility coverage; 91.6% fallback-resolved non-CF coverage"
        },
        "martina_comparison": {
            "groups_with_specific_techniques": "32.1%",
            "confidence_interval": "25.5% - 39.5%",
            "note": "Added CI not in original Martina paper"
        }
    }
    
    print("\n[Paper 1: Procedural Semantics Gap]")
    print(f"  Focus: {our_findings['paper1']['focus']}")
    print(f"  Methodology: {our_findings['paper1']['methodology']}")
    print(f"  Case studies: {our_findings['paper1']['case_studies']}")
    print(f"  Key metric: {our_findings['paper1']['key_metric']}")
    
    print("\n[Paper 2: Environment Semantics Gap]")
    print(f"  Focus: {our_findings['paper2']['focus']}")
    print(f"  Methodology: {our_findings['paper2']['methodology']}")
    print(f"  Campaigns: {our_findings['paper2']['campaigns']}")
    print(f"  Key metric: {our_findings['paper2']['key_metric']}")
    
    print("\n[Martina Comparison]")
    print(f"  Groups with specific techniques: {our_findings['martina_comparison']['groups_with_specific_techniques']}")
    print(f"  95% CI: {our_findings['martina_comparison']['confidence_interval']}")
    print(f"  Note: {our_findings['martina_comparison']['note']}")
    
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    
    comparison_table = """
    | Aspect              | Jin et al. NDSS 2024    | Our Work              |
    |---------------------|-------------------------|----------------------|
    | Focus               | CTI sharing quality     | CTI semantic gaps   |
    | Data size           | 10M+ objects           | 52 campaigns         |
    | Key metric          | 61% unique             | 32.7% explicit compatibility coverage |
    | Statistical CI      | No                     | Yes (95% CI)        |
    | Novelty             | Volume/timeliness      | Procedural/environment|
    """
    
    print(comparison_table)
    
    print("\n[Key Differences]")
    print("1. Jin et al. measure SHARING patterns, we measure CONTENT quality")
    print("2. Jin et al. show 38% duplication, we show sparse environment semantics and reliance on compatibility fallback")
    print("3. We add confidence intervals (not in Jin or Martina)")
    print("4. Our work extends Martina by adding statistical rigor")
    
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print("""
Our work complements Jin et al. by analyzing WHAT is shared
(volume/timeliness) vs WHAT'S MISSING (semantic gaps).

- Jin et al.: "Is CTI being shared?" → Yes, but 38% duplicate
- Our work: "Is CTI useful?" → Partial, gaps in procedural/environment

Together, these provide a complete picture of CTI limitations.
    """)
    
    return {
        "jin": jin_findings,
        "ours": our_findings,
        "comparison_timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    main()
