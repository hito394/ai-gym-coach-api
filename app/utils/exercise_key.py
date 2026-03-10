import re
import unicodedata
from sqlalchemy import text
from sqlalchemy.engine import Engine


NORMALIZE_ALLOWED = re.compile(r"[^a-z0-9 _-]")
WHITESPACE_OR_HYPHEN = re.compile(r"[\s-]+")
UNDERSCORE = re.compile(r"_+")
TRIM_UNDERSCORE = re.compile(r"^_+|_+$")


def normalize_exercise_key(exercise_name: str) -> str:
    """
    Normalize an exercise name into a canonical exercise_key.

    Algorithm (exact order):
    0) normalize to NFKD
    1) lowercase
    2) trim whitespace
    3) replace "&" with "and"
    4) treat slashes as separators (replace "/" with space)
    5) remove punctuation except spaces and underscores
    6) replace any sequence of whitespace or hyphens with a single underscore
    7) collapse multiple underscores
    8) strip leading/trailing underscores

    Examples:
    - "Bench Press" -> "bench_press"
    - "Overhead-Press" -> "overhead_press"
    - "Pull/Up" -> "pull_up"
    """
    if exercise_name is None:
        return ""
    normalized = unicodedata.normalize("NFKD", exercise_name)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("’", "'").replace("‘", "'")
    normalized = normalized.lower().strip()
    normalized = normalized.replace("&", "and")
    normalized = normalized.replace("/", " ")
    normalized = NORMALIZE_ALLOWED.sub("", normalized)
    normalized = WHITESPACE_OR_HYPHEN.sub("_", normalized)
    normalized = UNDERSCORE.sub("_", normalized)
    normalized = TRIM_UNDERSCORE.sub("", normalized)
    return normalized


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(text(f"PRAGMA table_info({table_name})"))
    return any(row[1] == column_name for row in result)


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(text("PRAGMA index_list(set_logs)"))
    return any(row[1] == index_name for row in result)


def _add_column(conn, table_name: str, column_name: str, column_type: str) -> None:
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def ensure_exercise_key_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        if not _column_exists(conn, "set_logs", "exercise_key"):
            _add_column(conn, "set_logs", "exercise_key", "VARCHAR")
        if not _column_exists(conn, "recommendation_logs", "exercise_key"):
            _add_column(conn, "recommendation_logs", "exercise_key", "VARCHAR")
        if not _index_exists(conn, "ix_set_logs_user_exercise_key_performed_at"):
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_set_logs_user_exercise_key_performed_at "
                    "ON set_logs (user_id, exercise_key, performed_at)"
                )
            )
