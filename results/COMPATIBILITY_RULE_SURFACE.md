# Compatibility Rule Surface

This report exposes the exact reviewer-facing keyword and regex surface
behind the deterministic CF/VMR/ID compatibility rules used in the
measurement pipeline. It is an audit aid; it does not introduce new
measurements beyond the published rule-based classification.

## Fixed Rule Inputs

- Generated from: `measurement/sut/scripts/sut_measurement_pipeline.py`
- Default fallback class: `VMR`

## ID Platform Keywords

- `Azure AD`
- `Entra ID`
- `Google Workspace`
- `IaaS`
- `Identity Provider`
- `Office 365`
- `SaaS`
- `Windows Domain`

## Lateral-Movement Software Keywords

- `active directory`
- `domain`
- `kerberos`
- `ldap`

## VMR Signals

- Kernel/boot regex: `boot|firmware|kernel|driver|rootkit|bios|uefi|mbr|vbr|bootkit`
- Name-pattern regex: `process\s+inject|hook|dll\s+side|hijack|token\s+manipul|access\s+token|credential\s+dump|lsass|sam\s+database|registry|service\s+execut|scheduled\s+task|windows\s+management\s+instrument|wmi|exploitation\s+for\s+privilege`
- Privileged permissions: `Administrator, SYSTEM, root`

## CF Platforms

- Container-compatible platforms: `Containers, Linux`

