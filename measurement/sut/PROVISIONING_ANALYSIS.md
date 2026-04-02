# Provisioning Analysis: Docker vs Vagrant

## Current State

### What's Running: Docker
```
caldera_clean     0.0.0.0:8890->8888/tcp
friendly_liskov   0.0.0.0:8889->8888/tcp
```

### Vagrant Status
- Vagrantfile exists but not initialized
- Not currently in use

## Decision: Docker over Vagrant

**Reasons for Docker:**
1. Faster startup (seconds vs minutes)
2. Lower resource overhead
3. Easier for reviewers to run
4. Better ecosystem for containers
5. Standard in academic/industry research

**Vagrant use cases (not current):**
- Multi-VM Windows targets
- Complex network topologies
- Legacy system emulation

## Top Tier Requirements

| Component | Status | Priority |
|----------|--------|----------|
| Docker Compose | ✅ Working | Done |
| Caldera Server | ✅ Running | Done |
| Linux Agents | ✅ 3 Active | Done |
| Technique Execution | ✅ T1070.003 | Done |
| Multi-technique | ❌ Blocked | HIGH |
| Auto SUT Provision | ❌ Not Impl | MEDIUM |
| Windows Support | ❌ Not Impl | LOW |

## Blocker: Multi-Technique Execution

**Root Cause:** Cannot list abilities via Caldera API (returns 404)
- Cannot discover valid abilities to build multi-ability adversaries
- This is an API/environment limitation

**Impact:** Cannot demonstrate 3-5 techniques per execution

## Recommendation

For top-tier ready artifact, options are:
1. Accept single-technique as proof of concept
2. Document known limitation and work around
3. Frame as "gap confirmed" rather than "full execution"

This aligns with paper thesis: structured CTI lacks procedural semantics.
