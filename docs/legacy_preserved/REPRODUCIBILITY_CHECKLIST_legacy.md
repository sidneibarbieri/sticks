# Reproducibility Checklist

Historical document preserved from
`legacy/review_archive_root/REPRODUCIBILITY_CHECKLIST.md`.
It is kept as migration background only.

Key preserved lessons:

- A reviewer pipeline must run from a small set of explicit commands.
- Authentication and bootstrap bugs in orchestration scripts are reproducibility
  bugs, not minor polish issues.
- Agent/bootstrap steps that were performed manually must become explicit and
  automated before claiming reproducibility.
- Structured results must be saved in machine-readable form.
- The reviewer guide must document exact commands, not intentions.

Historical gap areas captured by the original note:

- automatic execution pipeline
- automatic agent deployment
- structured results collection
- reproducibility-focused README coverage

Those items remain useful as migration criteria, even though the specific old
scripts referenced there are no longer canonical.
