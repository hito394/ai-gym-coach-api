from datetime import datetime, timedelta

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


def _seed_user_and_logs(session_local):
    db = session_local()
    user = models.User(email="analytics@test.dev", training_days=4, weight_kg=75.0)
    db.add(user)
    db.commit()
    db.refresh(user)

    base = datetime.utcnow() - timedelta(days=21)
    logs = [
        models.SetLog(
            user_id=user.id,
            exercise="Bench Press",
            exercise_key="bench_press",
            reps=5,
            weight=80.0,
            performed_at=base,
        ),
        models.SetLog(
            user_id=user.id,
            exercise="Bench Press",
            exercise_key="bench_press",
            reps=5,
            weight=82.5,
            performed_at=base + timedelta(days=7),
        ),
        models.SetLog(
            user_id=user.id,
            exercise="Bench Press",
            exercise_key="bench_press",
            reps=5,
            weight=85.0,
            performed_at=base + timedelta(days=14),
        ),
        models.SetLog(
            user_id=user.id,
            exercise="Back Squat",
            exercise_key="back_squat",
            reps=5,
            weight=100.0,
            performed_at=base + timedelta(days=14),
        ),
    ]
    db.add_all(logs)
    db.commit()

    # Attach set metadata for history timeline grouping and rest tracking.
    meta_rows = [
        models.SetLogMeta(
            set_log_id=logs[0].id,
            user_id=user.id,
            session_id="session-a",
            rest_seconds=120,
        ),
        models.SetLogMeta(
            set_log_id=logs[1].id,
            user_id=user.id,
            session_id="session-b",
            rest_seconds=90,
        ),
        models.SetLogMeta(
            set_log_id=logs[2].id,
            user_id=user.id,
            session_id="session-b",
            rest_seconds=90,
        ),
        models.SetLogMeta(
            set_log_id=logs[3].id,
            user_id=user.id,
            session_id="session-b",
            rest_seconds=120,
        ),
    ]
    db.add_all(meta_rows)
    db.add(
        models.BodyWeightLog(
            user_id=user.id,
            weight_kg=74.5,
            measured_at=base + timedelta(days=7),
        )
    )
    db.add(
        models.BodyWeightLog(
            user_id=user.id,
            weight_kg=75.2,
            measured_at=base + timedelta(days=14),
        )
    )
    db.commit()
    user_id = user.id
    db.close()
    return user_id


def test_analytics_endpoints_return_expected_shapes():
    client, session_local = _create_client()
    user_id = _seed_user_and_logs(session_local)

    summary_response = client.get(f"/v1/analytics/summary/{user_id}", headers=auth_headers(user_id))
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert "progress_score" in summary
    assert isinstance(summary.get("insights"), list)
    assert len(summary.get("weekly_volume_points", [])) == 8

    progress_response = client.get(f"/v1/analytics/progress/{user_id}", headers=auth_headers(user_id))
    assert progress_response.status_code == 200
    progress = progress_response.json()
    assert progress.get("exercise_key") is not None
    assert len(progress.get("weight_points", [])) == 8
    assert len(progress.get("one_rm_points", [])) == 8

    score_response = client.get(f"/v1/analytics/progress-score/{user_id}", headers=auth_headers(user_id))
    assert score_response.status_code == 200
    score = score_response.json()
    assert 0.0 <= score.get("progress_score", -1.0) <= 100.0

    app.dependency_overrides = {}


def test_form_analyze_returns_feedback_and_scores():
    client, session_local = _create_client()
    db = session_local()
    user = models.User(email="form@test.dev", training_days=3)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()

    payload = {
        "user_id": user.id,
        "exercise_key": "squat",
        "diagnostics": {
            "quality": 82.0,
            "pose_jitter": 0.03,
            "depth_norm": 0.12,
            "knee_valgus_norm": 0.08,
            "torso_angle": 22.0,
            "symmetry": {"knee_angle_diff": 6.0, "hip_angle_diff": 5.0},
            "rep_issues": ["depth_insufficient"],
        },
    }

    response = client.post("/v1/form/analyze", json=payload, headers=auth_headers(payload["user_id"]))
    assert response.status_code == 200
    body = response.json()
    assert "feedback" in body
    assert "overall_score" in body
    assert isinstance(body.get("issues"), list)

    app.dependency_overrides = {}


def test_workout_history_timeline_includes_sets_and_rest_seconds():
    client, session_local = _create_client()
    user_id = _seed_user_and_logs(session_local)

    response = client.get(f"/v1/workouts/history/{user_id}", headers=auth_headers(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user_id
    assert len(body["sessions"]) >= 1

    first_session = body["sessions"][0]
    assert "session_id" in first_session
    assert "entries" in first_session
    assert first_session["total_sets"] >= 1
    assert any("rest_seconds" in entry for entry in first_session["entries"])

    app.dependency_overrides = {}


def test_body_weight_logging_updates_analytics_trend():
    client, session_local = _create_client()
    user_id = _seed_user_and_logs(session_local)

    write_response = client.post(
        f"/v1/users/{user_id}/body-weight",
        json={"weight_kg": 76.0},
        headers=auth_headers(user_id),
    )
    assert write_response.status_code == 200

    summary_response = client.get(f"/v1/analytics/summary/{user_id}", headers=auth_headers(user_id))
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert len(summary.get("body_weight_points", [])) == 8
    assert len(summary.get("exercise_weight_points", [])) == 8
    assert len(summary.get("muscle_group_points", [])) == 8

    app.dependency_overrides = {}
