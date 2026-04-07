# Execution Summary - Correct Terminology

## Key Terminology (Matching Paper)

- **Campaign**: CTI entity from MITRE ATT&CK (e.g., 0.solarwinds_compromise)
- **Operation**: Execution in Caldera (what we actually ran)
- **Inspired Profile**: Derived profile for execution

## What Was Demonstrated

### Infrastructure (Operation Level):
✅ 11 operations running in Caldera (8889)
✅ All with 3 hosts each
✅ Technique T1070.003 executed with status=0

### Data (Campaign Level):
✅ 51 campaigns in corpus (sticks/data/caldera_adversaries/)
✅ SUT specs generated (sticks/data/sut/<campaign>/)
✅ STIX data (sticks/data/stix/)

## Honest Framing

**Correct**: "We demonstrated end-to-end operation execution in Caldera with three agents and observable ATT&CK technique execution."

**NOT Correct**: "We executed the campaign"

## Technical Reality

- Campaign 0.solarwinds_compromise has 71 techniques
- We executed 1 technique (T1070.003)
- Using default adversary (Alice 2.0), not campaign-specific

## Paper Alignment

The paper measures whether CTI contains enough info to derive SUT requirements. Our execution demonstrates:
- Infrastructure can run operations
- Technique execution is possible
- More work needed for full campaign execution
