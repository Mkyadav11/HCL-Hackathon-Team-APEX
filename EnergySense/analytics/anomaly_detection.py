
import pandas as pd
import numpy as np

DATA_PATH = "data/selected_buildings.csv"
OUTPUT_PATH = "data/energy_anomalies.csv"


def detect_anomalies():
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    results = []

    buildings = [
        column for column in df.columns
        if column != "timestamp"
    ]

    # Analyze the final 30 days.
    test_start = max(0, len(df) - 30 * 24)

    for building in buildings:
        values = pd.to_numeric(
            df[building],
            errors="coerce"
        )

        # Compare each hour with the same hour one week earlier.
        baseline = values.shift(168)
        difference = values - baseline

        # Use historical differences before the final 30 days.
        historical_diff = difference.iloc[:test_start].dropna()

        if len(historical_diff) < 100:
            continue

        median_diff = historical_diff.median()
        deviations = (historical_diff - median_diff).abs()
        mad = deviations.median()

        # Estimate a threshold from historical variability.
        if mad > 0:
            threshold = abs(median_diff) + 3 * 1.4826 * mad
        else:
            threshold = historical_diff.abs().quantile(0.99)

        # Inspect readings in the final 30 days.
        for i in range(test_start, len(df)):
            actual = values.iloc[i]
            previous = baseline.iloc[i]
            change = difference.iloc[i]

            if pd.isna(actual) or pd.isna(previous):
                continue

            # Only flag unusually large positive changes.
            if change <= threshold or change <= 0:
                continue

            if change >= 2 * threshold:
                severity = "High"
            else:
                severity = "Moderate"

            if previous == 0:
                note = (
                    "Increase from a zero baseline; check the reading "
                    "and operating context."
                )
            else:
                note = (
                    "Unusually high reading; investigate the possible cause."
                )

            results.append({
                "timestamp": df["timestamp"].iloc[i],
                "building": building,
                "actual_reading": float(actual),
                "same_hour_last_week": float(previous),
                "increase": round(float(change), 3),
                "threshold": round(float(threshold), 3),
                "severity": severity,
                "note": note
            })

    columns = [
        "timestamp",
        "building",
        "actual_reading",
        "same_hour_last_week",
        "increase",
        "threshold",
        "severity",
        "note"
    ]

    output = pd.DataFrame(results, columns=columns)

    if not output.empty:
        output = output.sort_values(
            "increase",
            ascending=False
        )

    output.to_csv(OUTPUT_PATH, index=False)

    print("\nENERGYSENSE HOURLY ANOMALIES")
    print("=" * 75)
    print("Potential anomalies found:", len(output))

    if output.empty:
        print("No potential high-reading anomalies detected.")
    else:
        print("\nSeverity summary:")
        print(output["severity"].value_counts().to_string())

        print("\nTop 20 potential anomalies:")
        print(output.head(20).to_string(index=False))

    print(f"\nFull results saved to: {OUTPUT_PATH}")
    print("These are alerts for investigation, not proof of energy waste.")


if __name__ == "__main__":
    detect_anomalies()
