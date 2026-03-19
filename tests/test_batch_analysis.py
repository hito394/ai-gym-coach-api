"""
Tests for multi-frame batch form analysis:
  - Rep detection (single rep, multiple reps, no motion)
  - Depth / torso aggregation logic
  - Tempo CV calculation
  - POST /form/analyze-batch endpoint (saves to DB, triggers achievements)
"""
from __future__ import annotations

import math
from typing import Dict, List

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


def _create_user(sl):
    db = sl()
    u = models.User(email="batch@test.dev", training_days=4,
                    experience_level="intermediate", goal="strength")
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


# ---------------------------------------------------------------------------
# Frame builders (synthetic squat motion)
# ---------------------------------------------------------------------------

def _squat_frame(hip_y: float, conf: float = 0.9) -> Dict:
    """
    Build a synthetic squat keypoint frame where hip_y determines depth.
    hip_y ≈ 0.4 = standing, hip_y ≈ 0.70 = deep squat (below knee).
    """
    knee_y = 0.62
    # When hip goes below knee (hip_y > knee_y), it's a deep squat.
    return {
        "left_shoulder":  {"x": 0.43, "y": 0.18, "confidence": conf},
        "right_shoulder": {"x": 0.57, "y": 0.18, "confidence": conf},
        "left_hip":       {"x": 0.43, "y": hip_y, "confidence": conf},
        "right_hip":      {"x": 0.57, "y": hip_y, "confidence": conf},
        "left_knee":      {"x": 0.38, "y": knee_y, "confidence": conf},
        "right_knee":     {"x": 0.62, "y": knee_y, "confidence": conf},
        "left_ankle":     {"x": 0.38, "y": 0.88, "confidence": conf},
        "right_ankle":    {"x": 0.62, "y": 0.88, "confidence": conf},
    }


def _make_squat_clip(reps: int, fps: int = 30) -> List[Dict]:
    """
    Produce a synthetic clip with *reps* squat reps.
    Each rep takes ~2 seconds (descend 1 s, ascend 1 s).
    Returns list of {'timestamp_ms', 'keypoints'} dicts.
    """
    frames = []
    rep_frames = fps * 2  # 60 frames per rep at 30 fps
    half = rep_frames // 2
    t = 0

    # Start with 15 frames "standing" before any rep
    for _ in range(15):
        frames.append({"timestamp_ms": t, "keypoints": _squat_frame(0.40)})
        t += 1000 // fps

    for _ in range(reps):
        for i in range(half):
            # descend: hip goes from 0.40 to 0.70
            hip_y = 0.40 + 0.30 * (i / half)
            frames.append({"timestamp_ms": t, "keypoints": _squat_frame(hip_y)})
            t += 1000 // fps
        for i in range(half):
            # ascend: hip goes from 0.70 to 0.40
            hip_y = 0.70 - 0.30 * (i / half)
            frames.append({"timestamp_ms": t, "keypoints": _squat_frame(hip_y)})
            t += 1000 // fps

    # End with 15 frames standing
    for _ in range(15):
        frames.append({"timestamp_ms": t, "keypoints": _squat_frame(0.40)})
        t += 1000 // fps

    return frames


# ---------------------------------------------------------------------------
# Unit tests (service layer)
# ---------------------------------------------------------------------------

class TestRepDetection:
    def test_single_rep_detected(self):
        from app.services.multi_frame_analysis import analyse_batch
        from app.schemas.form import FormBatchIn, FrameIn, Keypoint

        clip = _make_squat_clip(reps=1)
        frames = [
            FrameIn(
                timestamp_ms=f["timestamp_ms"],
                keypoints={k: Keypoint(**v) for k, v in f["keypoints"].items()},
            )
            for f in clip
        ]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        assert result["rep_count"] == 1, f"Expected 1 rep, got {result['rep_count']}"

    def test_three_reps_detected(self):
        from app.services.multi_frame_analysis import analyse_batch
        from app.schemas.form import FormBatchIn, FrameIn, Keypoint

        clip = _make_squat_clip(reps=3)
        frames = [
            FrameIn(
                timestamp_ms=f["timestamp_ms"],
                keypoints={k: Keypoint(**v) for k, v in f["keypoints"].items()},
            )
            for f in clip
        ]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        assert result["rep_count"] == 3, f"Expected 3 reps, got {result['rep_count']}"

    def test_no_motion_gives_zero_reps(self):
        from app.services.multi_frame_analysis import analyse_batch
        from app.schemas.form import FormBatchIn, FrameIn, Keypoint

        # All frames at the same standing position
        frames = [
            FrameIn(
                timestamp_ms=i * 33,
                keypoints={k: Keypoint(**v) for k, v in _squat_frame(0.42).items()},
            )
            for i in range(60)
        ]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        assert result["rep_count"] == 0

    def test_deep_squat_gives_high_depth_score(self):
        from app.services.multi_frame_analysis import analyse_batch
        from app.schemas.form import FormBatchIn, FrameIn, Keypoint

        clip = _make_squat_clip(reps=2)
        frames = [FrameIn(timestamp_ms=f["timestamp_ms"],
                          keypoints={k: Keypoint(**v) for k, v in f["keypoints"].items()})
                  for f in clip]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        # Hip goes to y=0.70 which is below knee at 0.62 → good depth
        assert result["depth_score"] >= 70.0, f"Expected good depth, got {result['depth_score']}"

    def test_duration_ms_is_correct(self):
        from app.services.multi_frame_analysis import analyse_batch
        from app.schemas.form import FormBatchIn, FrameIn, Keypoint

        clip = _make_squat_clip(reps=1, fps=30)
        frames = [FrameIn(timestamp_ms=f["timestamp_ms"],
                          keypoints={k: Keypoint(**v) for k, v in f["keypoints"].items()})
                  for f in clip]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        expected_ms = clip[-1]["timestamp_ms"] - clip[0]["timestamp_ms"]
        assert result["duration_ms"] == expected_ms

    def test_per_rep_summaries_have_correct_count(self):
        from app.services.multi_frame_analysis import analyse_batch
        from app.schemas.form import FormBatchIn, FrameIn, Keypoint

        clip = _make_squat_clip(reps=4)
        frames = [FrameIn(timestamp_ms=f["timestamp_ms"],
                          keypoints={k: Keypoint(**v) for k, v in f["keypoints"].items()})
                  for f in clip]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        assert len(result["reps"]) == result["rep_count"]


class TestSignalExtraction:
    def test_fill_nones_interpolates(self):
        from app.services.multi_frame_analysis import _fill_nones
        signal = [0.4, None, None, 0.7]
        filled = _fill_nones(signal)
        assert filled[0] == 0.4
        assert filled[3] == 0.7
        assert 0.4 < filled[1] < 0.7
        assert 0.4 < filled[2] < 0.7

    def test_smooth_reduces_outlier(self):
        from app.services.multi_frame_analysis import _smooth
        signal = [0.5, 0.5, 0.9, 0.5, 0.5]  # single spike
        smoothed = _smooth(signal, window=3)
        # Spike should be reduced
        assert smoothed[2] < 0.9

    def test_depth_score_from_knee_angle(self):
        from app.services.multi_frame_analysis import _depth_score_from_knee_angle
        assert _depth_score_from_knee_angle(70)  == 100.0   # excellent depth
        assert _depth_score_from_knee_angle(90)  >= 85.0    # good depth
        assert _depth_score_from_knee_angle(130) < 60.0     # shallow
        assert _depth_score_from_knee_angle(None) == 50.0   # missing data

    def test_tempo_cv_good_vs_bad(self):
        from app.services.multi_frame_analysis import _tempo_score_from_cv
        assert _tempo_score_from_cv(0.05) == 95.0   # very consistent
        assert _tempo_score_from_cv(0.30) == 40.0   # very inconsistent
        assert _tempo_score_from_cv(None) == 65.0   # unknown


# ---------------------------------------------------------------------------
# Integration (endpoint)
# ---------------------------------------------------------------------------

class TestAnalyzeBatchEndpoint:
    def test_basic_batch_returns_200(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=2)
        payload = {
            "user_id": uid,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        resp = client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "rep_count" in data
        assert "reps" in data
        assert "depth_achieved_deg" in data
        assert "tempo_cv" in data

    def test_batch_saves_session_to_db(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=1)
        payload = {
            "user_id": uid,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        db = sl()
        count = db.query(models.FormAnalysisSession).filter_by(user_id=uid).count()
        db.close()
        assert count == 1

    def test_batch_triggers_first_session_achievement(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=1)
        payload = {
            "user_id": uid,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        db = sl()
        ach = db.query(models.FormAchievement).filter_by(
            user_id=uid, achievement_type="first_session"
        ).first()
        db.close()
        assert ach is not None

    def test_batch_404_unknown_user(self, ctx):
        client, _ = ctx
        clip = _make_squat_clip(reps=1)
        payload = {
            "user_id": 99999,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        resp = client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(99999))
        assert resp.status_code == 404

    def test_batch_rejects_unsupported_exercise(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=1)
        payload = {
            "user_id": uid,
            "exercise_key": "yoga_pose",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        resp = client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        assert resp.status_code == 422

    def test_batch_rejects_single_frame(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=1)
        payload = {
            "user_id": uid,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": clip[0]["timestamp_ms"], "keypoints": clip[0]["keypoints"]}
            ],
        }
        resp = client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        assert resp.status_code == 422

    def test_model_version_includes_rep_count(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=3)
        payload = {
            "user_id": uid,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        resp = client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        data = resp.json()
        # model_version = "v1-reps3"
        assert "reps" in data["model_version"]

    def test_three_rep_batch_dashboard_shows_correct_count(self, ctx):
        client, sl = ctx
        uid = _create_user(sl)
        clip = _make_squat_clip(reps=3)
        payload = {
            "user_id": uid,
            "exercise_key": "squat",
            "view": "front",
            "frames": [
                {"timestamp_ms": f["timestamp_ms"], "keypoints": f["keypoints"]}
                for f in clip
            ],
        }
        client.post("/v1/form/analyze-batch", json=payload, headers=auth_headers(uid))
        dash = client.get(f"/v1/users/{uid}/dashboard", headers=auth_headers(uid)).json()
        assert dash["total_sessions"] == 1   # one DB session record
