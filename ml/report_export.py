"""Collect every measured number the report needs into one flat file.

`report/build_report.py` currently holds invented placeholders wrapped in
`<<...>>`. This module produces `artifacts/report_facts.json`, a flat dict of
`key -> {value, text}` where `text` is already formatted the way the document
wants it, so filling the report is a lookup rather than a round of manual
transcription (and arithmetic nobody re-checks).

Writes no figures and touches nothing under `report/`.

Usage:
    python -m ml.report_export
"""
from __future__ import annotations

import argparse
import json

from ml import config


def fact(value, text: str) -> dict:
    return {"value": value, "text": text}


def count(value: int) -> dict:
    return fact(value, f"{value:,}")


def pct(value: float, places: int = 2) -> dict:
    return fact(value, f"{value * 100:.{places}f}%")


def num(value: float, places: int = 3) -> dict:
    return fact(value, f"{value:.{places}f}")


def date_range(start: str, end: str) -> dict:
    first, last = start[:10], end[:10]
    return fact([first, last], f"{first} to {last}")


def load(path, label: str) -> dict:
    if not path.exists():
        raise SystemExit(f"missing {label}: {path}. Run scripts/run_pipeline.py first.")
    return json.loads(path.read_text())


def build_facts() -> dict:
    generation = load(config.GENERATION_SUMMARY, "generation summary")
    dataset = load(config.DATASET_SUMMARY, "dataset summary")
    metrics = load(config.METRICS_PATH, "metrics")
    metadata = load(config.MODEL_METADATA_PATH, "model metadata")

    facts: dict[str, dict] = {}

    # --- Table 6.1: the generated dataset ---------------------------------
    facts["merchants"] = count(generation["n_merchants"])
    facts["history_range"] = fact(
        [generation["history_start"], generation["history_end"]],
        f"{generation['months']} months "
        f"({generation['history_start']} to {generation['history_end']})",
    )
    facts["seed"] = fact(generation["seed"], str(generation["seed"]))
    facts["merchant_churn_count"] = count(generation["merchant_churn_count"])
    facts["merchant_churn_rate"] = pct(generation["merchant_churn_rate"], 1)
    facts["merchant_churn_combined"] = fact(
        [generation["merchant_churn_count"], generation["merchant_churn_rate"]],
        f"{generation['merchant_churn_count']:,} merchants "
        f"({generation['merchant_churn_rate'] * 100:.1f}%)",
    )
    facts["payments_total"] = count(generation["payments_total"])
    facts["failures_total"] = count(generation["failures_total"])
    facts["failure_rate_overall"] = pct(generation["failure_rate_overall"])
    facts["failures_combined"] = fact(
        [generation["failures_total"], generation["failure_rate_overall"]],
        f"{generation['failures_total']:,} "
        f"({generation['failure_rate_overall'] * 100:.2f}% overall failure rate)",
    )
    facts["eligible_rows"] = count(dataset["eligible_rows"])
    facts["snapshot_positives"] = count(dataset["positives"])
    facts["snapshot_positive_rate"] = pct(dataset["positive_rate"])
    facts["snapshot_positives_combined"] = fact(
        [dataset["positives"], dataset["positive_rate"]],
        f"{dataset['positives']:,} positives "
        f"({dataset['positive_rate'] * 100:.2f}%)",
    )

    # --- Table 6.2: chronological splits ----------------------------------
    balance = metrics["label_balance"]
    facts["purge_gap_days"] = fact(
        balance["purge_gap_days"], f"{balance['purge_gap_days'] // 7}-week"
    )
    total_rows = total_pos = total_weeks = 0
    for key, entry in balance["splits"].items():
        prefix = key if key in {"train", "validation", "test"} else key
        facts[f"{prefix}_range"] = date_range(entry["start"], entry["end"])
        facts[f"{prefix}_weeks"] = fact(entry["weeks"], str(entry["weeks"]))
        if entry["positive_rate"] is None:
            continue
        facts[f"{prefix}_rows"] = count(entry["rows"])
        facts[f"{prefix}_positives"] = count(entry["positives"])
        facts[f"{prefix}_positive_rate"] = pct(entry["positive_rate"])
        if prefix in {"train", "validation", "test"}:
            total_rows += entry["rows"]
            total_pos += entry["positives"]
            total_weeks += entry["weeks"]
    facts["total_rows"] = count(total_rows)
    facts["total_positives"] = count(total_pos)
    facts["total_weeks"] = fact(total_weeks, str(total_weeks))
    facts["total_positive_rate"] = pct(total_pos / total_rows if total_rows else 0.0)
    facts["total_range"] = date_range(
        balance["splits"]["train"]["start"], balance["splits"]["test"]["end"]
    )
    facts["last_test_snapshot"] = fact(
        balance["splits"]["test"]["end"], balance["splits"]["test"]["end"][:10]
    )
    facts["dataset_end"] = fact(
        generation["history_end"], generation["history_end"]
    )

    # --- Table 6.3: the four models ---------------------------------------
    for name in ("a", "b", "c", "d"):
        row = metrics["test"][name.upper()]
        facts[f"{name}_pr_auc"] = num(row["pr_auc"])
        facts[f"{name}_f1"] = num(row["f1"], 3)
        facts[f"{name}_precision"] = (
            fact(None, "—") if row["precision"] is None else num(row["precision"], 3)
        )
        facts[f"{name}_recall"] = num(row["recall"], 3)
        facts[f"{name}_roc_auc"] = (
            fact(None, "—") if row["roc_auc"] is None else num(row["roc_auc"], 3)
        )

    # --- Model D's configuration and operating point ----------------------
    params = metadata["selected_hyperparameters"]
    for key, value in params.items():
        facts[f"d_{key}"] = fact(value, f"{value:g}")
    facts["d_scale_pos_weight"] = num(metadata["scale_pos_weight"], 2)
    facts["d_threshold"] = num(metadata["classification_threshold"], 2)
    facts["d_risk_band_medium"] = num(metadata["risk_band_edges"]["medium"], 2)
    facts["d_risk_band_high"] = num(metadata["risk_band_edges"]["high"], 2)

    confusion = metrics["test"]["D"]["confusion_matrix"]
    for cell in ("tp", "fp", "fn", "tn"):
        facts[f"d_{cell}"] = count(confusion[cell])
    flagged = confusion["tp"] + confusion["fp"]
    facts["d_flagged_total"] = count(flagged)
    facts["test_rows"] = count(metrics["test"]["D"]["n_rows"])
    facts["test_positives"] = count(metrics["test"]["D"]["n_positives"])
    facts["test_negatives"] = count(
        metrics["test"]["D"]["n_rows"] - metrics["test"]["D"]["n_positives"]
    )

    # --- Narrative claims the discussion makes ----------------------------
    facts["delta_pr_auc_failure_features"] = fact(
        metrics["delta_pr_auc_failure_features"],
        f"{metrics['delta_pr_auc_failure_features']:+.3f}",
    )
    facts["delta_pr_auc_over_recency"] = fact(
        metrics["delta_pr_auc_over_recency"],
        f"{metrics['delta_pr_auc_over_recency']:+.3f}",
    )
    base_rate = metrics["test"]["D"]["n_positives"] / metrics["test"]["D"]["n_rows"]
    facts["base_rate"] = pct(base_rate)
    facts["accuracy_of_majority"] = pct(1 - base_rate)

    if config.SHAP_GLOBAL_PATH.exists():
        ranking = json.loads(config.SHAP_GLOBAL_PATH.read_text())["ranking"]
        names = [entry["feature"] for entry in ranking]
        facts["shap_ranking_csv"] = fact(names, ", ".join(names))
        facts["shap_top_feature"] = fact(names[0], names[0])

    if config.EXEMPLARS_PATH.exists():
        exemplars = json.loads(config.EXEMPLARS_PATH.read_text())
        for which, short in (("high_risk", "high"), ("low_risk", "low")):
            entry = exemplars[which]
            facts[f"exemplar_{short}_merchant_id"] = fact(
                entry["merchant_id"], entry["merchant_id"]
            )
            facts[f"exemplar_{short}_score"] = num(entry["score_d"], 2)
            facts[f"exemplar_{short}_snapshot"] = fact(
                entry["snapshot_at"], entry["snapshot_at"][:10]
            )

    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    facts = build_facts()
    config.ensure_dirs()
    config.REPORT_FACTS_PATH.write_text(json.dumps(facts, indent=2) + "\n")
    print(f"wrote {len(facts)} facts to {config.REPORT_FACTS_PATH}")
    for key in sorted(facts):
        print(f"  {key:<34} {facts[key]['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
