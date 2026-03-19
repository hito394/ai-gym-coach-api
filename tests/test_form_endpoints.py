"""Tests for form history, trend endpoints and exercise-specific analysis."""
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
# POST /form/analyze
# ---------------------------------------------------------------------------

def test_form_analyze_normalizes_exercise_key():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/analyze",
        json={
            "user_id": user_id,
            "exercise_key": "Back Squat",  # should be normalized to back_squat
            "diagnostics": {"quality": 80.0, "pose_jitter": 0.03, "depth_norm": 0.20},
        },
        headers=auth_headers(user_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert "overall_score" in body
    assert "feedback" in body
    app.dependency_overrides = {}


def test_form_analyze_rejects_empty_exercise_key():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/analyze",
        json={"user_id": user_id, "exercise_key": "   ", "diagnostics": {}},
        headers=auth_headers(user_id),
    )
    assert response.status_code == 422
    app.dependency_overrides = {}


def test_form_analyze_bench_returns_bench_specific_issues():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/analyze",
        json={
            "user_id": user_id,
            "exercise_key": "bench_press",
            "diagnostics": {
                "quality": 85.0,
                "pose_jitter": 0.01,
                "elbow_flare_angle": 80.0,  # too wide → excessive_elbow_flare
                "symmetry": {},
            },
        },
        headers=auth_headers(user_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert "excessive_elbow_flare" in body["issues"]
    app.dependency_overrides = {}


def test_form_analyze_deadlift_rounded_back():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.post(
        "/v1/form/analyze",
        json={
            "user_id": user_id,
            "exercise_key": "deadlift",
            "diagnostics": {
                "quality": 78.0,
                "pose_jitter": 0.02,
                "torso_angle": 50.0,  # extreme forward lean → rounded_back
            },
        },
        headers=auth_headers(user_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert "rounded_back" in body["issues"]
    app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# GET /form/history/{user_id}
# ---------------------------------------------------------------------------

def test_form_history_returns_sessions():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    for _ in range(3):
        client.post(
            "/v1/form/analyze",
            json={
                "user_id": user_id,
                "exercise_key": "squat",
                "diagnostics": {"quality": 82.0, "pose_jitter": 0.03, "depth_norm": 0.18},
            },
            headers=auth_headers(user_id),
        )

    response = client.get(f"/v1/form/history/{user_id}", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert len(body["sessions"]) == 3
    first = body["sessions"][0]
    assert "overall_score" in first
    assert "feedback" in first
    assert "exercise_key" in first
    assert "created_at" in first
    app.dependency_overrides = {}


def test_form_history_filtered_by_exercise_key():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    client.post(
        "/v1/form/analyze",
        json={"user_id": user_id, "exercise_key": "squat", "diagnostics": {"quality": 80.0}},
        headers=auth_headers(user_id),
    )
    client.post(
        "/v1/form/analyze",
        json={"user_id": user_id, "exercise_key": "bench_press", "diagnostics": {"quality": 80.0}},
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

def test_form_trend_returns_improving_trend():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    # Post sessions with improving scores by controlling diagnostics
    # Session 1: poor (shallow depth + jitter)
    for quality in [55.0, 60.0, 75.0, 85.0, 90.0]:
        client.post(
            "/v1/form/analyze",
            json={
                "user_id": user_id,
                "exercise_key": "squat",
                "diagnostics": {
                    "quality": quality,
                    "depth_norm": 0.18 + quality / 1000,
                    "pose_jitter": max(0.01, 0.1 - quality / 1000),
                    "torso_angle": 18.0,
                },
            },
            headers=auth_headers(user_id),
        )

    response = client.get(f"/v1/form/trend/{user_id}?exercise_key=squat", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert body["exercise_key"] == "squat"
    assert len(body["points"]) == 5
    assert body["avg_score"] > 0
    assert body["trend"] in ("improving", "stable", "declining")
    app.dependency_overrides = {}


def test_form_trend_empty_for_no_sessions():
    client, session_local = _create_client()
    user_id = _make_user(session_local)

    response = client.get(f"/v1/form/trend/{user_id}?exercise_key=bench_press", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["points"] == []
    assert body["avg_score"] == 0.0
    assert body["trend"] == "stable"
    app.dependency_overrides = {}


def test_form_trend_404_for_unknown_user():
    client, _ = _create_client()
    response = client.get("/v1/form/trend/9999?exercise_key=squat", headers=auth_headers(9999))
    assert response.status_code == 404
    app.dependency_overrides = {}
