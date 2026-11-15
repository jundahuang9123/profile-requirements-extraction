import json
import re

# ---------------- Hilfsfunktionen ----------------

def parse_prefixes(prefix_str):
    """Extrahiert Präfix-Mapping aus dem Prefix-Block in der JSON."""
    prefix_pattern = r"@prefix\s+(\w+):\s+<([^>]+)>"
    return {match[0]: match[1] for match in re.findall(prefix_pattern, prefix_str)}


def resolve_prefixes_in_string(mapping_str, prefix_map):
    """Ersetzt Präfixe (z. B. vcslam:) durch volle URIs."""
    if not mapping_str:
        return mapping_str

    def replace_prefix(match):
        prefix, local = match.groups()
        return f"<{prefix_map[prefix]}{local}>" if prefix in prefix_map else match.group(0)

    return re.sub(r'(\w+):([A-Za-z0-9_]+)', replace_prefix, mapping_str)


def normalize_mapping(mapping: str, prefix_map=None) -> str:
    """Normalisiert ein Mapping (ohne Kleinschreibung, Präfixe aufgelöst, ohne Literal)."""
    if not mapping:
        return ""

    mapping = mapping.strip().rstrip('.').replace('"', '')
    if prefix_map:
        mapping = resolve_prefixes_in_string(mapping, prefix_map)

    parts = mapping.split()
    if len(parts) < 2:
        return mapping

    subj, rel = parts[0], parts[1]
    return f"{subj} {rel}"


def sort_input_json(json_data):
    """Sortiert Kandidatenlisten nach Score (absteigend)."""
    for key, candidates in json_data["mappings_candidates"].items():
        json_data["mappings_candidates"][key] = sorted(
            candidates, key=lambda x: x["score"], reverse=True
        )
    return json_data


def evaluate_top_k(k=1, reference_model=None, to_evaluate=None):
    """Vergleicht top-k Kandidaten mit Referenzmodell."""

    to_evaluate_current = sort_input_json(to_evaluate)

    # Präfixe beider Modelle auflösen
    prefix_map_eval = parse_prefixes(to_evaluate_current["prefix"])
    prefix_map_ref = parse_prefixes(reference_model["prefix"])

    evaluations = {}
    errors = []

    ref_keys = set(reference_model["mappings"].keys())
    eval_keys = set(to_evaluate_current["mappings_candidates"].keys())

    # Fehlerhafte Keys, die nicht im Referenzmodell existieren
    unknown_keys = eval_keys - ref_keys
    if unknown_keys:
        errors.extend(sorted(unknown_keys))

    # Vergleich für alle Keys im Referenzmodell
    for key in sorted(ref_keys):
        ref_mapping_full = reference_model["mappings"][key].get("mapping", None)
        if not ref_mapping_full:
            evaluations[key] = None
            continue

        ref_norm = normalize_mapping(ref_mapping_full, prefix_map_ref)

        if (
                key not in to_evaluate_current["mappings_candidates"]
                or not to_evaluate_current["mappings_candidates"][key]
        ):
            evaluations[key] = None
            continue

        # Es gibt Vorschläge, überprüfe Top-k
        top_k_candidates = [
            normalize_mapping(c["candidate"], prefix_map_eval)
            for c in to_evaluate_current["mappings_candidates"][key][:k]
        ]

        match_found = any(ref_norm == cand for cand in top_k_candidates)
        evaluations[key] = True if match_found else False

    hits = sum(1 for v in evaluations.values() if v is True)
    not_hits = sum(1 for v in evaluations.values() if v is False)
    no_mappings = sum(1 for v in evaluations.values() if v is None)

    result = {
        f"hits@{k}": hits,
        f"not_hits@{k}": not_hits,
        "no_mappings_provided": no_mappings,
        "evaluations": evaluations,
        "errors": errors
    }

    return result


# ---------------- Beispielaufruf ----------------
def run_example():
    # ---------------- Beispiel-Input ----------------

    input_json = {
        "prefix": "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n@prefix vcslam: <http://www.vcslam.tmdt.info/schema#>.",
        "mappings_candidates": {
            "location.coordinates": [
                {"candidate": "vcslam:Fire vcslam:coordinate_pair_DP \"location.coordinates\".", "score": 3},
                {"candidate": "vcslam:Coordinates vcslam:coordinate_pair_DP \"location.coordinates\"^^xsd:string.", "score": 4},
            ],
            "tvm_identifier": [
                {"candidate": "vcslam:Ticket_vending_machine vcslam:identifier \"tvm_identifier\".", "score": 3},
                {"candidate": "vcslam:Ticket_vending_machine vcslam:id \"tvm_identifier\".", "score": 4},
            ],
            "something.random": [  # absichtlich nicht im Reference Model
                {"candidate": "vcslam:Foo vcslam:bar \"something.random\".", "score": 5}
            ]
        }
    }

    reference_model = {
        "prefix": "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n@prefix vcslam: <http://www.vcslam.tmdt.info/schema#>.",
        "mappings": {
            "pay_by_cash": {
                "key": "pay_by_cash",
                "Path": None,
                "mapping": "vcslam:Cash vcslam:is_available \"pay_by_cash\"."
            },
            "pay_by_credit_card": {
                "key": "pay_by_credit_card",
                "Path": None,
                "mapping": "vcslam:Card vcslam:is_available \"pay_by_credit_card\"."
            },
            "address": {
                "key": "address",
                "Path": None,
                "mapping": "vcslam:Location vcslam:address \"address\"."
            },
            "tvm_identifier": {
                "key": "tvm_identifier",
                "Path": None,
                "mapping": "vcslam:Ticket_vending_machine vcslam:identifier \"tvm_identifier\"."
            },
            "latitude": {
                "key": "latitude",
                "Path": None,
                "mapping": "vcslam:Coordinate_pair vcslam:latitude \"latitude\"."
            },
            "longitude": {
                "key": "longitude",
                "Path": None,
                "mapping": "vcslam:Coordinate_pair vcslam:longitude \"longitude\"."
            },
            "location.type": {
                "key": "type",
                "Path": "location",
                "mapping": "vcslam:Coordinates vcslam:geometry_type \"location.type\"."
            },
            "location.coordinates": {
                "key": "coordinates",
                "Path": "location",
                "mapping": "vcslam:Coordinates vcslam:coordinate_pair_DP \"location.coordinates\"."
            }
        }
    }

    output_json = evaluate_top_k(
        k=1, reference_model=reference_model, to_evaluate=input_json
    )

if __name__ == "__main__":
    print(json.dumps(run_example(),indent=4))