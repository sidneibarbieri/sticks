# Windows Techniques - Execution Fidelity Classification

## Overview

This document provides honest classification of Windows-specific ATT&CK techniques when executed on Linux infrastructure. The STICKS framework prioritizes **operational truth over appearance**, explicitly documenting when techniques are classified as INSPIRED due to platform limitations.

## Fidelity Classification Framework

### FAITHFUL
Techniques executed exactly as documented in MITRE ATT&CK, on the original platform, with identical mechanisms.

### ADAPTED
Techniques executed with modifications to core mechanism while preserving the conceptual attack vector. Operational differences exist but the essence remains.

### INSPIRED
Techniques simulated or approximated due to platform incompatibility. The concept is preserved but execution differs significantly from real-world scenarios.

---

## Windows Techniques on Linux Infrastructure

### T1059.001 - PowerShell
**Platform**: Windows (original), Linux (execution)
**Classification**: **INSPIRED**

**Execution on Linux**:
```bash
# Simulated via log file creation
echo "[SIMULATION] PowerShell execution attempted" >> /tmp/powershell_simulation.log
echo "[PAYLOAD] Get-Process | Out-File processes.txt" >> /tmp/powershell_simulation.log
```

**Limitations**:
- No actual PowerShell runtime (PowerShell Core exists but lacks Windows-specific cmdlets)
- No Windows API interaction (WMI, COM objects, .NET Framework)
- No registry manipulation
- No Windows-specific process enumeration

**Justification**:
> "T1059.001 (PowerShell) is fundamentally a Windows-specific technique leveraging .NET Framework, WMI, and Windows APIs. Linux execution simulates PowerShell command patterns through log files, preserving the concept (using command-line interface for execution) but lacking Windows-specific operational mechanisms. Classification: INSPIRED."

---

### T1059.005 - Visual Basic Script (VBScript)
**Platform**: Windows (original), Linux (execution)
**Classification**: **INSPIRED**

**Execution on Linux**:
```bash
# Simulated via log file creation
echo "[SIMULATION] VBScript execution attempted" >> /tmp/vbscript_simulation.log
echo "[PAYLOAD] CreateObject(\"WScript.Shell\").Run \"cmd.exe\"" >> /tmp/vbscript_simulation.log
```

**Limitations**:
- No Windows Script Host (WSH) environment
- No COM object instantiation
- No registry access via WScript.Shell
- No Windows-specific automation capabilities

**Justification**:
> "T1059.005 (VBScript) requires Windows Script Host and COM infrastructure unavailable on Linux. Execution simulates VBScript payload patterns through log entries. The concept (malicious script execution) is preserved, but operational reality differs completely. Classification: INSPIRED."

---

### T1059.007 - JavaScript via WSH
**Platform**: Windows (original), Linux (execution)
**Classification**: **INSPIRED**

**Execution on Linux**:
```bash
# Simulated via log file creation
echo "[SIMULATION] JScript/WSH execution attempted" >> /tmp/jscript_simulation.log
echo "[PAYLOAD] WScript.CreateObject(\"WScript.Shell\")" >> /tmp/jscript_simulation.log
```

**Limitations**:
- No Windows Script Host environment
- No JScript engine with Windows bindings
- No COM object access
- No ActiveX object instantiation

**Justification**:
> "T1059.007 specifically involves JScript execution through Windows Script Host with COM/ActiveX access. Linux simulation cannot replicate WSH environment or Windows-specific JavaScript bindings. Classification: INSPIRED."

---

### T1574 - Hijack Execution Flow (DLL Hijacking)
**Platform**: Windows (original), Linux (execution)
**Classification**: **INSPIRED**

**Execution on Linux**:
```bash
# Simulated via LD_PRELOAD on Linux
export LD_PRELOAD=/tmp/malicious_preload.so
# Or create decoy DLL files
touch /tmp/vulnerable.dll /tmp/malicious.dll
```

**Limitations**:
- No Windows PE format DLLs
- No Windows loader behavior
- No Windows DLL search order
- LD_PRELOAD operates differently from DLL hijacking

**Justification**:
> "T1574 (DLL Hijacking) exploits Windows PE loader behavior and search order. Linux uses ELF format with different loading mechanisms (LD_PRELOAD, LD_LIBRARY_PATH). Concept (library injection) is similar but implementation differs fundamentally. Classification: INSPIRED on Linux, would be FAITHFUL on Windows."

---

### T1566.001 - Spearphishing Attachment
**Platform**: Platform-agnostic
**Classification**: **ADAPTED** (when simulated)

**Execution**:
```bash
# Create decoy malicious attachment
echo "X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*" > /tmp/malicious_attachment.exe
# Or simulate via log
echo "[SIMULATION] Email attachment opened" >> /tmp/phishing_simulation.log
```

**Justification**:
> "T1566.001 concept (malicious email attachment) is platform-agnostic. Execution can simulate attachment handling without Windows-specific email clients. Classification: ADAPTED when using decoy files, INSPIRED when pure log simulation."

---

### T1566.002 - Spearphishing Link
**Platform**: Platform-agnostic
**Classification**: **ADAPTED** (when simulated)

**Execution**:
```bash
# Simulate link click
echo "[SIMULATION] Phishing link clicked: http://malicious.example.com" >> /tmp/phishing_simulation.log
# Or create decoy URL file
echo "[InternetShortcut]" > /tmp/malicious.url
echo "URL=http://malicious.example.com" >> /tmp/malicious.url
```

**Justification**:
> "T1566.002 concept (malicious URL) is platform-agnostic. Simulation preserves the attack vector concept. Classification: ADAPTED."

---

## Technical Honesty Statement

The STICKS framework explicitly acknowledges these limitations rather than masking them. This honesty serves several purposes:

1. **Scientific Integrity**: Results are reproducible and limitations are transparent
2. **Reviewer Trust**: ACM CCS reviewers can verify claims against documented limitations
3. **Community Value**: Other researchers understand exactly what is being measured
4. **Future Work**: Identifies specific areas for platform expansion

## Recommended Artifact Notation

When presenting results in academic papers, use explicit notation:

```
Technique T1059.001 (PowerShell)
├─ Classification: INSPIRED
├─ Platform: Linux (target was Windows in original attack)
├─ Execution: Log-based simulation
└─ Limitation: No PowerShell runtime, no Windows API access

Technique T1021.004 (SSH Remote Services)
├─ Classification: ADAPTED
├─ Platform: Linux (matching original)
├─ Execution: Real SSH connections with generated keys
└─ Limitation: Keys generated rather than stolen from compromise
```

## Windows Infrastructure Alternative

For FAITHFUL execution of Windows techniques, the infrastructure would require:

- **Windows 10/11 VMs** (Vagrant box `gusztavvargadr/windows-10` or similar)
- **License**: Windows 180-day evaluation licenses available from Microsoft
- **Provider**: VirtualBox or VMware (libvirt/KVM supports Windows but requires drivers)
- **Caldera agents**: Windows sandcat agents
- **Size impact**: Windows VMs ~4-8GB per instance vs Linux ~1-2GB

**Current Decision**: Linux-only infrastructure prioritizes:
- Resource efficiency (ARM64 Apple Silicon compatibility)
- Open-source tooling (no licensing concerns)
- Automation simplicity (SSH-based provisioning vs WinRM)
- Reproducibility (Linux boxes readily available)

**Trade-off**: Windows techniques classified as INSPIRED rather than FAITHFUL.

---

## Validation Summary

| Campaign | Topology | Windows Techniques | Classification |
|----------|----------|-------------------|----------------|
| 0.c0011 | 3 VMs (Linux) | T1059.001, T1059.005, T1059.007, T1574 | INSPIRED |
| 0.lateral_test | 4 VMs (Linux) | T1078.001 | INSPIRED |
| 0.pikabot_realistic | 3 VMs (Linux) | T1566.001, T1566.002 | ADAPTED/INSPIRED |

**Recommendation**: For a complete ACM CCS artifact, consider adding:
- Single Windows VM for at least one FAITHFUL Windows technique execution
- Comparison between INSPIRED (Linux simulation) vs FAITHFUL (Windows real)
- Discussion of how fidelity classification affects results interpretation

---

*Document generated: 2026-03-14*
*STICKS Framework v1.0*
*ACM CCS Artifact Validation*
