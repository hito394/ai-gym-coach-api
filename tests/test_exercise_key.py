import pytest
from app.utils.exercise_key import normalize_exercise_key


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bench Press", "bench_press"),
        ("  Bench   Press  ", "bench_press"),
        ("Barbell Back Squat", "barbell_back_squat"),
        ("Overhead-Press", "overhead_press"),
        ("Dumbbell RDL", "dumbbell_rdl"),
        ("Lat Pulldown", "lat_pulldown"),
        ("Chest-Supported Row", "chest_supported_row"),
        ("Pull-up", "pull_up"),
        ("Pull/Up", "pull_up"),
        ("Lunge (Walking)", "lunge_walking"),
        ("Farmer’s Carry", "farmers_carry"),
        ("Hip Thrust & Glute Bridge", "hip_thrust_and_glute_bridge"),
        ("Leg Press 45°", "leg_press_45"),
        ("Incline DB Press", "incline_db_press"),
        ("  ___Bench__Press___ ", "bench_press"),
    ],
)
def test_normalize_exercise_key(raw, expected):
    assert normalize_exercise_key(raw) == expected
