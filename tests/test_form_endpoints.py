"""Tests for POST /v1/form/log, GET /v1/form/history, GET /v1/form/trend."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app
from tests.conftest import auth_headers


def _create_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), testing_session


def _make_user(session_local):
    db = session_local()
    user = models.User(email="form_test@test.dev", training_days=3)
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


# ---------------------------------------------------------------------------
# POST /form/log
# ---------------------------------------------------------------------------

def test_form_log_saves_entry():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/log",
        json={"user_id": user_id, "exercise_key": "squat", "feeling": 8, "note": "felt solid"},
        headers=auth_headers(user_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exercise_key"] == "squat"
    assert body["feeling"] == 8
    assert body["note"] == "felt solid"
    assert "id" in body
    assert "created_at" in body
    app.dependency_overrides = {}


def test_form_log_without_note():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/log",
        json={"user_id": user_id, "exercise_key": "bench_press", "feeling": 5},
        headers=auth_headers(user_id),
    )
    assert response.status_code == 200
    assert response.json()["note"] is None
    app.dependency_overrides = {}


def test_form_log_rejects_feeling_out_of_range():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    for bad_feeling in [0, 11]:
        response = client.post(
            "/v1/form/log",
            json={"user_id": user_id, "exercise_key": "squat", "feeling": bad_feeling},
            headers=auth_headers(user_id),
        )
        assert response.status_code == 422
    app.dependency_overrides = {}


def test_form_log_rejects_empty_exercise_key():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/log",
        json={"user_id": user_id, "exercise_key": "", "feeling": 7},
        headers=auth_headers(user_id),
    )
    assert response.status_code == 422
    app.dependency_overrides = {}


def test_form_log_404_unknown_user():
    client, _ = _create_client()
    response = client.post(
        "/v1/form/log",
        json={"user_id": 9999, "exercise_key": "squat", "feeling": 7},
        headers=auth_headers(9999),
    )
    assert response.status_code == 404
    app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# GET /form/history/{user_id}
# ---------------------------------------------------------------------------

def test_form_history_returns_sessions():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    for i in range(3):
        client.post(
            "/v1/form/log",
            json={"user_id": user_id, "exercise_key": "squat", "feeling": 6 + i},
            headers=auth_headers(user_id),
        )

    response = client.get(f"/v1/form/history/{user_id}", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert len(body["sessions"]) == 3
    first = body["sessions"][0]
    assert "feeling" in first
    assert "exercise_key" in first
    assert "created_at" in first
    app.dependency_overrides = {}


def test_form_history_filtered_by_exercise_key():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    client.post(
        "/v1/form/log",
        json={"user_id": user_id, "exercise_key": "squat", "feeling": 7},
        headers=auth_headers(user_id),
    )
    client.post(
        "/v1/form/log",
        json={"user_id": user_id, "exercise_key": "bench_press", "feeling": 6},
        headers=auth_headers(user_id),
    )

    response = client.get(f"/v1/form/history/{user_id}?exercise_key=squat", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert all(s["exercise_key"] == "squat" for s in body["sessions"])
    assert len(body["sessions"]) == 1
    app.dependency_overrides = {}


def test_form_history_404_for_unknown_user():
    client, _ = _create_client()
    response = client.get("/v1/form/history/9999", headers=auth_headers(9999))
    assert response.status_code == 404
    app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# GET /form/trend/{user_id}
# ---------------------------------------------------------------------------

def test_form_trend_returns_data():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    for feeling in [4, 5, 6, 7, 8]:
        client.post(
            "/v1/form/log",
            json={"user_id": user_id, "exercise_key": "squat", "feeling": feeling},
            headers=auth_headers(user_id),
        )

    response = client.get(f"/v1/form/trend/{user_id}?exercise_key=squat", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert body["exercise_key"] == "squat"
    assert len(body["points"]) == 5
    assert body["avg_feeling"] > 0
    assert body["trend"] in ("improving", "stable", "declining")
    app.dependency_overrides = {}


def test_form_trend_empty_for_no_sessions():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.get(f"/v1/form/trend/{user_id}?exercise_key=bench_press", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["points"] == []
    assert body["avg_feeling"] == 0.0
    assert body["trend"] == "stable"
    app.dependency_overrides = {}


def test_form_trend_404_for_unknown_user():
    client, _ = _create_client()
    response = client.get("/v1/form/trend/9999?exercise_key=squat", headers=auth_headers(9999))
    assert response.status_code == 404
    app.dependency_overrides = {}
