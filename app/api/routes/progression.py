from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.schemas.progression import ProgressionInput, ProgressionDecision, ReadinessInput, ReadinessOutput
from app.services.progression import adjust_progression
from app.services.readiness import compute_readiness

router = APIRouter(prefix="/progression", tags=["progression"])


@router.post("/adjust", response_model=ProgressionDecision)
def progression_adjust(payload: ProgressionInput, db: Session = Depends(get_db)):
    return adjust_progression(payload, db)


@router.post("/readiness", response_model=ReadinessOutput)
def readiness(payload: ReadinessInput):
    return compute_readiness(payload)
