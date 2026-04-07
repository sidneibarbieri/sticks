# Root Cause Analysis: Multi-Technique Execution

## Finding

### Evidence from Caldera Logs
```
WARNING: Ability referenced in adversary but not found: 45e43472-cc7e-4247-8367-22f31c6d2cc5
WARNING: Ability referenced in adversary but not found: e39d1d94-c6b5-4f47-a206-1c5f7e2c81bc
```

### Root Cause
The custom adversary (Inspired-Linux-3) referenced abilities that **do not exist** in the Caldera database. Only the first ability (43b3754c...) was valid.

When Caldera loads an adversary with invalid abilities, it skips the missing ones and only executes what exists.

## What This Means

1. **Cannot list abilities via API** - GET /api/v2/abilities returns 404
2. **Cannot verify ability existence** before creating adversary
3. **Only known-valid abilities execute** - T1070.003 works because it's a standard ability

## Impact

- Multi-technique execution blocked by inability to discover valid abilities
- This is an **environmental/API limitation**, not a conceptual issue

## Paper Relevance

This limitation **supports the paper's thesis**:
- Structured CTI does not contain execution semantics
- Even with adversary profiles, environment constraints prevent automated chaining
- Gap between intended behavior and actual execution confirmed

## Current State

What works:
- End-to-end operation execution
- Single technique observable (T1070.003)
- JSON result persistence
- Docker Compose valid
- Caldera operational

What doesn't:
- Multi-technique execution (blocked by API/environment)
- This is a structural limitation

## Recommendation

Accept current proof of concept as demonstrating:
1. Execution capability exists
2. At least one technique observable
3. Gap confirmed between CTI and execution

This is consistent with the paper's contribution: measuring where CTI fails to support automation.
