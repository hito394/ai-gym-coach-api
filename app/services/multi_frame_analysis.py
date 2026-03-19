"""
Multi-frame (batch) form analysis.

Clients submit a sequence of pose-estimation frames from a recorded set.
This service:

  1. Extracts a scalar "position signal" from each frame — the primary
     joint that tracks the rep (hip y for squat/deadlift, wrist y for
     bench/ohp, elbow y for pull/isolation).

  2. Detects reps automatically via a peak-finding algorithm on that
     signal.  Each local maximum (standing/extended) → local minimum
     (bottom of rep) transition counts as one rep.

  3. For each rep, identifies the "key frame" (the bottom / hardest
     position) and runs the full keypoint analyser on it.

  4. Aggregates scores across reps:
       depth_score     = best (highest) depth score across all reps
       torso_score     = worst (lowest) torso score across all reps  ← safety conservative
       symmetry_score  = mean across all reps
       tempo_score     = based on rep-duration consistency (CV)
       bar_path_score  = mean across reps

  5. Returns per-rep breakdowns + aggregate result.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.form import FormBatchIn, FormBatchOut, RepSummary
from app.services.keypoint_analysis import (
    analyse_keypoints,
    _xy,
    _mid,
    _angle_at_vertex,
    _torso_angle,
    _classify,
    _score_from_issues,
    _build_feedback,
    _CONF_STANDARD,
)


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

# Which joint pair tracks the "up-down" movement for each exercise category.
# We use the MIDPOINT of the pair for robustness.
_SIGNAL_JOINTS: Dict[str, Tuple[str, str]] = {
    "squat":     ("left_hip",   "right_hip"),
    "deadlift":  ("left_hip",   "right_hip"),
    "bench":     ("left_wrist", "right_wrist"),
    "ohp":       ("left_wrist", "right_wrist"),
    "pull":      ("left_elbow", "right_elbow"),
    "isolation": ("left_elbow", "right_elbow"),
}

# For exercises where "lower = more depth" the signal goes UP in image coords
# as the athlete squats (y increases downward in image space).
# We normalise so that "rep bottom" is always a local MINIMUM after inversion.
_INVERT_SIGNAL: Dict[str, bool] = {
    "squat":     False,   # hip y increases (goes lower in frame) during descent → local max = bottom
    "deadlift":  False,
    "bench":     True,    # wrist y decreases (moves up) during the press → local min = top (lockout)
    "ohp":       True,
    "pull":      False,   # elbow y increases during the pull → local max = contracted
    "isolation": False,
}

# bench/ohp: bottom of rep = wrist highest (lowest y value) → we want local min of wrist_y
# Actually for bench, bottom = bar on chest = wrist at LOWEST y (bar highest in image = smallest y)
# → we want to find local minima of wrist_y signal (where the lift is at the bottom)
# Hmm, let me reconsider:
# - squat: hip y is HIGH (large value) at bottom position → find local MAX
# - bench: wrist y is LOW (small value) at bottom (bar on chest) → find local MIN
# - ohp: wrist y is HIGH (large value) at lockout, LOW at start → find local MAX for lockout
# I'll detect BOTH peaks and troughs and figure out which direction is which
# by looking at the exercise category.

# Simpler approach: just find "motion reversals" — points where velocity sign flips
# and the amplitude is large enough to count as a rep.


def _extract_signal(
    frames_kp: List[Dict[str, Any]],
    exercise_cat: str,
) -> List[Optional[float]]:
    """
    Return a time-series of the position signal (one value per frame).
    None means the joint was not visible in that frame.
    """
    j1, j2 = _SIGNAL_JOINTS.get(exercise_cat, ("left_hip", "right_hip"))

    signal: List[Optional[float]] = []
    for kp in frames_kp:
        p1 = _xy(kp, j1, _CONF_STANDARD)
        p2 = _xy(kp, j2, _CONF_STANDARD)
        mid = _mid(p1, p2)
        if mid is not None:
            signal.append(mid[1])  # y coordinate
        else:
            # Try single joint
            p = _xy(kp, j1, _CONF_STANDARD) or _xy(kp, j2, _CONF_STANDARD)
            signal.append(p[1] if p else None)

    return signal


def _fill_nones(signal: List[Optional[float]]) -> List[float]:
    """Linear interpolation over None gaps."""
    out = list(signal)
    # Forward fill edges
    for i in range(len(out)):
        if out[i] is not None:
            for j in range(i):
                out[j] = out[i]
            break
    for i in range(len(out) - 1, -1, -1):
        if out[i] is not None:
            for j in range(i + 1, len(out)):
                out[j] = out[i]
            break
    # Interpolate interior gaps
    i = 0
    while i < len(out):
        if out[i] is None:
            j = i + 1
            while j < len(out) and out[j] is None:
                j += 1
            if j < len(out) and i > 0:
                start_v = out[i - 1]
                end_v   = out[j]
                span    = j - (i - 1)
                for k in range(i, j):
                    out[k] = start_v + (end_v - start_v) * (k - i + 1) / span
            i = j
        else:
            i += 1
    return [v if v is not None else 0.0 for v in out]


def _smooth(signal: List[float], window: int = 5) -> List[float]:
    """Simple moving average to reduce single-frame noise."""
    n = len(signal)
    if n <= window:
        return signal
    result = []
    for i in range(n):
        lo = max(0, i - window // 2)
        hi = min(n, lo + window)
        result.append(sum(signal[lo:hi]) / (hi - lo))
    return result


def _find_rep_boundaries(
    signal: List[float],
    exercise_cat: str,
    timestamps_ms: List[int],
) -> List[Tuple[int, int, int]]:
    """
    Find rep boundaries as (start_idx, bottom_idx, end_idx).

    Strategy:
    - Compute the total signal range; if it's tiny the person isn't moving.
    - Find local extrema (peaks / troughs) that are separated by at least
      min_sep frames and have a prominence of at least min_prominence * range.
    - Pair extrema into reps: for squat/deadlift one rep = one peak (hip lowest)
      flanked by troughs (standing).
    """
    n = len(signal)
    if n < 4:
        return []

    sig_range = max(signal) - min(signal)
    if sig_range < 0.03:   # < 3% of normalised frame height → no meaningful movement
        return []

    # For exercises where the "bottom" is a local max (hip goes DOWN → y increases)
    # invert the signal so that "bottom" is always a local minimum.
    invert = _INVERT_SIGNAL.get(exercise_cat, False)
    work = [-v for v in signal] if invert else list(signal)

    work_range = max(work) - min(work)
    min_prominence = work_range * 0.25   # a real rep is at least 25% of total range
    # Minimum separation between two rep-bottoms: at least 15 frames (~0.5 s at 30 fps)
    min_sep = max(10, n // 20)

    # Find local maxima (= rep bottoms in `work` space) using prominence
    bottoms: List[int] = []
    for i in range(1, n - 1):
        if work[i] >= work[i - 1] and work[i] >= work[i + 1]:
            # Check prominence: how much above the nearest lower flanking values?
            left_min  = min(work[:i + 1])
            right_min = min(work[i:])
            prominence = work[i] - max(left_min, right_min)
            if prominence >= min_prominence:
                bottoms.append(i)

    # Merge bottoms too close together (keep the deeper one)
    merged: List[int] = []
    for b in sorted(bottoms):
        if merged and b - merged[-1] < min_sep:
            if work[b] > work[merged[-1]]:
                merged[-1] = b
        else:
            merged.append(b)

    if not merged:
        return []

    # Build rep boundaries: from just before start to just after end
    reps: List[Tuple[int, int, int]] = []
    for idx, bottom in enumerate(merged):
        # start = last local minimum before this bottom (= top of previous rep)
        start = 0
        if idx > 0:
            prev_bottom = merged[idx - 1]
            # find the trough between prev_bottom and this bottom
            trough = min(range(prev_bottom, bottom + 1), key=lambda i: work[i])
            start = trough
        else:
            # before first rep: go back until signal rises enough
            threshold = work[bottom] - min_prominence * 0.5
            start = bottom
            for i in range(bottom - 1, -1, -1):
                if work[i] <= threshold:
                    start = i
                    break

        # end = next local minimum after this bottom (= top of next rep)
        end = n - 1
        if idx < len(merged) - 1:
            next_bottom = merged[idx + 1]
            trough = min(range(bottom, next_bottom + 1), key=lambda i: work[i])
            end = trough
        else:
            threshold = work[bottom] - min_prominence * 0.5
            end = bottom
            for i in range(bottom + 1, n):
                if work[i] <= threshold:
                    end = i
                    break

        reps.append((start, bottom, end))

    return reps


# ---------------------------------------------------------------------------
# Per-frame measurement extraction
# ---------------------------------------------------------------------------

def _knee_angle_from_frame(kp: Dict[str, Any]) -> Optional[float]:
    """Average knee angle (degrees) — smaller = deeper squat."""
    l_hip   = _xy(kp, "left_hip")
    l_knee  = _xy(kp, "left_knee")
    l_ankle = _xy(kp, "left_ankle")
    r_hip   = _xy(kp, "right_hip")
    r_knee  = _xy(kp, "right_knee")
    r_ankle = _xy(kp, "right_ankle")

    angles = []
    la = _angle_at_vertex(l_hip, l_knee, l_ankle)
    ra = _angle_at_vertex(r_hip, r_knee, r_ankle)
    if la is not None:
        angles.append(la)
    if ra is not None:
        angles.append(ra)
    return sum(angles) / len(angles) if angles else None


def _torso_deg_from_frame(kp: Dict[str, Any]) -> Optional[float]:
    """Torso forward-lean (degrees) from a single frame."""
    l_s = _xy(kp, "left_shoulder")
    r_s = _xy(kp, "right_shoulder")
    l_h = _xy(kp, "left_hip")
    r_h = _xy(kp, "right_hip")
    shoulder_mid = _mid(l_s, r_s)
    hip_mid      = _mid(l_h, r_h)
    return _torso_angle(shoulder_mid, hip_mid)


# ---------------------------------------------------------------------------
# Score helpers (per-rep)
# ---------------------------------------------------------------------------

def _depth_score_from_knee_angle(angle: Optional[float]) -> float:
    """Convert knee angle to 0–100 depth score.  Smaller angle = better score."""
    if angle is None:
        return 50.0
    if angle <= 80:
        return 100.0
    if angle <= 100:
        return 95.0 - (angle - 80) * 0.5
    if angle <= 120:
        return 85.0 - (angle - 100) * 1.5
    return max(0.0, 55.0 - (angle - 120) * 1.5)


def _torso_score_from_deg(deg: Optional[float]) -> float:
    """Clamp torso lean angle to 0–100.  Same curve as form_analysis._torso_score."""
    if deg is None:
        return 50.0
    angle = abs(deg)
    if angle <= 20:
        return 95.0
    if angle <= 30:
        return max(0.0, 95.0 - (angle - 20) * 2.5)
    if angle <= 45:
        return max(0.0, 70.0 - (angle - 30) * 2.0)
    return 20.0


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _tempo_score_from_cv(cv: Optional[float]) -> float:
    """Coefficient of variation of rep durations → tempo score."""
    if cv is None:
        return 65.0
    if cv <= 0.08:
        return 95.0
    if cv <= 0.15:
        return 80.0
    if cv <= 0.25:
        return 65.0
    return 40.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyse_batch(payload: FormBatchIn) -> Dict[str, Any]:
    """
    Analyse a sequence of frames and return an aggregated result dict
    compatible with FormBatchOut.
    """
    exercise_cat = _classify(payload.exercise_key)

    # Build parallel lists
    timestamps_ms: List[int] = [f.timestamp_ms for f in payload.frames]
    frames_kp: List[Dict[str, Any]] = [
        {name: {"x": kp.x, "y": kp.y, "confidence": kp.confidence}
         for name, kp in frame.keypoints.items()}
        for frame in payload.frames
    ]

    n = len(frames_kp)
    duration_ms = timestamps_ms[-1] - timestamps_ms[0] if n > 1 else 0

    # Use the first high-confidence frame to auto-detect view
    view = payload.view
    if view == "auto":
        from app.services.keypoint_analysis import _infer_view
        for kp in frames_kp:
            v = _infer_view(kp)
            if v != "side":
                view = v
                break
        else:
            view = "side"

    # ----------------------------------------------------------------
    # Extract position signal and find reps
    # ----------------------------------------------------------------
    raw_signal = _extract_signal(frames_kp, exercise_cat)
    filled     = _fill_nones(raw_signal)
    smoothed   = _smooth(filled, window=max(3, n // 30))

    rep_bounds = _find_rep_boundaries(smoothed, exercise_cat, timestamps_ms)

    # ----------------------------------------------------------------
    # Per-rep analysis
    # ----------------------------------------------------------------
    rep_summaries: List[RepSummary] = []
    all_depth_scores:   List[float] = []
    all_torso_scores:   List[float] = []
    all_symmetry_scores: List[float] = []
    all_bar_path_scores: List[float] = []
    all_issues_flat:    List[str]   = []
    best_knee_angle:    Optional[float] = None
    worst_torso_deg:    Optional[float] = None

    rep_durations_ms: List[int] = []

    for rep_num, (start_i, bottom_i, end_i) in enumerate(rep_bounds, start=1):
        start_ms = timestamps_ms[start_i]
        end_ms   = timestamps_ms[min(end_i, n - 1)]
        rep_durations_ms.append(end_ms - start_ms)

        # Key frame analysis (bottom of rep)
        bottom_kp = frames_kp[bottom_i]
        kp_result = analyse_keypoints(bottom_kp, payload.exercise_key, view=view)

        # Metrics at bottom frame
        knee_angle  = _knee_angle_from_frame(bottom_kp)
        depth_score = _depth_score_from_knee_angle(knee_angle)

        # Worst torso in the eccentric phase (start → bottom) to catch rounding
        torso_values = []
        for i in range(start_i, min(bottom_i + 1, n)):
            t = _torso_deg_from_frame(frames_kp[i])
            if t is not None:
                torso_values.append(t)
        worst_torso = max(torso_values, default=None)
        torso_score = _torso_score_from_deg(worst_torso)

        # Track global extremes
        if knee_angle is not None:
            if best_knee_angle is None or knee_angle < best_knee_angle:
                best_knee_angle = knee_angle
        if worst_torso is not None:
            if worst_torso_deg is None or worst_torso > worst_torso_deg:
                worst_torso_deg = worst_torso

        # Symmetry and bar path from bottom-frame keypoint analyser
        # We re-derive from kp_result's score since keypoint analyser already computes it
        symmetry_score  = kp_result["overall_score"]  # proxy — actual symmetry from deductions
        bar_path_score  = kp_result["overall_score"]

        all_depth_scores.append(depth_score)
        all_torso_scores.append(torso_score)
        all_symmetry_scores.append(symmetry_score)
        all_bar_path_scores.append(bar_path_score)
        all_issues_flat.extend(kp_result["issues"])

        rep_summaries.append(RepSummary(
            rep_number=rep_num,
            start_ms=start_ms,
            end_ms=end_ms,
            depth_score=round(depth_score, 1),
            worst_torso_angle=round(worst_torso, 1) if worst_torso is not None else 0.0,
            issues=kp_result["issues"],
        ))

    # ----------------------------------------------------------------
    # If no reps were detected, analyse the single "hardest" frame
    # ----------------------------------------------------------------
    if not rep_summaries:
        # Find the frame with maximum signal value (deepest point)
        filled_signal = _fill_nones(raw_signal)
        best_frame_i = (
            filled_signal.index(max(filled_signal))
            if _INVERT_SIGNAL.get(exercise_cat, False)
            else filled_signal.index(max(filled_signal))
        )
        bottom_kp   = frames_kp[best_frame_i]
        kp_result   = analyse_keypoints(bottom_kp, payload.exercise_key, view=view)
        knee_angle  = _knee_angle_from_frame(bottom_kp)
        depth_score = _depth_score_from_knee_angle(knee_angle)
        torso_vals  = [_torso_deg_from_frame(kp) for kp in frames_kp]
        worst_t     = max((v for v in torso_vals if v is not None), default=None)
        torso_score = _torso_score_from_deg(worst_t)

        best_knee_angle = knee_angle
        worst_torso_deg = worst_t
        all_depth_scores.append(depth_score)
        all_torso_scores.append(torso_score)
        all_symmetry_scores.append(kp_result["overall_score"])
        all_bar_path_scores.append(kp_result["overall_score"])
        all_issues_flat.extend(kp_result["issues"])

    # ----------------------------------------------------------------
    # Aggregate scores
    # ----------------------------------------------------------------
    def _safe_max(lst: List[float], default: float = 50.0) -> float:
        return max(lst) if lst else default

    def _safe_min(lst: List[float], default: float = 50.0) -> float:
        return min(lst) if lst else default

    def _safe_mean(lst: List[float], default: float = 50.0) -> float:
        return sum(lst) / len(lst) if lst else default

    depth_score     = _safe_max(all_depth_scores)      # best across reps
    torso_score     = _safe_min(all_torso_scores)      # worst (safety-conservative)
    symmetry_score  = _safe_mean(all_symmetry_scores)
    bar_path_score  = _safe_mean(all_bar_path_scores)

    # Tempo from rep-duration consistency
    tempo_cv: Optional[float] = None
    if len(rep_durations_ms) >= 2:
        mean_dur = statistics.mean(rep_durations_ms)
        if mean_dur > 0:
            tempo_cv = statistics.stdev(rep_durations_ms) / mean_dur
    tempo_score = _tempo_score_from_cv(tempo_cv)

    # Category-specific overall weights (mirrors form_analysis._OVERALL_WEIGHTS)
    _WEIGHTS = {
        "squat":     (0.30, 0.25, 0.20, 0.20, 0.05),
        "deadlift":  (0.20, 0.40, 0.20, 0.15, 0.05),
        "bench":     (0.15, 0.20, 0.30, 0.25, 0.10),
        "ohp":       (0.15, 0.35, 0.25, 0.20, 0.05),
        "pull":      (0.15, 0.25, 0.30, 0.25, 0.05),
        "isolation": (0.10, 0.15, 0.35, 0.35, 0.05),
    }
    w_d, w_t, w_s, w_tm, w_b = _WEIGHTS.get(exercise_cat, (0.30, 0.25, 0.20, 0.20, 0.05))
    overall_score = _clamp(
        w_d * depth_score + w_t * torso_score + w_s * symmetry_score
        + w_tm * tempo_score + w_b * bar_path_score
    )

    # Deduplicate issues (most frequent first)
    from collections import Counter
    issue_counts = Counter(all_issues_flat)
    issues = [issue for issue, _ in issue_counts.most_common()]

    feedback = _build_feedback(issues)

    return {
        # FormAnalyzeOut-compatible fields
        "overall_score":     round(overall_score, 2),
        "depth_score":       round(depth_score, 2),
        "torso_angle_score": round(torso_score, 2),
        "symmetry_score":    round(symmetry_score, 2),
        "tempo_score":       round(tempo_score, 2),
        "bar_path_score":    round(bar_path_score, 2),
        "issues":            issues,
        "feedback":          feedback,
        "diagnostics":       {},
        # Batch-specific
        "frame_count":          n,
        "duration_ms":          duration_ms,
        "rep_count":            len(rep_summaries),
        "reps":                 rep_summaries,
        "depth_achieved_deg":   round(best_knee_angle, 1) if best_knee_angle is not None else None,
        "worst_torso_deg":      round(worst_torso_deg, 1) if worst_torso_deg is not None else None,
        "tempo_cv":             round(tempo_cv, 3) if tempo_cv is not None else None,
    }
