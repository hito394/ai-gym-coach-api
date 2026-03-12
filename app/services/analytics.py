from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from app.db import models
from app.utils.exercise_key import normalize_exercise_key


MUSCLE_GROUP_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "chest": ("bench", "incline", "fly", "press"),
    "back": ("row", "pulldown", "pull", "chin"),
    "legs": ("squat", "leg", "lunge", "split_squat"),
    "posterior_chain": ("deadlift", "rdl", "hip_thrust", "hinge"),
    "shoulders": ("overhead", "shoulder", "lateral_raise"),
    "arms": ("curl", "triceps", "extension"),
    "core": ("plank", "crunch", "core"),
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def estimate_one_rm(weight: float, reps: int) -> float:
    if reps <= 0:
        return 0.0
    return weight * (1.0 + (reps / 30.0))


def week_label(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def last_week_labels(weeks: int = 8) -> List[str]:
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())
    labels: List[str] = []
    for i in range(weeks - 1, -1, -1):
        start = monday - timedelta(days=7 * i)
        year, week, _ = start.isocalendar()
        labels.append(f"{year}-W{week:02d}")
    return labels


def to_trend_points(labels: Iterable[str], values: Dict[str, float]) -> List[Dict[str, float | str]]:
    return [{"label": label, "value": round(float(values.get(label, 0.0)), 2)} for label in labels]


def muscle_group_for_exercise(exercise_key: str, exercise_name: str) -> str:
    candidate = f"{exercise_key} {exercise_name}".lower()
    for group, keys in MUSCLE_GROUP_KEYWORDS.items():
        if any(key in candidate for key in keys):
            return group
    return "other"


def _fastest_improving_lift(
    exercise_week_1rm: Dict[str, Dict[str, float]],
    labels: List[str],
) -> Optional[str]:
    best_name: Optional[str] = None
    best_growth = 0.0

    for exercise_key, by_week in exercise_week_1rm.items():
        seq = [by_week.get(label, 0.0) for label in labels]
        recent = [v for v in seq[-3:] if v > 0]
        previous = [v for v in seq[-6:-3] if v > 0]
        if not recent or not previous:
            continue
        prev_avg = sum(previous) / len(previous)
        recent_avg = sum(recent) / len(recent)
        if prev_avg <= 0:
            continue
        growth = (recent_avg - prev_avg) / prev_avg
        if growth > best_growth:
            best_growth = growth
            best_name = exercise_key

    return best_name


def _plateau_exercise(
    exercise_week_1rm: Dict[str, Dict[str, float]],
    labels: List[str],
) -> Optional[str]:
    for exercise_key, by_week in exercise_week_1rm.items():
        seq = [by_week.get(label, 0.0) for label in labels]
        non_zero = [v for v in seq if v > 0]
        if len(non_zero) < 4:
            continue
        window = non_zero[-4:]
        if max(window[-3:]) <= (window[0] * 1.01):
            return exercise_key
    return None


def build_analytics_snapshot(
    user: models.User,
    logs: List[models.SetLog],
    body_weight_logs: Optional[List[models.BodyWeightLog]] = None,
) -> Dict[str, object]:
    labels = last_week_labels(8)
    current_label = labels[-1]
    previous_label = labels[-2]

    weekly_volume: Dict[str, float] = defaultdict(float)
    weekly_days: Dict[str, set] = defaultdict(set)
    weekly_max_1rm: Dict[str, float] = defaultdict(float)

    exercise_week_weight: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    exercise_week_1rm: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    exercise_best_1rm: Dict[str, float] = defaultdict(float)
    muscle_group_week_volume: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for log in logs:
        performed_at = log.performed_at or datetime.utcnow()
        label = week_label(performed_at)
        if label not in labels:
            continue

        exercise_name = (log.exercise or "").strip()
        exercise_key = (log.exercise_key or "").strip() or normalize_exercise_key(exercise_name)
        one_rm = estimate_one_rm(float(log.weight or 0.0), int(log.reps or 0))
        volume = float((log.weight or 0.0) * (log.reps or 0))

        weekly_volume[label] += volume
        weekly_days[label].add(performed_at.date())
        weekly_max_1rm[label] = max(weekly_max_1rm[label], one_rm)

        exercise_week_weight[exercise_key][label] = max(exercise_week_weight[exercise_key][label], float(log.weight or 0.0))
        exercise_week_1rm[exercise_key][label] = max(exercise_week_1rm[exercise_key][label], one_rm)
        exercise_best_1rm[exercise_key] = max(exercise_best_1rm[exercise_key], one_rm)

        muscle = muscle_group_for_exercise(exercise_key, exercise_name)
        muscle_group_week_volume[muscle][label] += volume

    current_week_volume = float(weekly_volume.get(current_label, 0.0))
    current_week_frequency = len(weekly_days.get(current_label, set()))

    current_one_rm = float(weekly_max_1rm.get(current_label, 0.0))
    previous_one_rm = float(weekly_max_1rm.get(previous_label, 0.0))

    if previous_one_rm <= 0:
        strength_component = 60.0 if current_one_rm > 0 else 0.0
    else:
        strength_growth = (current_one_rm - previous_one_rm) / previous_one_rm
        strength_component = _clamp(50.0 + (strength_growth * 500.0))

    target_workouts = max(int(user.training_days or 4), 1)
    consistency_component = _clamp(min(current_week_frequency / target_workouts, 1.0) * 100.0)

    prev_volumes = [weekly_volume[label] for label in labels[:-1] if weekly_volume[label] > 0]
    if not prev_volumes:
        volume_quality_component = 60.0 if current_week_volume > 0 else 0.0
    else:
        recent_prev = prev_volumes[-4:]
        baseline = sum(recent_prev) / len(recent_prev)
        ratio = current_week_volume / baseline if baseline > 0 else 1.0
        deviation = abs(ratio - 1.0)
        volume_quality_component = _clamp(100.0 - (deviation * 120.0))

    progress_score = _clamp(
        (0.40 * strength_component)
        + (0.35 * consistency_component)
        + (0.25 * volume_quality_component)
    )

    strongest_exercise = max(exercise_best_1rm, key=exercise_best_1rm.get) if exercise_best_1rm else None
    fastest_improving_lift = _fastest_improving_lift(exercise_week_1rm, labels)
    plateau_exercise = _plateau_exercise(exercise_week_1rm, labels)

    current_group_volume = {
        group: volumes.get(current_label, 0.0)
        for group, volumes in muscle_group_week_volume.items()
    }
    non_zero_groups = {k: v for k, v in current_group_volume.items() if v > 0}
    weakest_muscle_group = min(non_zero_groups, key=non_zero_groups.get) if non_zero_groups else None

    insights: List[str] = []
    if strongest_exercise:
        insights.append(f"Strongest lift right now: {strongest_exercise.replace('_', ' ')}")
    if fastest_improving_lift:
        insights.append(f"Fastest improving lift: {fastest_improving_lift.replace('_', ' ')}")
    if weakest_muscle_group:
        insights.append(f"Weakest muscle group this week: {weakest_muscle_group.replace('_', ' ')}")
    if plateau_exercise:
        insights.append(f"Plateau detected: {plateau_exercise.replace('_', ' ')} has not improved for ~3 weeks")
    if not insights:
        insights.append("Log 2-3 sessions to unlock personalized analytics insights")

    strongest_key = strongest_exercise
    if strongest_key:
        strongest_weight_points = to_trend_points(labels, exercise_week_weight.get(strongest_key, {}))
    else:
        strongest_weight_points = [{"label": label, "value": 0.0} for label in labels]

    focus_muscle = None
    if weakest_muscle_group and weakest_muscle_group in muscle_group_week_volume:
        focus_muscle = weakest_muscle_group
    elif muscle_group_week_volume:
        focus_muscle = max(
            muscle_group_week_volume,
            key=lambda group: sum(muscle_group_week_volume[group].values()),
        )

    if focus_muscle:
        muscle_group_points = to_trend_points(labels, muscle_group_week_volume[focus_muscle])
    else:
        muscle_group_points = [{"label": label, "value": 0.0} for label in labels]

    body_weight_points: List[Dict[str, float | str]] = []
    if body_weight_logs:
        weekly_body_weight: Dict[str, float] = {}
        ordered_weight_logs = sorted(body_weight_logs, key=lambda log: log.measured_at)
        for item in ordered_weight_logs:
            key = week_label(item.measured_at)
            if key in labels:
                weekly_body_weight[key] = float(item.weight_kg)

        carry = float(user.weight_kg) if user.weight_kg is not None else 0.0
        for label in labels:
            if label in weekly_body_weight:
                carry = weekly_body_weight[label]
            body_weight_points.append({"label": label, "value": round(carry, 2)})
    elif user.weight_kg is not None:
        body_weight_points = [
            {"label": label, "value": round(float(user.weight_kg), 2)} for label in labels
        ]

    return {
        "labels": labels,
        "summary": {
            "user_id": int(user.id),
            "weekly_volume": round(current_week_volume, 2),
            "workout_frequency": int(current_week_frequency),
            "progress_score": round(progress_score, 2),
            "strongest_exercise": strongest_exercise,
            "fastest_improving_lift": fastest_improving_lift,
            "weakest_muscle_group": weakest_muscle_group,
            "plateau_exercise": plateau_exercise,
            "insights": insights,
            "exercise_weight_points": strongest_weight_points,
            "weekly_volume_points": to_trend_points(labels, weekly_volume),
            "one_rm_points": to_trend_points(labels, weekly_max_1rm),
            "workout_frequency_points": [
                {"label": label, "value": float(len(weekly_days.get(label, set())))} for label in labels
            ],
            "muscle_group_volume": {
                group: round(volume, 2) for group, volume in current_group_volume.items()
            },
            "muscle_group_points": muscle_group_points,
            "body_weight_points": body_weight_points,
        },
        "score": {
            "user_id": int(user.id),
            "progress_score": round(progress_score, 2),
            "strength_component": round(strength_component, 2),
            "consistency_component": round(consistency_component, 2),
            "volume_quality_component": round(volume_quality_component, 2),
        },
        "exercise_week_weight": exercise_week_weight,
        "exercise_week_1rm": exercise_week_1rm,
    }


def build_exercise_progress(
    user_id: int,
    labels: List[str],
    exercise_week_weight: Dict[str, Dict[str, float]],
    exercise_week_1rm: Dict[str, Dict[str, float]],
    exercise_key: Optional[str],
    strongest_exercise: Optional[str],
) -> Dict[str, object]:
    selected = exercise_key or strongest_exercise

    if selected is None:
        return {
            "user_id": user_id,
            "exercise_key": None,
            "weight_points": [{"label": label, "value": 0.0} for label in labels],
            "one_rm_points": [{"label": label, "value": 0.0} for label in labels],
        }

    by_week_weight = exercise_week_weight.get(selected, {})
    by_week_1rm = exercise_week_1rm.get(selected, {})

    return {
        "user_id": user_id,
        "exercise_key": selected,
        "weight_points": to_trend_points(labels, by_week_weight),
        "one_rm_points": to_trend_points(labels, by_week_1rm),
    }
