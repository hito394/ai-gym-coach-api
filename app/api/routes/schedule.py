"""
Today's workout and calendar endpoints.

GET /v1/schedule/today/{user_id}
    Returns the most recent plan's "today" day, the active session (if any),
    and the next exercise to log (based on what's already been logged).

GET /v1/schedule/calendar/{user_id}?month=2026-03
    Returns per-day session summaries for the given month — ready for
    a mobile calendar / heatmap widget.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.utils.exercise_key import normalize_exercise_key

router = APIRouter(prefix="/schedule", tags=["schedule"])


# ---------------------------------------------------------------------------
# Today's workout
# ---------------------------------------------------------------------------

@router.get("/today/{user_id}", summary="Today's workout plan")
def today(user_id: int, db: Session = Depends(get_db)):
    """
    Returns:
      - today_day: the WorkoutDay that matches today's position in the plan
        (cycles through days; None if no plan exists)
      - active_session: the current unfinished session (None if not started)
      - next_exercise: next exercise to log this session (based on plan order
        vs. already-logged exercises)
      - completed_exercises: exercises already logged in the active session
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Most recent workout plan
    plan = (
        db.query(models.WorkoutPlan)
        .filter(models.WorkoutPlan.user_id == user_id)
        .order_by(models.WorkoutPlan.created_at.desc())
        .first()
    )

    today_day: Optional[Dict[str, Any]] = None
    if plan:
        days = (
            db.query(models.WorkoutDay)
            .filter(models.WorkoutDay.plan_id == plan.id)
            .order_by(models.WorkoutDay.day_index)
            .all()
        )
        if days:
            # Cycle through plan days based on calendar day
            day_offset = (date.today() - plan.created_at.date()).days % len(days)
            wd = days[day_offset]
            today_day = {
                "plan_id": plan.id,
                "plan_name": plan.name,
                "day_index": wd.day_index,
                "focus": wd.focus,
                "exercises": wd.exercises or [],
            }

    # Active (unfinished) session
    session = (
        db.query(models.WorkoutSession)
        .filter(
            models.WorkoutSession.user_id == user_id,
            models.WorkoutSession.finished_at.is_(None),
        )
        .order_by(models.WorkoutSession.started_at.desc())
        .first()
    )

    active_session = None
    completed_exercises: List[str] = []
    next_exercise: Optional[Dict] = None

    if session:
        # Which exercises have already been logged in this session?
        logged = (
            db.query(models.SetLog.exercise_key)
            .join(models.SetLogMeta, models.SetLogMeta.set_log_id == models.SetLog.id)
            .filter(models.SetLogMeta.session_id == session.session_key)
            .distinct()
            .all()
        )
        completed_exercises = [r[0] for r in logged if r[0]]

        active_session = {
            "id": session.id,
            "session_key": session.session_key,
            "started_at": session.started_at.isoformat(),
            "total_sets": session.total_sets,
            "total_volume": round(session.total_volume or 0.0, 2),
        }

        # Find next exercise from today's plan not yet started
        if today_day:
            plan_exercises = today_day["exercises"]
            done_set = set(completed_exercises)
            for ex in plan_exercises:
                key = ex.get("exercise_key") or normalize_exercise_key(ex.get("name", ""))
                if key not in done_set:
                    next_exercise = {
                        "name": ex.get("name"),
                        "exercise_key": key,
                        "sets": ex.get("sets"),
                        "rep_range": ex.get("rep_range"),
                        "rpe_target": ex.get("rpe_target"),
                        "rest_seconds": ex.get("rest_seconds"),
                        "notes": ex.get("notes"),
                    }
                    break

    return {
        "user_id": user_id,
        "date": date.today().isoformat(),
        "today_day": today_day,
        "active_session": active_session,
        "completed_exercises": completed_exercises,
        "next_exercise": next_exercise,
    }


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

@router.get("/calendar/{user_id}", summary="Monthly workout calendar")
def calendar(
    user_id: int,
    month: str = Query(
        default=...,
        description="YYYY-MM format, e.g. 2026-03",
        pattern=r"^\d{4}-\d{2}$",
    ),
    db: Session = Depends(get_db),
):
    """
    Returns a per-day summary for every day in *month* that had at least one
    workout session.  Empty days are omitted.

    Response is designed for a calendar heatmap:
      - volume_kg: total weight × reps
      - session_count: number of separate sessions
      - exercises: distinct exercise keys logged
      - form_score: average overall form score (if any form analysis done)
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        year, mon = int(month[:4]), int(month[5:])
        month_start = date(year, mon, 1)
        _, last_day = monthrange(year, mon)
        month_end = date(year, mon, last_day)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid month format")

    start_dt = datetime(month_start.year, month_start.month, month_start.day)
    end_dt   = datetime(month_end.year, month_end.month, month_end.day, 23, 59, 59)

    # ----- Workout sessions -----
    sessions = (
        db.query(models.WorkoutSession)
        .filter(
            models.WorkoutSession.user_id == user_id,
            models.WorkoutSession.started_at >= start_dt,
            models.WorkoutSession.started_at <= end_dt,
        )
        .all()
    )

    day_data: Dict[str, Dict] = {}

    for s in sessions:
        d = s.started_at.date().isoformat()
        if d not in day_data:
            day_data[d] = {
                "date": d,
                "session_count": 0,
                "total_sets": 0,
                "volume_kg": 0.0,
                "exercises": set(),
                "form_score": None,
                "_form_scores": [],
            }
        day_data[d]["session_count"] += 1
        day_data[d]["total_sets"]   += s.total_sets or 0
        day_data[d]["volume_kg"]    += s.total_volume or 0.0

        # Exercises from this session
        logged = (
            db.query(models.SetLog.exercise_key)
            .join(models.SetLogMeta, models.SetLogMeta.set_log_id == models.SetLog.id)
            .filter(models.SetLogMeta.session_id == s.session_key)
            .distinct()
            .all()
        )
        for (key,) in logged:
            if key:
                day_data[d]["exercises"].add(key)

    # ----- Form analysis sessions -----
    form_sessions = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == user_id,
            models.FormAnalysisSession.created_at >= start_dt,
            models.FormAnalysisSession.created_at <= end_dt,
        )
        .all()
    )
    for fs in form_sessions:
        d = fs.created_at.date().isoformat()
        if d not in day_data:
            day_data[d] = {
                "date": d,
                "session_count": 0,
                "total_sets": 0,
                "volume_kg": 0.0,
                "exercises": set(),
                "form_score": None,
                "_form_scores": [],
            }
        day_data[d]["_form_scores"].append(fs.overall_score)

    # Finalise
    result = []
    for d, info in sorted(day_data.items()):
        scores = info.pop("_form_scores")
        info["exercises"] = sorted(info["exercises"])
        info["volume_kg"] = round(info["volume_kg"], 2)
        info["form_score"] = round(sum(scores) / len(scores), 1) if scores else None
        result.append(info)

    return {
        "user_id": user_id,
        "month": month,
        "days_with_activity": len(result),
        "days": result,
    }
