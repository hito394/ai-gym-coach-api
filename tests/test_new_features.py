"""Tests for exercise directory API, user profile GET, and health check."""
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
# Shared test helpers
# ---------------------------------------------------------------------------

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


def _make_user(session_local, experience_level="intermediate", goal="strength"):
    db = session_local()
    user = models.User(
        email="features_test@test.dev",
        training_days=3,
        experience_level=experience_level,
        goal=goal,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


# ---------------------------------------------------------------------------
# Exercise directory API
# ---------------------------------------------------------------------------

class TestExerciseDirectory:
    def setup_method(self):
        self.client, _ = _create_client()

    def teardown_method(self):
        app.dependency_overrides = {}

    def test_list_exercises_returns_categories(self):
        resp = self.client.get("/v1/exercises")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        for cat in ("squat", "deadlift", "bench", "ohp", "pull", "arms", "core"):
            assert cat in data, f"Expected category '{cat}' in response"

    def test_list_exercises_contains_exercises(self):
        resp = self.client.get("/v1/exercises")
        data = resp.json()
        assert "squat" in data["squat"]
        assert "deadlift" in data["deadlift"]
        assert "bench_press" in data["bench"]

    def test_categories_endpoint(self):
        resp = self.client.get("/v1/exercises/categories")
        assert resp.status_code == 200
        cats = resp.json()
        assert isinstance(cats, list)
        assert len(cats) >= 8

    def test_search_returns_matches(self):
        resp = self.client.get("/v1/exercises/search?q=squat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        keys = [r["key"] for r in data["results"]]
        assert any("squat" in k for k in keys)

    def test_search_by_category_filter(self):
        resp = self.client.get("/v1/exercises/search?q=press&category=bench")
        assert resp.status_code == 200
        data = resp.json()
        for result in data["results"]:
            assert result["category"] == "bench"

    def test_search_no_match_returns_empty(self):
        resp = self.client.get("/v1/exercises/search?q=xyznonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_search_requires_query(self):
        resp = self.client.get("/v1/exercises/search")
        assert resp.status_code == 422

    def test_search_curl_finds_biceps(self):
        resp = self.client.get("/v1/exercises/search?q=curl")
        data = resp.json()
        keys = [r["key"] for r in data["results"]]
        assert "biceps_curl" in keys or any("curl" in k for k in keys)


# ---------------------------------------------------------------------------
# User profile GET
# ---------------------------------------------------------------------------

class TestUserProfileGet:
    def setup_method(self):
        self.client, self.session_local = _create_client()

    def teardown_method(self):
        app.dependency_overrides = {}

    def test_get_profile_returns_user(self):
        user_id = _make_user(self.session_local)
        resp = self.client.get(f"/v1/users/{user_id}/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == user_id
        assert data["experience_level"] == "intermediate"
        assert data["goal"] == "strength"

    def test_get_profile_404_for_missing_user(self):
        resp = self.client.get("/v1/users/99999/profile")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def setup_method(self):
        self.client, _ = _create_client()

    def teardown_method(self):
        app.dependency_overrides = {}

    def test_health_ok(self):
        resp = self.client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"


# ---------------------------------------------------------------------------
# AI feedback service (unit test — no live API call)
# ---------------------------------------------------------------------------

class TestAIFormFeedback:
    def test_returns_none_without_api_key(self):
        from app.services.ai_form_feedback import generate_ai_feedback

        result = generate_ai_feedback(
            exercise_key="squat",
            scores={"overall_score": 75.0, "depth_score": 60.0, "torso_angle_score": 80.0,
                    "symmetry_score": 82.0, "tempo_score": 70.0, "bar_path_score": 75.0},
            issues=["shallow_depth"],
            experience_level="beginner",
            goal="muscle_gain",
            trend="stable",
            api_key=None,
        )
        assert result is None

    def test_returns_none_with_empty_api_key(self):
        from app.services.ai_form_feedback import generate_ai_feedback

        result = generate_ai_feedback(
            exercise_key="deadlift",
            scores={"overall_score": 88.0, "depth_score": 90.0, "torso_angle_score": 85.0,
                    "symmetry_score": 88.0, "tempo_score": 90.0, "bar_path_score": 87.0},
            issues=[],
            api_key="",
        )
        assert result is None

    def test_prompt_contains_exercise_and_scores(self):
        from app.services.ai_form_feedback import _build_prompt

        prompt = _build_prompt(
            exercise_key="bench_press",
            scores={"overall_score": 72.0, "depth_score": 50.0, "torso_angle_score": 85.0,
                    "symmetry_score": 78.0, "tempo_score": 65.0, "bar_path_score": 73.0},
            issues=["tempo_inconsistent"],
            experience_level="advanced",
            goal="strength",
            trend="improving",
        )
        assert "Bench Press" in prompt
        assert "advanced" in prompt
        assert "strength" in prompt
        assert "improving" in prompt
        assert "tempo_inconsistent" in prompt

    def test_issue_severity_classification(self):
        from app.services.ai_form_feedback import _ISSUE_SEVERITY

        assert _ISSUE_SEVERITY["rounded_back"] == "high"
        assert _ISSUE_SEVERITY["shallow_depth"] == "medium"
        assert _ISSUE_SEVERITY["tempo_inconsistent"] == "low"
