from sqlalchemy import text
from sqlalchemy.orm import Session
from app.utils.exercise_key import normalize_exercise_key


def backfill_exercise_key(db: Session) -> int:
    updates = 0
    set_logs = db.execute(
        text(
            "SELECT id, exercise FROM set_logs "
            "WHERE (exercise_key IS NULL OR exercise_key = '') "
            "AND exercise IS NOT NULL AND exercise != ''"
        )
    ).fetchall()
    for row in set_logs:
        key = normalize_exercise_key(row.exercise)
        db.execute(
            text("UPDATE set_logs SET exercise_key = :key WHERE id = :id"),
            {"key": key, "id": row.id},
        )
        updates += 1

    rec_logs = db.execute(
        text(
            "SELECT id, exercise FROM recommendation_logs "
            "WHERE (exercise_key IS NULL OR exercise_key = '') "
            "AND exercise IS NOT NULL AND exercise != ''"
        )
    ).fetchall()
    for row in rec_logs:
        key = normalize_exercise_key(row.exercise)
        db.execute(
            text("UPDATE recommendation_logs SET exercise_key = :key WHERE id = :id"),
            {"key": key, "id": row.id},
        )
        updates += 1

    if updates:
        db.commit()
    return updates
