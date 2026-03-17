from __future__ import annotations

from typing import Any, Dict, List


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _depth_score(depth_norm: float | None) -> float:
    if depth_norm is None:
        return 50.0
    if depth_norm < 0.10:
        return _clamp(45.0 + (depth_norm * 300.0))
    if depth_norm <= 0.28:
        return _clamp(75.0 + ((depth_norm - 0.10) * 110.0))
    return _clamp(95.0 - ((depth_norm - 0.28) * 120.0))


def _torso_score(torso_angle: float | None) -> float:
    if torso_angle is None:
        return 50.0
    angle = abs(torso_angle)
    if angle <= 20:
        return 95.0
    if angle <= 30:
        return _clamp(95.0 - ((angle - 20) * 2.5))
    if angle <= 45:
        return _clamp(70.0 - ((angle - 30) * 2.0))
    return 20.0


def _symmetry_score(symmetry: Any, asymmetry: float | None) -> float:
    if asymmetry is not None:
        return _clamp(100.0 - (abs(asymmetry) * 5.0))

    if isinstance(symmetry, dict) and symmetry:
        numeric_values = [
            abs(float(v))
            for v in symmetry.values()
            if isinstance(v, (int, float))
        ]
        if numeric_values:
            return _clamp(100.0 - ((sum(numeric_values) / len(numeric_values)) * 4.0))

    return 50.0


def _tempo_score(jitter: float | None, rep_issues: List[str]) -> float:
    if jitter is None:
        score = 65.0
    elif jitter <= 0.02:
        score = 92.0
    elif jitter <= 0.04:
        score = 78.0
    elif jitter <= 0.08:
        score = 60.0
    else:
        score = 40.0

    if any("tempo" in issue for issue in rep_issues):
        score -= 10.0

    return _clamp(score)


# ---------------------------------------------------------------------------
# Exercise-specific issue detection
# ---------------------------------------------------------------------------

from app.utils.exercise_registry import get_exercise_category as _registry_category

# Map registry categories to the analyser categories used in this service
_ANALYSER_CATEGORY_MAP = {
    "squat": "squat",
    "deadlift": "deadlift",
    "bench": "bench",
    "ohp": "ohp",
    "pull": "pull",
    "arms": "isolation",
    "shoulder_isolation": "isolation",
    "legs": "isolation",
    "core": "isolation",
}


def _classify_exercise(exercise_key: str) -> str:
    """Return the analyser category for *exercise_key* (gym exercises only)."""
    registry_cat = _registry_category(exercise_key.lower().strip())
    return _ANALYSER_CATEGORY_MAP.get(registry_cat or "", "isolation")


def _detect_issues(
    exercise_category: str,
    depth_score: float,
    torso_angle_score: float,
    symmetry_score: float,
    tempo_score: float,
    quality: float,
    diagnostics: Dict[str, Any],
) -> List[str]:
    issues: List[str] = []

    if quality < 70:
        issues.append("low_capture_quality")

    if exercise_category == "squat":
        if depth_score < 70:
            issues.append("shallow_depth")
        if torso_angle_score < 70:
            issues.append("forward_lean")
        if symmetry_score < 70:
            issues.append("asymmetry_instability")
        if tempo_score < 70:
            issues.append("tempo_inconsistent")

    elif exercise_category == "bench":
        # For bench, torso stays flat – we repurpose torso_angle for wrist/elbow flare
        elbow_flare = _to_float(diagnostics.get("elbow_flare_angle"))
        if elbow_flare is not None and elbow_flare > 75:
            issues.append("excessive_elbow_flare")
        if symmetry_score < 70:
            issues.append("uneven_press")
        if tempo_score < 70:
            issues.append("tempo_inconsistent")
        bar_path_deviation = _to_float(diagnostics.get("bar_path_deviation"))
        if bar_path_deviation is not None and bar_path_deviation > 0.05:
            issues.append("bar_path_inconsistent")

    elif exercise_category == "deadlift":
        if torso_angle_score < 70:
            issues.append("rounded_back")
        if symmetry_score < 70:
            issues.append("asymmetry_instability")
        if tempo_score < 70:
            issues.append("tempo_inconsistent")
        lockout = _to_float(diagnostics.get("hip_lockout_angle"))
        if lockout is not None and lockout < 160:
            issues.append("incomplete_lockout")

    elif exercise_category == "ohp":
        if torso_angle_score < 70:
            issues.append("excessive_layback")
        if symmetry_score < 70:
            issues.append("asymmetry_instability")
        if tempo_score < 70:
            issues.append("tempo_inconsistent")

    elif exercise_category == "pull":
        if torso_angle_score < 70:
            issues.append("rounded_back")
        if symmetry_score < 70:
            issues.append("pull_asymmetry")
        if tempo_score < 70:
            issues.append("tempo_inconsistent")

    else:  # isolation (arms, legs, shoulder isolation, core)
        if symmetry_score < 70:
            issues.append("asymmetry_instability")
        if tempo_score < 70:
            issues.append("tempo_inconsistent")

    return issues


def _feedback_for_issues(issues: List[str], exercise_category: str) -> str:
    if not issues:
        return "Your form looks stable. Keep bracing, maintain tempo, and progress load gradually."

    messages: List[str] = []

    # Shared
    if "low_capture_quality" in issues:
        messages.append("Camera quality is limiting analysis. Use side view, full body framing, and stronger lighting.")

    # Squat cues
    if "shallow_depth" in issues:
        messages.append("Your squat depth is slightly shallow. Try going 2-3 inches deeper while keeping tension.")
    if "forward_lean" in issues:
        messages.append("Your torso is leaning forward. Brace harder and keep the chest more upright through the ascent.")
    if "asymmetry_instability" in issues:
        messages.append("Left-right balance is off. Reduce load 5-10% and focus on even pressure through both feet.")
    if "tempo_inconsistent" in issues:
        messages.append("Tempo is inconsistent. Use a controlled descent and a smooth, powerful ascent.")

    # Bench cues
    if "excessive_elbow_flare" in issues:
        messages.append("Elbows are flaring too wide. Tuck them 45-60° to protect your shoulders and increase power transfer.")
    if "uneven_press" in issues:
        messages.append("One side is pressing more than the other. Focus on driving both hands evenly and check grip width.")
    if "bar_path_inconsistent" in issues:
        messages.append("Bar path is drifting. Keep the bar over your lower chest and drive it in a slight arc toward the rack.")

    # Deadlift cues
    if "rounded_back" in issues:
        messages.append("Your back is rounding. Set your lats before pulling, brace 360°, and keep a neutral spine throughout.")
    if "incomplete_lockout" in issues:
        messages.append("Hips aren't fully locking out at the top. Drive hips through and squeeze glutes at lockout.")

    # OHP cues
    if "excessive_layback" in issues:
        messages.append("You're leaning back too much. Brace your core tightly and keep the bar path vertical.")

    # Pull cues
    if "pull_asymmetry" in issues:
        messages.append("Both sides aren't pulling equally. Focus on initiating with the lat on the weaker side.")

    return " ".join(messages)


def analyze_form_diagnostics(
    diagnostics: Dict[str, Any],
    exercise_key: str,
) -> Dict[str, Any]:
    exercise_category = _classify_exercise(exercise_key)

    quality = _to_float(diagnostics.get("quality")) or 0.0
    jitter = _to_float(diagnostics.get("pose_jitter"))
    depth_norm = _to_float(diagnostics.get("depth_norm"))
    knee_valgus_norm = _to_float(diagnostics.get("knee_valgus_norm"))
    torso_angle = _to_float(diagnostics.get("torso_angle"))
    asymmetry = _to_float(diagnostics.get("asymmetry"))

    metrics = diagnostics.get("metrics")
    if asymmetry is None and isinstance(metrics, dict):
        asymmetry = _to_float(metrics.get("asymmetry"))

    symmetry = diagnostics.get("symmetry")
    rep_issues = diagnostics.get("rep_issues")
    rep_issues = rep_issues if isinstance(rep_issues, list) else []

    depth_score = _depth_score(depth_norm)
    torso_angle_score = _torso_score(torso_angle)
    symmetry_score = _symmetry_score(symmetry, asymmetry)
    if knee_valgus_norm is not None and knee_valgus_norm > 0.12:
        symmetry_score = _clamp(symmetry_score - min(25.0, (knee_valgus_norm - 0.12) * 220.0))

    tempo_score = _tempo_score(jitter, rep_issues)
    bar_path_score = _clamp((0.4 * torso_angle_score) + (0.4 * symmetry_score) + (0.2 * quality))

    overall_score = _clamp(
        (0.30 * depth_score)
        + (0.25 * torso_angle_score)
        + (0.20 * symmetry_score)
        + (0.20 * tempo_score)
        + (0.05 * bar_path_score)
    )

    issues = _detect_issues(
        exercise_category,
        depth_score,
        torso_angle_score,
        symmetry_score,
        tempo_score,
        quality,
        diagnostics,
    )

    feedback = _feedback_for_issues(issues, exercise_category)

    return {
        "overall_score": round(overall_score, 2),
        "depth_score": round(depth_score, 2),
        "torso_angle_score": round(torso_angle_score, 2),
        "symmetry_score": round(symmetry_score, 2),
        "tempo_score": round(tempo_score, 2),
        "bar_path_score": round(bar_path_score, 2),
        "issues": issues,
        "feedback": feedback,
    }
