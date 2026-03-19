"""
Auth endpoints: register, login, me.

POST /v1/auth/register  → create account, return token
POST /v1/auth/token     → login with email+password, return token
GET  /v1/auth/me        → current user profile (requires token)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import (
    create_access_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from app.db import models
from app.schemas.user import UserProfileOut

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", response_model=TokenOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """Create a new account. Returns an access token immediately."""
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = models.User(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenOut(
        access_token=create_access_token(user.id),
        user_id=user.id,
    )


@router.post("/token", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    """Exchange email + password for an access token."""
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return TokenOut(
        access_token=create_access_token(user.id),
        user_id=user.id,
    )


@router.get("/me", response_model=UserProfileOut)
def me(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Return the authenticated user's profile."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfileOut(
        id=user.id,
        age=user.age,
        weight_kg=user.weight_kg,
        height_cm=user.height_cm,
        experience_level=user.experience_level,
        goal=user.goal,
        training_days=user.training_days,
        equipment=user.equipment or [],
    )
