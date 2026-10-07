# Shared ontology context

SAST maps each dataset's fields to classes and datatype properties in a supplied ontology. The ontology is the stable reference; dataset values, documentation, column names and agent tasks change between requests. A run may use one ontology, a bundle of local Turtle ontologies, or a different bundle for selected samples.

## Request layout

`context_mode="shared"` places the complete ontology in an identical first system message for **candidate generation and documentation checks only**. Sample ID, column ID, stage, instructions and examples follow that message. These two stages refer to the shared message instead of inserting another copy of the ontology. History, example values, name proximity and final selection retain their original compact task inputs, followed by the same independent-request boundary used elsewhere. The full ontology is not added to these signals.

The identical prefix makes server-side reuse possible, but does not guarantee it. This is not a cache of generated answers. Every agent still makes its own inference request. All requests remain stateless, and results remain separated by sample and field. Reference answers for the current sample are not put into its prompt. The existing rule excluding the current sample from historical references remains in effect.

Council planning and discussions also keep their original compact prompts: a full ontology plus a large reasoning matrix can exceed the remaining context window. Council-triggered candidate regeneration uses the generation stage and receives the full ontology. Compact signals and councils can interrupt server cache reuse; measure those boundaries rather than assume the ontology survives between requests or samples.

`context_mode="legacy"` is the default for existing callers and keeps their original prompt layout. Shared mode changes message order and namespace validation, so identical mapping quality or paper results are not claimed. Candidate counts, signal sequence, selection, council turn bounds, and evaluation stay in place.

### Controlled correction for local Qwen

Prompt version `sast-shared-ontology-v2-compact-signals` corrects the first proposal's extra ontology inputs. In the 7 October 2026 comparison using the same Qwen3.5 27B model digest, sample 0001 sent 28 ontology-containing requests instead of the baseline's 14. All 28 reported zero cached tokens. Native Ollama logs show that recurrent-state checkpoints were unavailable before the point where the next request changed, forcing the full input to be processed again. Native prompt evaluation increased from 6,704 to 14,630 seconds; output generation stayed near 915–919 seconds. Ollama also changed versions, so the runs are not an isolated runtime-version experiment.

The correction changes only the stages receiving the full ontology and the prompt-version label recording that layout. It keeps the model, context size, thinking setting, output limit, provider adapter, namespace validation, candidate counts, agent order and council unchanged. It removes demonstrated extra input work without depending on cache reuse. It does not repair the model server's checkpoint behavior or establish a measured speedup. No model warmup, extra inference, retry or hosted fallback is introduced. Use a controlled runtime comparison before claiming performance or submitting the proposal upstream.

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

Each sample export gains an additive `llm_context` section with mode, prompt version, ontology content SHA-256/source manifests and per-request timing/usage metadata. The existing attribute, matrix, discussion and evaluation fields remain. `ontology_prefix_attached` is true for shared-mode generation/documentation and false for compact signals, selection and councils. `cached_tokens=null` means the provider did not expose that metric; it does not prove a cache miss. The request records exclude prompt text, response text, provider keys and exception bodies. A failed request is logged in process metadata and propagated without a new session-level retry.

Cache availability, context capacity, eviction, parallel clients and model-server configuration determine whether this layout helps. It does not reduce the ontology token count in the wire request or guarantee resident KV memory. Check the local server's prompt-evaluation timings and cached-prefix counts, where available, as well as wall time and exact reference agreement for matched samples.

Before the first proposal, a seven-hour local Qwen3.5 27B Q4_K_M run completed samples 0001 and 0002 in 7,806.44 and 5,526.48 seconds. Total native prompt evaluation took 6,704.11 and 4,552.24 seconds respectively. These timings include other prompt text and are not ontology-only measurements or predicted savings. The third sample was cut off; this is a small throughput observation, not a full benchmark or reproduction of the paper. Performance of the corrected compact-signal layout awaits a controlled local run.

Background: [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) describes identical reusable prefixes; [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) describes the compatible client boundary. Provider-specific cache controls are deliberately not sent by this provider-neutral code.

## Offline verification

```sh
python -m pip install -r requirements-context-tests.txt
python -m unittest discover -s tests -v
```

Tests use mocked responses only. They exercise real generation, validation, signal selection and two-turn councils in legacy/shared modes, output evaluation, sample isolation, distinct sample bundles, malformed/unknown namespace rejection, conflicting prefixes, stable multi-file serialization, blank-node scoping, and missing cache telemetry. No model inference is required. Offline tests establish execution/contract behavior; only a live controlled run can establish a speed or quality change.
