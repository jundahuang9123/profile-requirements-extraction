# Reprocessing and consolidation

Use **Re-run steps 4–7 with new settings** on a fully completed extraction to create a separate downstream trial. It copies the frozen observations, stakeholder panel, completed role reports and referenced excerpt catalogues. Acquisition through extraction remain completed. The original run and its review decisions are unchanged; the new trial has no extraction calls and inherits the original extraction policy version.

The derive endpoint requires the source's current version, completed extraction and all role reports completed; automatic/override panels must also be completed. Active workers and incomplete extraction are refused. Derived trials can resume downstream checkpoints but cannot reset extraction.

Identical content hashes reuse assessments only under `rq1-support-quality-v2.2`, with the matching revision hash. Provider-failed, old-policy and human assessments are not imported. Original-source verification always runs again. Metrics distinguish reused extraction and assessments from newly incurred calls. Human review and baseline publication remain explicit human actions.

This implementation is offline-tested only. No new live inference or consolidation-quality evaluation has been performed.
