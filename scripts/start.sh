#!/usr/bin/env bash
# Production startup script — runs DB migrations then starts Uvicorn.
set -e

echo "[start.sh] Running DB schema sync..."
python -c "
from app.db.session import engine
from app.db.base import Base
from app.utils.exercise_key import ensure_exercise_key_columns
import app.db.models  # ensure all models are imported
Base.metadata.create_all(bind=engine)
ensure_exercise_key_columns(engine)
print('[start.sh] DB ready.')
"

echo "[start.sh] Starting Uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-2}" \
    --access-log
