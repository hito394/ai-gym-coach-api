"""
Tests for body measurement logging and growth graph endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app
from tests.conftest import auth_headers


def _make_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SL = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override():
        db = SL()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), SL


@pytest.fixture()
def ctx():
    client, SL = _make_client()
    yield client, SL
    app.dependency_overrides.pop(get_db, None)


def _make_user(SL):
    with SL() as db:
        u = models.User(email=f"bm{id(SL)}@test.com")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


# ---------------------------------------------------------------------------
# POST /v1/users/{user_id}/measurements
# ---------------------------------------------------------------------------

class TestLogMeasurement:
    def test_log_basic(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.post(
            f"/v1/users/{uid}/measurements",
            json={"waist_cm": 82.0, "chest_cm": 100.0},
            headers=auth_headers(uid),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["user_id"] == uid
        assert body["waist_cm"] == 82.0
        assert body["chest_cm"] == 100.0
        assert body["body_fat_pct"] is None

    def test_log_full_measurement(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        payload = {
            "body_fat_pct": 18.5,
            "muscle_mass_kg": 65.0,
            "chest_cm": 102.0,
            "waist_cm": 80.0,
            "hips_cm": 95.0,
            "left_arm_cm": 36.0,
            "right_arm_cm": 36.5,
            "left_thigh_cm": 58.0,
            "right_thigh_cm": 58.5,
            "neck_cm": 38.0,
            "notes": "Morning measurement",
        }
        r = client.post(
            f"/v1/users/{uid}/measurements",
            json=payload,
            headers=auth_headers(uid),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["body_fat_pct"] == 18.5
        assert body["muscle_mass_kg"] == 65.0
        assert body["notes"] == "Morning measurement"

    def test_log_no_auth(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.post(f"/v1/users/{uid}/measurements", json={"waist_cm": 82.0})
        assert r.status_code == 401

    def test_log_wrong_user_auth(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.post(
            f"/v1/users/{uid}/measurements",
            json={"waist_cm": 82.0},
            headers=auth_headers(uid + 999),
        )
        assert r.status_code == 403

    def test_log_user_not_found(self, ctx):
        client, _ = ctx
        r = client.post(
            "/v1/users/99999/measurements",
            json={"waist_cm": 82.0},
            headers=auth_headers(99999),
        )
        assert r.status_code == 404

    def test_log_invalid_body_fat(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.post(
            f"/v1/users/{uid}/measurements",
            json={"body_fat_pct": 150.0},  # too high
            headers=auth_headers(uid),
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/users/{user_id}/measurements
# ---------------------------------------------------------------------------

class TestGetMeasurements:
    def test_empty_list(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(f"/v1/users/{uid}/measurements", headers=auth_headers(uid))
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_logged_measurements(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        client.post(
            f"/v1/users/{uid}/measurements",
            json={"waist_cm": 80.0},
            headers=auth_headers(uid),
        )
        client.post(
            f"/v1/users/{uid}/measurements",
            json={"waist_cm": 79.0},
            headers=auth_headers(uid),
        )
        r = client.get(f"/v1/users/{uid}/measurements", headers=auth_headers(uid))
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_no_auth_returns_401(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(f"/v1/users/{uid}/measurements")
        assert r.status_code == 401

    def test_wrong_user_returns_403(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(f"/v1/users/{uid}/measurements", headers=auth_headers(uid + 99))
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /v1/users/{user_id}/growth
# ---------------------------------------------------------------------------

class TestGrowthGraph:
    def _seed_weight(self, SL, uid, count=5):
        with SL() as db:
            base_dt = datetime(2026, 1, 1)
            for i in range(count):
                db.add(models.BodyWeightLog(
                    user_id=uid,
                    weight_kg=80.0 - i * 0.5,
                    measured_at=base_dt + timedelta(days=i * 7),
                ))
            db.commit()

    def test_weight_graph(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        self._seed_weight(SL, uid)
        r = client.get(
            f"/v1/users/{uid}/growth",
            params={"metric": "weight_kg"},
            headers=auth_headers(uid),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["metric"] == "weight_kg"
        assert body["unit"] == "kg"
        assert len(body["points"]) == 5
        assert body["first_value"] == 80.0
        assert body["latest_value"] == 78.0
        assert body["change"] == -2.0

    def test_body_fat_graph(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        with SL() as db:
            for i in range(3):
                db.add(models.BodyMeasurement(
                    user_id=uid,
                    body_fat_pct=20.0 - i * 1.0,
                    measured_at=datetime(2026, 1, 1) + timedelta(days=i * 30),
                ))
            db.commit()
        r = client.get(
            f"/v1/users/{uid}/growth",
            params={"metric": "body_fat_pct"},
            headers=auth_headers(uid),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["unit"] == "%"
        assert len(body["points"]) == 3
        assert body["change"] == -2.0

    def test_empty_graph_returns_no_points(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(
            f"/v1/users/{uid}/growth",
            params={"metric": "weight_kg"},
            headers=auth_headers(uid),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["points"] == []
        assert body["first_value"] is None
        assert body["change"] is None

    def test_invalid_metric(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(
            f"/v1/users/{uid}/growth",
            params={"metric": "invalid_metric"},
            headers=auth_headers(uid),
        )
        assert r.status_code == 422

    def test_no_auth_returns_401(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(f"/v1/users/{uid}/growth", params={"metric": "weight_kg"})
        assert r.status_code == 401

    def test_change_pct_calculated(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        with SL() as db:
            db.add(models.BodyWeightLog(user_id=uid, weight_kg=100.0, measured_at=datetime(2026, 1, 1)))
            db.add(models.BodyWeightLog(user_id=uid, weight_kg=90.0, measured_at=datetime(2026, 2, 1)))
            db.commit()
        r = client.get(
            f"/v1/users/{uid}/growth",
            params={"metric": "weight_kg"},
            headers=auth_headers(uid),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["change_pct"] == -10.0  # -10kg / 100kg * 100

    def test_default_metric_is_weight(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        r = client.get(f"/v1/users/{uid}/growth", headers=auth_headers(uid))
        assert r.status_code == 200
        assert r.json()["metric"] == "weight_kg"

    def test_all_supported_metrics(self, ctx):
        client, SL = ctx
        uid = _make_user(SL)
        metrics = ["weight_kg", "body_fat_pct", "muscle_mass_kg", "chest_cm", "waist_cm", "hips_cm"]
        for m in metrics:
            r = client.get(
                f"/v1/users/{uid}/growth",
                params={"metric": m},
                headers=auth_headers(uid),
            )
            assert r.status_code == 200, f"Failed for metric: {m}"
