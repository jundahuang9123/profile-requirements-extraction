# Anonymous review copies of this repository

How to give ESWC 2027 Research Track reviewers access to this repository
without identifying its authors, and what `scripts/anonymization/` does. Nothing
here changes `main`; the tooling produces a separate copy for review.

## 1. What ESWC 2027 requires

The [Research Track call](https://2027.eswc-conferences.org/calls/papers-research-track/)
is dual-anonymous and says, verbatim:

- "Submissions in the research track are dual anonymous, and should not identify
  the authors." "Submissions will be rejected if not properly anonymized."
- Supplementary material: "Use anonymous links (e.g., by Dropbox or similar
  services) or pseudo-anonymous Github repositories", with
  [Anonymous Github](https://anonymous.4open.science/) and
  [Daniel Graziotin's article](https://ineed.coffee/post/how-to-disclose-data-for-double-blind-review-and-make-it-archived-open-data-upon-acceptance)
  (Zenodo/figshare workflow) as the linked examples. "All resources must be
  provided anonymously." "Reviewers will not actively try to identify the authors."
- Anonymity period: a submission "will not be considered anonymized if the
  authors post (or update) a non-anonymized preprint version" from one month
  before the deadline until notification or withdrawal. For 2027 that is
  **17 November 2026 to 19 February 2027**.
- A **Supplemental Material Statement** ends every paper: all resources needed
  to reproduce or verify the results, "indicating their persistent identifiers
  (e.g., DOI)", with a justification for anything that cannot be shared.
  Reviewers assess it; "Reproducibility and availability of resources" is a
  review criterion, and "Evaluations should be repeatable, and papers should
  provide links to the data sets, source code". The call points to ISWC's
  [Supplemental Material Statement Guide](https://iswc2025.semanticweb.org/#/guidelines/supplemental)
  (same text as the readable [2024 copy](https://iswc.umbc.edu/authors/supplemental-material-statement-guide/)),
  whose anonymous options are an EasyChair upload (up to 100 MB), "anonymous
  GitHub accounts", or Figshare/Zenodo records with author details suppressed;
  its examples list the creator as "Anonymous Authors".
- A Generative AI statement is required (use of generative AI "must be fully
  disclosed in the Work"). This repository was developed with AI assistance, so
  the paper needs one; it does not affect anonymity.

ESWC publishes no anonymization how-to of its own. The research-track call
delegates to the three linked resources above; the only ESWC-hosted guide is
the HTML submission guide. The
[Resources Track](https://2027.eswc-conferences.org/calls/papers-resource-track/)
is single-anonymous and asks for a persistent URI (PURL, DOI or w3id), a
licence, public availability and findability. The
[In-Use Track](https://2027.eswc-conferences.org/calls/papers-in-use-track/) is
single-anonymous too, "should not be anonymized", and recommends access to code
and data during review "at a permanent location".

| Date (23:59 AoE) | Research, Resources, In-Use |
|---|---|
| 17 November 2026 | anonymity period starts |
| 10 December 2026 | abstract |
| 17 December 2026 | full paper |
| 26 to 29 January 2027 | rebuttal |
| 19 February 2027 | notification (anonymity period ends) |
| 18 March 2027 | camera-ready |
| 23 to 27 May 2027 | conference, Limassol |

Source: [important dates](https://2027.eswc-conferences.org/important-dates/).

## 2. What identifies the authors in this repository

`python3 scripts/anonymization/anonymize.py check --history` reports it; as of
8 November 2026:

- The first author's name in 29 files: dated decision notes in docs, code and
  test docstrings ("Junda, 23 Oct"), the `author` field of
  `benchmark-data/mobilitydcat/use-cases.json`, the `reviewer` of the reviewed
  DCAT-AP 2.0.1 base catalogue (whose `catalogue_hash` covers that field), and
  one test assertion.
- The GitHub account name in 5 files, as links to the sibling repositories
  `visual-profile-editor` and `rq1-blackboard`, and three 40-hex commit
  identifiers of those repositories and of the colleague's upstream repository.
  GitHub's commit search resolves a public repository's commit to its owner, so
  the identifiers are on the replace list too.
- A colleague's first name and his repository URL in README,
  THIRD_PARTY_NOTICES, four docs and the frontend header.
- Git history: 181 commits, 65 of them with the first author's name and a
  personal or an institutional e-mail address, 117 authored by the AI assistant,
  116 messages with session links or trailers and 48 that name someone. A proxy
  hides history, but any repository you push does not, so a review copy needs a
  fresh history.
- The repository is public and indexed, and its GitHub description names the
  colleague. Searching a distinctive phrase from the paper finds it. Make it
  and the sibling repositories `visual-profile-editor` and `rq1-blackboard`
  private for the anonymity period (Settings, General, Danger Zone, Change
  visibility), or accept the risk given that reviewers will not actively search.
- Third-party corpora contain other people's data (W3C editors' e-mail
  addresses and names). That is not the authors' identity; those paths are
  protected and never rewritten.

Judgement calls, listed under `[flag]` in `terms.txt` and only reported:
the `vcslam.tmdt.info` namespace of the published VC-SLAM corpus (a hint at the
group; the URIs are data and stay), the `KI:connect` provider (a hint at a
German university; it is a feature), the upstream project names "SimpleLLM"
and "SAST Blackboard", and the repository names. Two weaker hints stay as well:
the figure PDFs under `benchmark-data/figures/` carry Central European time-zone
offsets in their creation dates, and a few inherited code comments are in German.

## 3. Where a review copy can live

| Option | What it hides | Watch out |
|---|---|---|
| **Anonymous GitHub** proxy of a repository ([source](https://github.com/tdurieux/anonymous_github)) | owner, organisation and repository name, listed terms in contents and file names; no history is shown | the source repository is unchanged, so a public one stays searchable; links expire (extendable by six months) |
| **Public repository under a new, neutral GitHub organisation** | your account name; membership is private by default ([docs](https://docs.github.com/en/account-and-profile/concepts/organization-membership)) | push only the anonymized snapshot with its fresh history; give the repository a neutral name and description |
| **Private repository in your own account**, proxied by Anonymous GitHub | everything above, and search engines | only if the public instance lists your private repositories after login (its code supports a GitHub App for that) |
| Second personal GitHub account | your account name | not allowed: "One person or legal entity may maintain no more than one free Account" ([GitHub terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)) |
| **Zenodo** record with creator "Anonymous Authors", open access | author metadata until you edit it; the DOI stays the same after the edit ([docs](https://help.zenodo.org/docs/deposit/manage-records/)) | the file is public and indexed; a zip, no browsing; Graziotin warns that restricted or embargoed access either hides the file or reveals account names during access requests, so keep it open |
| OSF project with an anonymized view-only link | contributor names | only while the project stays private; once it is public, the same URL without the token shows the contributors |
| EasyChair supplementary upload | everything, from everyone but the reviewers | ISWC's guide allows 100 MB; the snapshot zip is about 43 MB |

Recommended: a public repository under a neutral organisation, proxied by
Anonymous GitHub for the browsing link, plus a Zenodo record of the same zip for
the DOI the statement asks for. If Anonymous GitHub offers your private
repositories, a private repository in your own account replaces the organisation.

## 4. Procedure

1. Check what would leak, and extend `scripts/anonymization/terms.txt` if new
   names or links appeared:

   ```sh
   python3 scripts/anonymization/anonymize.py check --history
   ```

2. Build the anonymized copy next to the repository, with a zip for Zenodo:

   ```sh
   python3 scripts/anonymization/anonymize.py snapshot --zip
   ```

   This exports `HEAD` (tracked files only), drops `scripts/anonymization/` and
   this document, rewrites every `[replace]` term outside protected paths,
   re-pins `review_file_sha256` and `catalogue_hash` of the reviewed base
   catalogue so `load_catalogue` still accepts it, re-pins the workflow
   implementation hash that `scripts/closed_book.py`, `scripts/cb_base_labels.py`,
   their tests and two docs record (comment text in five workflow modules
   changes, so the hash changes), prepends a review notice to README.md,
   verifies that no `[replace]` term remains in text files, file names or the
   raw bytes of binary files, writes
   `../profile-requirements-extraction-anonymous` and `.zip`, and commits
   everything once as `Anonymous Authors <anonymous@example.org>`.

3. Verify the copy as a reviewer would. In the snapshot directory, with the
   project's virtual environment:

   ```sh
   python -m pytest tests -q
   python scripts/build_base_needs.py --check
   ```

   Both pass for the 8 November 2026 snapshot. Ignored paths (`.env`,
   `.rq1-workflow/`, `requirement-sets/`, `evaluation/`, exports) are not in
   the copy; add the saved runs the paper reports, anonymized, to the snapshot
   repository or to the Zenodo zip before sharing.

4. Host it. Create a GitHub organisation with a neutral name, then an empty
   public repository with a neutral name and description, and push:

   ```sh
   cd ../profile-requirements-extraction-anonymous
   git remote add origin git@github.com:<neutral-org>/<neutral-name>.git
   git push -u origin main
   ```

   Later changes to that repository must also be committed as the anonymous
   author: `git -c user.name='Anonymous Authors' -c user.email=anonymous@example.org commit`.

5. Create the proxy link. Log in at <https://anonymous.4open.science/>, add the
   repository, paste the `[replace]` and `[flag]` terms from `terms.txt` (the
   part before `=>`), set the expiration after notification, for example
   30 April 2027, and leave downloads enabled. Open the generated link in a
   private browser window and read the README, a doc and a test file as a
   reviewer would.

6. Create the DOI. Upload the zip to Zenodo with a neutral title and
   description, creator "Anonymous Authors", open access and a licence. Note
   that this repository has no LICENSE file and the inherited upstream code
   has none either (see THIRD_PARTY_NOTICES.md), so decide the licence of the
   authors' own code before publishing. After acceptance, edit the record's
   creators; the DOI does not change.

7. Write the statement at the end of the paper, before the references:

   > *Supplemental Material Statement:* Source code, benchmark corpora with
   > provenance manifests, reviewed base catalogues and evaluation scripts are
   > available anonymously at \<Anonymous GitHub link\>, archived as
   > \<Zenodo DOI\>. The saved runs behind Tables X to Y are in \<path\> of that
   > archive. Live model runs need a provider key and are not required to
   > regenerate the reported tables.

   Cite your own earlier work in the third person, do not link the public
   repository, and keep the Generative AI statement separate.

8. During the anonymity period, keep this repository and its sibling
   repositories private, post no non-anonymized preprint, and do not link the
   paper from personal pages.

9. After notification, for the camera-ready: restore attribution in
   THIRD_PARTY_NOTICES.md and README.md, replace the anonymous links with the
   public repository and the DOI, update the Zenodo creators, make the
   repository public again, and tag the submitted commit, for example
   `archive/eswc2027-submission`.

## 5. Checklist before 17 December 2026

- [ ] `anonymize.py check --history` reviewed; new names or links added to `terms.txt`
- [ ] snapshot built; tests and `build_base_needs.py --check` pass in it
- [ ] saved runs the paper reports are in the copy, anonymized
- [ ] neutral organisation and repository created; snapshot pushed
- [ ] Anonymous GitHub link created, terms pasted, expiration set, link tested privately
- [ ] Zenodo record published with "Anonymous Authors"; DOI in the statement
- [ ] this repository and its siblings set to private; no preprint posted
- [ ] Supplemental Material Statement and Generative AI statement in the paper
