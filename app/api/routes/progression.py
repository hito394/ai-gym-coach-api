from fastapi import APIRouter
from app.schemas.progression import ProgressionInput, ProgressionDecision, ReadinessInput, ReadinessOutput
from app.services.progression import adjust_progression
from app.services.readiness import compute_readiness

router = APIRouter(prefix="/progression", tags=["progression"])


@router.post("/adjust", response_model=ProgressionDecision)
def progression_adjust(payload: ProgressionInput):
    return adjust_progression(payload)


@router.post("/readiness", response_model=ReadinessOutput)
def readiness(payload: ReadinessInput):
    return compute_readiness(payload)
