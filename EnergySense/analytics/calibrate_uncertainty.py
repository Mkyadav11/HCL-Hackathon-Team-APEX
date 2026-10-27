
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_FILE = Path("data/forecast_uncertainty.csv")
OUTPUT_FILE = Path("data/uncertainty_calibration_comparison.csv")

CALIBRATION_FRACTION = 0.50
TARGET_COVERAGE = 0.90


def evaluate_intervals(actual, lower, upper):
    """Calculate empirical coverage and average interval width."""
    valid = actual.notna() & lower.notna() & upper.notna()

    if valid.sum() == 0:
        return np.nan, np.nan

    coverage = (
        (actual[valid] >= lower[valid])
        & (actual[valid] <= upper[valid])
    ).mean() * 100

    width = (upper[valid] - lower[valid]).mean()

    return coverage, width


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {INPUT_FILE}. "
            "Run this script from the EnergySense project folder."
        )

    df = pd.read_csv(INPUT_FILE)
    required = {
        "timestamp",
        "building",
        "actual",
        "predicted",
        "lower_90_estimate",
        "upper_90_estimate",
    }

    missing_columns = required - set(df.columns)
    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], errors="coerce"
    )

    numeric_columns = [
        "actual",
        "predicted",
        "lower_90_estimate",
        "upper_90_estimate",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(
        subset=["timestamp", "building"] + numeric_columns
    )

    results = []

    for building, group in df.groupby("building"):
        group = group.sort_values("timestamp").copy()
        group = group.reset_index(drop=True)

        if len(group) < 20:
            continue

        split = int(len(group) * CALIBRATION_FRACTION)

        calibration = group.iloc[:split].copy()
        evaluation = group.iloc[split:].copy()

        if len(calibration) == 0 or len(evaluation) == 0:
            continue

        # Use only earlier-period errors to calibrate the range.
        calibration_errors = (
            calibration["actual"] - calibration["predicted"]
        ).abs()

        margin = float(
            calibration_errors.quantile(TARGET_COVERAGE)
        )

        actual = evaluation["actual"]
        predicted = evaluation["predicted"]

        old_coverage, old_width = evaluate_intervals(
            actual,
            evaluation["lower_90_estimate"],
            evaluation["upper_90_estimate"],
        )

        new_lower = predicted - margin
        new_upper = predicted + margin

        new_coverage, new_width = evaluate_intervals(
            actual,
            new_lower,
            new_upper,
        )

        mae = float((actual - predicted).abs().mean())

        results.append(
            {
                "building": building,
                "calibration_hours": len(calibration),
                "evaluation_hours": len(evaluation),
                "MAE": round(mae, 3),
                "old_coverage_percent": round(old_coverage, 2),
                "calibrated_coverage_percent": round(
                    new_coverage, 2
                ),
                "old_average_interval_width": round(old_width, 3),
                "calibrated_average_interval_width": round(
                    new_width, 3
                ),
                "calibration_margin": round(margin, 3),
            }
        )

    if not results:
        raise ValueError("No buildings had enough valid forecast rows.")

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values(
        "calibrated_coverage_percent"
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT_FILE, index=False)

    print()
    print("ENERGYSENSE UNCERTAINTY CALIBRATION EXPERIMENT")
    print("=" * 100)
    print(result_df.to_string(index=False))
    print()
    print("Overall comparison on the later evaluation periods:")
    print(
        "Old interval coverage:",
        round(result_df["old_coverage_percent"].mean(), 2),
        "%",
    )
    print(
        "Calibrated interval coverage:",
        round(
            result_df["calibrated_coverage_percent"].mean(), 2
        ),
        "%",
    )
    print(
        "Old average interval width:",
        round(result_df["old_average_interval_width"].mean(), 3),
    )
    print(
        "Calibrated average interval width:",
        round(
            result_df["calibrated_average_interval_width"].mean(),
            3,
        ),
    )
    print()
    print("Saved comparison to:", OUTPUT_FILE)
    print(
        "Note: these are empirical results on a later time period, "
        "not guaranteed 90% coverage."
    )


if __name__ == "__main__":
    main()
