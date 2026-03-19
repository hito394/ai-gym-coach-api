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
    # バーベルスクワット
    "squat",
    "back_squat",
    "front_squat",
    "low_bar_squat",
    "high_bar_squat",
    "pause_squat",
    "box_squat",
    "pin_squat",
    "safety_bar_squat",
    "zercher_squat",
    # ダンベル・その他スクワット
    "goblet_squat",
    "dumbbell_squat",
    "hack_squat",
    "machine_hack_squat",
    "belt_squat",
    # 片脚・スプリット系
    "bulgarian_split_squat",
    "split_squat",
    "pistol_squat",
    "single_leg_squat",
    "rear_foot_elevated_split_squat",
    # ランジ系（スクワットパターン）
    "lunge",
    "lunges",
    "walking_lunge",
    "reverse_lunge",
    "lateral_lunge",
    "curtsy_lunge",
    "step_up",
    "step_ups",
})

HINGE_EXERCISES: FrozenSet[str] = frozenset({
    # デッドリフト系
    "deadlift",
    "conventional_deadlift",
    "sumo_deadlift",
    "trap_bar_deadlift",
    "hex_bar_deadlift",
    "deficit_deadlift",
    "rack_pull",
    "romanian_deadlift",
    "rdl",
    "stiff_leg_deadlift",
    "single_leg_deadlift",
    "single_leg_rdl",
    # ヒップヒンジ系
    "good_morning",
    "barbell_good_morning",
    "hip_thrust",
    "barbell_hip_thrust",
    "dumbbell_hip_thrust",
    "machine_hip_thrust",
    "glute_bridge",
    "single_leg_glute_bridge",
    "banded_hip_thrust",
    "45_degree_back_extension",
    "back_extension",
    "hyperextension",
    "reverse_hyperextension",
    "nordic_curl",
    "nordic_hamstring_curl",
    "kettlebell_swing",
})

BENCH_EXERCISES: FrozenSet[str] = frozenset({
    # バーベルベンチプレス
    "bench_press",
    "barbell_bench_press",
    "flat_bench_press",
    "incline_bench_press",
    "decline_bench_press",
    "close_grip_bench_press",
    "wide_grip_bench_press",
    "paused_bench_press",
    "floor_press",
    "board_press",
    # ダンベルプレス
    "dumbbell_bench_press",
    "dumbbell_press",
    "incline_dumbbell_press",
    "decline_dumbbell_press",
    "neutral_grip_dumbbell_press",
    # ディップス・プッシュアップ
    "dips",
    "chest_dips",
    "weighted_dips",
    "push_up",
    "wide_grip_push_up",
    "diamond_push_up",
    "archer_push_up",
    "pike_push_up",
    # フライ系
    "cable_fly",
    "cable_flye",
    "cable_crossover",
    "low_cable_fly",
    "high_cable_fly",
    "pec_deck",
    "pec_deck_fly",
    "dumbbell_fly",
    "incline_dumbbell_fly",
    "decline_dumbbell_fly",
    "svend_press",
})

OHP_EXERCISES: FrozenSet[str] = frozenset({
    # バーベル系
    "overhead_press",
    "ohp",
    "military_press",
    "shoulder_press",
    "seated_overhead_press",
    "behind_the_neck_press",
    "push_press",
    "jerk",
    # ダンベル・マシン系
    "dumbbell_shoulder_press",
    "seated_dumbbell_press",
    "arnold_press",
    "landmine_press",
    "machine_shoulder_press",
    "smith_machine_overhead_press",
    # 片手・その他
    "single_arm_dumbbell_press",
    "log_press",
    "axle_press",
})

PULL_EXERCISES: FrozenSet[str] = frozenset({
    # チンアップ・プルアップ
    "pull_up",
    "pullup",
    "chin_up",
    "chinup",
    "weighted_pull_up",
    "weighted_chin_up",
    "neutral_grip_pull_up",
    "wide_grip_pull_up",
    "close_grip_chin_up",
    "archer_pull_up",
    # ラットプルダウン
    "lat_pulldown",
    "pulldown",
    "wide_grip_lat_pulldown",
    "close_grip_lat_pulldown",
    "neutral_grip_lat_pulldown",
    "single_arm_lat_pulldown",
    "straight_arm_pulldown",
    "straight_arm_lat_pulldown",
    # ロウ系
    "row",
    "barbell_row",
    "bent_over_row",
    "overhand_barbell_row",
    "underhand_barbell_row",
    "pendlay_row",
    "dumbbell_row",
    "single_arm_dumbbell_row",
    "cable_row",
    "seated_cable_row",
    "seated_row",
    "chest_supported_row",
    "chest_supported_dumbbell_row",
    "t_bar_row",
    "machine_row",
    "meadows_row",
    "kroc_row",
    "landmine_row",
    "inverted_row",
    # リアデルト・フェイスプル
    "face_pull",
    "cable_face_pull",
    "rear_delt_fly",
    "rear_delt_row",
    "dumbbell_rear_delt_fly",
    "cable_rear_delt_fly",
    "band_pull_apart",
    # シュラッグ
    "shrug",
    "barbell_shrug",
    "dumbbell_shrug",
    "trap_bar_shrug",
    "cable_shrug",
})

SHOULDER_ISOLATION: FrozenSet[str] = frozenset({
    "lateral_raise",
    "dumbbell_lateral_raise",
    "cable_lateral_raise",
    "machine_lateral_raise",
    "leaning_lateral_raise",
    "front_raise",
    "dumbbell_front_raise",
    "cable_front_raise",
    "plate_front_raise",
    "upright_row",
    "barbell_upright_row",
    "cable_upright_row",
    "y_raise",
    "w_raise",
    "prone_y_raise",
})

ARM_EXERCISES: FrozenSet[str] = frozenset({
    # バイセップス
    "biceps_curl",
    "bicep_curl",
    "curl",
    "barbell_curl",
    "ez_bar_curl",
    "dumbbell_curl",
    "alternating_dumbbell_curl",
    "hammer_curl",
    "cross_body_curl",
    "preacher_curl",
    "ez_bar_preacher_curl",
    "concentration_curl",
    "incline_curl",
    "incline_dumbbell_curl",
    "cable_curl",
    "rope_curl",
    "reverse_curl",
    "spider_curl",
    "21s",
    # トライセップス
    "triceps_pushdown",
    "tricep_pushdown",
    "rope_pushdown",
    "rope_triceps_pushdown",
    "straight_bar_pushdown",
    "skull_crusher",
    "ez_bar_skull_crusher",
    "dumbbell_skull_crusher",
    "triceps_extension",
    "tricep_extension",
    "overhead_triceps_extension",
    "dumbbell_overhead_triceps_extension",
    "cable_overhead_triceps_extension",
    "close_grip_bench_press",
    "diamond_push_up",
    "triceps_dips",
    "kickback",
    "triceps_kickback",
    # 前腕
    "wrist_curl",
    "reverse_wrist_curl",
    "wrist_roller",
    "farmer_carry",
    "farmers_carry",
    "farmers_walk",
})

LEG_ISOLATION: FrozenSet[str] = frozenset({
    # マシン系
    "leg_press",
    "single_leg_press",
    "leg_curl",
    "lying_leg_curl",
    "seated_leg_curl",
    "standing_leg_curl",
    "leg_extension",
    "abductor_machine",
    "adductor_machine",
    "hip_abduction",
    "hip_adduction",
    # カーフ
    "calf_raise",
    "standing_calf_raise",
    "seated_calf_raise",
    "donkey_calf_raise",
    "single_leg_calf_raise",
    "leg_press_calf_raise",
    # 徒手・その他
    "sissy_squat",
    "wall_sit",
    "glute_kickback",
    "cable_glute_kickback",
    "donkey_kick",
    "fire_hydrant",
})

CORE_EXERCISES: FrozenSet[str] = frozenset({
    # プランク系
    "plank",
    "side_plank",
    "rkg_plank",
    "plank_up",
    "plank_row",
    "hollow_body_hold",
    # アブホイール・ケーブル
    "ab_wheel",
    "ab_rollout",
    "cable_crunch",
    "rope_crunch",
    "kneeling_cable_crunch",
    # 体幹回旋
    "russian_twist",
    "pallof_press",
    "cable_pallof_press",
    "landmine_rotation",
    "woodchop",
    "cable_woodchop",
    # クランチ・レイズ系
    "crunch",
    "bicycle_crunch",
    "reverse_crunch",
    "hanging_leg_raise",
    "hanging_knee_raise",
    "toes_to_bar",
    "dragon_flag",
    "v_up",
    "sit_up",
    "decline_sit_up",
    # 体幹安定系
    "dead_bug",
    "bird_dog",
    "suitcase_carry",
    "suitcase_walk",
    "Copenhagen_plank",
    "copenhagen_plank",
    # バックエクステンション（コア補助）
    "hyperextension",
    "back_extension",
})

OLYMPIC_LIFTS: FrozenSet[str] = frozenset({
    "clean",
    "power_clean",
    "hang_clean",
    "hang_power_clean",
    "snatch",
    "power_snatch",
    "hang_snatch",
    "clean_and_jerk",
    "clean_and_press",
    "muscle_snatch",
    "overhead_squat",
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
    "olympic": OLYMPIC_LIFTS,
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
