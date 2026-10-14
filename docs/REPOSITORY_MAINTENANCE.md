# Active development and archived branches

The default and sole active development branch is `main`.
It contains the RQ1 workflow fixes, grouped-candidate work, inherited-base
comparison and per-run DCAT/DCAT-AP version selection.

During the 13 October 2026 cleanup, obsolete branch tips were preserved under
`archive/2026-10-13/<original-branch-name>` tags before their branches were removed.
This includes merged fixes and legacy blackboard optimization branches; archiving
their history does not merge that legacy implementation into the RQ1 workflow.
Unmerged or superseded commits remain recoverable through their tags. Local
branch tips that differ from the remote are preserved under
`archive/2026-10-13/local/<original-branch-name>` as well.

Use the default branch for subsequent changes. To inspect or recover an archived
tip deliberately:

```sh
git fetch origin --tags
git tag --list 'archive/2026-10-13/*'
git switch --detach archive/2026-10-13/codex/fewer-candidates
# If further development of that snapshot is needed:
git switch -c recovery/fewer-candidates
```

Branches represent ongoing development; archive tags represent historical
snapshots. Do not delete archive tags as routine branch housekeeping. Completed
run databases, provider credentials and local outputs are not part of this Git
cleanup and remain outside the committed source history.
