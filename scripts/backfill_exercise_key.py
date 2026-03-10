from app.db.session import SessionLocal
from app.db.backfill import backfill_exercise_key


def main() -> None:
    db = SessionLocal()
    try:
        updated = backfill_exercise_key(db)
        print(f"Backfilled exercise_key for {updated} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
