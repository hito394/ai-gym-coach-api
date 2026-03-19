from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.api.routes.workouts import router as workouts_router
from app.api.routes.chat import router as chat_router
from app.api.routes.progression import router as progression_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.form import router as form_router
from app.api.routes.exercises import router as exercises_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.auth import router as auth_router
from app.api.routes.schedule import router as schedule_router
from app.db.session import engine, SessionLocal
from app.db.base import Base
from app.utils.exercise_key import ensure_exercise_key_columns
from app.db.backfill import backfill_exercise_key

settings = get_settings()
configure_logging()

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="AI Gym Coach API",
    description="Personalised strength training coaching with real-time form analysis.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production via env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Unified error handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger(__name__).exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(workouts_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(progression_router, prefix=settings.api_prefix)
app.include_router(analytics_router, prefix=settings.api_prefix)
app.include_router(form_router, prefix=settings.api_prefix)
app.include_router(exercises_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(schedule_router, prefix=settings.api_prefix)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_exercise_key_columns(engine)
    if os.getenv("BACKFILL_ON_STARTUP", "false").lower() == "true":
        db = SessionLocal()
        try:
            backfill_exercise_key(db)
        finally:
            db.close()
