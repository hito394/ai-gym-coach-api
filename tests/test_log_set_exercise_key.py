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


def test_log_set_with_same_client_id_updates_existing_record():
    client, session_local = _create_client()
    db = session_local()
    user = _create_user(db)
    db.close()

    first = {
        "user_id": user.id,
        "client_id": "abc-update-1",
        "exercise_name": "Bench Press",
        "exercise_key": "bench_press",
        "reps": 5,
        "weight": 100.0,
        "rpe": 8.0,
    }
    response_first = client.post("/v1/workouts/log_set", json=first)
    assert response_first.status_code == 200
    first_body = response_first.json()

    second = {
        "user_id": user.id,
        "client_id": "abc-update-1",
        "exercise_name": "Bench Press",
        "exercise_key": "bench_press",
        "reps": 6,
        "weight": 102.5,
        "rpe": 8.5,
    }
    response_second = client.post("/v1/workouts/log_set", json=second)
    assert response_second.status_code == 200
    second_body = response_second.json()

    assert second_body["id"] == first_body["id"]
    assert second_body["reps"] == 6
    assert second_body["weight"] == 102.5
    assert second_body["rpe"] == 8.5

    app.dependency_overrides = {}


def test_delete_set_removes_client_id_log_idempotently():
    client, session_local = _create_client()
    db = session_local()
    user = _create_user(db)
    db.close()

    payload = {
        "user_id": user.id,
        "client_id": "abc-delete-1",
        "exercise_name": "Squat",
        "exercise_key": "squat",
        "reps": 5,
        "weight": 120.0,
    }
    create_response = client.post("/v1/workouts/log_set", json=payload)
    assert create_response.status_code == 200

    delete_payload = {"user_id": user.id, "client_id": "abc-delete-1"}
    delete_response = client.post("/v1/workouts/delete_set", json=delete_payload)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "client_id": "abc-delete-1"}

    # Deleting the same client_id again should remain successful.
    delete_again = client.post("/v1/workouts/delete_set", json=delete_payload)
    assert delete_again.status_code == 200
    assert delete_again.json() == {"deleted": True, "client_id": "abc-delete-1"}

    app.dependency_overrides = {}
