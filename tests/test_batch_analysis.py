"""
Tests for multi-frame batch analysis service layer.
(Batch endpoint removed in favour of simpler form logging.)
"""
from __future__ import annotations

import math
from typing import Dict, List

import pytest

from app.schemas.form import FormBatchIn, FrameIn
from app.schemas.realtime import Keypoint


# ---------------------------------------------------------------------------
# Frame builders (synthetic squat motion)
# ---------------------------------------------------------------------------

def _squat_frame(hip_y: float, conf: float = 0.9) -> Dict:
    knee_y = 0.62
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
    frames = []
    rep_frames = fps * 2
    half = rep_frames // 2
    t = 0

    for _ in range(15):
        frames.append({"timestamp_ms": t, "keypoints": _squat_frame(0.40)})
        t += 1000 // fps

    for _ in range(reps):
        for i in range(half):
            hip_y = 0.40 + 0.30 * (i / half)
            frames.append({"timestamp_ms": t, "keypoints": _squat_frame(hip_y)})
            t += 1000 // fps
        for i in range(half):
            hip_y = 0.70 - 0.30 * (i / half)
            frames.append({"timestamp_ms": t, "keypoints": _squat_frame(hip_y)})
            t += 1000 // fps

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

        clip = _make_squat_clip(reps=2)
        frames = [FrameIn(timestamp_ms=f["timestamp_ms"],
                          keypoints={k: Keypoint(**v) for k, v in f["keypoints"].items()})
                  for f in clip]
        payload = FormBatchIn(user_id=1, exercise_key="squat", view="front", frames=frames)
        result = analyse_batch(payload)
        assert result["depth_score"] >= 70.0, f"Expected good depth, got {result['depth_score']}"

    def test_duration_ms_is_correct(self):
        from app.services.multi_frame_analysis import analyse_batch

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
        signal = [0.5, 0.5, 0.9, 0.5, 0.5]
        smoothed = _smooth(signal, window=3)
        assert smoothed[2] < 0.9

    def test_depth_score_from_knee_angle(self):
        from app.services.multi_frame_analysis import _depth_score_from_knee_angle
        assert _depth_score_from_knee_angle(70)  == 100.0
        assert _depth_score_from_knee_angle(90)  >= 85.0
        assert _depth_score_from_knee_angle(130) < 60.0
        assert _depth_score_from_knee_angle(None) == 50.0

    def test_tempo_cv_good_vs_bad(self):
        from app.services.multi_frame_analysis import _tempo_score_from_cv
        assert _tempo_score_from_cv(0.05) == 95.0
        assert _tempo_score_from_cv(0.30) == 40.0
        assert _tempo_score_from_cv(None) == 65.0
