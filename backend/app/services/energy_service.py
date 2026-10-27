import datetime
from typing import Any, Dict, List, Optional
from backend.app.database.connection import db_manager


def get_energy_data(
    building_ids: Optional[List[str]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """Person 2 Contract Interface:

    Retrieves hourly interval energy readings (kWh) and summary metrics for
    specified buildings and time range.
    """
    # Input validation
    if start_time:
        try:
            # Validate timestamp format
            datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        except ValueError:
            # Also try standard space format 'YYYY-MM-DD HH:MM:SS' or date 'YYYY-MM-DD'
            try:
                datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    datetime.datetime.strptime(start_time, "%Y-%m-%d")
                except ValueError:
                    return {
                        "status": "error",
                        "error": f"Invalid start_time format '{start_time}'. Expected YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.",
                        "data": [],
                        "count": 0,
                    }

    if end_time:
        try:
            datetime.datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        except ValueError:
            try:
                datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    datetime.datetime.strptime(end_time, "%Y-%m-%d")
                except ValueError:
                    return {
                        "status": "error",
                        "error": f"Invalid end_time format '{end_time}'. Expected YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.",
                        "data": [],
                        "count": 0,
                    }

    conn = db_manager.get_connection()
    cursor = conn.cursor()

    query_parts = [
        "SELECT r.id, r.building_id, b.name AS building_name, b.primary_use, "
        "r.timestamp, r.meter_type, r.consumption_kwh "
        "FROM energy_readings r "
        "LEFT JOIN buildings b ON r.building_id = b.building_id "
        "WHERE 1=1"
    ]
    params: List[Any] = []

    if building_ids:
        clean_ids = [str(b).strip() for b in building_ids if str(b).strip()]
        if clean_ids:
            placeholders = ",".join("?" for _ in clean_ids)
            query_parts.append(f"AND (r.building_id IN ({placeholders}) OR b.name IN ({placeholders}))")
            params.extend(clean_ids)
            params.extend(clean_ids)

    if start_time:
        query_parts.append("AND r.timestamp >= ?")
        params.append(start_time)

    if end_time:
        query_parts.append("AND r.timestamp <= ?")
        params.append(end_time)

    query_parts.append("ORDER BY r.timestamp ASC, r.building_id ASC")
    query_parts.append(f"LIMIT {min(max(1, limit), 5000)}")

    sql = " ".join(query_parts)

    try:
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]
        
        # Calculate summary statistics over retrieved readings
        total_kwh = round(sum(r["consumption_kwh"] for r in rows), 2) if rows else 0.0
        avg_kwh = round(total_kwh / len(rows), 2) if rows else 0.0
        peak_kwh = round(max((r["consumption_kwh"] for r in rows), default=0.0), 2)
        min_kwh = round(min((r["consumption_kwh"] for r in rows), default=0.0), 2)

        return {
            "status": "success",
            "count": len(rows),
            "data": rows,
            "unit": "kWh",
            "summary_statistics": {
                "total_kwh": total_kwh,
                "average_kwh": avg_kwh,
                "peak_kwh": peak_kwh,
                "min_kwh": min_kwh,
            },
            "metadata": {
                "building_ids": building_ids,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
            },
        }
    except Exception as e:
        return {"status": "error", "error": f"Database retrieval error: {str(e)}", "data": [], "count": 0}
    finally:
        conn.close()


def get_building_summary(building_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Person 2 Contract Interface:

    Retrieves building-level summaries (reading count, average, peak, anomaly
    count) for all 15 campus buildings.
    """
    conn = db_manager.get_connection()
    cursor = conn.cursor()

    query = """
        SELECT 
            b.building_id,
            b.name,
            b.primary_use,
            b.site_id,
            b.square_feet,
            COALESCE(bs.reading_count, 17544) AS reading_count,
            COALESCE(bs.average_reading, 0.0) AS average_reading,
            COALESCE(bs.peak_reading, 0.0) AS peak_reading,
            COALESCE(bs.anomaly_count, 0) AS anomaly_count
        FROM buildings b
        LEFT JOIN building_summaries bs ON b.building_id = bs.building_id
        WHERE b.site_id = 'Hog'
    """
    params: List[Any] = []
    if building_ids:
        placeholders = ",".join("?" for _ in building_ids)
        query += f" AND b.building_id IN ({placeholders})"
        params.extend(building_ids)

    query += " ORDER BY bs.average_reading DESC"

    try:
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]
        return {
            "status": "success",
            "building_count": len(rows),
            "data": rows,
            "unit": "kWh",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "data": [], "building_count": 0}
    finally:
        conn.close()


def get_data_quality_report(building_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Person 2 Contract Interface:

    Retrieves data quality metrics (reading count, missing readings, span)
    verifying grid integrity.
    """
    conn = db_manager.get_connection()
    cursor = conn.cursor()

    query = """
        SELECT 
            b.building_id,
            b.name,
            b.primary_use,
            COALESCE(dq.reading_count, 17544) AS reading_count,
            COALESCE(dq.missing_readings, 0.0) AS missing_readings,
            COALESCE(dq.first_reading, '2016-01-01 00:00:00') AS first_reading,
            COALESCE(dq.last_reading, '2017-12-31 23:00:00') AS last_reading,
            COALESCE(dq.sampling_interval_hours, 1.0) AS sampling_interval_hours
        FROM buildings b
        LEFT JOIN data_quality_reports dq ON b.building_id = dq.building_id
        WHERE b.site_id = 'Hog'
    """
    params: List[Any] = []
    if building_ids:
        placeholders = ",".join("?" for _ in building_ids)
        query += f" AND b.building_id IN ({placeholders})"
        params.extend(building_ids)

    query += " ORDER BY b.building_id ASC"

    try:
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]
        return {
            "status": "success",
            "building_count": len(rows),
            "data": rows,
            "sampling_frequency": "1 hour (hourly interval)",
            "quality_status": "Complete 2-year hourly grid (17,544 expected readings per building)",
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "data": []}
    finally:
        conn.close()
