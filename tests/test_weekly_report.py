"""
Tests for the weekly AI coaching report endpoint.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app
from tests.conftest import auth_headers


def _make_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SL = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override():
        db = SL()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), SL


@pytest.fixture()
def ctx():
    client, SL = _make_client()
    yield client, SL
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# GET /v1/users/{user_id}/weekly-report
# ---------------------------------------------------------------------------

class TestWeeklyReport:
    def _make_user(self, SL, experience="intermediate", goal="muscle_gain"):
        with SL() as db:
            u = models.User(
                email=f"report{id(SL)}@test.com",
                experience_level=experience,
                goal=goal,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            return u.id

    def test_empty_week_returns_report(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        body = r.json()
        assert "ai_report" in body
        assert "source" in body
        assert body["source"] in ("ai", "rule_based")
        assert body["sessions_count"] == 0

    def test_returns_required_fields(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        body = r.json()
        required = [
            "period_start", "period_end", "sessions_count",
            "total_volume_kg", "form_avg_score", "top_exercise",
            "achievements_earned", "body_weight_change_kg",
            "ai_report", "source",
        ]
        for key in required:
            assert key in body, f"Missing key: {key}"

    def test_counts_sessions_in_last_7_days(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        now = datetime.utcnow()
        with SL() as db:
            # 3 sessions this week
            for i in range(3):
                db.add(models.WorkoutSession(
                    user_id=uid,
                    session_key=str(uuid.uuid4()),
                    started_at=now - timedelta(days=i),
                    total_sets=5,
                    total_volume=500.0,
                ))
            # 1 session last month — should NOT be counted
            db.add(models.WorkoutSession(
                user_id=uid,
                session_key=str(uuid.uuid4()),
                started_at=now - timedelta(days=30),
                total_sets=4,
                total_volume=400.0,
            ))
            db.commit()
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        body = r.json()
        assert body["sessions_count"] == 3
        assert body["total_volume_kg"] == 1500.0

    def test_body_weight_change_calculated(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        now = datetime.utcnow()
        with SL() as db:
            db.add(models.BodyWeightLog(user_id=uid, weight_kg=80.0, measured_at=now - timedelta(days=8)))
            db.add(models.BodyWeightLog(user_id=uid, weight_kg=79.2, measured_at=now - timedelta(days=1)))
            db.commit()
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        assert r.json()["body_weight_change_kg"] is not None

    def test_form_avg_score_included(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        now = datetime.utcnow()
        with SL() as db:
            for score in [80.0, 85.0, 90.0]:
                db.add(models.FormAnalysisSession(
                    user_id=uid,
                    exercise_key="squat",
                    overall_score=score,
                    depth_score=score,
                    torso_angle_score=score,
                    symmetry_score=score,
                    tempo_score=score,
                    bar_path_score=score,
                    created_at=now - timedelta(days=2),
                ))
            db.commit()
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        assert r.json()["form_avg_score"] == 85.0

    def test_achievements_counted(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        now = datetime.utcnow()
        with SL() as db:
            db.add(models.FormAchievement(
                user_id=uid,
                achievement_type="first_session",
                exercise_key="squat",
                score=80.0,
                created_at=now - timedelta(days=1),
            ))
            db.commit()
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        assert r.json()["achievements_earned"] == 1

    def test_report_text_not_empty(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        assert len(r.json()["ai_report"]) > 50

    def test_no_auth_returns_401(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        r = client.get(f"/v1/users/{uid}/weekly-report")
        assert r.status_code == 401

    def test_wrong_user_returns_403(self, ctx):
        client, SL = ctx
        uid = self._make_user(SL)
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid + 999))
        assert r.status_code == 403

    def test_unknown_user_returns_404(self, ctx):
        client, _ = ctx
        r = client.get("/v1/users/99999/weekly-report", headers=auth_headers(99999))
        assert r.status_code == 404

    def test_rule_based_fallback_when_no_api_key(self, ctx):
        """Without an API key the service should always use rule_based."""
        client, SL = ctx
        uid = self._make_user(SL)
        r = client.get(f"/v1/users/{uid}/weekly-report", headers=auth_headers(uid))
        assert r.status_code == 200
        # In test environment, no API key → always rule_based
        assert r.json()["source"] == "rule_based"
