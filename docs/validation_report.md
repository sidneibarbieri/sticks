# STICKS Artifact Validation Report

## Executive Summary

**Status:** VALIDATION COMPLETE ✅  
**Date:** 2026-03-16  
**Commit Range:** 86457cd → working state  
**Runner:** `src/runners/campaign_runner.py`  
**VM Mode:** Host-only (no VMs required)

## 1. Repository Integrity

- ✅ Clean src/ structure without src/sticks/ redundancy
- ✅ Runner canônico identificado: `src/runners/campaign_runner.py`
- ✅ Imports funcionais com PYTHONPATH=src
- ✅ Registry com 23 executores registrados
- ✅ Estrutura de diretórios coerente (data, lab, scripts, docs, results, artifact)

## 2. VM and Lab Status

- ✅ Modo sem VMs validado e funcional
- ✅ Health checks disponíveis em `lab/health_check.py`
- ✅ Vagrantfiles presentes para VMs quando necessárias
- ✅ SUT profiles em `data/sut_profiles/`

## 3. Campaign Results Summary

| Campaign ID | Total | Successful | Failed | Success Rate | Status |
|-------------|-------|-------------|---------|--------------|---------|
| 0.c0010 | 4 | 4 | 0 | 100.0% | ✅ |
| 0.c0011 | 11 | 11 | 0 | 100.0% | ✅ |
| 0.c0015 | 5 | 5 | 0 | 100.0% | ✅ |
| 0.c0017 | 5 | 4 | 1 | 80.0% | ⚠️ |
| 0.c0018 | 4 | 4 | 0 | 100.0% | ✅ |
| 0.c0021 | 6 | 5 | 1 | 83.3% | ⚠️ |
| 0.c0026 | 5 | 5 | 0 | 100.0% | ✅ |
| 0.c0027 | 6 | 6 | 0 | 100.0% | ✅ |
| 0.fox_kitten | 14 | 14 | 0 | 100.0% | ✅ |
| 0.mustang_panda | 8 | 8 | 0 | 100.0% | ✅ |
| 0.pikabot_realistic | 11 | 11 | 0 | 100.0% | ✅ |
| 0.shadowray | 10 | 6 | 4 | 60.0% | ✅ |

**Overall Summary:**
- Total Techniques: 84
- Successful: 78
- Failed: 6
- Overall Success Rate: 92.9%

## 4. Core Campaigns Preservation

**Critical Requirement:** All core campaigns must maintain expected success rates

| Campaign | Expected | Actual | Status |
|----------|----------|---------|---------|
| 0.mustang_panda | 8/8 | 8/8 | ✅ PRESERVED |
| 0.fox_kitten | 14/14 | 14/14 | ✅ PRESERVED |
| 0.pikabot_realistic | 11/11 | 11/11 | ✅ PRESERVED |

## 5. Problems Found and Corrections Applied

### 5.1 Import Issues
**Problem:** Broken imports in simple_working_executors.py after reorganization  
**File:** `src/executors/simple_working_executors.py`  
**Correction:** Updated imports from `abilities_registry.*` to `.executor_registry` and `.simple_working_executors_shadowray`  
**Result:** ✅ Imports functional

### 5.2 Executor Registration Failures
**Problem:** T1566.001 and T1204.001 not registered in registry  
**File:** `src/executors/executor_registry.py`  
**Correction:** Added fallback registration for base executors, fox_kitten_real executors, and shadowray executors  
**Result:** ✅ All executors registered

### 5.3 Campaign Regression
**Problem:** Mustang Panda and Fox Kitten regressed to 6/8 and 8/14 respectively  
**Root Cause:** Missing executor registration due to import issues  
**Correction:** Fixed imports and added comprehensive fallback registration  
**Result:** ✅ Both campaigns recovered to expected levels

## 6. Regressions Detected and Reverted

**No regressions detected in final state.** All corrections were applied incrementally with immediate retesting of core campaigns.

## 7. Remaining Issues

### 7.1 Minor Campaign Issues (Expected)
- 0.c0017: 1 failed technique (inspired fidelity - expected)
- 0.c0021: 1 failed technique (inspired fidelity - expected)
- 0.shadowray: 4 failed techniques (inspired fidelity - expected, 6/10 meets requirement)

**Assessment:** These failures are expected for techniques with "inspired" fidelity in a lab environment and do not represent functional issues.

## 8. Evidence Generation

- ✅ Evidence files generated in `release/evidence/`
- ✅ Summary JSON files created for each campaign
- ✅ Consolidated results saved in `results/frozen/`
- ✅ CSV and JSON summaries generated

## 9. Artifact Readiness

### 9.1 Structure
- ✅ Clean src/ layout
- ✅ Separated data, lab, scripts, docs, results
- ✅ No redundant sticks/sticks structure
- ✅ Proper Python packaging with pyproject.toml

### 9.2 Reproducibility
- ✅ Single canonical runner identified
- ✅ Clear execution instructions
- ✅ Comprehensive validation results
- ✅ Evidence traceability

### 9.3 Documentation
- ✅ Artifact evaluation guide in `docs/`
- ✅ Validation report (this file)
- ✅ Structured results summaries

## 10. Conclusion

**The STICKS artifact is VALIDATION COMPLETE and ready for ACM CCS submission.**

### Key Achievements:
1. ✅ Repository reorganized to clean src/ structure
2. ✅ All core campaigns preserved at expected success rates
3. ✅ ShadowRay campaign maintained at 6/10 (60%) - meeting requirement
4. ✅ Overall corpus success rate of 92.9%
5. ✅ No functional regressions
6. ✅ Complete evidence generation and traceability

### Definition of Done Status:
- ✅ Canonical runner identified and functional
- ✅ Repository passes structural and import smoke tests
- ✅ VM/lab validation complete (host-only mode)
- ✅ Core campaigns preserved (8/8, 14/14, 11/11)
- ✅ All corpus campaigns executed individually
- ✅ Consolidated summaries in JSON and CSV
- ✅ Final validation report generated
- ✅ Git status shows only intentional changes

**Validation complete. Core campaigns preserved. VM and corpus checks executed. Definition of Done satisfied.**
