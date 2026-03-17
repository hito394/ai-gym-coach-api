from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    age = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    experience_level = Column(String, nullable=True)
    goal = Column(String, nullable=True)
    training_days = Column(Integer, nullable=True)
    equipment = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    workout_plans = relationship("WorkoutPlan", back_populates="user")


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    split = Column(String, nullable=False)
    week_index = Column(Integer, default=1)
    block_index = Column(Integer, default=1)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="workout_plans")
    days = relationship("WorkoutDay", back_populates="plan")


class WorkoutDay(Base):
    __tablename__ = "workout_days"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("workout_plans.id"))
    day_index = Column(Integer, nullable=False)
    focus = Column(String, nullable=False)
    exercises = Column(JSON, nullable=False)

    plan = relationship("WorkoutPlan", back_populates="days")


class SetLog(Base):
    __tablename__ = "set_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_set_logs_user_client"),
        Index(
            "ix_set_logs_user_exercise_key_performed_at",
            "user_id",
            "exercise_key",
            "performed_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    client_id = Column(String, nullable=True, index=True)
    exercise = Column(String, nullable=False)
    exercise_key = Column(String, nullable=True, index=True)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False)
    rpe = Column(Float, nullable=True)
    performed_at = Column(DateTime, default=datetime.utcnow)


class SetLogMeta(Base):
    __tablename__ = "set_log_meta"

    id = Column(Integer, primary_key=True, index=True)
    set_log_id = Column(Integer, ForeignKey("set_logs.id"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(String, nullable=True, index=True)
    rest_seconds = Column(Integer, nullable=True)
    logged_at = Column(DateTime, default=datetime.utcnow)


class BodyWeightLog(Base):
    __tablename__ = "body_weight_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    weight_kg = Column(Float, nullable=False)
    measured_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    exercise = Column(String, nullable=True)
    exercise_key = Column(String, nullable=True, index=True)
    recommendation = Column(JSON, nullable=False)
    outcome = Column(JSON, nullable=True)
    accuracy = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class FormAnalysisSession(Base):
    __tablename__ = "form_analysis_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exercise_key = Column(String, nullable=False, index=True)
    model_name = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    depth_score = Column(Float, nullable=False, default=0.0)
    torso_angle_score = Column(Float, nullable=False, default=0.0)
    symmetry_score = Column(Float, nullable=False, default=0.0)
    tempo_score = Column(Float, nullable=False, default=0.0)
    bar_path_score = Column(Float, nullable=False, default=0.0)
    overall_score = Column(Float, nullable=False, default=0.0)
    issues = Column(JSON, nullable=True)
    diagnostics = Column(JSON, nullable=True)
    feedback = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FormPersonalBest(Base):
    """Tracks each user's best overall form score per exercise."""
    __tablename__ = "form_personal_bests"
    __table_args__ = (
        UniqueConstraint("user_id", "exercise_key", name="uq_form_pb_user_exercise"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    exercise_key = Column(String, nullable=False, index=True)
    best_score = Column(Float, nullable=False)
    session_id = Column(Integer, ForeignKey("form_analysis_sessions.id"), nullable=True)
    achieved_at = Column(DateTime, default=datetime.utcnow)


class FormAchievement(Base):
    """Milestone events surfaced in the user dashboard."""
    __tablename__ = "form_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    achievement_type = Column(String, nullable=False)   # e.g. "first_90", "personal_best"
    exercise_key = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    meta = Column(JSON, nullable=True)                  # extra context
    created_at = Column(DateTime, default=datetime.utcnow)
