# Source attribution

This repository starts from Sebastian's SimpleLLM & SAST Blackboard repository,
https://github.com/U0iS112/654321, at commit
`074ddfc409bdd120c93a0b68773bafa464e56504`. Its original Git history and source
folders are preserved. Its original README is reproduced in
`docs/UPSTREAM_README.md`. No license file was present at this upstream commit;
this project does not assign a new license to those inherited files.

The standalone RQ1 service, requirements UI, research role configuration,
curated role notes, and related tests were adapted from Visual Profile Editor,
https://github.com/jundahuang9123/visual-profile-editor. That source carries the
Apache License 2.0, reproduced in `docs/licenses/VPE-APACHE-2.0.txt`. The source
commit, working-tree status, selected paths, and pre-migration file hashes are
recorded in `docs/VPE_SOURCE_MANIFEST.json`. The snapshot includes uncommitted
local implementation, so its commit alone does not reproduce all imported files.

Migration changes separate RQ1 service routes and UI from the VPE editor and
RQ2 profile generation, add a standalone application shell and packaging, and
adapt tests to the RQ1 boundary. The manifest's hashes identify the source
before those adaptations. Original authorship and copyright notices are retained.
