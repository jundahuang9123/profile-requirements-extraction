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

## Bundled official base-profile sources

Path: `requirement-reuse-service/config/base_profiles/source-inputs/`.
The six RDF/HTML files are unchanged, checksum-pinned copies used to rebuild
draft catalogues offline. Each copy retains its original notices and attribution;
copied definitions and usage notes in the catalogues derive from these files.

| Bundled file (relative to that path) | Attribution and licence |
|---|---|
| `w3c/dcat-2.html` | DCAT 2, W3C Recommendation, 4 February 2020. Copyright © 2020 W3C® (MIT, ERCIM, Keio, Beihang). [W3C Software and Document License, 2015](https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document). |
| `w3c/dcat-3.html` | DCAT 3, W3C Recommendation, 22 August 2024. Copyright © 2024 World Wide Web Consortium. [W3C Software and Document License, 2023](https://www.w3.org/copyright/software-license-2023/). |
| `releases/2.0.1/dcat-ap_2.0.1.rdf` | SEMIC / European Commission, DCAT-AP 2.0.1 release file. [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/), as declared in the RDF. |
| `releases/2.1.1/dcat-ap_2.1.1.rdf` | SEMIC / European Commission, DCAT-AP 2.1.1. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as declared in the RDF. |
| `releases/3.0.0/index.html` | SEMIC, DCAT-AP 3.0.0. Copyright © 2023 European Union in the licence declaration. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). |
| `releases/3.0.1/index.html` | SEMIC, DCAT-AP 3.0.1. Copyright © 2025 European Union in the licence declaration. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). |

W3C originals: [dated DCAT 2](https://www.w3.org/TR/2020/REC-vocab-dcat-2-20200204/)
and [dated DCAT 3](https://www.w3.org/TR/2024/REC-vocab-dcat-3-20240822/).
SEMIC copies come from [DCAT-AP commit
4470b8ea907b7eb9ec55ab22befd1ecd2210ff32](https://github.com/SEMICeu/DCAT-AP/tree/4470b8ea907b7eb9ec55ab22befd1ecd2210ff32/releases).
The 3.x HTML's licence link has an inconsistent “CC0” caption: its URL and explicit
repository licence declaration specify CC BY 4.0. The copies preserve that
original text without alteration. These licences cover the attributed source
files and copied prose; they do not relicense unrelated repository code.
