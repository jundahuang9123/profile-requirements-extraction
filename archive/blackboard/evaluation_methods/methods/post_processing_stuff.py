import os
import json
import glob
import pandas as pd
import matplotlib.pyplot as plt
import logging
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
PREFIX_STR = (
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    "@prefix vcslam: <http://www.vcslam.tmdt.info/schema#> ."
)


# ----------------------------------------
# Extract candidates
# ----------------------------------------

def extract_candidate_before_reasoning(attr_data):
    fm = attr_data.get("state", {}).get("final_mapping")
    if not fm:
        return None

    meta = fm.get("meta")
    if isinstance(meta, dict) and "candidate" in meta:
        return meta["candidate"]

    return fm.get("candidate")


def extract_candidate_after_reasoning(attr_data):
    fm = attr_data.get("state", {}).get("final_mapping")
    if not fm:
        return None

    return fm.get("candidate")


# ----------------------------------------
# Build mappings json for evaluation
# ----------------------------------------

def build_mappings_to_eval(attributes, mode):
    result = {
        "prefix": PREFIX_STR,
        "mappings_candidates": {}
    }

    for attr_name, attr_data in attributes.items():

        if mode == "before":
            cand = extract_candidate_before_reasoning(attr_data)
        else:
            cand = extract_candidate_after_reasoning(attr_data)

        if not cand:
            result["mappings_candidates"][attr_name] = []
        else:
            result["mappings_candidates"][attr_name] = [{
                "candidate": cand,
                "score": 1
            }]

    return result


# ----------------------------------------
# Compute percentages
# ----------------------------------------

def compute_percentages(stats: dict) -> dict:
    total = stats.get("hits@1", 0) + stats.get("not_hits@1", 0) + stats.get("no_mappings_provided", 0)

    if total == 0:
        return {
            **stats,
            "hits@1_percent": 0.0,
            "not_hits@1_percent": 0.0,
            "no_mappings_provided_percent": 0.0
        }

    stats["hits@1_percent"] = round((stats["hits@1"] / total) * 100, 2)
    stats["not_hits@1_percent"] = round((stats["not_hits@1"] / total) * 100, 2)
    stats["no_mappings_provided_percent"] = round((stats["no_mappings_provided"] / total) * 100, 2)

    return stats


# ----------------------------------------
# Process single SID folder
# ----------------------------------------

def process_sid_folder(folder_path: str):
    sid = os.path.basename(folder_path)
    file_path = os.path.join(folder_path, f"{sid}_mapping_results.json")

    if not os.path.exists(file_path):
        logger.info(f"Skipping {folder_path} → no mapping_results.json found")
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    attributes = data.get("attributes", {})
    eval_data = data.get("evaluation", {})

    before = compute_percentages(eval_data.get("before_reasoning", {}))
    after = compute_percentages(eval_data.get("after_reasoning", {}))

    before_map = build_mappings_to_eval(attributes, "before")
    after_map = build_mappings_to_eval(attributes, "after")

    new_json = {
        "before_reasoning": {
            "hits@k_eval": before,
            "mappings_to_eval": before_map
        },
        "after_reasoning": {
            "hits@k_eval": after,
            "mappings_to_eval": after_map
        }
    }

    out_path = os.path.join(folder_path, "evaluations.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(new_json, f, indent=4)

    return new_json


# ----------------------------------------
# Generate plots
# ----------------------------------------

def generate_plots(global_results: dict, root_folder: str):
    plot_dir = os.path.join(root_folder, "plots")
    os.makedirs(plot_dir, exist_ok=True)

    df_rows = []
    for sid, result in global_results.items():
        before = result["before_reasoning"]["hits@k_eval"]
        after = result["after_reasoning"]["hits@k_eval"]

        df_rows.append({
            "sid": int(sid),
            "hits_before": before["hits@1_percent"],
            "hits_after": after["hits@1_percent"],
            "not_before": before["not_hits@1_percent"],
            "not_after": after["not_hits@1_percent"],
            "missing_before": before["no_mappings_provided_percent"],
            "missing_after": after["no_mappings_provided_percent"],
        })

    df = pd.DataFrame(df_rows).sort_values("sid")

    df.to_csv(os.path.join(plot_dir, "global_results.csv"), index=False)

    # ----- GLOBAL AVERAGES -----
    avg = df.mean(numeric_only=True).round(2)
    avg_df = pd.DataFrame({"metric": avg.index, "percentage": avg.values})
    avg_df.to_csv(os.path.join(plot_dir, "global_averages.csv"), index=False)

    # ----- Plot Helper -----
    def single_plot(col, title, filename):
        plt.figure(figsize=(8, 5))
        plt.plot(df["sid"], df[col], marker="o")
        plt.title(title)
        plt.xlabel("Sample ID")
        plt.ylabel("Percentage (%)")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.savefig(os.path.join(plot_dir, filename), dpi=300)
        plt.close()

    def overlay(col_before, col_after, title, filename):
        plt.figure(figsize=(10, 5))
        plt.plot(df["sid"], df[col_before], marker="o", label="Before")
        plt.plot(df["sid"], df[col_after], marker="o", label="After")
        plt.title(title)
        plt.xlabel("Sample ID")
        plt.ylabel("Percentage (%)")
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend()
        plt.savefig(os.path.join(plot_dir, filename), dpi=300)
        plt.close()

    # ----- SINGLE PLOTS -----
    single_plot("hits_before", "Hits@1 Before Reasoning", "hits_before.png")
    single_plot("hits_after", "Hits@1 After Reasoning", "hits_after.png")

    single_plot("not_before", "Not Hits@1 Before Reasoning", "not_before.png")
    single_plot("not_after", "Not Hits@1 After Reasoning", "not_after.png")

    single_plot("missing_before", "Missing Before Reasoning", "missing_before.png")
    single_plot("missing_after", "Missing After Reasoning", "missing_after.png")

    # ----- OVERLAYS -----
    overlay("hits_before", "hits_after", "Hits@1 - Before vs After", "hits_overlay.png")
    overlay("not_before", "not_after", "Not Hits@1 - Before vs After", "not_overlay.png")
    overlay("missing_before", "missing_after", "Missing - Before vs After", "missing_overlay.png")


# ----------------------------------------
# Main Runner
# ----------------------------------------

def run(root_folder: str):
    sid_folders = [f for f in glob.glob(os.path.join(root_folder, "*")) if os.path.isdir(f)]
    global_results = {}

    for folder in sid_folders:
        sid = os.path.basename(folder)
        res = process_sid_folder(folder)
        if res:
            global_results[sid] = res

    generate_plots(global_results, root_folder)
    logger.info("\nDONE — evaluations.json + plots + global averages created.")


