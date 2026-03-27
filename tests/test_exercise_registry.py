"""Tests for the gym exercise registry and form endpoint validation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app
from app.utils.exercise_registry import (
    is_gym_exercise,
    get_exercise_category,
    ALL_GYM_EXERCISES,
)
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Unit tests: exercise_registry helpers
# ---------------------------------------------------------------------------

class TestIsGymExercise:
    @pytest.mark.parametrize("key", [
        # スクワット系
        "squat", "back_squat", "front_squat", "goblet_squat", "hack_squat",
        "bulgarian_split_squat", "pistol_squat", "low_bar_squat",
        "lunge", "walking_lunge", "reverse_lunge", "step_up",
        # ヒンジ系
        "deadlift", "romanian_deadlift", "rdl", "sumo_deadlift",
        "trap_bar_deadlift", "hip_thrust", "glute_bridge", "kettlebell_swing",
        "good_morning", "back_extension", "nordic_curl",
        # ベンチ系
        "bench_press", "incline_bench_press", "dumbbell_bench_press",
        "floor_press", "dips", "push_up", "cable_fly", "pec_deck",
        # OHP系
        "overhead_press", "ohp", "military_press", "arnold_press", "push_press",
        # プル系
        "pull_up", "chin_up", "lat_pulldown", "barbell_row", "face_pull",
        "t_bar_row", "pendlay_row", "inverted_row", "shrug", "band_pull_apart",
        # 肩アイソレーション
        "lateral_raise", "front_raise", "upright_row", "y_raise",
        # アーム
        "biceps_curl", "hammer_curl", "preacher_curl", "ez_bar_curl",
        "triceps_pushdown", "skull_crusher", "triceps_extension", "kickback",
        "farmer_carry", "farmers_walk",
        # 脚アイソレーション
        "leg_press", "leg_curl", "leg_extension", "calf_raise",
        "abductor_machine", "sissy_squat", "glute_kickback",
        # コア
        "plank", "ab_wheel", "pallof_press", "hanging_leg_raise",
        "russian_twist", "toes_to_bar", "dead_bug",
        # オリンピックリフト
        "clean", "power_clean", "snatch", "clean_and_jerk", "overhead_squat",
    ])
    def test_gym_exercises_accepted(self, key):
        assert is_gym_exercise(key), f"'{key}' should be a supported gym exercise"

    @pytest.mark.parametrize("key", [
        # Other sports – must NOT be accepted
        "golf_swing",
        "tennis_serve",
        "swimming",
        "running",
        "soccer_kick",
        "baseball_pitch",
        "yoga_pose",
        "pilates",
        "dance",
        "cycling",
        "rowing_machine",   # not in registry
        "box_jump",
        "burpee",
    ])
    def test_non_gym_exercises_rejected(self, key):
        assert not is_gym_exercise(key), f"'{key}' should NOT be a supported gym exercise"


class TestGetExerciseCategory:
    @pytest.mark.parametrize("key,expected_category", [
        ("squat", "squat"),
        ("back_squat", "squat"),
        ("bulgarian_split_squat", "squat"),
        ("lunge", "squat"),
        ("deadlift", "deadlift"),
        ("rdl", "deadlift"),
        ("hip_thrust", "deadlift"),
        ("kettlebell_swing", "deadlift"),
        ("bench_press", "bench"),
        ("incline_bench_press", "bench"),
        ("cable_fly", "bench"),
        ("overhead_press", "ohp"),
        ("ohp", "ohp"),
        ("arnold_press", "ohp"),
        ("pull_up", "pull"),
        ("lat_pulldown", "pull"),
        ("shrug", "pull"),
        ("band_pull_apart", "pull"),
        ("biceps_curl", "arms"),
        ("skull_crusher", "arms"),
        ("farmer_carry", "arms"),
        ("leg_press", "legs"),
        ("sissy_squat", "legs"),
        ("lateral_raise", "shoulder_isolation"),
        ("y_raise", "shoulder_isolation"),
        ("plank", "core"),
        ("toes_to_bar", "core"),
        ("clean", "olympic"),
        ("snatch", "olympic"),
        ("overhead_squat", "olympic"),
    ])
    def test_category_mapping(self, key, expected_category):
        assert get_exercise_category(key) == expected_category

    def test_unknown_exercise_returns_none(self):
        assert get_exercise_category("golf_swing") is None

    def test_registry_has_sufficient_exercises(self):
        assert len(ALL_GYM_EXERCISES) > 150


# ---------------------------------------------------------------------------
# API validation tests
# ---------------------------------------------------------------------------

def _create_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), testing_session


def _make_user(session_local):
    db = session_local()
    user = models.User(email="registry_test@test.dev", training_days=3)
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()
    return user_id


class TestFormLogAcceptsAnyKey:
    """POST /v1/form/log accepts any non-empty exercise_key string."""

    def test_form_log_accepts_gym_exercise(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        resp = client.post(
            "/v1/form/log",
            json={"user_id": user_id, "exercise_key": "deadlift", "feeling": 8},
            headers=auth_headers(user_id),
        )
        assert resp.status_code == 200
        app.dependency_overrides = {}

    def test_form_log_rejects_empty_key(self):
        client, session_local = _create_client()
        user_id = _make_user(session_local)

        resp = client.post(
            "/v1/form/log",
            json={"user_id": user_id, "exercise_key": "", "feeling": 8},
            headers=auth_headers(user_id),
        )
        assert resp.status_code == 422
        app.dependency_overrides = {}
