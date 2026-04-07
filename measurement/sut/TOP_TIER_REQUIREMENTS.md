# Top-Tier Ready Requirements

## Current State
- Proof of concept: YES
- Top-tier ready: NO

## What is Missing

### 1. Full Campaign Execution (CRITICAL)
**Status:** NOT IMPLEMENTED

**Required:**
- Execute more than 1 technique (currently only T1070.003)
- Replace "running forever" default objective with finite execution
- Achieve observable completion state

**How to fix:**
- Create custom finite objective in Caldera
- Or use atomic planner with limited abilities
- Execute at least 3-5 techniques per run

### 2. Campaign-to-Adversary Mapping (CRITICAL)
**Status:** PARTIAL

**Required:**
- True mapping from campaign (51 in corpus) to specific adversary
- Currently all map to default Alice 2.0
- Need custom adversaries or inspired profiles

**How to fix:**
- Create 2-3 custom adversaries based on campaign techniques
- Or create inspired profiles with 3-5 specific techniques

### 3. Auto SUT Provisioning (HIGH)
**Status:** NOT IMPLEMENTED

**Required:**
- Automated environment setup
- Currently manual

**How to fix:**
- Complete Docker Compose setup automation
- Add pre-flight checks

### 4. Multiple Campaign Execution (HIGH)
**Status:** NOT IMPLEMENTED

**Required:**
- Execute at least 3-5 different campaigns
- Each with finite execution
- Each with observable results

**How to fix:**
- Run multiple campaigns using different adversaries
- Document results per campaign

### 5. Windows Execution (OPTIONAL)
**Status:** NOT IMPLEMENTED

**Required for full coverage:**
- Windows target support
- Or explicit documentation that Linux-only is supported scope

## Minimum for Top-Tier

To achieve top-tier, you need at minimum:

1. **Execute 3+ techniques** (not just 1)
2. **Run 3+ different campaigns** (not just SolarWinds)
3. **Achieve finite completion** (not "running forever")
4. **Generate clean results** per campaign

## Roadmap

Priority 1: Fix infinite execution
- Create finite objective
- Execute 3+ techniques

Priority 2: Run 3 campaigns
- Use existing 20 adversaries
- Document results

Priority 3: Auto-provisioning
- Complete Docker automation
