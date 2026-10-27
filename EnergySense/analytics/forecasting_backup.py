
import pandas as pd
import numpy as np

DATA_PATH = "data/selected_buildings.csv"
WEEK_HOURS = 168
TEST_DAYS = 30


def evaluate_forecast():
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    buildings = [c for c in df.columns if c != "timestamp"]
    test_start = len(df) - TEST_DAYS * 24

    metrics = []
    uncertainty = []

    for building in buildings:
        actual = pd.to_numeric(df[building], errors="coerce")
        predicted = actual.shift(WEEK_HOURS)

        # Use only pre-test errors to estimate uncertainty.
        train_errors = (
            actual.iloc[:test_start]
            - predicted.iloc[:test_start]
        ).dropna()

        if len(train_errors) == 0:
            continue

        # 90th percentile of absolute historical errors.
        error_margin = float(train_errors.abs().quantile(0.90))

        test_actual = actual.iloc[test_start:]
        test_predicted = predicted.iloc[test_start:]
        valid = test_actual.notna() & test_predicted.notna()

        if valid.sum() == 0:
            continue

        y = test_actual[valid]
        p = test_predicted[valid]
        errors = y - p

        total_actual = y.abs().sum()
        wape = (
            errors.abs().sum() / total_actual * 100
            if total_actual > 0 else np.nan
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

        # Save hourly forecasts and their estimated ranges.
        part = pd.DataFrame({
            "timestamp": df.loc[test_actual[valid].index, "timestamp"].values,
            "building": building,
            "actual": y.values,
            "predicted": p.values,
            "lower_90_estimate": lower.values,
            "upper_90_estimate": upper.values,
        })
        uncertainty.append(part)

    pd.DataFrame(metrics).to_csv(
        "data/forecast_evaluation.csv", index=False
    )

    if uncertainty:
        pd.concat(uncertainty, ignore_index=True).to_csv(
            "data/forecast_uncertainty.csv", index=False
        )

    print("\nENERGYSENSE FORECAST EVALUATION")
    print(pd.DataFrame(metrics).to_string(index=False))
    print("\nSaved: data/forecast_evaluation.csv")
    print("Saved: data/forecast_uncertainty.csv")
    print("\nInterval coverage shows how often actual readings")
    print("fell inside the estimated prediction range.")


if __name__ == "__main__":
    evaluate_forecast()
