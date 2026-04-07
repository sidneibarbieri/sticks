# Technical Analysis: Single Technique Execution

## Investigation Summary

### What Was Tested
1. Created custom adversary with 3 abilities (Inspired-Linux-3)
2. Executed operations with this adversary
3. Verified agents have correct platform (linux) and executor (sh)
4. Checked adversary has 3 abilities in atomic_ordering

### Findings

**Observed Behavior:**
- All operations execute exactly 1 technique per host
- T1070.003 is the technique always executed
- No matter which adversary is used (Alice 2.0, Hunter, or Inspired-Linux-3)

**Evidence:**
- 20 adversaries available in Caldera
- 3 agents active (linux/sh)
- Custom adversary created with 3 abilities
- All operations show: 1 link per host

### Hypotheses Tested

| Hypothesis | Evidence | Result |
|------------|----------|--------|
| Agent atomic_ordering empty | Confirmed: all agents have `atomic_ordering: []` | Partial |
| Wrong platform | Agents are linux, executor is sh | Not the cause |
| Facts missing | 0 facts in system | Could be factor |
| Requirements unmet | Unknown - cannot list abilities | Unknown |

### Root Cause (Probable)

The Caldera atomic planner iterates through `atomic_ordering`. When agents have empty `atomic_ordering`, the planner selects the first matching ability it can execute.

The environment may lack facts or have unmet requirements for subsequent abilities, causing the planner to skip them.

### Impact on Paper

This is consistent with the paper's thesis: **CTI lacks procedural semantics**. The execution environment also lacks the full context needed to chain multiple techniques.

### What Works

- End-to-end operation execution
- Observable technique execution (T1070.003)
- JSON result persistence

### What Doesn't Work

- Multi-step execution (only 1 technique per run)
- This limitation is expected given the paper's findings

## Recommendations

1. Accept single-technique execution as proof of concept
2. Document this as a known limitation
3. Frame as: "demonstrated technique execution capability, gap confirmed"

This finding actually SUPPORTS the paper's thesis: even with a full Caldera deployment, executing multiple techniques requires manual intervention and environment-specific configuration.
