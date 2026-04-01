#!/usr/bin/env bash
# Production startup script — runs DB migrations then starts Uvicorn.
set -e

echo "[start.sh] Running DB schema sync..."
python -c "
from app.db.session import engine
from app.db.base import Base
from app.utils.exercise_key import ensure_exercise_key_columns
import app.db.models
from sqlalchemy import text, inspect

# Create any missing tables
Base.metadata.create_all(bind=engine)

# Add missing columns to existing tables (safe ALTER TABLE)
inspector = inspect(engine)
with engine.begin() as conn:
    existing = {c['name'] for c in inspector.get_columns('users')}
    missing = {
        'password_hash': 'ALTER TABLE users ADD COLUMN password_hash VARCHAR',
        'email':         'ALTER TABLE users ADD COLUMN email VARCHAR',
        'age':           'ALTER TABLE users ADD COLUMN age INTEGER',
        'weight_kg':     'ALTER TABLE users ADD COLUMN weight_kg FLOAT',
        'height_cm':     'ALTER TABLE users ADD COLUMN height_cm FLOAT',
        'experience_level': 'ALTER TABLE users ADD COLUMN experience_level VARCHAR',
        'goal':          'ALTER TABLE users ADD COLUMN goal VARCHAR',
        'training_days': 'ALTER TABLE users ADD COLUMN training_days INTEGER',
        'equipment':     'ALTER TABLE users ADD COLUMN equipment JSON',
    }
    for col, sql in missing.items():
        if col not in existing:
            print(f'[start.sh] Adding missing column: {col}')
            conn.execute(text(sql))

ensure_exercise_key_columns(engine)
print('[start.sh] DB ready.')
"

echo "[start.sh] Starting Uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-2}" \
    --access-log
