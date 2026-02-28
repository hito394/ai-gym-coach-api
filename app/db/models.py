from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
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

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    exercise = Column(String, nullable=False)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False)
    rpe = Column(Float, nullable=True)
    performed_at = Column(DateTime, default=datetime.utcnow)
