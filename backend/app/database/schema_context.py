from typing import Dict, List, Set


class SchemaContext:
    """Provides schema metadata and LLM system context for natural language to SQL."""

    def __init__(self):
        # Database schema representation finalized by Person 2
        self.tables = {
            "buildings": {
                "description": "Metadata for campus buildings (15 canonical Hog_* buildings from Building Data Genome Project 2 + legacy mappings).",
                "columns": {
                    "building_id": "TEXT PRIMARY KEY (e.g., 'Hog_education_Donnie', 'Hog_assembly_Colette')",
                    "name": "TEXT (Display name, e.g. 'Donnie Education Hall', 'Colette Performing Arts')",
                    "primary_use": "TEXT (e.g., 'Education', 'Industrial', 'Assembly', 'Lodging', 'Food Service')",
                    "site_id": "TEXT (Site code, e.g., 'Hog')",
                    "square_feet": "REAL (Gross floor area in square feet)",
                    "year_built": "INTEGER (Construction year)",
                    "floor_count": "INTEGER (Number of floors)",
                },
            },
            "energy_readings": {
                "description": (
                    "Hourly interval electricity consumption records for each building. "
                    "Data is recorded every hour. 'consumption_kwh' represents the interval "
                    "energy used during that hour in kilowatt-hours (kWh)."
                ),
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "building_id": "TEXT FOREIGN KEY -> buildings(building_id)",
                    "timestamp": "TIMESTAMP (Hourly timestamp in format 'YYYY-MM-DD HH:00:00')",
                    "meter_type": "TEXT (Meter type, e.g. 'electricity')",
                    "consumption_kwh": "REAL (Interval energy consumption in kWh)",
                },
            },
            "anomaly_events": {
                "description": "Historical anomaly detection events (high consumption and flatline records).",
                "columns": {
                    "anomaly_id": "INTEGER PRIMARY KEY",
                    "building_id": "TEXT FOREIGN KEY -> buildings(building_id)",
                    "detected_at": "TIMESTAMP (Timestamp when anomaly was observed)",
                    "anomaly_type": "TEXT ('high_consumption', 'flatline')",
                    "actual_value": "REAL (Recorded reading in kWh)",
                    "baseline_value": "REAL (Expected baseline reading in kWh)",
                    "deviation_pct": "REAL (Percentage deviation from baseline: ((actual - baseline)/baseline)*100)",
                    "severity": "TEXT ('high', 'medium', 'review', 'low')",
                    "details": "TEXT (Explanation of anomaly event)",
                },
            },
            "building_summaries": {
                "description": "Pre-computed 2-year operational summaries across the 15 buildings.",
                "columns": {
                    "building_id": "TEXT PRIMARY KEY FOREIGN KEY -> buildings(building_id)",
                    "reading_count": "INTEGER (Total reading count, typically 17,544)",
                    "average_reading": "REAL (Average hourly consumption in kWh)",
                    "peak_reading": "REAL (Peak hourly consumption in kWh)",
                    "anomaly_count": "INTEGER (Total anomalies recorded for building)",
                },
            },
            "data_quality_reports": {
                "description": "Data completeness and timestamp verification report for each building.",
                "columns": {
                    "building_id": "TEXT PRIMARY KEY FOREIGN KEY -> buildings(building_id)",
                    "reading_count": "INTEGER (Total readings in grid)",
                    "missing_readings": "REAL (Missing reading count)",
                    "first_reading": "TIMESTAMP (First reading timestamp)",
                    "last_reading": "TIMESTAMP (Last reading timestamp)",
                    "sampling_interval_hours": "REAL (Expected hourly interval, 1.0)",
                },
            },
            "flatline_candidates": {
                "description": "Candidate meter freeze events where identical readings were recorded for 24+ consecutive hours.",
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "building_id": "TEXT FOREIGN KEY -> buildings(building_id)",
                    "start_time": "TIMESTAMP",
                    "end_time": "TIMESTAMP",
                    "reading_count": "INTEGER (Duration in hours, e.g. 125 hours)",
                    "energy_value": "REAL (Constant kWh recorded)",
                    "status": "TEXT ('under_investigation', 'verified')",
                },
            },
            "anomaly_summary": {
                "description": "High-level summary of anomaly counts by type and severity.",
                "columns": {
                    "id": "INTEGER PRIMARY KEY",
                    "anomaly_type": "TEXT ('high_consumption', 'flatline')",
                    "severity": "TEXT ('high', 'medium', 'review')",
                    "event_count": "INTEGER",
                    "affected_buildings": "INTEGER",
                },
            },
        }

    def get_allowed_schema_whitelist(self) -> Dict[str, Set[str]]:
        """Returns allowed tables and columns dictionary for SQLValidator."""
        return {
            table_name: set(table_meta["columns"].keys())
            for table_name, table_meta in self.tables.items()
        }

    def update_schema(self, new_tables: dict) -> None:
        """Allows updating or registering the finalized schema."""
        self.tables = new_tables

    def get_llm_schema_prompt(self) -> str:
        """Generates formatted schema documentation for injection into LLM prompts."""
        lines: List[str] = [
            "### Database Schema Information:",
            "Dialect: SQL (Standard / SQLite / PostgreSQL compatible)",
            "",
        ]
        for tbl, meta in self.tables.items():
            lines.append(f"Table: {tbl}")
            lines.append(f"Description: {meta['description']}")
            lines.append("Columns:")
            for col, col_desc in meta["columns"].items():
                lines.append(f"  - {col}: {col_desc}")
            lines.append("")

        lines.extend([
            "### Critical Query Guidelines:",
            "1. Only generate standard SELECT statements.",
            "2. Table names and column names must strictly match the schema above.",
            "3. 'consumption_kwh' represents interval electricity consumption (kWh) recorded hourly. To find total consumption over a period, use SUM(consumption_kwh).",
            "4. For comparisons across buildings, GROUP BY building_id (or building name) and ORDER BY SUM(consumption_kwh) DESC.",
            "5. Timestamps are formatted as 'YYYY-MM-DD HH:MM:SS'. Use standard date functions or string comparisons.",
            "6. Always include a sensible LIMIT (e.g. LIMIT 10 or LIMIT 50). Never omit LIMIT.",
            "7. Never use DROP, DELETE, UPDATE, INSERT, ALTER, or administrative functions.",
        ])
        return "\n".join(lines)


schema_context = SchemaContext()
