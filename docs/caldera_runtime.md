# CALDERA guest runtime

The Python runtime has two inputs under `lab/vagrant/shared/`:
`caldera-runtime-requirements.in` declares direct requirements, and
`caldera-runtime-requirements.txt` locks the complete active dependency closure
with exact versions and SHA-256 distribution hashes. Provisioning uses pip's
`--require-hashes`, then checks installed versions and active transitive
requirements before building Magma or starting CALDERA. A missing package,
version mismatch, unsupported dependency form, or unreachable lock entry fails
provisioning.

The guest retains its inputs and verification record in
`/opt/caldera/.sticks-runtime/`. The closure verifier checks distribution metadata;
it does not attest every installed file. Package download hashes and prepared-image
hashes are separate integrity boundaries.

## Updating dependencies

Change the direct requirements deliberately, resolve the transitive closure for
the supported guest Python and architecture, and review every version change.
Keep hashes for each selected distribution. Run the runtime-lock tests and the
full suite. Rebuild CALDERA from the base image, verify its services and inventory,
and package it under a new box name. Do not overwrite an already qualified box.
Use `scripts/freeze_prepared_c0045_runtime.py --help` to freeze the new inventory
and box alias into a new runtime manifest and strict execution profile. Qualify
the profile with a fresh boot, independent effect observation, and verified
teardown before promoting it.

A new profile is an engineering qualification. It does not replace a published
experimental series or its frozen results. Keep exploration, qualification, and
paper evidence separate.

## Scope

The November 2026 refresh was executed on an ARM64 Linux guest with Python 3.10.
Resolving another architecture's dependencies does not qualify that architecture
by execution. The Python lock does not freeze APT repositories, npm build
infrastructure, Python source-distribution build dependencies, or the host.
Prepared-image and provisioning fingerprints bind the qualified runtime more
narrowly. A locally installed prepared box is not evidence that its archive is
publicly distributed; another host must obtain or build and qualify its own
matching image.
