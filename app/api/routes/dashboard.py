"""
Dashboard endpoint – visual growth and continuity data for the mobile app.

GET /v1/users/{user_id}/dashboard
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import get_current_user_id
from app.db import models
from app.services.achievements import ACHIEVEMENT_META

router = APIRouter(prefix="/users", tags=["dashboard"])


@router.get("/{user_id}/dashboard", summary="User progress dashboard")
def get_dashboard(
    user_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    """
    Returns a consolidated view of the user's form training progress:
    - streak (consecutive days with at least one form session)
    - total sessions and total exercises analysed
    - personal bests per exercise
    - recent achievements (last 10)
    - weekly form score trend (last 7 days vs previous 7 days)
    - per-exercise score summary (best / latest / avg)
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ------------------------------------------------------------------
    # All form sessions for this user, newest first
    # ------------------------------------------------------------------
    all_sessions = (
        db.query(models.FormAnalysisSession)
        .filter(models.FormAnalysisSession.user_id == user_id)
        .order_by(models.FormAnalysisSession.created_at.desc())
        .all()
    )

    total_sessions = len(all_sessions)

    # ------------------------------------------------------------------
    # Streak – consecutive calendar days (most recent first)
    # ------------------------------------------------------------------
    streak = _compute_streak(all_sessions)

    # ------------------------------------------------------------------
    # Weekly comparison
    # ------------------------------------------------------------------
    now = datetime.utcnow()
    week_ago      = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    this_week_sessions = [s for s in all_sessions if s.created_at >= week_ago]
    prev_week_sessions = [s for s in all_sessions if two_weeks_ago <= s.created_at < week_ago]

    this_week_avg = _avg_score(this_week_sessions)
    prev_week_avg = _avg_score(prev_week_sessions)

    weekly_change = (
        round(this_week_avg - prev_week_avg, 1)
        if this_week_avg is not None and prev_week_avg is not None
        else None
    )

    # ------------------------------------------------------------------
    # Personal bests
    # ------------------------------------------------------------------
    pbs = (
        db.query(models.FormPersonalBest)
        .filter(models.FormPersonalBest.user_id == user_id)
        .order_by(models.FormPersonalBest.best_score.desc())
        .all()
    )
    personal_bests = [
        {
            "exercise_key": pb.exercise_key,
            "best_score":   round(pb.best_score, 1),
            "achieved_at":  pb.achieved_at.isoformat() if pb.achieved_at else None,
        }
        for pb in pbs
    ]

    # ------------------------------------------------------------------
    # Per-exercise summary
    # ------------------------------------------------------------------
    exercise_summary = _build_exercise_summary(all_sessions)

    # ------------------------------------------------------------------
    # Recent achievements
    # ------------------------------------------------------------------
    recent_achievements = (
        db.query(models.FormAchievement)
        .filter(models.FormAchievement.user_id == user_id)
        .order_by(models.FormAchievement.created_at.desc())
        .limit(10)
        .all()
    )
    achievements_out = [
        {
            "type":         a.achievement_type,
            "exercise_key": a.exercise_key,
            "score":        a.score,
            "earned_at":    a.created_at.isoformat() if a.created_at else None,
            **ACHIEVEMENT_META.get(a.achievement_type, {}),
        }
        for a in recent_achievements
    ]

    return {
        "user_id":        user_id,
        "total_sessions": total_sessions,
        "streak_days":    streak,
        "weekly": {
            "this_week_sessions": len(this_week_sessions),
            "this_week_avg_score": this_week_avg,
            "prev_week_avg_score": prev_week_avg,
            "score_change":        weekly_change,
        },
        "personal_bests":   personal_bests,
        "exercise_summary": exercise_summary,
        "achievements":     achievements_out,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_streak(sessions_desc: List[models.FormAnalysisSession]) -> int:
    """Count consecutive calendar days ending today (or yesterday)."""
    if not sessions_desc:
        return 0

    days_with_sessions = sorted(
        {s.created_at.date() for s in sessions_desc},
        reverse=True,
    )

    today = datetime.utcnow().date()
    start_day = days_with_sessions[0]

    # streak must include today or yesterday to be active
    if start_day < today - timedelta(days=1):
        return 0

    streak = 1
    for i in range(1, len(days_with_sessions)):
        if days_with_sessions[i - 1] - days_with_sessions[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


def _avg_score(sessions: List[models.FormAnalysisSession]) -> Optional[float]:
    if not sessions:
        return None
    return round(sum(s.overall_score for s in sessions) / len(sessions), 1)


def _build_exercise_summary(sessions: List[models.FormAnalysisSession]) -> List[Dict[str, Any]]:
    from collections import defaultdict

    groups: Dict[str, List[models.FormAnalysisSession]] = defaultdict(list)
    for s in sessions:
        groups[s.exercise_key].append(s)

    summary = []
    for exercise_key, s_list in groups.items():
        scores = [s.overall_score for s in s_list]
        # s_list is already newest-first (from the parent query ordering)
        summary.append({
            "exercise_key": exercise_key,
            "sessions":     len(s_list),
            "best_score":   round(max(scores), 1),
            "latest_score": round(s_list[0].overall_score, 1),
            "avg_score":    round(sum(scores) / len(scores), 1),
            "first_score":  round(s_list[-1].overall_score, 1),
            "improvement":  round(s_list[0].overall_score - s_list[-1].overall_score, 1),
        })

    # Sort by most sessions first
    summary.sort(key=lambda x: x["sessions"], reverse=True)
    return summary
