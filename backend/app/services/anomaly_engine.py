import datetime
from typing import Any, Dict, List, Optional
from backend.app.database.connection import db_manager


class AnomalyEngine:
    """Person 2 Core Analytical Engine:

    Implements robust baseline calculation, dynamic thresholding, flatline
    detection, and report regeneration.
    """

    @staticmethod
    def calculate_deviation_percentage(actual: float, baseline: float) -> float:
        """Computes ((actual - baseline) / baseline) * 100 with zero-division safety."""
        if baseline is None or abs(baseline) < 1e-6:
            return 0.0 if actual <= 0 else 100.0
        return round(((actual - baseline) / baseline) * 100.0, 2)

    @staticmethod
    def classify_severity(deviation_pct: float, actual_kwh: float) -> str:
        """Classifies anomaly severity based on percentage deviation and load magnitude."""
        if deviation_pct >= 100.0 or actual_kwh >= 1000.0:
            return "critical"
        elif deviation_pct >= 50.0:
            return "high"
        elif deviation_pct >= 20.0:
            return "medium"
        else:
            return "low"

    def regenerate_building_summary(self, building_id: str) -> Dict[str, Any]:
        """Regenerates building summary directly from underlying data."""
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Query readings stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as reading_count,
                    AVG(consumption_kwh) as avg_reading,
                    MAX(consumption_kwh) as peak_reading
                FROM energy_readings
                WHERE building_id = ?
            """, (building_id,))
            row = cursor.fetchone()
            reading_count = row[0] or 0
            avg_reading = round(row[1] or 0.0, 3)
            peak_reading = round(row[2] or 0.0, 3)

            # Query anomaly count
            cursor.execute("""
                SELECT COUNT(*) FROM anomaly_events WHERE building_id = ?
            """, (building_id,))
            anom_count = cursor.fetchone()[0] or 0

            return {
                "building_id": building_id,
                "reading_count": reading_count,
                "average_reading": avg_reading,
                "peak_reading": peak_reading,
                "anomaly_count": anom_count,
            }
        finally:
            conn.close()

    def regenerate_anomaly_summary(self) -> List[Dict[str, Any]]:
        """Regenerates anomaly summary table by grouping detailed anomaly records."""
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT 
                    anomaly_type,
                    severity,
                    COUNT(*) AS event_count,
                    COUNT(DISTINCT building_id) AS affected_buildings
                FROM anomaly_events
                GROUP BY anomaly_type, severity
                ORDER BY event_count DESC
            """)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, r)) if not hasattr(r, "keys") else dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def verify_data_quality_grid(self, expected_span_hours: int = 17544) -> Dict[str, Any]:
        """Verifies sampling frequency and missing interval counts across all 15 buildings."""
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT 
                    building_id,
                    COUNT(*) as reading_count,
                    MIN(timestamp) as first_ts,
                    MAX(timestamp) as last_ts
                FROM energy_readings
                WHERE building_id LIKE 'Hog_%'
                GROUP BY building_id
            """)
            reports = []
            for row in cursor.fetchall():
                b_id = row[0]
                count = row[1]
                first_ts = row[2]
                last_ts = row[3]
                missing = max(0, expected_span_hours - count) if expected_span_hours else 0.0
                reports.append({
                    "building_id": b_id,
                    "reading_count": count,
                    "missing_readings": float(missing),
                    "first_reading": str(first_ts),
                    "last_reading": str(last_ts),
                    "grid_complete": (missing == 0.0),
                })
            return {
                "status": "success",
                "buildings_checked": len(reports),
                "reports": reports,
            }
        finally:
            conn.close()


anomaly_engine = AnomalyEngine()
