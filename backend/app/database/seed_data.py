from backend.app.database.ingest_person2_data import ingest_person2_data


def seed_database(db_path: str = None) -> None:
    """Populates SQLite database with Person 2 canonical tables and readings."""
    ingest_person2_data(db_path)


if __name__ == "__main__":
    seed_database()
