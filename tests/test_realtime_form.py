"""
Tests for POST /v1/form/realtime – real-time keypoint colour annotation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app
from app.services.keypoint_analysis import analyse_keypoints


# ---------------------------------------------------------------------------
# Test client setup
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


def _make_user(session_local):
    db = session_local()
    user = models.User(email="realtime@test.dev", training_days=3)
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


# ---------------------------------------------------------------------------
# Keypoint fixtures
# ---------------------------------------------------------------------------

def _good_squat_keypoints(view="side"):
    """Upright squat – hips at knee level, no valgus, minimal lean."""
    if view == "front":
        return {
            "left_shoulder":  {"x": 0.60, "y": 0.30, "confidence": 0.95},
            "right_shoulder": {"x": 0.40, "y": 0.30, "confidence": 0.95},
            "left_hip":       {"x": 0.58, "y": 0.55, "confidence": 0.95},
            "right_hip":      {"x": 0.42, "y": 0.55, "confidence": 0.95},
            "left_knee":      {"x": 0.60, "y": 0.70, "confidence": 0.95},
            "right_knee":     {"x": 0.40, "y": 0.70, "confidence": 0.95},
            "left_ankle":     {"x": 0.60, "y": 0.88, "confidence": 0.95},
            "right_ankle":    {"x": 0.40, "y": 0.88, "confidence": 0.95},
        }
    # side view: only one visible side matters
    return {
        "left_shoulder": {"x": 0.50, "y": 0.25, "confidence": 0.95},
        "left_hip":      {"x": 0.48, "y": 0.55, "confidence": 0.95},
        "left_knee":     {"x": 0.52, "y": 0.55, "confidence": 0.95},  # hip ≈ knee level
        "left_ankle":    {"x": 0.54, "y": 0.88, "confidence": 0.95},
    }


def _forward_lean_squat_keypoints():
    """Squat with severe forward lean."""
    return {
        "left_shoulder": {"x": 0.35, "y": 0.30, "confidence": 0.95},
        "right_shoulder": {"x": 0.33, "y": 0.30, "confidence": 0.90},
        "left_hip":      {"x": 0.50, "y": 0.55, "confidence": 0.95},
        "right_hip":     {"x": 0.50, "y": 0.55, "confidence": 0.90},
        "left_knee":     {"x": 0.52, "y": 0.70, "confidence": 0.95},
        "right_knee":    {"x": 0.52, "y": 0.70, "confidence": 0.90},
        "left_ankle":    {"x": 0.54, "y": 0.88, "confidence": 0.95},
        "right_ankle":   {"x": 0.54, "y": 0.88, "confidence": 0.90},
    }


def _knee_valgus_keypoints():
    """Front-view squat with left knee caving inward."""
    return {
        "left_shoulder":  {"x": 0.65, "y": 0.28, "confidence": 0.95},
        "right_shoulder": {"x": 0.35, "y": 0.28, "confidence": 0.95},
        "left_hip":       {"x": 0.63, "y": 0.52, "confidence": 0.95},
        "right_hip":      {"x": 0.37, "y": 0.52, "confidence": 0.95},
        # left knee pulled inward toward center (x smaller than ankle/hip midpoint)
        "left_knee":      {"x": 0.48, "y": 0.68, "confidence": 0.95},
        "right_knee":     {"x": 0.38, "y": 0.68, "confidence": 0.95},
        "left_ankle":     {"x": 0.62, "y": 0.87, "confidence": 0.95},
        "right_ankle":    {"x": 0.38, "y": 0.87, "confidence": 0.95},
    }


def _elbow_flare_bench_keypoints():
    """Bench press with elbows flaring wide (angle > 110°)."""
    return {
        "left_shoulder":  {"x": 0.62, "y": 0.40, "confidence": 0.95},
        "right_shoulder": {"x": 0.38, "y": 0.40, "confidence": 0.95},
        # elbows pushed far out
        "left_elbow":     {"x": 0.80, "y": 0.45, "confidence": 0.95},
        "right_elbow":    {"x": 0.20, "y": 0.45, "confidence": 0.95},
        "left_wrist":     {"x": 0.75, "y": 0.38, "confidence": 0.95},
        "right_wrist":    {"x": 0.25, "y": 0.38, "confidence": 0.95},
    }


def _rounded_back_deadlift_keypoints():
    """Deadlift with severe back rounding (torso angle > 50°)."""
    return {
        # shoulders shifted far forward from hips
        "left_shoulder":  {"x": 0.25, "y": 0.30, "confidence": 0.95},
        "right_shoulder": {"x": 0.23, "y": 0.30, "confidence": 0.90},
        "left_hip":       {"x": 0.50, "y": 0.55, "confidence": 0.95},
        "right_hip":      {"x": 0.50, "y": 0.55, "confidence": 0.90},
        "left_knee":      {"x": 0.52, "y": 0.72, "confidence": 0.95},
        "right_knee":     {"x": 0.52, "y": 0.72, "confidence": 0.90},
        "left_ankle":     {"x": 0.50, "y": 0.88, "confidence": 0.95},
    }


def _layback_ohp_keypoints():
    """Overhead press with excessive layback – shoulders well behind hips."""
    return {
        # shoulders far behind hips (large horizontal offset → big lean angle)
        "left_shoulder":  {"x": 0.28, "y": 0.30, "confidence": 0.95},
        "right_shoulder": {"x": 0.26, "y": 0.30, "confidence": 0.90},
        "left_hip":       {"x": 0.50, "y": 0.55, "confidence": 0.95},
        "right_hip":      {"x": 0.50, "y": 0.55, "confidence": 0.90},
        "left_elbow":     {"x": 0.27, "y": 0.16, "confidence": 0.95},
        "right_elbow":    {"x": 0.25, "y": 0.16, "confidence": 0.90},
    }


# ---------------------------------------------------------------------------
# Unit tests: keypoint analysis service
# ---------------------------------------------------------------------------

class TestAnalyseKeypoints:
    def test_good_squat_returns_no_issues(self):
        result = analyse_keypoints(_good_squat_keypoints("side"), "squat", view="side")
        assert result["overall_score"] >= 80
        assert "excessive_forward_lean" not in result["issues"]

    def test_forward_lean_squat_flagged(self):
        result = analyse_keypoints(_forward_lean_squat_keypoints(), "back_squat", view="side")
        assert "excessive_forward_lean" in result["issues"] or "forward_lean" in result["issues"]
        # spine bones should be red or yellow
        bone_colors = {(b["from_joint"], b["to_joint"]): b["color"] for b in result["bone_colors"]}
        spine = bone_colors.get(("left_shoulder", "left_hip")) or bone_colors.get(("right_shoulder", "right_hip"))
        assert spine in ("red", "yellow")

    def test_knee_valgus_flagged_front_view(self):
        result = analyse_keypoints(_knee_valgus_keypoints(), "squat", view="front")
        assert "left_knee_valgus" in result["issues"]
        joint_colors = {j["joint"]: j["color"] for j in result["joint_colors"]}
        assert joint_colors.get("left_knee") == "red"

    def test_elbow_flare_bench_flagged(self):
        result = analyse_keypoints(_elbow_flare_bench_keypoints(), "bench_press", view="front")
        assert "excessive_elbow_flare" in result["issues"]
        joint_colors = {j["joint"]: j["color"] for j in result["joint_colors"]}
        assert joint_colors.get("left_elbow") == "red" or joint_colors.get("right_elbow") == "red"

    def test_rounded_back_deadlift_flagged(self):
        result = analyse_keypoints(_rounded_back_deadlift_keypoints(), "deadlift", view="side")
        assert "rounded_back" in result["issues"]

    def test_layback_ohp_flagged(self):
        result = analyse_keypoints(_layback_ohp_keypoints(), "overhead_press", view="side")
        assert "excessive_layback" in result["issues"]

    def test_all_joints_present_in_output(self):
        result = analyse_keypoints(_good_squat_keypoints("front"), "squat", view="front")
        joint_names = {j["joint"] for j in result["joint_colors"]}
        assert "left_knee" in joint_names
        assert "right_knee" in joint_names

    def test_all_bones_have_valid_colors(self):
        result = analyse_keypoints(_good_squat_keypoints("front"), "squat", view="front")
        for bone in result["bone_colors"]:
            assert bone["color"] in ("green", "yellow", "red")

    def test_score_decreases_with_issues(self):
        good = analyse_keypoints(_good_squat_keypoints("side"), "squat", view="side")
        bad = analyse_keypoints(_forward_lean_squat_keypoints(), "back_squat", view="side")
        assert bad["overall_score"] <= good["overall_score"]

    def test_feedback_non_empty(self):
        result = analyse_keypoints(_rounded_back_deadlift_keypoints(), "deadlift", view="side")
        assert len(result["feedback"]) > 0

    def test_low_confidence_joints_ignored(self):
        kp = {
            "left_shoulder": {"x": 0.5, "y": 0.2, "confidence": 0.10},  # low confidence
            "left_hip": {"x": 0.5, "y": 0.5, "confidence": 0.95},
        }
        result = analyse_keypoints(kp, "squat", view="side")
        joint_names = {j["joint"] for j in result["joint_colors"]}
        assert "left_shoulder" not in joint_names  # excluded due to low confidence

    def test_auto_view_infers_front(self):
        result = analyse_keypoints(_good_squat_keypoints("front"), "squat", view="auto")
        assert isinstance(result["issues"], list)


# ---------------------------------------------------------------------------
# Integration tests: POST /v1/form/realtime
# ---------------------------------------------------------------------------

class TestRealtimeEndpoint:
    def test_returns_200_with_valid_payload(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        response = client.post(
            "/v1/form/realtime",
            json={
                "user_id": user_id,
                "exercise_key": "squat",
                "view": "side",
                "keypoints": _good_squat_keypoints("side"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "joint_colors" in body
        assert "bone_colors" in body
        assert "issues" in body
        assert "feedback" in body
        assert 0 <= body["overall_score"] <= 100
        app.dependency_overrides = {}

    def test_normalises_exercise_key(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        response = client.post(
            "/v1/form/realtime",
            json={
                "user_id": user_id,
                "exercise_key": "Back Squat",  # should normalise
                "keypoints": _good_squat_keypoints("side"),
            },
        )
        assert response.status_code == 200
        app.dependency_overrides = {}

    def test_rejects_empty_exercise_key(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        response = client.post(
            "/v1/form/realtime",
            json={"user_id": user_id, "exercise_key": "  ", "keypoints": {}},
        )
        assert response.status_code == 422
        app.dependency_overrides = {}

    def test_404_for_unknown_user(self):
        client, _ = _create_client()
        response = client.post(
            "/v1/form/realtime",
            json={
                "user_id": 9999,
                "exercise_key": "squat",
                "keypoints": _good_squat_keypoints("side"),
            },
        )
        assert response.status_code == 404
        app.dependency_overrides = {}

    def test_knee_valgus_flagged_via_api(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        response = client.post(
            "/v1/form/realtime",
            json={
                "user_id": user_id,
                "exercise_key": "squat",
                "view": "front",
                "keypoints": _knee_valgus_keypoints(),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "left_knee_valgus" in body["issues"]
        red_joints = {j["joint"] for j in body["joint_colors"] if j["color"] == "red"}
        assert "left_knee" in red_joints
        app.dependency_overrides = {}

    def test_rounded_back_deadlift_via_api(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        response = client.post(
            "/v1/form/realtime",
            json={
                "user_id": user_id,
                "exercise_key": "deadlift",
                "view": "side",
                "keypoints": _rounded_back_deadlift_keypoints(),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "rounded_back" in body["issues"]
        red_bones = {(b["from_joint"], b["to_joint"]) for b in body["bone_colors"] if b["color"] == "red"}
        assert ("left_shoulder", "left_hip") in red_bones or ("right_shoulder", "right_hip") in red_bones
        app.dependency_overrides = {}

    def test_empty_keypoints_returns_gracefully(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        response = client.post(
            "/v1/form/realtime",
            json={"user_id": user_id, "exercise_key": "squat", "keypoints": {}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["joint_colors"] == []
        assert body["bone_colors"] == []
        app.dependency_overrides = {}
