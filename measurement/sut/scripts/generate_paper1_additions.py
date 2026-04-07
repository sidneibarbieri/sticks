#!/usr/bin/env python3
"""
Paper 1 Campaign Additions Generator

This script generates campaign profiles for Paper 1 additions.
Uses the same methodology as the original ShadowRay and Soft Cell case studies.

Recommended campaigns:
1. Solarwinds (71 techniques, 13 tactics)
2. Wocao (70 techniques, 12 tactics)
3. Dream Job (55 techniques, 12 tactics)
4. SharePoint (35 techniques, 13 tactics)
5. C0015 (34 techniques, 10 tactics)
"""

import json
import yaml
from pathlib import Path
from collections import Counter


CALDERA_DIR = Path("../../../sticks/data/caldera_adversaries")
OUTPUT_DIR = Path("results/paper1_additions")


def load_campaign(campaign_name):
    """Load a single campaign from YAML."""
    campaign_file = CALDERA_DIR / f"{campaign_name}.yml"
    
    if not campaign_file.exists():
        raise FileNotFoundError(f"Campaign not found: {campaign_file}")
    
    with open(campaign_file) as file:
        return yaml.safe_load(file)


def extract_technique_profile(campaign_data):
    """Extract technique profile from campaign data."""
    techniques = []
    tactic_counts = Counter()
    platforms = set()
    
    # Get from atomic_ordering
    atomic_ordering = campaign_data.get("atomic_ordering", [])
    for ap_id in atomic_ordering:
        if "attack-pattern--" in ap_id:
            techniques.append(ap_id)
    
    # Get from abilities
    abilities = campaign_data.get("abilities", {})
    for ability_id, ability_data in abilities.items():
        if "attack-pattern--" in ability_id:
            if ability_id not in techniques:
                techniques.append(ability_id)
        
        # Get tactic
        if "tactic" in ability_data:
            tactic_counts[ability_data["tactic"]] += 1
        
        # Get platforms from executors (e.g., executors[].sh.platform)
        executors = ability_data.get("executors", [])
        for executor in executors:
            for executor_type, executor_data in executor.items():
                if isinstance(executor_data, dict) and "platform" in executor_data:
                    platforms.add(executor_data["platform"])
    
    # Get platforms from campaign level (fallback)
    if not platforms:
        platforms = set(campaign_data.get("platforms", []))
    if not platforms:
        platforms = set(campaign_data.get("attack-platforms", []))
    
    return {
        "technique_count": len(techniques),
        "techniques": techniques,
        "tactic_counts": dict(tactic_counts),
        "tactic_coverage": len(tactic_counts),
        "platforms": list(platforms),
        "has_initial_access": "initial-access" in tactic_counts,
        "has_execution": "execution" in tactic_counts,
        "has_exfiltration": "exfiltration" in tactic_counts,
        "has_impact": "impact" in tactic_counts,
        "is_linux_only": "linux" in platforms and "windows" not in platforms and "darwin" not in platforms,
    }


def generate_campaign_latex(campaign_name, profile):
    """Generate LaTeX text for a campaign."""
    # Campaign name without prefix
    clean_name = campaign_name.replace("0.", "").replace("_", " ").title()
    
    latex = f"""
\\subsection*{{{clean_name}}}

\\textbf{{Profile:}} {profile['technique_count']} techniques, {profile['tactic_coverage']} tactics

\\textbf{{Platforms:}} {', '.join(profile['platforms']) if profile['platforms'] else 'Not specified'}

\\textbf{{Kill chain coverage:}}
"""
    
    if profile['has_initial_access']:
        latex += "Initial Access, "
    if profile['has_execution']:
        latex += "Execution, "
    if profile['has_exfiltration']:
        latex += "Exfiltration, "
    if profile['has_impact']:
        latex += "Impact, "
    
    latex = latex.rstrip(", ") + "."
    
    # Analysis of what would be needed
    latex += f"""

\\textbf{{Analysis:}} To emulate this campaign using our three-stage methodology,
the following would be required:

1. \\textbf{{Stage 1 (Structured CTI):}} Extract {profile['technique_count']} techniques
   from STIX/ATT&CK representation.
"""
    
    # Estimate environment assumptions
    if "windows" in profile['platforms']:
        latex += "   - Windows environment assumptions required.\\n"
    if "linux" in profile['platforms']:
        latex += "   - Linux environment assumptions required.\\n"
    if "network" in profile['platforms']:
        latex += "   - Network device environment assumptions required.\\n"
    
    latex += f"""
2. \\textbf{{Stage 2 (NLP Extraction):}} Use LLM to extract procedural details
   for {profile['technique_count']} techniques. Estimated analyst time: ~1 hour.
3. \\textbf{{Stage 3 (Caldera Translation):}} Generate {profile['technique_count']}
   abilities and validate execution in isolated environment.

\\textbf{{Expected outcome:}} Based on our methodology, we expect this campaign
to be \\textit{{partially deployable}} due to missing environment specifications
in the original CTI. The number of environment assumptions required would be:
{len(profile['platforms']) if profile['platforms'] else 0} platform-specific assumptions.
"""
    
    return latex


def main():
    """Main function."""
    print("=" * 70)
    print("Paper 1 Campaign Additions Generator")
    print("=" * 70)
    
    # Recommended campaigns
    recommended = [
        "0.solarwinds_compromise",
        "0.operation_wocao",
        "0.operation_dream_job",
        "0.sharepoint_toolshell_exploitation",
        "0.c0015",
    ]
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    all_profiles = []
    all_latex = "\\section{Additional Case Studies}\n"
    all_latex += "\\label{sec:additional_case_studies}\n\n"
    
    print("\n[1/2] Processing campaigns...")
    
    for campaign in recommended:
        try:
            print(f"  Processing: {campaign}")
            data = load_campaign(campaign)
            profile = extract_technique_profile(data)
            profile["campaign_id"] = campaign
            
            # Get campaign name
            clean_name = campaign.replace("0.", "").replace("_", " ").title()
            profile["display_name"] = clean_name
            
            all_profiles.append(profile)
            
            # Generate LaTeX
            latex = generate_campaign_latex(campaign, profile)
            all_latex += latex + "\n\n"
            
        except Exception as error:
            print(f"  Warning: {campaign}: {error}")
    
    # Save profiles
    profiles_file = OUTPUT_DIR / "campaign_profiles.json"
    with open(profiles_file, "w") as file:
        json.dump(all_profiles, file, indent=2)
    
    print(f"\n[+] Profiles saved to {profiles_file}")
    
    # Save LaTeX
    latex_file = OUTPUT_DIR / "additional_case_studies.tex"
    with open(latex_file, "w") as file:
        file.write(all_latex)
    
    print(f"[+] LaTeX saved to {latex_file}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print(f"\n{'Campaign':<40} {'Techniques':<12} {'Tactics':<8} {'Platforms'}")
    print("-" * 80)
    
    for profile in all_profiles:
        print(f"{profile['display_name']:<40} {profile['technique_count']:<12} {profile['tactic_coverage']:<8} {', '.join(profile['platforms']) if profile['platforms'] else 'N/A'}")
    
    print("\n" + "=" * 70)
    print("INSTRUCTIONS FOR PAPER 1")
    print("=" * 70)
    print("""
To add these case studies to Paper 1:

1. Copy the LaTeX from results/paper1_additions/additional_case_studies.tex
2. Paste into main.tex after the existing ShadowRay/Soft Cell sections
3. Update the Results section to include these additional case studies
4. Add to bibliography if needed

Note: These are theoretical profiles based on technique/tactic analysis.
Actual execution would require running the full pipeline as in the paper.
    """)


if __name__ == "__main__":
    main()
