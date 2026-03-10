from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.api.deps import get_db
from app.db.base import Base
from app.db import models


def _create_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


def _create_user(db):
    user = models.User(email="test@example.com", training_days=3)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_log_set_persists_provided_exercise_key():
    client, session_local = _create_client()
    db = session_local()
    user = _create_user(db)
    db.close()

    payload = {
        "user_id": user.id,
        "client_id": "abc-123",
        "exercise_name": "Bench Press",
        "exercise_key": "custom_key",
        "reps": 5,
        "weight": 100.0,
    }
    response = client.post("/v1/workouts/log_set", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["exercise_key"] == "custom_key"

    app.dependency_overrides = {}


def test_log_set_computes_exercise_key_from_name():
    client, session_local = _create_client()
    db = session_local()
    user = _create_user(db)
    db.close()

    payload = {
        "user_id": user.id,
        "client_id": "abc-124",
        "exercise_name": "Bench Press",
        "reps": 5,
        "weight": 100.0,
    }
    response = client.post("/v1/workouts/log_set", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["exercise_key"] == "bench_press"

    app.dependency_overrides = {}


def test_log_set_requires_exercise_key_or_name():
    client, session_local = _create_client()
    db = session_local()
    user = _create_user(db)
    db.close()

    payload = {
        "user_id": user.id,
        "client_id": "abc-125",
        "reps": 5,
        "weight": 100.0,
    }
    response = client.post("/v1/workouts/log_set", json=payload)
    assert response.status_code == 422
    assert "exercise_key or exercise_name is required" in response.text

    app.dependency_overrides = {}
