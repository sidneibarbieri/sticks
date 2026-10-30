# Third-party material

The project `LICENSE` covers STICKS-authored material. It does not replace the
terms attached to the pinned third-party inputs below.

## MITRE ATT&CK STIX data

`data/stix/enterprise-attack.json` is Enterprise ATT&CK v19.2 from
[`mitre-attack/attack-stix-data`](https://github.com/mitre-attack/attack-stix-data).
The pinned source URL and version are recorded in
`data/stix/enterprise-attack.metadata.json`. Additional Enterprise, Mobile, and
ICS ATT&CK snapshots are under `measurement/sut/scripts/data/`, together with
an older Enterprise 10.1 snapshot. The upstream ATT&CK license text follows:

License
-------
The MITRE Corporation (MITRE) hereby grants you a non-exclusive, royalty-free license to use ATT&CK® for research,
development, and commercial purposes. Any copy you make for such purposes is authorized provided that you reproduce
MITRE's copyright designation and this license in any such copy.

"© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation."

Disclaimers
-----------
MITRE does not claim ATT&CK enumerates all possibilities for the types of actions and behaviors documented as part
of its adversary model and framework of techniques. Using the information contained within ATT&CK to address or cover
full categories of techniques will not guarantee full defensive coverage as there may be undisclosed techniques or
variations on existing techniques not documented by ATT&CK.

ALL DOCUMENTS AND THE INFORMATION CONTAINED THEREIN ARE PROVIDED ON AN "AS IS" BASIS AND THE CONTRIBUTOR, THE
ORGANIZATION HE/SHE REPRESENTS OR IS SPONSORED BY (IF ANY), THE MITRE CORPORATION, ITS BOARD OF TRUSTEES, OFFICERS,
AGENTS, AND EMPLOYEES, DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTY THAT
THE USE OF THE INFORMATION THEREIN WILL NOT INFRINGE ANY RIGHTS OR ANY IMPLIED WARRANTIES OF MERCHANTABILITY OR
FITNESS FOR A PARTICULAR PURPOSE.

## Atomic Red Team external procedure example

`examples/atomic_hostname/T1082.yaml` is retained from
[`redcanaryco/atomic-red-team`](https://github.com/redcanaryco/atomic-red-team)
at revision `59ea87397c5faf8cad1e6ebe36fd625d0063e894`. The example selects only
Hostname Discovery, GUID `486e88ea-4f56-470f-9b57-3f4d73f39133`.
Copyright (c) 2018 Red Canary, Inc. The complete upstream MIT license is retained
at `examples/atomic_hostname/LICENSE.upstream.txt`. Source digests and authored
laboratory adaptations are declared in that example's `manifest.json` and README.

## MITRE CAPEC

`measurement/sut/scripts/data/stix-capec.json` is CAPEC STIX data from
[`mitre/cti`](https://github.com/mitre/cti). The upstream repository carries
a separate CAPEC license and copyright designation. Its complete `LICENSE.txt`
is included at `THIRD_PARTY_LICENSES/MITRE_CTI_LICENSE.txt`.

## Attack Flow example

`data/interop/equifax-breach.afb` is the published
[`Equifax Breach.afb`](https://github.com/center-for-threat-informed-defense/attack-flow/blob/main/corpus/Equifax%20Breach.afb)
from the MITRE Center for Threat-Informed Defense. Its repository specifies
Apache License 2.0. The upstream license is included at
`THIRD_PARTY_LICENSES/ATTACK_FLOW_APACHE-2.0.txt`. Preserve the source file's
authorship and reference metadata when redistributing it.
