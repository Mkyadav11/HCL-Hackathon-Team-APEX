from typing import Any, Dict, List, Optional
from backend.app.database.connection import db_manager


def calculate_baseline_deviation(actual: float, baseline: float) -> float:
    """Calculates percentage deviation safely, preventing division by zero.

    Formula: ((actual - baseline) / baseline) * 100
    """
    if baseline is None or abs(baseline) < 1e-6:
        # Near-zero baseline safety
        return 0.0 if actual <= 0 else 100.0
    return round(((actual - baseline) / baseline) * 100.0, 2)


def detect_anomalies(
    building_ids: Optional[List[str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """Person 2 Contract Interface:

    Retrieves structured anomaly records with measurements, baselines,
    deviation percentages, and severities from the canonical anomaly database.
    """
    conn = db_manager.get_connection()
    cursor = conn.cursor()

    query_parts = [
        "SELECT a.anomaly_id, a.building_id, b.name AS building_name, b.primary_use, "
        "a.detected_at, a.anomaly_type, a.actual_value, a.baseline_value, "
        "a.deviation_pct, a.severity, a.details "
        "FROM anomaly_events a "
        "LEFT JOIN buildings b ON a.building_id = b.building_id "
        "WHERE 1=1"
    ]
    params: List[Any] = []

    if building_ids:
        clean_ids = [str(b).strip() for b in building_ids if str(b).strip()]
        if clean_ids:
            placeholders = ",".join("?" for _ in clean_ids)
            query_parts.append(f"AND (a.building_id IN ({placeholders}) OR b.name IN ({placeholders}))")
            params.extend(clean_ids)
            params.extend(clean_ids)

    if start_time:
        query_parts.append("AND a.detected_at >= ?")
        params.append(start_time)

    if end_time:
        query_parts.append("AND a.detected_at <= ?")
        params.append(end_time)

    if anomaly_type:
        query_parts.append("AND LOWER(a.anomaly_type) = LOWER(?)")
        params.append(anomaly_type)

    if severity:
        query_parts.append("AND LOWER(a.severity) = LOWER(?)")
        params.append(severity)

    query_parts.append("ORDER BY a.detected_at DESC, a.deviation_pct DESC")
    query_parts.append(f"LIMIT {min(max(1, limit), 2000)}")

    sql = " ".join(query_parts)

    try:
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]

        # Query total count matching filters
        count_sql = "SELECT COUNT(*) FROM anomaly_events a WHERE 1=1"
        count_params: List[Any] = []
        if building_ids:
            clean_ids = [str(b).strip() for b in building_ids if str(b).strip()]
            if clean_ids:
                placeholders = ",".join("?" for _ in clean_ids)
                count_sql += f" AND a.building_id IN ({placeholders})"
                count_params.extend(clean_ids)
        if anomaly_type:
            count_sql += " AND LOWER(a.anomaly_type) = LOWER(?)"
            count_params.append(anomaly_type)
        if severity:
            count_sql += " AND LOWER(a.severity) = LOWER(?)"
            count_params.append(severity)

        cursor.execute(count_sql, count_params)
        total_matched = cursor.fetchone()[0]

        # Calculate severity counts in sample
        severity_breakdown = {}
        type_breakdown = {}
        for r in rows:
            sev = r["severity"]
            typ = r["anomaly_type"]
            severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1
            type_breakdown[typ] = type_breakdown.get(typ, 0) + 1

        return {
            "status": "success",
            "anomaly_count": len(rows),
            "total_matched_events": total_matched,
            "anomalies": rows,
            "data": rows,
            "severity_breakdown": severity_breakdown,
            "type_breakdown": type_breakdown,
            "unit": "kWh",
            "metadata": {
                "building_ids": building_ids,
                "start_time": start_time,
                "end_time": end_time,
                "anomaly_type": anomaly_type,
                "severity": severity,
                "limit": limit,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Database error querying anomaly records: {str(e)}",
            "anomalies": [],
            "anomaly_count": 0,
            "total_matched_events": 0,
        }
    finally:
        conn.close()


def detect_flatlines(
    building_ids: Optional[List[str]] = None,
    min_consecutive_hours: int = 24,
) -> Dict[str, Any]:
    """Person 2 Contract Interface:

    Identifies flatline anomalies where a meter reports repeated identical
    readings over extended intervals (e.g., telemetry freeze or gateway
    dropout).
    """
    conn = db_manager.get_connection()
    cursor = conn.cursor()

    query = """
        SELECT 
            fc.id,
            fc.building_id,
            b.name AS building_name,
            b.primary_use,
            fc.start_time,
            fc.end_time,
            fc.reading_count,
            fc.energy_value,
            fc.status
        FROM flatline_candidates fc
        LEFT JOIN buildings b ON fc.building_id = b.building_id
        WHERE fc.reading_count >= ?
    """
    params: List[Any] = [min_consecutive_hours]

    if building_ids:
        placeholders = ",".join("?" for _ in building_ids)
        query += f" AND fc.building_id IN ({placeholders})"
        params.extend(building_ids)

    query += " ORDER BY fc.reading_count DESC"

    try:
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]

        # Contextual explanation for the user/frontend
        explanation = (
            "Flatline candidates represent meters that reported identical floating-point values "
            "for multiple days consecutively without sensor variation. "
            "Notice: May 26 to May 31 coincides with US Memorial Day weekend, indicating potential gateway dropout."
        )

        return {
            "status": "success",
            "candidate_count": len(rows),
            "candidates": rows,
            "explanation": explanation,
            "unit": "kWh",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "candidates": []}
    finally:
        conn.close()


def get_anomaly_summary_report() -> Dict[str, Any]:
    """Person 2 Contract Interface:

    Returns aggregated anomaly counts by type and severity across all 15
    buildings.
    """
    conn = db_manager.get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT anomaly_type, severity, event_count, affected_buildings
            FROM anomaly_summary
            ORDER BY event_count DESC
        """)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT SUM(event_count) FROM anomaly_summary")
        total_events = cursor.fetchone()[0] or 0

        return {
            "status": "success",
            "total_anomalies": total_events,
            "breakdown": rows,
            "total_buildings": 15,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "breakdown": []}
    finally:
        conn.close()
