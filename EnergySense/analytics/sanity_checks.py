
def calculate_deviation(actual, baseline):
    """Calculate percentage change from a historical baseline."""
    if baseline <= 0:
        raise ValueError("Baseline must be greater than zero.")

    return (actual - baseline) / baseline * 100


def validate_deviation(actual, baseline, reported_percentage):
    """Check whether a reported percentage is mathematically correct."""
    expected = calculate_deviation(actual, baseline)

    is_valid = abs(expected - reported_percentage) <= 0.1

    return {
        "valid": is_valid,
        "expected_percentage": round(expected, 2),
        "reported_percentage": reported_percentage,
    }


if __name__ == "__main__":
    result = validate_deviation(
        actual=138,
        baseline=100,
        reported_percentage=38,
    )

    print("Sanity Check Result")
    print("-------------------")
    print(f"Valid: {result['valid']}")
    print(f"Expected: {result['expected_percentage']}%")
    print(f"Reported: {result['reported_percentage']}%")
