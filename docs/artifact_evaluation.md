# Artifact Evaluation Guide

This document provides instructions for reproducing the experimental results presented in the STICKS paper.

## Overview

STICKS is a framework for executing MITRE ATT&CK campaigns in a controlled laboratory environment. The artifact includes:

- **Framework code**: Python package for campaign execution (`src/sticks/`)
- **Campaign definitions**: YAML files defining ATT&CK technique sequences (`data/campaigns/`)
- **SUT profiles**: System-under-test configurations (`lab/sut_profiles/`)
- **Execution scripts**: Automated campaign runners (`scripts/`)
- **Results**: Evidence and execution summaries (`results/`)

## System Requirements

### Minimum Requirements
- Python 3.8 or higher
- 8GB RAM
- 10GB free disk space
- macOS, Linux, or Windows (with WSL2)

### Optional Requirements (for full lab mode)
- Vagrant 2.3+
- VirtualBox 6.1+, libvirt, or QEMU
- 16GB RAM
- 20GB free disk space

## Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd sticks
```

### 2. Install Dependencies
```bash
# Install Python package in development mode
pip install -e .

# Or install requirements directly
pip install -r requirements.txt
```

### 3. Verify Installation
```bash
python -c "import sticks; print('STICKS package imported successfully')"
```

## Quick Start

### List Available Campaigns
```bash
python scripts/run_campaign.py --list
```

### Execute Single Campaign
```bash
# Execute ShadowRay campaign
python scripts/run_campaign.py --campaign 0.shadowray

# Execute with custom output directory
python scripts/run_campaign.py --campaign 0.mustang_panda --output results/my_run
```

### Execute All Campaigns
```bash
# Run all campaigns for regression testing
python scripts/run_all_campaigns.py

# Run with custom output directory
python scripts/run_all_campaigns.py --output results/batch_test
```

## Campaign Details

### Primary Campaigns
- **0.shadowray**: AI/ML infrastructure attack (C0045)
- **0.mustang_panda**: Realistic Chinese APT campaign (C0047)
- **0.pikabot_realistic**: Realistic malware campaign (C0026)

### Extended Validation Campaigns
- **0.fox_kitten**: Iranian intrusion set (C0011)

### Expected Success Rates
- **Primary campaigns**: ≥60% techniques successful
- **Extended validation**: Variable (inspired techniques expected to fail)

## Output Structure

### Evidence Files
Each campaign execution generates:
```
results/evidence/<campaign>_<timestamp>/
├── summary.json              # Execution summary
├── per_technique/            # Individual technique evidence
│   ├── T1059.006_<timestamp>.json
│   ├── T1546.004_<timestamp>.json
│   └── ...
└── artifacts/                # Generated artifacts
    ├── logs/
    ├── files/
    └── network/
```

### Summary Format
```json
{
  "campaign_id": "0.shadowray",
  "total_techniques": 10,
  "successful": 6,
  "failed": 4,
  "success_rate": 60.0,
  "duration_seconds": 45.2,
  "technique_results": [...]
}
```

## Generating Paper Tables

### LaTeX Tables
```bash
# Generate all tables
python scripts/generate_tables.py --output results/tables

# Generate specific format
python scripts/generate_tables.py --format latex
python scripts/generate_tables.py --format json
```

### Generated Tables
- `corpus_table.tex`: Campaign corpus overview
- `fidelity_table.tex`: Fidelity classification summary
- `execution_table.tex`: Execution results

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Ensure src layout is properly configured
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python scripts/run_campaign.py --list
```

#### Permission Errors
```bash
# Ensure scripts are executable
chmod +x scripts/*.py
```

#### Executor Registration Failures
```bash
# Check executor registry
python -c "from sticks.data.abilities_registry.executor_registry import registry; print(f'Registered: {len(registry._executors)} executors')"
```

#### Campaign Loading Errors
```bash
# Validate campaign files
python -c "from sticks.campaign_loader import load_campaign; load_campaign('0.shadowray')"
```

### Expected Failures

Some techniques are expected to fail:
- **Inspired techniques**: Platform-specific mechanisms not available
- **Privilege escalation**: Requires elevated privileges
- **External C2**: No internet access in isolated environment

### Debug Mode
```bash
# Enable verbose logging
python scripts/run_campaign.py --campaign 0.shadowray --debug
```

## Full Lab Mode (Optional)

For complete infrastructure emulation:

### 1. Setup Virtual Environment
```bash
cd lab/vagrant
vagrant up
```

### 2. Run with Full Infrastructure
```bash
# Campaigns will use real VMs for execution
python scripts/run_all_campaigns.py --lab-mode full
```

### 3. Cleanup
```bash
cd lab/vagrant
vagrant destroy -f
```

## Reproducing Paper Results

### ShadowRay Campaign (Primary Result)
```bash
# Should achieve 6/10 successful techniques
python scripts/run_campaign.py --campaign 0.shadowray

# Verify success rate
grep "Successful:" results/evidence/0.shadowray_*/summary.json
```

### All Campaigns Regression Test
```bash
# All primary campaigns should pass
python scripts/run_all_campaigns.py

# Check batch summary
cat results/evidence/batch_*/batch_summary.json | python -m json.tool
```

### Generate Paper Tables
```bash
# Generate all tables for paper inclusion
python scripts/generate_tables.py --output results/tables
```

## Contact and Support

For issues with artifact reproduction:
1. Check this guide first
2. Review error logs in `results/evidence/`
3. Verify system requirements
4. Contact: [maintainer-email]

## Citation

If you use this artifact in research, please cite:
```
[Paper citation details]
```

## License

STICKS is released under MIT License. See `LICENSE` file for details.
