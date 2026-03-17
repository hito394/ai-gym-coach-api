"""
Real-time keypoint analysis service.

Receives MoveNet-style 2D keypoints (x, y normalised 0-1, confidence 0-1)
and returns per-joint / per-bone colour annotations:
  "green"  – correct form
  "yellow" – minor deviation, monitor closely
  "red"    – significant error, injury risk

Coordinate convention
---------------------
  x: 0 = left edge of frame, 1 = right edge
  y: 0 = top edge of frame,  1 = bottom edge
  => larger y = lower in the frame (gravity direction)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Skeleton definition (MoveNet 17-keypoint topology)
# ---------------------------------------------------------------------------

SKELETON_BONES: List[Tuple[str, str]] = [
    ("nose", "left_shoulder"),
    ("nose", "right_shoulder"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
]

ALL_JOINTS = [
    "nose",
    "left_eye", "right_eye",
    "left_ear", "right_ear",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]

_CONFIDENCE_THRESHOLD = 0.25


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _xy(keypoints: Dict[str, Any], name: str) -> Optional[Tuple[float, float]]:
    """Return (x, y) for a joint if confidence is sufficient, else None."""
    kp = keypoints.get(name)
    if kp is None:
        return None
    conf = kp.get("confidence", 1.0) if isinstance(kp, dict) else getattr(kp, "confidence", 1.0)
    if conf < _CONFIDENCE_THRESHOLD:
        return None
    x = kp.get("x") if isinstance(kp, dict) else kp.x
    y = kp.get("y") if isinstance(kp, dict) else kp.y
    return (float(x), float(y))


def _mid(p1: Optional[Tuple], p2: Optional[Tuple]) -> Optional[Tuple[float, float]]:
    if p1 is None or p2 is None:
        return None
    return ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)


def _angle_at_vertex(
    p1: Optional[Tuple],
    vertex: Optional[Tuple],
    p2: Optional[Tuple],
) -> Optional[float]:
    """Interior angle (°) at *vertex* formed by the two rays vertex→p1 and vertex→p2."""
    if p1 is None or vertex is None or p2 is None:
        return None
    v1 = (p1[0] - vertex[0], p1[1] - vertex[1])
    v2 = (p2[0] - vertex[0], p2[1] - vertex[1])
    mag1 = math.hypot(*v1)
    mag2 = math.hypot(*v2)
    if mag1 < 1e-6 or mag2 < 1e-6:
        return None
    cos_a = (v1[0] * v2[0] + v1[1] * v2[1]) / (mag1 * mag2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))


def _torso_angle(
    shoulder_mid: Optional[Tuple],
    hip_mid: Optional[Tuple],
) -> Optional[float]:
    """
    Forward-lean angle of the torso from vertical (°).
    0° = perfectly upright. Positive = leaning forward.
    Works in image coordinates where y increases downward.
    """
    if shoulder_mid is None or hip_mid is None:
        return None
    dx = shoulder_mid[0] - hip_mid[0]
    # In image coords shoulders should be above hips → hip_y > shoulder_y
    dy = hip_mid[1] - shoulder_mid[1]
    if dy < 1e-6:
        return None
    return math.degrees(math.atan2(abs(dx), dy))


def _infer_view(keypoints: Dict[str, Any]) -> str:
    """
    Heuristic: if left and right shoulder x-values are far apart → front view.
    If they are close together → side view.
    """
    ls = _xy(keypoints, "left_shoulder")
    rs = _xy(keypoints, "right_shoulder")
    if ls is None or rs is None:
        return "side"
    return "front" if abs(ls[0] - rs[0]) > 0.15 else "side"


# ---------------------------------------------------------------------------
# Colour result builder
# ---------------------------------------------------------------------------

class _ColorMap:
    def __init__(self) -> None:
        self._joints: Dict[str, Tuple[str, Optional[str]]] = {}  # joint → (color, reason)
        self._bones: Dict[Tuple[str, str], str] = {}

    def mark_joint(self, joint: str, color: str, reason: Optional[str] = None) -> None:
        priority = {"red": 2, "yellow": 1, "green": 0}
        current = self._joints.get(joint, ("green", None))
        if priority[color] > priority[current[0]]:
            self._joints[joint] = (color, reason)

    def mark_bone(self, from_j: str, to_j: str, color: str) -> None:
        key = (from_j, to_j)
        priority = {"red": 2, "yellow": 1, "green": 0}
        current = self._bones.get(key, "green")
        if priority[color] > priority[current]:
            self._bones[key] = color

    def mark_bones_for_joints(self, joints: List[str], color: str) -> None:
        for from_j, to_j in SKELETON_BONES:
            if from_j in joints or to_j in joints:
                self.mark_bone(from_j, to_j, color)

    def build_joints(self, present_joints: List[str]) -> List[Dict]:
        result = []
        for joint in present_joints:
            color, reason = self._joints.get(joint, ("green", None))
            result.append({"joint": joint, "color": color, "reason": reason})
        return result

    def build_bones(self, present_joints: List[str]) -> List[Dict]:
        present = set(present_joints)
        result = []
        for from_j, to_j in SKELETON_BONES:
            if from_j in present and to_j in present:
                color = self._bones.get((from_j, to_j), "green")
                result.append({"from_joint": from_j, "to_joint": to_j, "color": color})
        return result


# ---------------------------------------------------------------------------
# Exercise-specific analysers
# ---------------------------------------------------------------------------

def _analyse_squat(
    kp: Dict[str, Any],
    view: str,
    cmap: _ColorMap,
) -> List[str]:
    issues: List[str] = []

    l_hip = _xy(kp, "left_hip")
    r_hip = _xy(kp, "right_hip")
    l_knee = _xy(kp, "left_knee")
    r_knee = _xy(kp, "right_knee")
    l_ankle = _xy(kp, "left_ankle")
    r_ankle = _xy(kp, "right_ankle")
    l_shoulder = _xy(kp, "left_shoulder")
    r_shoulder = _xy(kp, "right_shoulder")

    hip_mid = _mid(l_hip, r_hip)
    shoulder_mid = _mid(l_shoulder, r_shoulder)
    knee_mid = _mid(l_knee, r_knee)

    # --- 1. Torso lean (works well in side view) ---
    lean = _torso_angle(shoulder_mid, hip_mid)
    if lean is not None:
        if lean > 45:
            issues.append("excessive_forward_lean")
            for joint in ["left_shoulder", "right_shoulder", "left_hip", "right_hip"]:
                cmap.mark_joint(joint, "red", "excessive forward lean")
            cmap.mark_bone("left_shoulder", "left_hip", "red")
            cmap.mark_bone("right_shoulder", "right_hip", "red")
        elif lean > 30:
            issues.append("forward_lean")
            cmap.mark_bone("left_shoulder", "left_hip", "yellow")
            cmap.mark_bone("right_shoulder", "right_hip", "yellow")

    # --- 2. Squat depth ---
    # hip_mid.y should be >= knee_mid.y (hip at or below knee in image = good depth)
    if hip_mid is not None and knee_mid is not None:
        depth_diff = hip_mid[1] - knee_mid[1]  # positive = hip below knee (good)
        if depth_diff < -0.04:  # hips clearly above knees
            issues.append("shallow_depth")
            cmap.mark_joint("left_hip", "yellow", "hips above knees")
            cmap.mark_joint("right_hip", "yellow", "hips above knees")

    # --- 3. Knee valgus (cave-in) – best seen from front ---
    # For front view: person's left knee (appears on image right) should not drift inward
    if view == "front":
        # Left leg: left_knee.x should be >= left_ankle.x (knee tracks over foot)
        if l_knee is not None and l_ankle is not None and l_hip is not None:
            # Expected knee x = between hip and ankle
            expected_x = (l_hip[0] + l_ankle[0]) / 2.0
            if l_knee[0] < expected_x - 0.04:
                issues.append("left_knee_valgus")
                cmap.mark_joint("left_knee", "red", "knee caving inward")
                cmap.mark_bone("left_hip", "left_knee", "red")
                cmap.mark_bone("left_knee", "left_ankle", "red")

        if r_knee is not None and r_ankle is not None and r_hip is not None:
            expected_x = (r_hip[0] + r_ankle[0]) / 2.0
            if r_knee[0] > expected_x + 0.04:
                issues.append("right_knee_valgus")
                cmap.mark_joint("right_knee", "red", "knee caving inward")
                cmap.mark_bone("right_hip", "right_knee", "red")
                cmap.mark_bone("right_knee", "right_ankle", "red")

    # --- 4. Knee angle (check for hyper-flexion or too-shallow) ---
    l_knee_angle = _angle_at_vertex(l_hip, l_knee, l_ankle)
    r_knee_angle = _angle_at_vertex(r_hip, r_knee, r_ankle)
    for side, angle, knee_joint, hip_joint, ankle_joint, hip_bone_to, knee_bone_to in [
        ("left", l_knee_angle, "left_knee", "left_hip", "left_ankle", "left_knee", "left_ankle"),
        ("right", r_knee_angle, "right_knee", "right_hip", "right_ankle", "right_knee", "right_ankle"),
    ]:
        if angle is not None and angle > 150:
            # Very straight knee – person is likely standing (not in squat)
            # Don't flag this as error; it's OK between reps
            pass

    return issues


def _analyse_deadlift(
    kp: Dict[str, Any],
    view: str,
    cmap: _ColorMap,
) -> List[str]:
    issues: List[str] = []

    l_shoulder = _xy(kp, "left_shoulder")
    r_shoulder = _xy(kp, "right_shoulder")
    l_hip = _xy(kp, "left_hip")
    r_hip = _xy(kp, "right_hip")
    l_knee = _xy(kp, "left_knee")
    r_knee = _xy(kp, "right_knee")

    shoulder_mid = _mid(l_shoulder, r_shoulder)
    hip_mid = _mid(l_hip, r_hip)
    knee_mid = _mid(l_knee, r_knee)

    # --- 1. Back rounding / excessive forward lean ---
    # Deadlift threshold is lower than squat: torso must stay more neutral
    lean = _torso_angle(shoulder_mid, hip_mid)
    if lean is not None:
        if lean > 40:
            issues.append("rounded_back")
            for joint in ["left_shoulder", "right_shoulder"]:
                cmap.mark_joint(joint, "red", "back rounding – injury risk")
            cmap.mark_bone("left_shoulder", "left_hip", "red")
            cmap.mark_bone("right_shoulder", "right_hip", "red")
            cmap.mark_bone("nose", "left_shoulder", "red")
            cmap.mark_bone("nose", "right_shoulder", "red")
        elif lean > 25:
            issues.append("forward_lean")
            cmap.mark_bone("left_shoulder", "left_hip", "yellow")
            cmap.mark_bone("right_shoulder", "right_hip", "yellow")

    # --- 2. Hip lockout at top ---
    # At lockout: hip should be fully extended (shoulder-hip-knee angle ~180°)
    l_lockout = _angle_at_vertex(l_shoulder, l_hip, l_knee)
    r_lockout = _angle_at_vertex(r_shoulder, r_hip, r_knee)
    for angle, hip_j in [(l_lockout, "left_hip"), (r_lockout, "right_hip")]:
        if angle is not None and angle < 155:
            issues.append("incomplete_lockout")
            cmap.mark_joint(hip_j, "yellow", "hips not fully locked out")

    # --- 3. Symmetry (front view) ---
    if view == "front" and l_shoulder is not None and r_shoulder is not None:
        shoulder_diff = abs(l_shoulder[1] - r_shoulder[1])
        if shoulder_diff > 0.05:
            issues.append("shoulder_asymmetry")
            higher = "left_shoulder" if l_shoulder[1] < r_shoulder[1] else "right_shoulder"
            cmap.mark_joint(higher, "yellow", "shoulder height uneven")

    return issues


def _analyse_bench(
    kp: Dict[str, Any],
    view: str,
    cmap: _ColorMap,
) -> List[str]:
    issues: List[str] = []

    l_shoulder = _xy(kp, "left_shoulder")
    r_shoulder = _xy(kp, "right_shoulder")
    l_elbow = _xy(kp, "left_elbow")
    r_elbow = _xy(kp, "right_elbow")
    l_wrist = _xy(kp, "left_wrist")
    r_wrist = _xy(kp, "right_wrist")

    # --- 1. Elbow flare (front view: elbow should not be much wider than shoulder) ---
    # In front-facing image: left body parts have larger x, right have smaller x
    # Flare = elbow x is significantly outside shoulder x
    if l_elbow is not None and l_shoulder is not None:
        if l_elbow[0] > l_shoulder[0] + 0.12:  # elbow far outside shoulder (left side)
            issues.append("excessive_elbow_flare")
            cmap.mark_joint("left_elbow", "red", "elbow flaring – rotator cuff risk")
            cmap.mark_bone("left_shoulder", "left_elbow", "red")
    if r_elbow is not None and r_shoulder is not None:
        if r_elbow[0] < r_shoulder[0] - 0.12:  # elbow far outside shoulder (right side)
            issues.append("excessive_elbow_flare")
            cmap.mark_joint("right_elbow", "red", "elbow flaring – rotator cuff risk")
            cmap.mark_bone("right_shoulder", "right_elbow", "red")

    # --- 2. Wrist alignment (wrist should be roughly above elbow) ---
    for elbow, wrist, elbow_j, wrist_j, bone_from, bone_to in [
        (l_elbow, l_wrist, "left_elbow", "left_wrist", "left_elbow", "left_wrist"),
        (r_elbow, r_wrist, "right_elbow", "right_wrist", "right_elbow", "right_wrist"),
    ]:
        if elbow is not None and wrist is not None:
            drift = abs(wrist[0] - elbow[0])
            if drift > 0.10:
                issues.append("wrist_misalignment")
                cmap.mark_joint(wrist_j, "yellow", "wrist drifting from elbow")
                cmap.mark_bone(bone_from, bone_to, "yellow")

    # --- 3. Symmetry ---
    if view == "front":
        if l_elbow is not None and r_elbow is not None:
            if abs(l_elbow[1] - r_elbow[1]) > 0.06:
                issues.append("uneven_press")
                higher = "left_elbow" if l_elbow[1] < r_elbow[1] else "right_elbow"
                cmap.mark_joint(higher, "yellow", "one side pressing unevenly")

    return issues


def _analyse_ohp(
    kp: Dict[str, Any],
    view: str,
    cmap: _ColorMap,
) -> List[str]:
    issues: List[str] = []

    l_shoulder = _xy(kp, "left_shoulder")
    r_shoulder = _xy(kp, "right_shoulder")
    l_hip = _xy(kp, "left_hip")
    r_hip = _xy(kp, "right_hip")
    l_elbow = _xy(kp, "left_elbow")
    r_elbow = _xy(kp, "right_elbow")

    shoulder_mid = _mid(l_shoulder, r_shoulder)
    hip_mid = _mid(l_hip, r_hip)

    # --- 1. Layback (excessive lumbar extension) ---
    lean = _torso_angle(shoulder_mid, hip_mid)
    if lean is not None and lean > 20:
        issues.append("excessive_layback")
        cmap.mark_bone("left_shoulder", "left_hip", "red")
        cmap.mark_bone("right_shoulder", "right_hip", "red")
        cmap.mark_joint("left_hip", "red", "excessive layback – lower back risk")
        cmap.mark_joint("right_hip", "red", "excessive layback – lower back risk")

    # --- 2. Elbow position (elbows should be in front of bar, not flared) ---
    l_elbow_angle = _angle_at_vertex(l_hip, l_shoulder, l_elbow)
    r_elbow_angle = _angle_at_vertex(r_hip, r_shoulder, r_elbow)
    for angle, elbow_j, shoulder_j in [
        (l_elbow_angle, "left_elbow", "left_shoulder"),
        (r_elbow_angle, "right_elbow", "right_shoulder"),
    ]:
        if angle is not None and angle > 100:
            issues.append("elbow_flare_ohp")
            cmap.mark_joint(elbow_j, "yellow", "elbows drifting behind bar")
            cmap.mark_bone(shoulder_j, elbow_j, "yellow")

    # --- 3. Symmetry ---
    if view == "front":
        if l_elbow is not None and r_elbow is not None:
            if abs(l_elbow[1] - r_elbow[1]) > 0.06:
                issues.append("asymmetry_instability")
                cmap.mark_joint("left_elbow", "yellow", "height uneven")
                cmap.mark_joint("right_elbow", "yellow", "height uneven")

    return issues


def _analyse_pull(
    kp: Dict[str, Any],
    view: str,
    cmap: _ColorMap,
) -> List[str]:
    """Pull exercises: lat pulldown, rows, pull-ups, face pulls."""
    issues: List[str] = []

    l_shoulder = _xy(kp, "left_shoulder")
    r_shoulder = _xy(kp, "right_shoulder")
    l_hip = _xy(kp, "left_hip")
    r_hip = _xy(kp, "right_hip")
    l_elbow = _xy(kp, "left_elbow")
    r_elbow = _xy(kp, "right_elbow")

    shoulder_mid = _mid(l_shoulder, r_shoulder)
    hip_mid = _mid(l_hip, r_hip)

    # Back rounding during rows – torso should stay relatively upright
    lean = _torso_angle(shoulder_mid, hip_mid)
    if lean is not None and lean > 50:
        issues.append("rounded_back")
        cmap.mark_bone("left_shoulder", "left_hip", "red")
        cmap.mark_bone("right_shoulder", "right_hip", "red")
        for j in ["left_shoulder", "right_shoulder"]:
            cmap.mark_joint(j, "red", "back rounding – retract scapulae")

    # Elbow symmetry (elbows should reach same height)
    if l_elbow is not None and r_elbow is not None:
        if abs(l_elbow[1] - r_elbow[1]) > 0.06:
            issues.append("pull_asymmetry")
            higher = "left_elbow" if l_elbow[1] < r_elbow[1] else "right_elbow"
            cmap.mark_joint(higher, "yellow", "elbows not pulling evenly")

    # Shoulder asymmetry
    if view == "front" and l_shoulder is not None and r_shoulder is not None:
        if abs(l_shoulder[1] - r_shoulder[1]) > 0.05:
            issues.append("shoulder_asymmetry")
            higher = "left_shoulder" if l_shoulder[1] < r_shoulder[1] else "right_shoulder"
            cmap.mark_joint(higher, "yellow", "one shoulder shrugging")

    return issues


def _analyse_isolation(
    kp: Dict[str, Any],
    view: str,
    cmap: _ColorMap,
) -> List[str]:
    """
    Arm, shoulder isolation, leg isolation, and core exercises.
    Checks bilateral symmetry and shoulder/hip stability.
    """
    issues: List[str] = []

    l_shoulder = _xy(kp, "left_shoulder")
    r_shoulder = _xy(kp, "right_shoulder")
    l_elbow = _xy(kp, "left_elbow")
    r_elbow = _xy(kp, "right_elbow")
    l_wrist = _xy(kp, "left_wrist")
    r_wrist = _xy(kp, "right_wrist")
    l_hip = _xy(kp, "left_hip")
    r_hip = _xy(kp, "right_hip")

    # Shoulder stability – they should not rise during arm isolation
    if l_shoulder is not None and r_shoulder is not None:
        if abs(l_shoulder[1] - r_shoulder[1]) > 0.05:
            issues.append("shoulder_asymmetry")
            higher = "left_shoulder" if l_shoulder[1] < r_shoulder[1] else "right_shoulder"
            cmap.mark_joint(higher, "yellow", "shoulder rising – reduce momentum")

    # Elbow drift (curls/extensions: elbow should stay fixed at the side)
    if view == "front":
        if l_elbow is not None and r_elbow is not None:
            if abs(l_elbow[1] - r_elbow[1]) > 0.07:
                issues.append("asymmetry_instability")
                cmap.mark_joint("left_elbow", "yellow", "uneven elbow height")
                cmap.mark_joint("right_elbow", "yellow", "uneven elbow height")

    # Hip rocking (using body English – hips shift during arm work)
    if l_hip is not None and r_hip is not None:
        if abs(l_hip[1] - r_hip[1]) > 0.05:
            issues.append("hip_rock")
            cmap.mark_joint("left_hip", "yellow", "hips rocking – use less weight")
            cmap.mark_joint("right_hip", "yellow", "hips rocking – use less weight")

    return issues


# ---------------------------------------------------------------------------
# Exercise classifier – delegates to the shared registry
# ---------------------------------------------------------------------------

from app.utils.exercise_registry import get_exercise_category as _registry_category

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
    "olympic": "squat",   # Olympic lifts share squat/hinge mechanics
}


def _classify(exercise_key: str) -> str:
    """Map a gym exercise key to an analyser category."""
    registry_cat = _registry_category(exercise_key.lower().strip())
    return _ANALYSER_CATEGORY_MAP.get(registry_cat or "", "isolation")


# ---------------------------------------------------------------------------
# Issue → human feedback
# ---------------------------------------------------------------------------

_ISSUE_FEEDBACK: Dict[str, str] = {
    # Squat
    "excessive_forward_lean": "Back is leaning too far forward. Brace your core, keep chest up.",
    "forward_lean": "Slight forward lean detected. Focus on staying upright.",
    "shallow_depth": "Hips are above knees. Try to squat deeper.",
    "left_knee_valgus": "Left knee is caving in. Push your left knee out over your toes.",
    "right_knee_valgus": "Right knee is caving in. Push your right knee out over your toes.",
    # Deadlift
    "rounded_back": "Back is rounding – injury risk! Lock your lats and maintain a neutral spine.",
    "incomplete_lockout": "Hips not fully locked out. Stand tall, squeeze glutes at the top.",
    # Bench
    "excessive_elbow_flare": "Elbows are flaring too wide. Tuck them 45-60° to protect your rotator cuff.",
    "wrist_misalignment": "Wrists are drifting from elbow line. Keep wrists stacked over elbows.",
    "uneven_press": "Press is uneven. Focus on driving both hands at the same speed.",
    # OHP
    "excessive_layback": "You're leaning back too much. Brace your core to prevent lower-back strain.",
    "elbow_flare_ohp": "Elbows are drifting back. Keep them slightly in front of the bar.",
    # Pull
    "pull_asymmetry": "Elbows aren't pulling evenly. Initiate with the weaker side's lat.",
    # Shared / isolation
    "shoulder_asymmetry": "Shoulders are uneven. Ensure both sides are engaged equally.",
    "asymmetry_instability": "Left-right asymmetry detected. Reduce load and focus on even engagement.",
    "hip_rock": "Hips are rocking. Reduce weight and keep your core braced throughout.",
}


def _build_feedback(issues: List[str]) -> str:
    if not issues:
        return "Form looks good! Maintain this position and progress load gradually."
    msgs = [_ISSUE_FEEDBACK.get(issue, issue) for issue in issues[:3]]
    return " ".join(msgs)


def _score_from_issues(issues: List[str]) -> float:
    red_issues = {
        "excessive_forward_lean", "rounded_back", "left_knee_valgus",
        "right_knee_valgus", "excessive_elbow_flare", "excessive_layback",
    }
    yellow_issues = {
        "forward_lean", "shallow_depth", "incomplete_lockout", "shoulder_asymmetry",
        "wrist_misalignment", "uneven_press", "elbow_flare_ohp", "asymmetry_instability",
        "pull_asymmetry", "hip_rock",
    }
    score = 100.0
    for issue in issues:
        if issue in red_issues:
            score -= 20.0
        elif issue in yellow_issues:
            score -= 10.0
    return max(0.0, round(score, 1))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse_keypoints(
    keypoints: Dict[str, Any],
    exercise_key: str,
    view: str = "auto",
) -> Dict[str, Any]:
    """
    Main entry point.  Returns a dict ready to be serialised as FormRealtimeOut.
    """
    if view == "auto":
        view = _infer_view(keypoints)

    exercise_cat = _classify(exercise_key)
    cmap = _ColorMap()

    if exercise_cat == "squat":
        issues = _analyse_squat(keypoints, view, cmap)
    elif exercise_cat == "deadlift":
        issues = _analyse_deadlift(keypoints, view, cmap)
    elif exercise_cat == "bench":
        issues = _analyse_bench(keypoints, view, cmap)
    elif exercise_cat == "ohp":
        issues = _analyse_ohp(keypoints, view, cmap)
    elif exercise_cat == "pull":
        issues = _analyse_pull(keypoints, view, cmap)
    else:
        issues = _analyse_isolation(keypoints, view, cmap)

    # Collect which joints are actually present in this frame
    present = [j for j in ALL_JOINTS if _xy(keypoints, j) is not None]

    joint_colors = cmap.build_joints(present)
    bone_colors = cmap.build_bones(present)
    feedback = _build_feedback(issues)
    overall_score = _score_from_issues(issues)

    return {
        "joint_colors": joint_colors,
        "bone_colors": bone_colors,
        "issues": issues,
        "feedback": feedback,
        "overall_score": overall_score,
    }
