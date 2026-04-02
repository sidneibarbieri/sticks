# Multi-Technique Execution Analysis

## Evidence

### Operation: exp_0.apt28_nearest_neighbor_campaign
- Adversary: Alice 2.0
- Atomic ordering: 8 abilities defined
- **Observed: 1 link per host**
- Technique executed: T1070.003

### Root Cause Investigation

| Check | Result |
|-------|--------|
| Adversary has multiple abilities | ✅ 8 abilities |
| Abilities have no requirements | ✅ reqs=0 |
| Executor matches platform | ✅ sh/linux |
| Agent sleep allows multiple | ❌ 30-60s sleep |
| More than 1 technique executed | ❌ Only T1070.003 |

## Conclusion

**Confirmed: Single technique per execution**

Even with 8 abilities defined in adversary, only T1070.003 executes.

## Hypothesis

The atomic planner iterates through atomic_ordering, but:
1. Agent sleep (30-60s) is too long for typical observation windows
2. First ability (T1070.003) always succeeds
3. Environment constraints block subsequent abilities

## Impact

- Multi-technique execution: NOT DEMONSTRATED
- Gap between CTI and execution: CONFIRMED

## Valid Claim

"We demonstrated end-to-end operation execution in Caldera with three active agents and observable ATT&CK technique execution (T1070.003)."
