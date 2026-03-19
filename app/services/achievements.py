"""
Achievement / milestone detection for form analysis sessions.

Called after each FormAnalysisSession is persisted.  Returns a list of
newly-earned achievement dicts (to be written to form_achievements) and
the updated personal-best record (upserted into form_personal_bests).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db import models


# ---------------------------------------------------------------------------
# Achievement types and display metadata
# ---------------------------------------------------------------------------

ACHIEVEMENT_META: Dict[str, Dict[str, str]] = {
    "first_session":    {"label": "First Rep!", "icon": "🏋️",  "desc": "Completed your first form analysis."},
    "first_80":         {"label": "Score 80+",  "icon": "🌟",  "desc": "Achieved a form score of 80 or above."},
    "first_90":         {"label": "Score 90+",  "icon": "🏆",  "desc": "Achieved a form score of 90 or above."},
    "perfect_form":     {"label": "Perfect!",   "icon": "💎",  "desc": "Scored 100 on a form analysis."},
    "personal_best":    {"label": "New PR!",     "icon": "📈",  "desc": "Set a new personal best form score."},
    "ten_sessions":     {"label": "10 Sessions", "icon": "🔟",  "desc": "Completed 10 form analyses."},
    "fifty_sessions":   {"label": "50 Sessions", "icon": "⭐",  "desc": "Completed 50 form analyses."},
    "consistent_week":  {"label": "Week Streak", "icon": "📅",  "desc": "3+ form sessions in one week."},
    "improving_streak": {"label": "On the Rise", "icon": "📊",  "desc": "Form improving over 3 consecutive sessions."},
    "no_issues":        {"label": "Clean Rep",   "icon": "✅",  "desc": "Completed a form analysis with no issues."},
}


def _already_earned(
    db: Session,
    user_id: int,
    achievement_type: str,
    exercise_key: Optional[str] = None,
) -> bool:
    """Return True if the user already holds this achievement (globally or per-exercise)."""
    q = db.query(models.FormAchievement).filter(
        models.FormAchievement.user_id == user_id,
        models.FormAchievement.achievement_type == achievement_type,
    )
    if exercise_key:
        q = q.filter(models.FormAchievement.exercise_key == exercise_key)
    return q.first() is not None


def process_session(
    db: Session,
    session: models.FormAnalysisSession,
) -> Tuple[List[models.FormAchievement], Optional[models.FormPersonalBest]]:
    """
    Evaluate achievements and personal best for the just-saved *session*.

    Returns:
        - list of newly created FormAchievement objects (already added to db)
        - the FormPersonalBest record (upserted) or None
    """
    user_id     = session.user_id
    exercise_key = session.exercise_key
    score       = session.overall_score

    new_achievements: List[models.FormAchievement] = []

    # -----------------------------------------------------------------------
    # Helper: create and persist a new achievement
    # -----------------------------------------------------------------------
    def _award(atype: str, ex_key: Optional[str] = None, meta: Optional[Dict] = None) -> None:
        ach = models.FormAchievement(
            user_id=user_id,
            achievement_type=atype,
            exercise_key=ex_key,
            score=score,
            meta=meta or {},
        )
        db.add(ach)
        new_achievements.append(ach)

    # -----------------------------------------------------------------------
    # Count total sessions for this user
    # -----------------------------------------------------------------------
    total_sessions = (
        db.query(models.FormAnalysisSession)
        .filter(models.FormAnalysisSession.user_id == user_id)
        .count()
    )

    # -----------------------------------------------------------------------
    # One-time global milestones
    # -----------------------------------------------------------------------
    if total_sessions == 1 and not _already_earned(db, user_id, "first_session"):
        _award("first_session")

    if score >= 80 and not _already_earned(db, user_id, "first_80"):
        _award("first_80")

    if score >= 90 and not _already_earned(db, user_id, "first_90"):
        _award("first_90")

    if score >= 100 and not _already_earned(db, user_id, "perfect_form"):
        _award("perfect_form")

    if total_sessions >= 10 and not _already_earned(db, user_id, "ten_sessions"):
        _award("ten_sessions")

    if total_sessions >= 50 and not _already_earned(db, user_id, "fifty_sessions"):
        _award("fifty_sessions")

    # -----------------------------------------------------------------------
    # No-issues achievement (per exercise, repeatable is fine – only award once globally)
    # -----------------------------------------------------------------------
    issues = session.issues or []
    if not issues and not _already_earned(db, user_id, "no_issues", exercise_key):
        _award("no_issues", ex_key=exercise_key)

    # -----------------------------------------------------------------------
    # Consistent-week: 3+ sessions in the last 7 days
    # -----------------------------------------------------------------------
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_count = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == user_id,
            models.FormAnalysisSession.created_at >= seven_days_ago,
        )
        .count()
    )
    if recent_count >= 3 and not _already_earned(db, user_id, "consistent_week"):
        _award("consistent_week", meta={"sessions_in_7_days": recent_count})

    # -----------------------------------------------------------------------
    # Improving streak: last 3 sessions of THIS exercise are strictly increasing
    # -----------------------------------------------------------------------
    last_3 = (
        db.query(models.FormAnalysisSession)
        .filter(
            models.FormAnalysisSession.user_id == user_id,
            models.FormAnalysisSession.exercise_key == exercise_key,
        )
        .order_by(models.FormAnalysisSession.created_at.desc())
        .limit(3)
        .all()
    )
    if len(last_3) == 3:
        # desc order: [newest, middle, oldest]
        newest, middle, oldest = last_3[0].overall_score, last_3[1].overall_score, last_3[2].overall_score
        if newest > middle > oldest and not _already_earned(db, user_id, "improving_streak", exercise_key):
            _award("improving_streak", ex_key=exercise_key,
                   meta={"scores": [oldest, middle, newest]})

    # -----------------------------------------------------------------------
    # Personal best (per exercise)
    # -----------------------------------------------------------------------
    pb_record = (
        db.query(models.FormPersonalBest)
        .filter(
            models.FormPersonalBest.user_id == user_id,
            models.FormPersonalBest.exercise_key == exercise_key,
        )
        .first()
    )

    pb_updated: Optional[models.FormPersonalBest] = None

    if pb_record is None:
        pb_record = models.FormPersonalBest(
            user_id=user_id,
            exercise_key=exercise_key,
            best_score=score,
            session_id=session.id,
            achieved_at=session.created_at or datetime.utcnow(),
        )
        db.add(pb_record)
        pb_updated = pb_record
    elif score > pb_record.best_score:
        pb_record.best_score = score
        pb_record.session_id = session.id
        pb_record.achieved_at = session.created_at or datetime.utcnow()
        pb_updated = pb_record
        if not _already_earned(db, user_id, "personal_best", exercise_key):
            _award("personal_best", ex_key=exercise_key,
                   meta={"prev_best": pb_record.best_score, "new_best": score})

    db.flush()   # assign IDs without committing – caller commits
    return new_achievements, pb_updated
