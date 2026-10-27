
from pathlib import Path

import numpy as np
import pandas as pd

INPUT_FILE = Path("data/forecast_uncertainty.csv")
OUTPUT_FILE = Path("data/hourly_calibration_comparison.csv")

TARGET_COVERAGE = 0.90
MIN_ERRORS_PER_GROUP = 10


def interval_metrics(actual, lower, upper):
    valid = actual.notna() & lower.notna() & upper.notna()

    if valid.sum() == 0:
        return np.nan, np.nan

    coverage = (
        (actual[valid] >= lower[valid])
        & (actual[valid] <= upper[valid])
    ).mean() * 100

    width = (upper[valid] - lower[valid]).mean()

    return float(coverage), float(width)


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input file: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE, parse_dates=["timestamp"])

    required = {
        "timestamp",
        "building",
        "actual",
        "predicted",
        "lower_90_estimate",
        "upper_90_estimate",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df = df.dropna(subset=list(required)).copy()
    df = df.sort_values(["building", "timestamp"])

    # Hour of week: Monday 00:00 = 0, Sunday 23:00 = 167.
    df["hour_of_week"] = (
        df["timestamp"].dt.dayofweek * 24
        + df["timestamp"].dt.hour
    )

    results = []

    for building, group in df.groupby("building"):
        group = group.sort_values("timestamp").copy()
        group = group.reset_index(drop=True)

        if len(group) < 40:
            continue

        split = int(len(group) * 0.50)
        calibration = group.iloc[:split].copy()
        test = group.iloc[split:].copy()

        # Historical absolute errors from calibration period only.
        calibration["abs_error"] = (
            calibration["actual"] - calibration["predicted"]
        ).abs()

        # Estimate a separate margin for each hour of the week.
        # If a group has too few examples, use the building-wide margin.
        building_margin = calibration["abs_error"].quantile(
            TARGET_COVERAGE
        )

        margins = {}
        for hour, hour_group in calibration.groupby("hour_of_week"):
            if len(hour_group) >= MIN_ERRORS_PER_GROUP:
                margins[hour] = hour_group["abs_error"].quantile(
                    TARGET_COVERAGE
                )
            else:
                margins[hour] = building_margin

        test["margin"] = test["hour_of_week"].map(margins)
        test["new_lower"] = test["predicted"] - test["margin"]
        test["new_upper"] = test["predicted"] + test["margin"]

        old_coverage, old_width = interval_metrics(
            test["actual"],
            test["lower_90_estimate"],
            test["upper_90_estimate"],
        )

        new_coverage, new_width = interval_metrics(
            test["actual"],
            test["new_lower"],
            test["new_upper"],
        )

        results.append({
            "building": building,
            "calibration_rows": len(calibration),
            "test_rows": len(test),
            "old_coverage_percent": round(old_coverage, 2),
            "hourly_coverage_percent": round(new_coverage, 2),
            "old_average_width": round(old_width, 3),
            "hourly_average_width": round(new_width, 3),
        })

    result_df = pd.DataFrame(results)

    if result_df.empty:
        raise ValueError("No buildings had enough data for evaluation.")

    result_df.to_csv(OUTPUT_FILE, index=False)

    print("\nENERGYSENSE HOUR-OF-WEEK CALIBRATION")
    print("=" * 95)
    print(result_df.to_string(index=False))

    print("\nMean coverage across buildings:")
    print(
        "Original:",
        round(result_df["old_coverage_percent"].mean(), 2),
        "%",
    )
    print(
        "Hour-of-week:",
        round(result_df["hourly_coverage_percent"].mean(), 2),
        "%",
    )

    print("\nMean interval width across buildings:")
    print(
        "Original:",
        round(result_df["old_average_width"].mean(), 3),
    )
    print(
        "Hour-of-week:",
        round(result_df["hourly_average_width"].mean(), 3),
    )

    print(f"\nSaved comparison to: {OUTPUT_FILE}")
    print(
        "These are empirical test results, not a guarantee "
        "of 90% future coverage."
    )


if __name__ == "__main__":
    main()
