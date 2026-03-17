"""
Gym exercise registry – single source of truth for supported exercises.

All exercise keys are normalised (lowercase, underscores).
Only weight-training / gym exercises are listed here; other sports
(golf, tennis, running, etc.) are explicitly NOT supported and will
be rejected at the API validation layer.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional

# ---------------------------------------------------------------------------
# Category → frozenset of exercise keys
# ---------------------------------------------------------------------------

SQUAT_EXERCISES: FrozenSet[str] = frozenset({
    "squat",
    "back_squat",
    "front_squat",
    "goblet_squat",
    "hack_squat",
    "box_squat",
    "pause_squat",
    "bulgarian_split_squat",
    "split_squat",
    "pistol_squat",
    "zercher_squat",
    "safety_bar_squat",
})

HINGE_EXERCISES: FrozenSet[str] = frozenset({
    "deadlift",
    "conventional_deadlift",
    "sumo_deadlift",
    "trap_bar_deadlift",
    "hex_bar_deadlift",
    "romanian_deadlift",
    "rdl",
    "stiff_leg_deadlift",
    "good_morning",
    "hip_thrust",
    "barbell_hip_thrust",
    "glute_bridge",
    "single_leg_rdl",
})

BENCH_EXERCISES: FrozenSet[str] = frozenset({
    "bench_press",
    "barbell_bench_press",
    "flat_bench_press",
    "incline_bench_press",
    "decline_bench_press",
    "close_grip_bench_press",
    "dumbbell_bench_press",
    "incline_dumbbell_press",
    "decline_dumbbell_press",
    "floor_press",
    "dips",
    "chest_dips",
    "push_up",
    "wide_grip_push_up",
    "diamond_push_up",
    "cable_fly",
    "cable_flye",
    "pec_deck",
    "dumbbell_fly",
})

OHP_EXERCISES: FrozenSet[str] = frozenset({
    "overhead_press",
    "ohp",
    "military_press",
    "shoulder_press",
    "seated_overhead_press",
    "seated_dumbbell_press",
    "arnold_press",
    "dumbbell_shoulder_press",
    "push_press",
    "landmine_press",
})

PULL_EXERCISES: FrozenSet[str] = frozenset({
    "pull_up",
    "pullup",
    "chin_up",
    "chinup",
    "lat_pulldown",
    "pulldown",
    "barbell_row",
    "bent_over_row",
    "dumbbell_row",
    "cable_row",
    "seated_row",
    "row",
    "chest_supported_row",
    "t_bar_row",
    "meadows_row",
    "face_pull",
    "rear_delt_fly",
    "rear_delt_row",
})

SHOULDER_ISOLATION: FrozenSet[str] = frozenset({
    "lateral_raise",
    "dumbbell_lateral_raise",
    "cable_lateral_raise",
    "front_raise",
    "upright_row",
})

ARM_EXERCISES: FrozenSet[str] = frozenset({
    "biceps_curl",
    "bicep_curl",
    "curl",
    "barbell_curl",
    "dumbbell_curl",
    "hammer_curl",
    "preacher_curl",
    "concentration_curl",
    "incline_curl",
    "cable_curl",
    "triceps_pushdown",
    "tricep_pushdown",
    "skull_crusher",
    "triceps_extension",
    "tricep_extension",
    "overhead_triceps_extension",
    "close_grip_bench_press",  # also in bench
    "diamond_push_up",         # also in bench
})

LEG_ISOLATION: FrozenSet[str] = frozenset({
    "leg_press",
    "leg_curl",
    "lying_leg_curl",
    "seated_leg_curl",
    "leg_extension",
    "calf_raise",
    "standing_calf_raise",
    "seated_calf_raise",
    "donkey_calf_raise",
    "lunges",
    "lunge",
    "walking_lunge",
    "reverse_lunge",
    "lateral_lunge",
    "step_up",
    "abductor_machine",
    "adductor_machine",
})

CORE_EXERCISES: FrozenSet[str] = frozenset({
    "plank",
    "ab_wheel",
    "hanging_leg_raise",
    "cable_crunch",
    "crunch",
    "russian_twist",
    "pallof_press",
    "dead_bug",
    "bird_dog",
    "side_plank",
})

# ---------------------------------------------------------------------------
# Master registry and category lookup
# ---------------------------------------------------------------------------

_CATEGORY_MAP: Dict[str, FrozenSet[str]] = {
    "squat": SQUAT_EXERCISES,
    "deadlift": HINGE_EXERCISES,
    "bench": BENCH_EXERCISES,
    "ohp": OHP_EXERCISES,
    "pull": PULL_EXERCISES,
    "shoulder_isolation": SHOULDER_ISOLATION,
    "arms": ARM_EXERCISES,
    "legs": LEG_ISOLATION,
    "core": CORE_EXERCISES,
}

# Flat set of all supported exercise keys
ALL_GYM_EXERCISES: FrozenSet[str] = frozenset(
    key for keys in _CATEGORY_MAP.values() for key in keys
)


def get_exercise_category(exercise_key: str) -> Optional[str]:
    """
    Return the broad category for *exercise_key*, or None if unsupported.

    Categories used by the form analysis services: "squat", "deadlift",
    "bench", "ohp".  Other gym exercises return their own category but are
    still accepted by the API.
    """
    key = exercise_key.lower().strip()
    for category, keys in _CATEGORY_MAP.items():
        if key in keys:
            return category
    return None


def is_gym_exercise(exercise_key: str) -> bool:
    """Return True if *exercise_key* is a recognised gym exercise."""
    return exercise_key.lower().strip() in ALL_GYM_EXERCISES
