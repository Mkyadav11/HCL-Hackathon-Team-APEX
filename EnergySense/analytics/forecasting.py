
import pandas as pd
import numpy as np
from pathlib import Path

DATA_PATH = Path("data/selected_buildings.csv")
OUTPUT_DIR = Path("data")
TEST_DAYS = 30
LAG_HOURS = 1


def evaluate_forecast():
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    buildings = [c for c in df.columns if c != "timestamp"]

    # Keep the same chronological 30-day test window.
    test_start = max(0, len(df) - TEST_DAYS * 24)

    metrics = []
    uncertainty = []

    for building in buildings:
        actual = pd.to_numeric(df[building], errors="coerce")

        # Previous-hour baseline: predict from the preceding reading.
        predicted = actual.shift(LAG_HOURS)

        # Estimate uncertainty using training-period errors only.
        train_actual = actual.iloc[:test_start]
        train_predicted = predicted.iloc[:test_start]
        train_valid = train_actual.notna() & train_predicted.notna()

        train_errors = (
            train_actual[train_valid] - train_predicted[train_valid]
        ).dropna()

        if train_errors.empty:
            print(f"Skipping {building}: insufficient training errors.")
            continue

        error_margin = float(train_errors.abs().quantile(0.90))

        test_actual = actual.iloc[test_start:]
        test_predicted = predicted.iloc[test_start:]
        valid = test_actual.notna() & test_predicted.notna()

        if not valid.any():
            print(f"Skipping {building}: no valid test predictions.")
            continue

        y = test_actual[valid]
        p = test_predicted[valid]
        errors = y - p

        total_actual = y.abs().sum()
        wape = (
            errors.abs().sum() / total_actual * 100
            if total_actual > 0
            else np.nan
        )

        lower = p - error_margin
        upper = p + error_margin
        coverage = ((y >= lower) & (y <= upper)).mean() * 100

        metrics.append({
            "building": building,
            "valid_test_hours": int(valid.sum()),
            "MAE": round(float(errors.abs().mean()), 3),
            "RMSE": round(float(np.sqrt((errors ** 2).mean())), 3),
            "WAPE_percent": round(float(wape), 2)
            if pd.notna(wape) else None,
            "uncertainty_margin": round(error_margin, 3),
            "interval_coverage_percent": round(float(coverage), 2),
        })

        # Store test timestamps, actual values, predictions, and ranges.
        test_indices = y.index

        part = pd.DataFrame({
            "timestamp": df.loc[test_indices, "timestamp"].to_numpy(),
            "building": building,
            "actual": y.to_numpy(),
            "predicted": p.to_numpy(),
            "lower_90_estimate": lower.to_numpy(),
            "upper_90_estimate": upper.to_numpy(),
        })

        uncertainty.append(part)

    if not metrics:
        raise ValueError("No valid forecast metrics were generated.")

    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(
        OUTPUT_DIR / "forecast_evaluation.csv",
        index=False,
    )

    if uncertainty:
        uncertainty_df = pd.concat(uncertainty, ignore_index=True)
        uncertainty_df.to_csv(
            OUTPUT_DIR / "forecast_uncertainty.csv",
            index=False,
        )

    print("\nENERGYSENSE FORECAST EVALUATION")
    print("=" * 90)
    print(metrics_df.to_string(index=False))

    print("\nAVERAGE METRICS ACROSS BUILDINGS")
    print(
        metrics_df[["MAE", "RMSE", "WAPE_percent"]]
        .mean()
        .round(3)
        .to_string()
    )

    print("\nSaved: data/forecast_evaluation.csv")
    print("Saved: data/forecast_uncertainty.csv")
    print("\nForecast method: previous-hour baseline.")
    print(
        "Uncertainty ranges use the 90th percentile of pre-test "
        "absolute errors. Coverage is empirical, not guaranteed."
    )


if __name__ == "__main__":
    evaluate_forecast()
