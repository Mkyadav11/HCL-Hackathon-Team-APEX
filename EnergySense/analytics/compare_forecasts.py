
from pathlib import Path

import numpy as np
import pandas as pd

DATA_FILE = Path("data/selected_buildings.csv")
OUTPUT_FILE = Path("data/model_comparison.csv")

# Load hourly electricity readings.
df = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

if "timestamp" not in df.columns:
    raise ValueError("The dataset must contain a timestamp column.")

building_columns = [
    col for col in df.columns
    if col != "timestamp"
]

if not building_columns:
    raise ValueError("No building columns were found.")

# Evaluate the final 30 days.
test_start = df["timestamp"].max() - pd.Timedelta(days=30)

results = []

for building in building_columns:
    actual = pd.to_numeric(df[building], errors="coerce")

    # Method 1: previous hour's reading.
    previous_hour = actual.shift(1)

    # Method 2: same hour one week earlier.
    previous_week = actual.shift(168)

    test_mask = df["timestamp"] > test_start

    for method, prediction in [
        ("Previous-hour baseline", previous_hour),
        ("Same-hour-last-week baseline", previous_week),
    ]:
        valid = (
            test_mask
            & actual.notna()
            & prediction.notna()
            & np.isfinite(actual)
            & np.isfinite(prediction)
        )

        y_true = actual[valid].to_numpy()
        y_pred = prediction[valid].to_numpy()

        if len(y_true) == 0:
            continue

        errors = y_true - y_pred
        mae = np.mean(np.abs(errors))
        rmse = np.sqrt(np.mean(errors ** 2))

        denominator = np.sum(np.abs(y_true))
        wape = (
            np.sum(np.abs(errors)) / denominator * 100
            if denominator > 0
            else np.nan
        )

        results.append({
            "building": building,
            "method": method,
            "test_hours": len(y_true),
            "MAE": round(float(mae), 3),
            "RMSE": round(float(rmse), 3),
            "WAPE_percent": round(float(wape), 2)
            if np.isfinite(wape) else np.nan,
        })

comparison = pd.DataFrame(results)

if comparison.empty:
    raise ValueError("No valid forecasts could be evaluated.")

comparison.to_csv(OUTPUT_FILE, index=False)

print("\nENERGYSENSE FORECAST COMPARISON")
print("=" * 90)
print(comparison.to_string(index=False))

print("\nAVERAGE RESULTS BY METHOD")
print("=" * 90)

summary = (
    comparison.groupby("method")
    .agg(
        buildings=("building", "nunique"),
        average_MAE=("MAE", "mean"),
        average_RMSE=("RMSE", "mean"),
        average_WAPE_percent=("WAPE_percent", "mean"),
    )
    .round(3)
)

print(summary.to_string())

print(f"\nSaved comparison to: {OUTPUT_FILE}")

