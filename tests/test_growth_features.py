"""
Tests for growth & continuity features:
  - Achievement detection (process_session)
  - Personal best tracking
  - Dashboard endpoint
  - Form achievements endpoint
  - Improved keypoint analysis accuracy
  - Category-specific score weights
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
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_test_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), SessionLocal


@pytest.fixture
def ctx():
    client, SessionLocal = _make_test_client()
    yield client, SessionLocal
    app.dependency_overrides = {}


def _create_user(sl, experience_level="intermediate", goal="strength"):
    db = sl()
    u = models.User(email="growth@test.dev", training_days=3,
                    experience_level=experience_level, goal=goal)
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def _post_analyze(client, user_id, exercise_key="squat", score_hint=80.0):
    """Log a workout feeling entry (replaces old form/analyze call)."""
    return client.post("/v1/form/log", json={
        "user_id": user_id,
        "exercise_key": exercise_key,
        "feeling": 8,
        "note": "test session",
    }, headers=auth_headers(user_id))


# ---------------------------------------------------------------------------
# Achievement detection (unit-level via service layer)
# ---------------------------------------------------------------------------

class TestAchievementService:
    def test_first_session_awarded(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        resp = _post_analyze(client, uid)
        assert resp.status_code == 200

        db = sl()
        achs = db.query(models.FormAchievement).filter_by(
            user_id=uid, achievement_type="first_session"
        ).all()
        db.close()
        assert len(achs) == 1

    def test_first_session_only_once(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        _post_analyze(client, uid)
        _post_analyze(client, uid)

        db = sl()
        count = db.query(models.FormAchievement).filter_by(
            user_id=uid, achievement_type="first_session"
        ).count()
        db.close()
        assert count == 1

    def test_personal_best_created_on_first_session(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        _post_analyze(client, uid)

        db = sl()
        pb = db.query(models.FormPersonalBest).filter_by(
            user_id=uid, exercise_key="squat"
        ).first()
        db.close()
        assert pb is not None
        assert pb.best_score > 0

    def test_personal_best_updated_when_score_improves(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        # first session
        _post_analyze(client, uid)

        db = sl()
        pb1 = db.query(models.FormPersonalBest).filter_by(
            user_id=uid, exercise_key="squat"
        ).first()
        first_best = pb1.best_score
        db.close()

        # inject a second session with explicitly higher score directly
        db = sl()
        session = models.FormAnalysisSession(
            user_id=uid, exercise_key="squat",
            model_name="test", model_version="v0",
            depth_score=98, torso_angle_score=98,
            symmetry_score=98, tempo_score=98, bar_path_score=98,
            overall_score=99.0, issues=[], diagnostics={}, feedback="great",
        )
        db.add(session)
        db.flush()
        from app.services.achievements import process_session
        process_session(db, session)
        db.commit()

        pb2 = db.query(models.FormPersonalBest).filter_by(
            user_id=uid, exercise_key="squat"
        ).first()
        assert pb2.best_score == 99.0
        db.close()

    def test_ten_sessions_achievement(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        for _ in range(10):
            _post_analyze(client, uid)

        db = sl()
        count = db.query(models.FormAchievement).filter_by(
            user_id=uid, achievement_type="ten_sessions"
        ).count()
        db.close()
        assert count == 1

    def test_improving_streak_detection(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)

        db = sl()
        for score in [65.0, 75.0, 85.0]:
            s = models.FormAnalysisSession(
                user_id=uid, exercise_key="deadlift",
                model_name="test", model_version="v0",
                depth_score=score, torso_angle_score=score,
                symmetry_score=score, tempo_score=score, bar_path_score=score,
                overall_score=score, issues=[], diagnostics={}, feedback="ok",
            )
            db.add(s)
            db.flush()
            from app.services.achievements import process_session
            process_session(db, s)
        db.commit()

        count = db.query(models.FormAchievement).filter_by(
            user_id=uid, achievement_type="improving_streak"
        ).count()
        db.close()
        assert count == 1


# ---------------------------------------------------------------------------
# Dashboard endpoint
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_returns_expected_keys(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        _post_analyze(client, uid)

        resp = client.get(f"/v1/users/{uid}/dashboard", headers=auth_headers(uid))
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert "streak_days" in data
        assert "total_sessions" in data
        assert "weekly" in data
        assert "personal_bests" in data
        assert "exercise_summary" in data
        assert "achievements" in data

    def test_dashboard_total_sessions(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        for _ in range(3):
            _post_analyze(client, uid)

        data = client.get(f"/v1/users/{uid}/dashboard", headers=auth_headers(uid)).json()
        assert data["total_sessions"] == 3

    def test_dashboard_exercise_summary_improvement(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)

        db = sl()
        for score in [60.0, 80.0]:
            s = models.FormAnalysisSession(
                user_id=uid, exercise_key="bench_press",
                model_name="test", model_version="v0",
                depth_score=score, torso_angle_score=score,
                symmetry_score=score, tempo_score=score, bar_path_score=score,
                overall_score=score, issues=[], diagnostics={}, feedback="ok",
            )
            db.add(s)
            db.flush()
            from app.services.achievements import process_session
            process_session(db, s)
        db.commit()
        db.close()

        data = client.get(f"/v1/users/{uid}/dashboard", headers=auth_headers(uid)).json()
        summary = {e["exercise_key"]: e for e in data["exercise_summary"]}
        bp = summary["bench_press"]
        assert bp["best_score"] == 80.0
        # improvement = latest - first = 80 - 60 = 20
        assert bp["improvement"] == 20.0

    def test_dashboard_404_unknown_user(self, ctx):
        client, _ = ctx
        assert client.get("/v1/users/99999/dashboard", headers=auth_headers(99999)).status_code == 404

    def test_dashboard_achievements_populated(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        _post_analyze(client, uid)

        data = client.get(f"/v1/users/{uid}/dashboard", headers=auth_headers(uid)).json()
        assert len(data["achievements"]) >= 1
        first = data["achievements"][0]
        assert "type" in first
        assert "earned_at" in first


# ---------------------------------------------------------------------------
# Form achievements endpoint
# ---------------------------------------------------------------------------

class TestFormAchievementsEndpoint:
    def test_achievements_endpoint_empty(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)

        resp = client.get(f"/v1/form/achievements/{uid}", headers=auth_headers(uid))
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert data["achievements"] == []

    def test_achievements_endpoint_returns_earned(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        _post_analyze(client, uid)

        resp = client.get(f"/v1/form/achievements/{uid}", headers=auth_headers(uid))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["achievements"]) >= 1

    def test_achievements_404_unknown_user(self, ctx):
        client, _ = ctx
        assert client.get("/v1/form/achievements/99999", headers=auth_headers(99999)).status_code == 404


# ---------------------------------------------------------------------------
# Keypoint analysis accuracy improvements
# ---------------------------------------------------------------------------

class TestKeypointAccuracyImprovements:
    """Verify confidence-gating, issue deduplication, and better depth detection."""

    def _kp(self, joints: dict, conf=0.9) -> dict:
        return {name: {"x": xy[0], "y": xy[1], "confidence": conf}
                for name, xy in joints.items()}

    def test_low_confidence_joints_do_not_trigger_issues(self):
        from app.services.keypoint_analysis import analyse_keypoints
        # Knee valgus positions but with very low confidence – should not flag
        kp = {
            "left_shoulder":  {"x": 0.45, "y": 0.25, "confidence": 0.05},
            "right_shoulder": {"x": 0.55, "y": 0.25, "confidence": 0.05},
            "left_hip":       {"x": 0.45, "y": 0.50, "confidence": 0.05},
            "right_hip":      {"x": 0.55, "y": 0.50, "confidence": 0.05},
            "left_knee":      {"x": 0.30, "y": 0.70, "confidence": 0.05},
            "right_knee":     {"x": 0.70, "y": 0.70, "confidence": 0.05},
            "left_ankle":     {"x": 0.40, "y": 0.90, "confidence": 0.05},
            "right_ankle":    {"x": 0.60, "y": 0.90, "confidence": 0.05},
        }
        result = analyse_keypoints(kp, "squat", view="front")
        # Should not flag knee_valgus since joints are below confidence gate
        assert "left_knee_valgus" not in result["issues"]
        assert "right_knee_valgus" not in result["issues"]

    def test_issue_deduplication_no_repeat_keys(self):
        from app.services.keypoint_analysis import analyse_keypoints
        # Bench with extreme elbow flare on both sides
        kp = {
            "left_shoulder":  {"x": 0.40, "y": 0.50, "confidence": 0.9},
            "right_shoulder": {"x": 0.60, "y": 0.50, "confidence": 0.9},
            "left_elbow":     {"x": 0.20, "y": 0.50, "confidence": 0.9},
            "right_elbow":    {"x": 0.80, "y": 0.50, "confidence": 0.9},
            "left_wrist":     {"x": 0.22, "y": 0.55, "confidence": 0.9},
            "right_wrist":    {"x": 0.78, "y": 0.55, "confidence": 0.9},
        }
        result = analyse_keypoints(kp, "bench_press", view="front")
        # The issue key should appear at most once even though both elbows flare
        assert result["issues"].count("excessive_elbow_flare") <= 1

    def test_score_deduction_scales_with_severity(self):
        from app.services.keypoint_analysis import _score_from_issues
        score_clean   = _score_from_issues([])
        score_yellow  = _score_from_issues(["forward_lean"])
        score_red     = _score_from_issues(["rounded_back"])
        assert score_clean == 100.0
        assert score_yellow < score_clean
        assert score_red < score_yellow  # red deducts more than yellow

    def test_good_squat_gives_no_issues(self):
        """
        Perfect deep squat: hips below knees (hip y > knee y in image coords),
        torso upright (shoulders directly above hips), knees tracking over feet.
        """
        from app.services.keypoint_analysis import analyse_keypoints
        kp = {
            # shoulders above hips – torso lean ≈ 0°
            "left_shoulder":  {"x": 0.43, "y": 0.18, "confidence": 0.9},
            "right_shoulder": {"x": 0.57, "y": 0.18, "confidence": 0.9},
            # hips below knee level in image (y=0.68 > knee y=0.62) → deep squat
            "left_hip":       {"x": 0.43, "y": 0.68, "confidence": 0.9},
            "right_hip":      {"x": 0.57, "y": 0.68, "confidence": 0.9},
            # knees track over feet (no valgus)
            "left_knee":      {"x": 0.38, "y": 0.62, "confidence": 0.9},
            "right_knee":     {"x": 0.62, "y": 0.62, "confidence": 0.9},
            "left_ankle":     {"x": 0.38, "y": 0.88, "confidence": 0.9},
            "right_ankle":    {"x": 0.62, "y": 0.88, "confidence": 0.9},
        }
        result = analyse_keypoints(kp, "squat", view="front")
        assert result["issues"] == []
        assert result["overall_score"] == 100.0


# ---------------------------------------------------------------------------
# Category-specific score weights
# ---------------------------------------------------------------------------

class TestCategorySpecificWeights:
    """Torso should be more critical for deadlift than squat."""

    def _make_diag(self, torso_angle: float) -> dict:
        return {
            "quality": 90,
            "depth_norm": 0.20,
            "torso_angle": torso_angle,
            "asymmetry": 1.0,
            "pose_jitter": 0.02,
        }

    def test_bad_torso_hurts_deadlift_more_than_squat(self):
        from app.services.form_analysis import analyze_form_diagnostics

        bad_torso_diag = self._make_diag(torso_angle=40)
        squat_result    = analyze_form_diagnostics(bad_torso_diag, exercise_key="squat")
        deadlift_result = analyze_form_diagnostics(bad_torso_diag, exercise_key="deadlift")

        # Deadlift weights torso at 0.40 vs squat's 0.25
        assert deadlift_result["overall_score"] < squat_result["overall_score"]
