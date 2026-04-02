# STICKS ACM CCS Artifact - Definition of Done Checklist

Historical document preserved from `legacy/review_archive_root/DOD_CHECKLIST.md`.
It is kept only as reference material for reviewer expectations and prior
artifact acceptance criteria.

## Status: RELEASE CANDIDATE (Local-test validated, Vagrant execution pending)

## 1. Scope and Artifact Identity

- Single reviewer-oriented package
- Root entrypoint
- Clear primary documentation
- Separate internal organization
- No manual editing required

## 2. Main Reviewer Flow

- Environment setup
- Campaign listing
- Campaign selection
- Automatic SUT startup
- Automatic execution
- Automatic evidence collection
- Reset and destroy support

## 3. Campaign-SUT Model

- One SUT profile per campaign
- Hosts, OS, and services declared
- Deliberate weaknesses declared
- Network topology declared
- Fidelity expected per technique
- Automatic SUT selection

## 4. Infrastructure as Code

- IaC-created topology
- Automatic provisioning
- Automatic credentials, services, and network
- Reset and destroy support
- Explicit failures

## 5. Preflight and Diagnostics

- Preflight stage
- Dependency validation
- Path and file validation
- Backend validation
- Clear failures
- Early exit on missing requirements

## 6. Real Campaign Execution

The preserved document explicitly distinguished local-test validation from
untested full-lab execution. That honesty criterion remains useful.

## 7. Experimental Evidence

- One directory per execution
- Manifest
- Summary
- Per-technique evidence
- Execution logs
- Campaign metadata
- SUT metadata
- Fidelity distribution

## 8. Methodological Fidelity

- Per-technique faithful/adapted/inspired classification
- Short justifications
- Explicit platform mismatch declaration
- No hidden simulation

## 9. Sanitization and Quality

- No temporary files
- No broken paths
- Minimal package contents

## 10. Documentation

- README
- Reviewer guide
- Detailed quickstart

## 11. Integration with Paper

The preserved document treated evidence-to-paper integration as a required
closing step, which remains a useful principle.

## 12. Truthfulness Rule

The most useful part of the preserved document is its operational-truth rule:
do not claim full-lab or infrastructure validation when only local-test mode
has been validated.
