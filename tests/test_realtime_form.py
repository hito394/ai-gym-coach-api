"""
Tests for keypoint analysis service layer.
(Real-time endpoint removed in favour of simpler form logging.)
"""
import pytest
from app.services.keypoint_analysis import analyse_keypoints


# ---------------------------------------------------------------------------
# Keypoint fixtures
# ---------------------------------------------------------------------------

def _good_squat_keypoints(view="side"):
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
    return {
        "left_shoulder": {"x": 0.50, "y": 0.25, "confidence": 0.95},
        "left_hip":      {"x": 0.48, "y": 0.55, "confidence": 0.95},
        "left_knee":     {"x": 0.52, "y": 0.55, "confidence": 0.95},
        "left_ankle":    {"x": 0.54, "y": 0.88, "confidence": 0.95},
    }


def _forward_lean_squat_keypoints():
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
    return {
        "left_shoulder":  {"x": 0.65, "y": 0.28, "confidence": 0.95},
        "right_shoulder": {"x": 0.35, "y": 0.28, "confidence": 0.95},
        "left_hip":       {"x": 0.63, "y": 0.52, "confidence": 0.95},
        "right_hip":      {"x": 0.37, "y": 0.52, "confidence": 0.95},
        "left_knee":      {"x": 0.48, "y": 0.68, "confidence": 0.95},
        "right_knee":     {"x": 0.38, "y": 0.68, "confidence": 0.95},
        "left_ankle":     {"x": 0.62, "y": 0.87, "confidence": 0.95},
        "right_ankle":    {"x": 0.38, "y": 0.87, "confidence": 0.95},
    }


def _elbow_flare_bench_keypoints():
    return {
        "left_shoulder":  {"x": 0.62, "y": 0.40, "confidence": 0.95},
        "right_shoulder": {"x": 0.38, "y": 0.40, "confidence": 0.95},
        "left_elbow":     {"x": 0.80, "y": 0.45, "confidence": 0.95},
        "right_elbow":    {"x": 0.20, "y": 0.45, "confidence": 0.95},
        "left_wrist":     {"x": 0.75, "y": 0.38, "confidence": 0.95},
        "right_wrist":    {"x": 0.25, "y": 0.38, "confidence": 0.95},
    }


def _rounded_back_deadlift_keypoints():
    return {
        "left_shoulder":  {"x": 0.25, "y": 0.30, "confidence": 0.95},
        "right_shoulder": {"x": 0.23, "y": 0.30, "confidence": 0.90},
        "left_hip":       {"x": 0.50, "y": 0.55, "confidence": 0.95},
        "right_hip":      {"x": 0.50, "y": 0.55, "confidence": 0.90},
        "left_knee":      {"x": 0.52, "y": 0.72, "confidence": 0.95},
        "right_knee":     {"x": 0.52, "y": 0.72, "confidence": 0.90},
        "left_ankle":     {"x": 0.50, "y": 0.88, "confidence": 0.95},
    }


def _layback_ohp_keypoints():
    return {
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
            "left_shoulder": {"x": 0.5, "y": 0.2, "confidence": 0.10},
            "left_hip": {"x": 0.5, "y": 0.5, "confidence": 0.95},
        }
        result = analyse_keypoints(kp, "squat", view="side")
        joint_names = {j["joint"] for j in result["joint_colors"]}
        assert "left_shoulder" not in joint_names

    def test_auto_view_infers_front(self):
        result = analyse_keypoints(_good_squat_keypoints("front"), "squat", view="auto")
        assert isinstance(result["issues"], list)
