# Shared ontology context

SAST maps each dataset's fields to classes and datatype properties in a supplied ontology. The ontology is the stable reference; dataset values, documentation, column names and agent tasks change between requests. A run may use one ontology, a bundle of local Turtle ontologies, or a different bundle for selected samples.

## Request layout

`context_mode="shared"` places the complete ontology in an identical first system message for every per-column request. Sample ID, column ID, stage, instructions and examples follow that message. Candidate generation and documentation checks refer to this shared message instead of inserting another copy of the ontology. The intervening history, example, name and selection checks use the same prefix, allowing a model server to reuse the ontology's processed context rather than replacing it with a short unrelated prompt.

This is prefix/KV reuse, not a cache of generated answers. Every agent still makes its own inference request. All requests remain stateless, and results remain separated by sample and field. Reference answers for the current sample are not put into its prompt. The existing rule excluding the current sample from historical references remains in effect.

Council planning and discussions keep their original compact prompts: a full ontology plus a large reasoning matrix can exceed the remaining context window. Council-triggered candidate regeneration returns to the shared mapping prefix. A council can therefore interrupt server cache reuse; measure that boundary rather than assume the ontology survives between samples.

`context_mode="legacy"` is the default for existing callers and keeps their original prompt layout. Shared mode changes which context some signal agents receive, message order and namespace validation, so identical mapping quality or paper results are not claimed. Candidate counts, signal sequence, selection, council turn bounds, and evaluation stay in place.

## Use from the existing pipeline

```python
from blackboard.codebase.core import blackboard_semantic_mapping as pipeline

pipeline.run_pipeline(
    vcslam_path="datacorpus/vcslam",
    sample_ids=["0001", "0002"],
    historical_ids=[],
    export_root="blackboard/exports",
    run_evaluation=False,
    context_mode="shared",
)
```

Use the existing environment/model configuration. This API does not switch providers, download a model, create a hosted fallback, warm a model, or start additional runs. The workbench's provider adapter supplies local Ollama when that connection is selected.

For multiple ontologies, add `ontology_paths=["ontologies/core.ttl", "ontologies/transport.ttl"]`. To select a different bundle for sample 0002, add `sample_ontology_paths={"0002": ["ontologies/core.ttl", "ontologies/retail.ttl"]}`. Unspecified samples use `ontology_paths`, or the existing `ontology/ontology.ttl` when it is omitted. Files are preflighted once per distinct bundle before inference. Conflicting namespace prefixes fail explicitly. `owl:imports` is not downloaded; provide imported ontologies as local files.

Multiple files are merged as RDF, keeping file-local blank nodes separate. Canonical ordering makes the merged text independent of input file order. One-file bundles retain their original text. Full IRIs distinguish identically named terms from different namespaces in shared-mode validation; the original range-check policy remains lenient. This is not ontology alignment: inconsistent definitions or ontology coverage still require review. CSV/XLSX inputs supported by the companion workbench become labelled JSON example records and use the same pipeline contract.

## Measure actual reuse

Each sample export gains an additive `llm_context` section with mode, prompt version, ontology content SHA-256/source manifests and per-request timing/usage metadata. The existing attribute, matrix, discussion and evaluation fields remain. `ontology_prefix_attached` distinguishes mapping requests from compact council requests. `cached_tokens=null` means the provider did not expose that metric; it does not prove a cache miss. The request records exclude prompt text, response text, provider keys and exception bodies. A failed request is logged in process metadata and propagated without a new session-level retry.

Cache availability, context capacity, eviction, parallel clients and model-server configuration determine whether this layout helps. It does not reduce the ontology token count in the wire request or guarantee resident KV memory. Check the local server's prompt-evaluation timings and cached-prefix counts, where available, as well as wall time and exact reference agreement for matched samples.

Before this change, a seven-hour local Qwen3.5 27B Q4_K_M run completed samples 0001 and 0002 in 7,806.44 and 5,526.48 seconds. Processing inputs in ontology-containing generation/documentation stages took 79.2% and 74.8% of those wall times. These timings include other prompt text and are not ontology-only measurements or predicted savings. The third sample was cut off; this is a small throughput observation, not a full benchmark or reproduction of the paper. Performance of the revised layout awaits a controlled local run.

Background: [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) describes identical reusable prefixes; [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) describes the compatible client boundary. Provider-specific cache controls are deliberately not sent by this provider-neutral code.

## Offline verification

```sh
python -m pip install -r requirements-context-tests.txt
python -m unittest discover -s tests -v
```

Tests use mocked responses only. They exercise real generation, validation, signal selection and two-turn councils in legacy/shared modes, output evaluation, sample isolation, distinct sample bundles, malformed/unknown namespace rejection, conflicting prefixes, stable multi-file serialization, blank-node scoping, and missing cache telemetry. No model inference is required. Offline tests establish execution/contract behavior; only a live controlled run can establish a speed or quality change.
