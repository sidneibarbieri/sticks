# Public Artifact Checklist

This checklist is for turning the staged review artifact into a public,
venue-neutral companion repository.

## Done in this workspace

- Minimal measurement-only artifact staged and tested
- One-command verifier passes in the staged artifact
- Generated outputs and measured values are synchronized
- Traceability and claim-to-evidence mapping are included

## Remaining manual publication steps

1. Create the public repository from the staged directory:
   - `artifacts/paper2-review-artifact/`
2. Choose and add the final repository license.
3. Update any private manuscript trees to point at the final public artifact URL.
4. Run `bash release_check.sh` once more in a fresh clone of the public repo.
5. Tag the release that corresponds to the submitted manuscript revision.
6. If desired for preservation/badging, archive the release in a long-term
   service such as Zenodo or Software Heritage.

## Scope guard

Do **not** expand the public artifact with unrelated workspace material unless it
supports a concrete reproducibility claim. In particular, keep unrelated
workspace material, optional runtime exploration, temporary outputs, and
host-local logs out of the release unless there is a clear reason to include
them.
