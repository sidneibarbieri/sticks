#!/usr/bin/env python3
"""
Additional Case Studies Generator for Paper 1

This script analyzes additional campaigns to add as case studies.
Currently Paper 1 has: ShadowRay, Soft Cell (2 cases)
Target: Add 3-5 more cases

Analysis includes:
- Technique count
- Tactic coverage
- Platform requirements
- Execution complexity
"""

import json
import yaml
from pathlib import Path
from collections import Counter


CALDERA_DIR = Path("../../../sticks/data/caldera_adversaries")
RESULTS_DIR = Path("results")


def analyze_campaign(campaign_file):
    """Analyze a single campaign."""
    with open(campaign_file) as file:
        data = yaml.safe_load(file)
    
    campaign_id = campaign_file.stem
    techniques = set()
    tactic_counts = Counter()
    
    # Get from atomic_ordering (attack-pattern IDs)
    if "atomic_ordering" in data:
        for ap_id in data["atomic_ordering"]:
            if "attack-pattern--" in ap_id:
                techniques.add(ap_id)
    
    # Also check abilities
    if "abilities" in data:
        for ability_id, ability_data in data["abilities"].items():
            # Get technique ID from ability key or data
            if "attack-pattern--" in ability_id:
                techniques.add(ability_id)
            elif "technique_id" in ability_data:
                techniques.add(ability_data["technique_id"])
            
            # Get tactic from ability
            if "tactic" in ability_data:
                tactic_counts[ability_data["tactic"]] += 1
    
    # Get platform info
    platforms = set()
    if "platforms" in data:
        platforms = set(data["platforms"])
    
    # Try to get from attack-platforms as fallback
    if not platforms and "attack-platforms" in data:
        platforms = set(data["attack-platforms"])
    
    return {
        "campaign_id": campaign_id,
        "technique_count": len(techniques),
        "techniques": list(techniques),
        "tactic_counts": dict(tactic_counts),
        "tactic_coverage": len(tactic_counts),
        "platforms": list(platforms),
        "has_initial_access": "initial-access" in tactic_counts,
        "has_execution": "execution" in tactic_counts,
        "has_exfiltration": "exfiltration" in tactic_counts,
        "has_impact": "impact" in tactic_counts,
    }


def rank_campaigns_for_case_study(campaigns):
    """Rank campaigns by suitability for case study."""
    scored = []
    
    for campaign in campaigns:
        score = 0
        
        # Prefer diverse tactic coverage
        score += campaign["tactic_coverage"] * 2
        
        # Prefer more techniques
        score += campaign["technique_count"]
        
        # Prefer complete killchain
        if campaign["has_initial_access"]:
            score += 5
        if campaign["has_exfiltration"]:
            score += 5
        if campaign["has_impact"]:
            score += 3
        
        # Prefer Windows/Linux mix
        if "windows" in campaign["platforms"] and "linux" in campaign["platforms"]:
            score += 3
        
        scored.append((score, campaign))
    
    # Sort by score descending
    scored.sort(key=lambda x: -x[0])
    
    return scored


def main():
    """Main function."""
    print("=" * 60)
    print("Additional Case Studies Generator")
    print("=" * 60)
    
    # Analyze all campaigns
    print("\n[1/2] Analyzing campaigns...")
    campaigns = []
    
    for campaign_file in CALDERA_DIR.glob("*.yml"):
        try:
            campaign = analyze_campaign(campaign_file)
            campaigns.append(campaign)
        except Exception as error:
            print(f"  Warning: {campaign_file.name}: {error}")
    
    print(f"  Analyzed {len(campaigns)} campaigns")
    
    # Rank by suitability
    print("\n[2/2] Ranking campaigns...")
    ranked = rank_campaigns_for_case_study(campaigns)
    
    # Show top candidates
    print("\n" + "=" * 60)
    print("TOP CANDIDATES FOR CASE STUDIES")
    print("=" * 60)
    
    print(f"\n{'Rank':<5} {'Campaign':<40} {'Score':<8} {'Techniques':<12} {'Tactics':<8}")
    print("-" * 80)
    
    for i, (score, campaign) in enumerate(ranked[:10], 1):
        print(f"{i:<5} {campaign['campaign_id'][:38]:<40} {score:<8} {campaign['technique_count']:<12} {campaign['tactic_coverage']:<8}")
    
    # Save detailed analysis
    output_file = RESULTS_DIR / "additional_case_studies.json"
    with open(output_file, "w") as file:
        json.dump({
            "all_campaigns": campaigns,
            "ranked": [{"score": s, "campaign": c} for s, c in ranked],
            "recommendations": [c for s, c in ranked[:5]]
        }, file, indent=2)
    
    print(f"\n[+] Results saved to {output_file}")
    
    # Show recommended additions
    print("\n" + "=" * 60)
    print("RECOMMENDED ADDITIONAL CASE STUDIES")
    print("=" * 60)
    
    current = ["ShadowRay", "Soft Cell"]
    recommended = [c["campaign_id"] for s, c in ranked[:5]]
    new_additions = [r for r in recommended if r not in current]
    
    print(f"\nCurrent case studies: {', '.join(current)}")
    print(f"Recommended additions: {', '.join(new_additions)}")
    
    print("\n[+] Add these 3-5 campaigns to Paper 1 for more robust evaluation!")


if __name__ == "__main__":
    main()
