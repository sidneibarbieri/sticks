# CVE Resolution Candidates

This report is a deterministic downstream artifact extension. It does not
infer exploits, rebuild vendor products automatically, or change the core
paper claim about the current ATT&CK corpus.

## Summary

- CVE-positive campaigns: `5`
- Campaign/CVE pairs: `8`
- Automatically supported candidate pairs: `1`
- Campaigns with any automatic candidate: `1`
- Direct ATT&CK target-product bindings: `0`
- Curated CVE-only bindings: `1`
- Appliance or enterprise-server pairs: `7`
- Open-package pairs (`apt/pip`-style scope): `1`
- Open-package campaigns (`apt/pip`-style scope): `1`

## Interpretation

The practical reading is conservative: campaign-linked CVEs are measurable,
but ATT&CK software links usually name attacker tooling instead of the
vulnerable target product. In the current public artifact, only one
campaign/CVE pair resolves to an automatically supported open-package
candidate: `ShadowRay / CVE-2023-48022 -> pip:ray`.

## Scope Reduction Readout

If the downstream system is intentionally narrowed to installable open-package ecosystems such as `pip` or `apt`, the automation problem becomes much simpler, but the current ATT&CK-linked campaign/CVE coverage also collapses.

- Open-package scope covers `1/8` campaign/CVE pairs in the current corpus slice.
- Open-package scope covers `1/5` CVE-positive campaigns in the current corpus slice.
This makes the package-ecosystem direction a strong next-step simplifier, but not a faithful replacement for the broader SUT measurement problem addressed by the current paper.

## Pair-Level Resolution

| Campaign | CVE | Kind | Auto | Ecosystem | Package | ATT&CK Binding | Linked ATT&CK Software | Overlay |
|---|---|---|---|---|---|---|---|---|
| Versa Director Zero Day Exploitation | CVE-2024-39717 | appliance | no | -- | -- | no_attck_software_link | -- | -- |
| APT28 Nearest Neighbor Campaign | CVE-2022-38028 | windows_component | no | -- | -- | no_attck_software_link | -- | -- |
| ShadowRay | CVE-2023-48022 | open_package | yes | pip | ray | cve_only_curated_binding | -- | ray_jobs_api_exposure |
| Operation MidnightEclipse | CVE-2024-3400 | appliance | no | -- | -- | no_attck_software_link | -- | -- |
| SharePoint ToolShell Exploitation | CVE-2025-49704 | enterprise_server | no | -- | -- | no_attck_software_link | -- | -- |
| SharePoint ToolShell Exploitation | CVE-2025-49706 | enterprise_server | no | -- | -- | no_attck_software_link | -- | -- |
| SharePoint ToolShell Exploitation | CVE-2025-53770 | enterprise_server | no | -- | -- | no_attck_software_link | -- | -- |
| SharePoint ToolShell Exploitation | CVE-2025-53771 | enterprise_server | no | -- | -- | no_attck_software_link | -- | -- |

## Source Paths

- `campaign_cves`: `measurement/sut/scripts/results/audit/campaign_cves.csv`
- `campaign_factual_structure`: `measurement/sut/scripts/results/audit/campaign_factual_structure.csv`
- `attack_bundle`: `measurement/sut/scripts/data/enterprise-attack.json`
- `rules`: `data/cve_resolution_rules.yml`

