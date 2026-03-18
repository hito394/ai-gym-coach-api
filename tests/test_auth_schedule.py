"""
Tests for JWT auth endpoints and schedule (today/calendar) endpoints.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db import models
from app.db.base import Base
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def client_db():
    c, sl = _make_client()
    yield c, sl
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Auth: /v1/auth/register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client_db):
        client, _ = client_db
        r = client.post("/v1/auth/register", json={"email": "a@test.com", "password": "password123"})
        assert r.status_code == 201
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert isinstance(body["user_id"], int)

    def test_register_duplicate_email(self, client_db):
        client, _ = client_db
        payload = {"email": "dup@test.com", "password": "password123"}
        client.post("/v1/auth/register", json=payload)
        r = client.post("/v1/auth/register", json=payload)
        assert r.status_code == 409
        assert "already registered" in r.json()["detail"].lower()

    def test_register_short_password(self, client_db):
        client, _ = client_db
        r = client.post("/v1/auth/register", json={"email": "b@test.com", "password": "short"})
        assert r.status_code == 422  # Pydantic validation

    def test_register_invalid_email(self, client_db):
        client, _ = client_db
        r = client.post("/v1/auth/register", json={"email": "not-an-email", "password": "password123"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Auth: /v1/auth/token
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client_db):
        client, _ = client_db
        client.post("/v1/auth/register", json={"email": "login@test.com", "password": "mypassword"})
        r = client.post("/v1/auth/token", json={"email": "login@test.com", "password": "mypassword"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert isinstance(body["user_id"], int)

    def test_login_wrong_password(self, client_db):
        client, _ = client_db
        client.post("/v1/auth/register", json={"email": "wp@test.com", "password": "correctpass"})
        r = client.post("/v1/auth/token", json={"email": "wp@test.com", "password": "wrongpass"})
        assert r.status_code == 401

    def test_login_unknown_email(self, client_db):
        client, _ = client_db
        r = client.post("/v1/auth/token", json={"email": "nobody@test.com", "password": "somepass"})
        assert r.status_code == 401

    def test_login_returns_valid_token(self, client_db):
        """Token from /token can be used on /me."""
        client, _ = client_db
        client.post("/v1/auth/register", json={"email": "chain@test.com", "password": "chainpass1"})
        r = client.post("/v1/auth/token", json={"email": "chain@test.com", "password": "chainpass1"})
        token = r.json()["access_token"]
        me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200


# ---------------------------------------------------------------------------
# Auth: /v1/auth/me
# ---------------------------------------------------------------------------

class TestMe:
    def _register_and_token(self, client, email="me@test.com", pw="mepassword"):
        r = client.post("/v1/auth/register", json={"email": email, "password": pw})
        return r.json()["access_token"]

    def test_me_success(self, client_db):
        client, _ = client_db
        token = self._register_and_token(client)
        r = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_me_no_token(self, client_db):
        client, _ = client_db
        r = client.get("/v1/auth/me")
        assert r.status_code == 401

    def test_me_bad_token(self, client_db):
        client, _ = client_db
        r = client.get("/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert r.status_code == 401

    def test_register_and_me_flow(self, client_db):
        client, _ = client_db
        reg = client.post("/v1/auth/register", json={"email": "flow@test.com", "password": "flowpass1"})
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200


# ---------------------------------------------------------------------------
# Schedule: /v1/schedule/today/{user_id}
# ---------------------------------------------------------------------------

class TestScheduleToday:
    def _make_user(self, db):
        u = models.User(email=f"u{id(self)}@test.com")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def test_today_no_plan(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = self._make_user(db)
            uid = u.id
        r = client.get(f"/v1/schedule/today/{uid}")
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == uid
        assert body["today_day"] is None
        assert body["active_session"] is None
        assert body["next_exercise"] is None
        assert body["completed_exercises"] == []

    def test_today_user_not_found(self, client_db):
        client, _ = client_db
        r = client.get("/v1/schedule/today/99999")
        assert r.status_code == 404

    def test_today_with_plan(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = models.User(email="plan@test.com")
            db.add(u)
            db.commit()
            db.refresh(u)
            plan = models.WorkoutPlan(user_id=u.id, name="Test Plan", split="push_pull_legs")
            db.add(plan)
            db.commit()
            db.refresh(plan)
            day = models.WorkoutDay(
                plan_id=plan.id,
                day_index=0,
                focus="Push",
                exercises=[{"name": "Bench Press", "exercise_key": "bench_press", "sets": 3, "rep_range": "8-10"}],
            )
            db.add(day)
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/today/{uid}")
        assert r.status_code == 200
        body = r.json()
        assert body["today_day"] is not None
        assert body["today_day"]["focus"] == "Push"
        assert len(body["today_day"]["exercises"]) == 1

    def test_today_with_active_session(self, client_db):
        client, SL = client_db
        import uuid
        with SL() as db:
            u = models.User(email="sess@test.com")
            db.add(u)
            db.commit()
            db.refresh(u)
            session = models.WorkoutSession(
                user_id=u.id,
                session_key=str(uuid.uuid4()),
                started_at=datetime.utcnow(),
            )
            db.add(session)
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/today/{uid}")
        assert r.status_code == 200
        body = r.json()
        assert body["active_session"] is not None
        assert "session_key" in body["active_session"]

    def test_today_date_field(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = models.User(email="date@test.com")
            db.add(u)
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/today/{uid}")
        assert r.status_code == 200
        assert r.json()["date"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# Schedule: /v1/schedule/calendar/{user_id}
# ---------------------------------------------------------------------------

class TestScheduleCalendar:
    def _make_user(self, db):
        u = models.User(email=f"cal{id(db)}@test.com")
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def test_calendar_empty(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = self._make_user(db)
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}", params={"month": "2026-03"})
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == uid
        assert body["month"] == "2026-03"
        assert body["days_with_activity"] == 0
        assert body["days"] == []

    def test_calendar_user_not_found(self, client_db):
        client, _ = client_db
        r = client.get("/v1/schedule/calendar/99999", params={"month": "2026-03"})
        assert r.status_code == 404

    def test_calendar_missing_month(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = self._make_user(db)
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}")
        assert r.status_code == 422  # month is required

    def test_calendar_invalid_month_format(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = self._make_user(db)
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}", params={"month": "03-2026"})
        assert r.status_code == 422

    def test_calendar_with_session(self, client_db):
        client, SL = client_db
        import uuid
        target_month = "2026-03"
        with SL() as db:
            u = models.User(email="calsess@test.com")
            db.add(u)
            db.commit()
            db.refresh(u)
            session = models.WorkoutSession(
                user_id=u.id,
                session_key=str(uuid.uuid4()),
                started_at=datetime(2026, 3, 10, 10, 0, 0),
                total_sets=5,
                total_volume=1000.0,
            )
            db.add(session)
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}", params={"month": target_month})
        assert r.status_code == 200
        body = r.json()
        assert body["days_with_activity"] == 1
        day = body["days"][0]
        assert day["date"] == "2026-03-10"
        assert day["session_count"] == 1
        assert day["total_sets"] == 5
        assert day["volume_kg"] == 1000.0

    def test_calendar_multiple_sessions_same_day(self, client_db):
        client, SL = client_db
        import uuid
        with SL() as db:
            u = models.User(email="multi@test.com")
            db.add(u)
            db.commit()
            db.refresh(u)
            for i in range(3):
                db.add(models.WorkoutSession(
                    user_id=u.id,
                    session_key=str(uuid.uuid4()),
                    started_at=datetime(2026, 3, 15, 8 + i, 0, 0),
                    total_sets=4,
                    total_volume=500.0,
                ))
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}", params={"month": "2026-03"})
        assert r.status_code == 200
        day = r.json()["days"][0]
        assert day["session_count"] == 3
        assert day["total_sets"] == 12
        assert round(day["volume_kg"], 2) == 1500.0

    def test_calendar_session_outside_month_not_counted(self, client_db):
        client, SL = client_db
        import uuid
        with SL() as db:
            u = models.User(email="outside@test.com")
            db.add(u)
            db.commit()
            db.refresh(u)
            # Session in February
            db.add(models.WorkoutSession(
                user_id=u.id,
                session_key=str(uuid.uuid4()),
                started_at=datetime(2026, 2, 15, 10, 0, 0),
                total_sets=3,
                total_volume=300.0,
            ))
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}", params={"month": "2026-03"})
        assert r.status_code == 200
        assert r.json()["days_with_activity"] == 0

    def test_calendar_with_form_score(self, client_db):
        client, SL = client_db
        with SL() as db:
            u = models.User(email="formscore@test.com")
            db.add(u)
            db.commit()
            db.refresh(u)
            db.add(models.FormAnalysisSession(
                user_id=u.id,
                exercise_key="squat",
                overall_score=85.0,
                depth_score=80.0,
                torso_angle_score=90.0,
                symmetry_score=85.0,
                tempo_score=82.0,
                bar_path_score=88.0,
                created_at=datetime(2026, 3, 20, 9, 0, 0),
            ))
            db.commit()
            uid = u.id
        r = client.get(f"/v1/schedule/calendar/{uid}", params={"month": "2026-03"})
        assert r.status_code == 200
        day = r.json()["days"][0]
        assert day["form_score"] == 85.0
