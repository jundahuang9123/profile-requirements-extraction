import pandas as pd
import matplotlib.pyplot as plt
import glob
import os
import re
import logging
import json
from pandas.api.types import CategoricalDtype
logger = logging.getLogger(__name__)
standard_root_dir = r""

def generate_plots_from_root_dir(root_dir=standard_root_dir):
    # === CONFIG ===
    plot_dir = os.path.join(root_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)

    # === Search for all CSV files ===
    csv_files = glob.glob(os.path.join(root_dir, "**", "*_mapping_results.csv"), recursive=True)

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found under: {root_dir}")

    all_data = []

    # === Load all files ===
    for file in csv_files:
        sid = os.path.basename(os.path.dirname(file))

        # Try comma, otherwise tab
        try:
            df = pd.read_csv(file, sep=",")
        except Exception:
            df = pd.read_csv(file, sep="\t")


        df["sample"] = sid
        all_data.append(df)

    # === Combine ===
    data = pd.concat(all_data, ignore_index=True)

    # === Clean percentage values (incl. fail_%) ===
    pct_columns = ["hits@1_pct", "hits@3_pct", "hits@5_pct", "hits@10_pct", "fail_%"]
    for col in pct_columns:
        if col in data.columns:
            data[col] = (
                data[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.strip()
            )
            data[col] = pd.to_numeric(data[col], errors="coerce")
            data.loc[data[col] > 100, col] = data[col] / 1000

    # === Sort numeric sample IDs ===
    data["sample"] = data["sample"].astype(int)
    data = data.sort_values("sample")

    # === Preserve original model order ===
    unique_models = data["Mappings_From"].drop_duplicates().tolist()
    model_order = CategoricalDtype(categories=unique_models, ordered=True)
    data["Mappings_From"] = data["Mappings_From"].astype(model_order)

    # === Compute model averages ===
    avg_cols = ["hits@1_pct", "hits@3_pct", "hits@5_pct", "hits@10_pct", "fail_%"]
    avg_data = (
        data.groupby("Mappings_From", observed=True)[avg_cols]
        .mean()
        .reset_index()
    )

    # === Round to 4 decimals ===
    for col in avg_cols:
        if col in avg_data.columns:
            avg_data[col] = avg_data[col].round(4)

    # === Save table ===
    avg_csv_path = os.path.join(plot_dir, "model_averages.csv")
    avg_data.rename(columns={"Mappings_From": "from"}, inplace=True)
    avg_data.to_csv(avg_csv_path, index=False)

    # === Split GPT vs. Non-GPT ===
    gpt_mask = data["Mappings_From"].str.contains(r"(?i)gpt", na=False)
    gpt_data = data[gpt_mask]
    non_gpt_data = data[~gpt_mask]

    # === Plot helper ===
    def plot_subset(subset, label):
        if subset.empty:
            return

        subdir = os.path.join(plot_dir, label)
        os.makedirs(subdir, exist_ok=True)

        # Standard hits@k plots
        for hits_col in ["hits@1_pct", "hits@3_pct", "hits@5_pct", "hits@10_pct"]:
            if hits_col not in subset.columns:
                continue

            plt.figure(figsize=(9, 5))
            for model in unique_models:
                if model not in subset["Mappings_From"].values:
                    continue
                group = subset[subset["Mappings_From"] == model]
                plt.plot(group["sample"], group[hits_col], marker="o", label=model)

            plt.title(f"{hits_col} across Samples – {label}")
            plt.xlabel("Sample ID")
            plt.ylabel(f"{hits_col} (%)")
            plt.legend(title="Model")
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.tight_layout()

            img_path = os.path.join(subdir, f"{hits_col}_plot.png")
            plt.savefig(img_path, dpi=300)
            plt.close()

        # Fail rate plot
        if "fail_%" in subset.columns:
            plt.figure(figsize=(9, 5))
            for model in unique_models:
                if model not in subset["Mappings_From"].values:
                    continue
                group = subset[subset["Mappings_From"] == model]
                plt.plot(group["sample"], group["fail_%"], marker="o", label=model)

            plt.title(f"Fail Rate (%) across Samples – {label}")
            plt.xlabel("Sample ID")
            plt.ylabel("Fail Rate (%)")
            plt.legend(title="Model")
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.tight_layout()

            img_path = os.path.join(subdir, "fail_rate_plot.png")
            plt.savefig(img_path, dpi=300)
            plt.close()

    # === GPT Models ===
    plot_subset(gpt_data, "GPT_models")

    # === Non-GPT Models ===
    plot_subset(non_gpt_data, "NonGPT_models")


def analyze_gpt_mapping_diversity(root_dir=standard_root_dir):
    """
    GPT-only analysis:
    - Avg Number of  mapping candidates per Attribute
    - Avg Number of  unique subjects
    - Avg Number of  unique relations
    Creates histograms per GPT model.
    """
    plot_dir = os.path.join(root_dir, "plots", "GPT_models")
    os.makedirs(plot_dir, exist_ok=True)

    json_files = glob.glob(os.path.join(root_dir, "**", "*_mapping_results.json"), recursive=True)
    if not json_files:
        raise FileNotFoundError(f"No mapping_results.json files under {root_dir}")

    all_records = []
    ttl_pattern = re.compile(r"(vcslam:[A-Za-z0-9_]+)\s+(vcslam:[A-Za-z0-9_]+)")


    for file_path in json_files:
        sid = os.path.basename(os.path.dirname(file_path))
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        models = data.get("evaluated_models", {})
        for model_name, model_data in models.items():
            if not re.search(r"(?i)gpt", model_name):
                continue

            mappings = model_data.get("mappings_candidates", {})
            if not isinstance(mappings, dict) or not mappings:
                continue

            for Attribute, candidates in mappings.items():
                if not isinstance(candidates, list) or len(candidates) == 0:
                    continue

                subjects = set()
                relations = set()
                for cand in candidates:
                    cand_text = cand.get("candidate", "")
                    m = ttl_pattern.search(cand_text)
                    if m:
                        subjects.add(m.group(1))
                        relations.add(m.group(2))

                all_records.append({
                    "sample": int(sid),
                    "model": model_name,
                    "Attribute": Attribute,
                    "Number of candidates": len(candidates),
                    "Number of subjects": len(subjects),
                    "Number of relations": len(relations)
                })

    df = pd.DataFrame(all_records)
    if df.empty:
        return

    # === Averages per SID & model ===
    avg_df = (
        df.groupby(["sample", "model"], observed=True)[["Number of candidates", "Number of subjects", "Number of relations"]]
        .mean()
        .reset_index()
    )

    # === Plot helper ===
    def plot_metric(metric_col, ylabel, title, fname):
        plt.figure(figsize=(10, 6))
        for model in avg_df["model"].unique():
            subset = avg_df[avg_df["model"] == model]
            plt.plot(subset["sample"], subset[metric_col], marker="o", label=model)
        plt.xlabel("Sample ID")
        plt.ylabel(ylabel)
        plt.title(title)
        plt.legend()
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.tight_layout()
        plt.savefig(os.path.join(plot_dir, fname), dpi=300)
        plt.close()

    # === GPT Diversity Plots ===
    plot_metric("Number of candidates",
                "Average Number of  candidates per Attribute",
                "GPT: Average Number of  Mapping Candidates per Attribute",
                "gpt_avg_candidates_per_Attribute.png")

    plot_metric("Number of subjects",
                "Average Number of  unique subjects",
                "GPT: Average Number of  Unique Subjects per Attribute",
                "gpt_avg_subjects_per_Attribute.png")

    plot_metric("Number of relations",
                "Average Number of  unique relations",
                "GPT: Average Number of  Unique Relations per Attribute",
                "gpt_avg_relations_per_Attribute.png")

    # === Histograms ===
    hist_dir = os.path.join(plot_dir, "histograms")
    os.makedirs(hist_dir, exist_ok=True)

    def plot_histograms(metric_col, title_prefix, fname_prefix):
        for model in df["model"].unique():
            subset = df[df["model"] == model]
            values = subset[metric_col].dropna().astype(int)

            if values.empty:
                continue

            bins = range(values.min(), values.max() + 2)

            plt.figure(figsize=(8, 5))
            counts, bins, patches = plt.hist(
                values,
                bins=bins,
                color="cornflowerblue",
                edgecolor="black",
                alpha=0.8,
                align="left",
                rwidth=0.85,
            )

            mean_val = values.mean()
            plt.axvline(mean_val, color="red", linestyle="--", linewidth=1.5,
                        label=f"Mean = {mean_val:.2f}")

            plt.title(f"{title_prefix} – {model}")
            plt.xlabel(metric_col.replace("_", " ").capitalize())
            plt.ylabel("Number of Attributes")
            plt.xticks(range(values.min(), values.max() + 1))
            plt.legend()
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.tight_layout()

            fname = f"{fname_prefix}_{model.replace('/', '_').replace(':', '_')}.png"
            plt.savefig(os.path.join(hist_dir, fname), dpi=300)
            plt.close()

    plot_histograms("Number of candidates",
                    "Distribution of Candidates per Attribute ",
                    "hist_candidates")

    plot_histograms("Number of subjects",
                    "Distribution of Unique Subjects per Attribute ",
                    "hist_subjects")

    plot_histograms("Number of relations",
                    "Distribution of Unique Relations per Attribute ",
                    "hist_relations")

    # === Summary table ===
    avg_summary = (
        avg_df.groupby("model")[["Number of candidates", "Number of subjects", "Number of relations"]]
        .mean()
        .round(4)
        .reset_index()
    )

    overall = avg_summary[["Number of candidates", "Number of subjects", "Number of relations"]].mean().to_dict()
    overall_df = pd.DataFrame([overall])
    overall_df.insert(0, "model", "Overall_Average")

    final_df = pd.concat([avg_summary, overall_df], ignore_index=True)

    csv_path = os.path.join(plot_dir, "gpt_mapping_diversity_averages.csv")
    final_df.to_csv(csv_path, index=False)


def run(root_dir):
    global standard_root_dir
    standard_root_dir = root_dir
    generate_plots_from_root_dir(root_dir=root_dir)
    analyze_gpt_mapping_diversity(root_dir=root_dir)
    logger.info("Finished global analysis")

def main():
    generate_plots_from_root_dir()
    analyze_gpt_mapping_diversity()

if __name__ == "__main__":
    main()