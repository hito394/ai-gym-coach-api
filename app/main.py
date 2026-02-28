from fastapi import FastAPI
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.api.routes.workouts import router as workouts_router
from app.api.routes.chat import router as chat_router
from app.api.routes.progression import router as progression_router
from app.db.session import engine
from app.db.base import Base

settings = get_settings()
configure_logging()

app = FastAPI(title="AI Gym Coach API")

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(workouts_router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(progression_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
