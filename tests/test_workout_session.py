"""
Tests for workout session management and AI menu generation (fallback path).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


@pytest.fixture
def ctx():
    client, sl = _make_client()
    yield client, sl
    app.dependency_overrides = {}


def _create_user(sl, training_days=4, experience="intermediate", goal="strength"):
    db = sl()
    u = models.User(
        email="session_test@test.dev",
        training_days=training_days,
        experience_level=experience,
        goal=goal,
        equipment=["barbell", "dumbbell"],
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

class TestSessionLifecycle:
    def test_start_session_returns_session_key(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        resp = client.post("/v1/workouts/sessions", json={"user_id": uid})
        assert resp.status_code == 200
        data = resp.json()
        assert "session_key" in data
        assert data["is_active"] is True
        assert data["total_sets"] == 0
        assert data["total_volume"] == 0.0

    def test_start_session_404_unknown_user(self, ctx):
        client, _ = ctx
        resp = client.post("/v1/workouts/sessions", json={"user_id": 99999})
        assert resp.status_code == 404

    def test_log_set_in_session(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]

        resp = client.post(f"/v1/workouts/sessions/{sk}/sets", json={
            "exercise_key": "squat",
            "reps": 5,
            "weight": 100.0,
            "rpe": 8.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["exercise_key"] == "squat"
        assert data["reps"] == 5
        assert data["weight"] == 100.0

    def test_session_totals_update_after_sets(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]

        for i in range(3):
            client.post(f"/v1/workouts/sessions/{sk}/sets", json={
                "exercise_key": "bench_press",
                "reps": 8,
                "weight": 80.0,
            })

        session = client.get(f"/v1/workouts/sessions/{sk}").json()
        assert session["total_sets"] == 3
        assert session["total_volume"] == pytest.approx(3 * 8 * 80.0)

    def test_get_session_includes_sets(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]

        client.post(f"/v1/workouts/sessions/{sk}/sets", json={
            "exercise_key": "deadlift",
            "reps": 3,
            "weight": 150.0,
        })
        session = client.get(f"/v1/workouts/sessions/{sk}").json()
        assert len(session["sets"]) == 1
        assert session["sets"][0]["exercise_key"] == "deadlift"

    def test_finish_session(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]
        client.post(f"/v1/workouts/sessions/{sk}/sets", json={
            "exercise_key": "squat", "reps": 5, "weight": 100.0,
        })

        resp = client.post(f"/v1/workouts/sessions/{sk}/finish", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
        assert data["finished_at"] is not None

    def test_cannot_log_to_finished_session(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]
        client.post(f"/v1/workouts/sessions/{sk}/finish", json={})

        resp = client.post(f"/v1/workouts/sessions/{sk}/sets", json={
            "exercise_key": "squat", "reps": 5, "weight": 100.0,
        })
        assert resp.status_code == 409

    def test_get_active_session(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]

        resp = client.get(f"/v1/workouts/sessions/active/{uid}")
        assert resp.status_code == 200
        assert resp.json()["session_key"] == sk

    def test_active_session_404_when_none(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        resp = client.get(f"/v1/workouts/sessions/active/{uid}")
        assert resp.status_code == 404

    def test_active_session_none_after_finish(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        sk = client.post("/v1/workouts/sessions", json={"user_id": uid}).json()["session_key"]
        client.post(f"/v1/workouts/sessions/{sk}/finish", json={})

        resp = client.get(f"/v1/workouts/sessions/active/{uid}")
        assert resp.status_code == 404

    def test_session_with_plan_id(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        # Create a plan first
        plan_resp = client.post("/v1/workouts/generate", json={
            "profile_id": uid, "split": "ppl",
        })
        plan_id = None
        if plan_resp.status_code == 200:
            # Get the plan id from db
            db = sl()
            plan = db.query(models.WorkoutPlan).filter_by(user_id=uid).first()
            plan_id = plan.id
            db.close()

        resp = client.post("/v1/workouts/sessions", json={
            "user_id": uid, "plan_id": plan_id,
        })
        assert resp.status_code == 200
        if plan_id:
            assert resp.json()["plan_id"] == plan_id

    def test_session_404_invalid_session_key(self, ctx):
        client, _ = ctx
        resp = client.get("/v1/workouts/sessions/nonexistent-key-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Plans listing
# ---------------------------------------------------------------------------

class TestPlansListing:
    def test_list_plans_empty(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        resp = client.get(f"/v1/workouts/plans/{uid}")
        assert resp.status_code == 200
        assert resp.json()["plans"] == []

    def test_list_plans_after_generate(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        client.post("/v1/workouts/generate", json={"profile_id": uid, "split": "ppl"})
        resp = client.get(f"/v1/workouts/plans/{uid}")
        assert resp.status_code == 200
        plans = resp.json()["plans"]
        assert len(plans) >= 1
        assert plans[0]["source"] == "rule_based"

    def test_list_plans_includes_days(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        client.post("/v1/workouts/generate", json={"profile_id": uid, "split": "full_body"})
        plans = client.get(f"/v1/workouts/plans/{uid}").json()["plans"]
        assert len(plans[0]["days"]) > 0

    def test_list_plans_404_unknown_user(self, ctx):
        client, _ = ctx
        resp = client.get("/v1/workouts/plans/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AI menu generation (no API key → falls back to rule-based)
# ---------------------------------------------------------------------------

class TestAIMenuGeneration:
    def test_generate_ai_falls_back_to_rule_based_without_key(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        resp = client.post("/v1/workouts/generate-ai", json={
            "profile_id": uid,
            "split": "ppl",
            "readiness_score": 0.8,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "days" in data
        assert len(data["days"]) > 0

    def test_generate_ai_404_unknown_user(self, ctx):
        client, _ = ctx
        resp = client.post("/v1/workouts/generate-ai", json={
            "profile_id": 99999, "split": "ppl",
        })
        assert resp.status_code == 404

    def test_generate_ai_invalid_split(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        resp = client.post("/v1/workouts/generate-ai", json={
            "profile_id": uid, "split": "bro_split",
        })
        assert resp.status_code == 422

    def test_generate_ai_saves_to_db(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        client.post("/v1/workouts/generate-ai", json={"profile_id": uid, "split": "upper_lower"})
        db = sl()
        count = db.query(models.WorkoutPlan).filter_by(user_id=uid).count()
        db.close()
        assert count == 1


# ---------------------------------------------------------------------------
# AI menu service (unit, no API call)
# ---------------------------------------------------------------------------

class TestAIMenuService:
    def test_returns_none_without_api_key(self):
        from app.services.ai_menu import generate_ai_menu
        result = generate_ai_menu(
            split="ppl", training_days=3, experience="intermediate",
            goal="strength", equipment=["barbell"],
            week_index=1, block_index=1, readiness_score=0.8,
            api_key=None,
        )
        assert result is None

    def test_prompt_contains_experience_and_goal(self):
        from app.services.ai_menu import _build_prompt
        prompt = _build_prompt(
            split="ppl", training_days=3, experience="advanced",
            goal="strength", equipment=["barbell", "dumbbell"],
            week_index=2, block_index=1, readiness_score=0.9,
            recent_muscle_groups=["legs"],
        )
        assert "advanced" in prompt
        assert "strength" in prompt
        assert "legs" in prompt    # recovery avoidance note

    def test_fatigue_note_added_when_low_readiness(self):
        from app.services.ai_menu import _build_prompt
        prompt = _build_prompt(
            split="full_body", training_days=3, experience="beginner",
            goal="fat_loss", equipment=["bodyweight"],
            week_index=1, block_index=1, readiness_score=0.3,
        )
        assert "fatigued" in prompt.lower() or "reduce" in prompt.lower()
