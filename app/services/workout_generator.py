from typing import List, Dict
from app.schemas.workout import WorkoutPlanOut, WorkoutDayOut, ExercisePrescription
from app.utils.exercise_key import normalize_exercise_key


SPLIT_TEMPLATES = {
    "ppl": ["push", "pull", "legs", "push", "pull", "legs"],
    "upper_lower": ["upper", "lower", "upper", "lower"],
    "full_body": ["full_body", "full_body", "full_body"],
}

EXERCISE_LIBRARY = {
    "push": [
        "Barbell Bench Press",
        "Incline Dumbbell Press",
        "Overhead Press",
        "Lateral Raise",
        "Triceps Pushdown",
    ],
    "pull": [
        "Pull-up",
        "Barbell Row",
        "Lat Pulldown",
        "Face Pull",
        "Biceps Curl",
    ],
    "legs": [
        "Back Squat",
        "Romanian Deadlift",
        "Leg Press",
        "Leg Curl",
        "Calf Raise",
    ],
    "upper": [
        "Bench Press",
        "Row",
        "Overhead Press",
        "Lat Pulldown",
        "Biceps Curl",
        "Triceps Pushdown",
    ],
    "lower": [
        "Squat",
        "RDL",
        "Leg Press",
        "Leg Curl",
        "Calf Raise",
    ],
    "full_body": [
        "Squat",
        "Bench Press",
        "Row",
        "Overhead Press",
        "Leg Curl",
    ],
}


def _volume_landmarks(experience: str) -> Dict[str, int]:
    if experience == "beginner":
        return {"mev": 6, "mav": 10, "mrv": 14}
    if experience == "advanced":
        return {"mev": 10, "mav": 16, "mrv": 22}
    return {"mev": 8, "mav": 12, "mrv": 18}


def generate_plan(
    split: str,
    training_days: int,
    experience: str,
    week_index: int,
    block_index: int,
    readiness_score: float,
) -> WorkoutPlanOut:
    split_days = SPLIT_TEMPLATES.get(split, SPLIT_TEMPLATES["ppl"]).copy()
    split_days = split_days[:training_days]

    volume = _volume_landmarks(experience)

    block_length = 5  # 4-6 week block, choose 5 for MVP
    intensity_modifier = 1.0 + (week_index - 1) * 0.03
    volume_modifier = 1.0 + (week_index - 1) * 0.05

    if readiness_score < 0.5:
        volume_modifier *= 0.85
        intensity_modifier *= 0.9

    if week_index >= block_length:
        volume_modifier *= 0.7  # deload week
        intensity_modifier *= 0.9

    days: List[WorkoutDayOut] = []
    for idx, focus in enumerate(split_days, start=1):
        exercises = []
        library = EXERCISE_LIBRARY.get(focus, EXERCISE_LIBRARY["full_body"])
        for name in library:
            exercises.append(
                ExercisePrescription(
                    name=name,
                    exercise_key=normalize_exercise_key(name),
                    sets=max(2, int(3 * volume_modifier)),
                    rep_range="6-12" if "Press" in name or "Row" in name else "8-15",
                    rpe_target=7.5 * intensity_modifier,
                    rest_seconds=120 if "Squat" in name or "Deadlift" in name else 90,
                    notes="Focus on controlled tempo and full range",
                )
            )
        days.append(
            WorkoutDayOut(
                day_index=idx,
                focus=focus,
                exercises=exercises,
            )
        )

    return WorkoutPlanOut(
        plan_name=f"{split.upper()} Block {block_index}",
        split=split,
        week_index=week_index,
        block_index=block_index,
        days=days,
        volume_landmarks=volume,
        readiness_score=readiness_score,
        fatigue_score=max(0.0, 1.0 - readiness_score),
    )
