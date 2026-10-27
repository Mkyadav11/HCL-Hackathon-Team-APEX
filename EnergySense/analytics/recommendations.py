
import pandas as pd
import numpy as np

DATA_PATH = "data/selected_buildings.csv"
OUTPUT_PATH = "data/energy_recommendations.csv"

HOURS_PER_WEEK = 168
MIN_DATA_COVERAGE = 0.90
INCREASE_THRESHOLD = 15.0


def suggest_action(building):
    name = building.lower()

    if "office" in name:
        return (
            "Review HVAC schedules, lighting schedules, "
            "and equipment left running after hours."
        )
    if "education" in name:
        return (
            "Review classroom and common-area schedules, "
            "HVAC operation, and lighting controls."
        )
    if "parking" in name:
        return (
            "Inspect parking lighting schedules, ventilation, "
            "and other continuously running equipment."
        )
    if "lodging" in name:
        return (
            "Review HVAC settings, hot-water systems, "
            "and energy use in unoccupied rooms."
        )
    if "retail" in name:
        return (
            "Review store operating hours, lighting, "
            "refrigeration if present, and HVAC schedules."
        )
    if "assembly" in name:
        return (
            "Compare event schedules with energy use and "
            "review HVAC and lighting during unoccupied periods."
        )

    return (
        "Inspect operating schedules and major equipment "
        "to identify possible causes of increased consumption."
    )


def analyze_buildings():
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    buildings = [c for c in df.columns if c != "timestamp"]

    if len(df) < 4 * HOURS_PER_WEEK:
        raise ValueError("At least four weeks of readings are required.")

    # Analyze the latest week and the three preceding weeks.
    recent = df.iloc[-HOURS_PER_WEEK:]
    previous = [
        df.iloc[-2 * HOURS_PER_WEEK:-HOURS_PER_WEEK],
        df.iloc[-3 * HOURS_PER_WEEK:-2 * HOURS_PER_WEEK],
        df.iloc[-4 * HOURS_PER_WEEK:-3 * HOURS_PER_WEEK],
    ]

    results = []

    for building in buildings:
        recent_values = pd.to_numeric(
            recent[building], errors="coerce"
        )

        recent_coverage = recent_values.notna().mean()

        weekly_totals = []
        weekly_coverages = []

        for week in previous:
            values = pd.to_numeric(week[building], errors="coerce")
            weekly_coverages.append(values.notna().mean())

            if values.notna().mean() >= MIN_DATA_COVERAGE:
                weekly_totals.append(values.sum())

        if (
            recent_coverage < MIN_DATA_COVERAGE
            or len(weekly_totals) < 2
        ):
            results.append({
                "building": building,
                "recent_week_total": None,
                "baseline_weekly_median": None,
                "change_percent": None,
                "status": "Insufficient data",
                "recommendation": "Check data completeness before assessing."
            })
            continue

        recent_total = recent_values.sum()
        baseline_total = float(np.median(weekly_totals))

        if baseline_total <= 0:
            results.append({
                "building": building,
                "recent_week_total": round(float(recent_total), 3),
                "baseline_weekly_median": round(baseline_total, 3),
                "change_percent": None,
                "status": "No usable baseline",
                "recommendation": "Review baseline readings before comparison."
            })
            continue

        change = (
            (recent_total - baseline_total) / baseline_total * 100
        )

        if change >= INCREASE_THRESHOLD:
            status = "Review recommended"
            action = suggest_action(building)
            recommendation = (
                f"Consumption is {change:.1f}% above the recent "
                f"weekly baseline. {action} This is a lead to investigate, "
                "not proof of energy waste."
            )
        elif change <= -INCREASE_THRESHOLD:
            status = "Consumption decreased"
            recommendation = (
                f"Consumption is {abs(change):.1f}% below the baseline. "
                "Check schedules and occupancy to understand what changed."
            )
        else:
            status = "No large weekly change"
            recommendation = (
                "No change of 15% or more was detected. Continue monitoring."
            )

        results.append({
            "building": building,
            "recent_week_total": round(float(recent_total), 3),
            "baseline_weekly_median": round(baseline_total, 3),
            "change_percent": round(float(change), 2),
            "status": status,
            "recommendation": recommendation,
        })

    result_df = pd.DataFrame(results)
    result_df.to_csv(OUTPUT_PATH, index=False)

    print("\nENERGYSENSE ENERGY RECOMMENDATIONS")
    print("=" * 70)
    print(
        result_df[
            ["building", "change_percent", "status"]
        ].to_string(index=False)
    )
    print(f"\nFull recommendations saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    analyze_buildings()
