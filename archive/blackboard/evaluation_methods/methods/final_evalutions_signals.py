import os
import json
import csv
from collections import defaultdict
import matplotlib.pyplot as plt
from pathlib import Path
from datacorpus.tools.top_k_eval import evaluate_top_k
import logging
logger = logging.getLogger(__name__)

PREFIX_STR = (
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    "@prefix vcslam: <http://www.vcslam.tmdt.info/schema#> ."
)

CURRENT = Path(__file__).resolve()
METHODS_DIR = CURRENT.parent
BLACKBOARD_DIR = METHODS_DIR.parent.parent
ROOT = BLACKBOARD_DIR.parent
VC_SLAM_BASE_PATH = ROOT / "datacorpus" / "vcslam"

VC_SLAM_BASE = str(VC_SLAM_BASE_PATH)



# ---------------------------------------------------------
# POOL EXTRACTION
# ---------------------------------------------------------

POOL_TYPES = ["documentation", "historical", "example_value", "proximity"]

def extract_vote_pools(validated_candidates):
    pools = {p: [] for p in POOL_TYPES}

    for idx, cand in enumerate(validated_candidates):
        cand_str = cand["candidate"]

        if cand.get("documentation_vote", {}).get("accepted"):
            pools["documentation"].append((cand_str, idx))

        if cand.get("historical_vote", {}).get("accepted"):
            pools["historical"].append((cand_str, idx))

        if cand.get("example_value_vote", {}).get("accepted"):
            pools["example_value"].append((cand_str, idx))

        if cand.get("attribute_name_mapping_proximity_vote", {}).get("accepted"):
            pools["proximity"].append((cand_str, idx))

    return pools


def build_pool_json(pool):
    arr = []
    n = len(pool)
    for cand_str, idx in pool:
        arr.append({"candidate": cand_str, "score": n - idx})
    return arr


def build_attribute_pool_json(attribute, pool):
    return {
        "prefix": PREFIX_STR,
        "mappings_candidates": {
            attribute: build_pool_json(pool)
        }
    }


# ---------------------------------------------------------
# SAMPLE ANALYSIS
# ---------------------------------------------------------

def analyze_sample(sample_file, sid):

    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Gold model
    ref_path = os.path.join(VC_SLAM_BASE, sid, f"{sid}_mapped.json")
    with open(ref_path, "r", encoding="utf-8") as f:
        reference_model = json.load(f)

    attributes = data["attributes"]
    evaluations = data["evaluation"]

    out = {
        "pools": {},
        "discussion_changes": [],
        "discussion_conclusions": defaultdict(int),
        "discussion_meta": {
            "weak": {"amount_change": 0, "better": 0, "worse": 0, "same": 0},
            "strong": {"amount_change": 0, "better": 0, "worse": 0, "same": 0}
        }
    }


    def eval_change(attr):
        before = evaluations["before_reasoning"]["evaluations"][attr]
        after = evaluations["after_reasoning"]["evaluations"][attr]

        if before == after:
            return before, after, "same"
        elif before is False and after is True:
            return before, after, "better"
        else:
            return before, after, "worse"

    # ===============================================================
    # 1. POOLS
    # ===============================================================

    for attr, content in attributes.items():
        validated = content["state"].get("validated_candidates", [])
        pools = extract_vote_pools(validated)

        out["pools"][attr] = {}
        for pool_name, pool in pools.items():

            size = len(pool)
            if size == 0:
                hit = 0
            else:
                pool_json = build_attribute_pool_json(attr, pool)
                hit = evaluate_top_k(1, reference_model, pool_json)["hits@1"]

            out["pools"][attr][pool_name] = {
                "size": size,
                "correct": 1 if hit > 0 else 0
            }


    discussions = data.get("discussions", {})

    for did, disc in discussions.items():
        conclusion = disc["conclusion"]
        out["discussion_conclusions"][conclusion] += 1

        participants = disc.get("participants", [])

        for p in participants:
            attr = p["attribute"]
            role = p["role"]

            # only changed attributes have final_mapping_before_discussion
            if "final_mapping_before_discussion" not in attributes[attr]["state"]:
                continue

            before, after, change = eval_change(attr)

            out["discussion_changes"].append({
                "attribute": attr,
                "role": role,
                "before_eval": before,
                "after_eval": after,
                "change_type": change
            })

            out["discussion_meta"][role]["amount_change"] += 1
            out["discussion_meta"][role][change] += 1

    return out




def plot_bar(labels, values, title, path , x = "" , y = ""):
    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.title(title)
    if x:
        plt.xlabel(x)
    if y:
        plt.ylabel(y)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def save_results(all_results, out_folder):

    sids_dir = os.path.join(out_folder, "sids")
    global_dir = os.path.join(out_folder, "global")

    os.makedirs(sids_dir, exist_ok=True)
    os.makedirs(global_dir, exist_ok=True)

    # ------------------------------------------------------
    # Save per-SID files
    # ------------------------------------------------------

    for sid, res in all_results.items():

        sid_dir = os.path.join(sids_dir, sid)
        os.makedirs(sid_dir, exist_ok=True)

        with open(os.path.join(sid_dir, "pools.json"), "w") as f:
            json.dump(res["pools"], f, indent=4)

        with open(os.path.join(sid_dir, "discussion_changes.json"), "w") as f:
            json.dump(res["discussion_changes"], f, indent=4)

        with open(os.path.join(sid_dir, "discussion_conclusions.json"), "w") as f:
            json.dump(res["discussion_conclusions"], f, indent=4)

        with open(os.path.join(sid_dir, "discussion_meta.json"), "w") as f:
            json.dump(res["discussion_meta"], f, indent=4)



    pool_sizes = {p: [] for p in POOL_TYPES}
    pool_correct = {p: [] for p in POOL_TYPES}

    # new: ANY pool

    pool_correct["any"] = []

    for sid, res in all_results.items():
        for attr, pdata in res["pools"].items():

            any_correct = 0
            any_pool_size = 0

            for p in POOL_TYPES:
                size = pdata[p]["size"]
                correct = pdata[p]["correct"]

                if size > 0:
                    pool_sizes[p].append(size)
                    pool_correct[p].append(correct)
                    any_pool_size += size

                if correct:
                    any_correct = 1

            if any_pool_size > 0:
                pool_correct["any"].append(any_correct)

    global_pool_sizes = {
        p: (sum(pool_sizes[p]) / len(pool_sizes[p])) if pool_sizes[p] else 0
        for p in pool_sizes
    }

    global_pool_correct = {
        p: (sum(pool_correct[p]) / len(pool_correct[p]) * 100) if pool_correct[p] else 0
        for p in pool_correct
    }


    # Save pool summary
    with open(os.path.join(global_dir, "pool_summary.json"), "w") as f:
        json.dump({
            "avg_pool_sizes": global_pool_sizes,
            "avg_pool_correctness": global_pool_correct
        }, f, indent=4)

    # Plots
    plot_bar(
        list(global_pool_sizes.keys())[::-1],
        list(global_pool_sizes.values())[::-1],
        "Average Candidate Amount",
        os.path.join(global_dir, "pool_sizes.png") , y="Candidate Amount"
    )

    plot_bar(
        list(global_pool_correct.keys())[::-1],
        list(global_pool_correct.values())[::-1],
        "Probability Correct Candidate in Pool %",
        os.path.join(global_dir, "pool_correctness.png") , y="Probability"
    )

    # ------------------------------------------------------
    # GLOBAL DISCUSSION STATS
    # ------------------------------------------------------

    global_discussion_role = {
        "weak": {"amount_change": 0, "better": 0, "worse": 0, "same": 0},
        "strong": {"amount_change": 0, "better": 0, "worse": 0, "same": 0}
    }

    global_discussion_conclusions = {
        "Acceptance": 0,
        "Correction": 0,
        "Disagreement": 0
    }

    for sid, res in all_results.items():

        # conclusions
        conc = res["discussion_conclusions"]
        global_discussion_conclusions["Acceptance"] += conc["Acceptance"]
        global_discussion_conclusions["Correction"] += conc["Correction"]
        global_discussion_conclusions["Disagreement"] += conc["Disagreement"]

        # per role
        meta = res["discussion_meta"]
        for role in ["weak", "strong"]:
            global_discussion_role[role]["amount_change"] += meta[role]["amount_change"]
            global_discussion_role[role]["better"] += meta[role]["better"]
            global_discussion_role[role]["worse"] += meta[role]["worse"]
            global_discussion_role[role]["same"] += meta[role]["same"]


    with open(os.path.join(global_dir, "avg_discussion_meta.json"), "w") as f:
        json.dump(global_discussion_role, f, indent=4)


    total_discussions = (
        global_discussion_conclusions["Acceptance"] +
        global_discussion_conclusions["Correction"] +
        global_discussion_conclusions["Disagreement"]
    )

    dc_json = {
        "total": total_discussions,
        **global_discussion_conclusions
    }

    with open(os.path.join(global_dir, "avg_discussion_conclusions.json"), "w") as f:
        json.dump(dc_json, f, indent=4)

    with open(os.path.join(global_dir, "avg_discussion_conclusions.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["total", "acceptance", "correction", "disagreement"])
        w.writerow([
            total_discussions,
            global_discussion_conclusions["Acceptance"],
            global_discussion_conclusions["Correction"],
            global_discussion_conclusions["Disagreement"]
        ])



# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def run(root_folder):

    all_results = {}

    for sid in os.listdir(root_folder):
        sid_dir = os.path.join(root_folder, sid)
        if not os.path.isdir(sid_dir):
            continue

        sample_file = os.path.join(sid_dir, f"{sid}_mapping_results.json")
        if not os.path.exists(sample_file):
            continue

        logger.info(f"→ Analyzing {sid}")
        all_results[sid] = analyze_sample(sample_file, sid)

    out = os.path.join(root_folder, "analysis_output")
    save_results(all_results, out)

    logger.info(f"\nDONE — output saved under: {out}")

