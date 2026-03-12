from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.form import FormAnalyzeIn, FormAnalyzeOut
from app.services.form_analysis import analyze_form_diagnostics

router = APIRouter(prefix="/form", tags=["form"])


@router.post("/analyze", response_model=FormAnalyzeOut)
def analyze_form(payload: FormAnalyzeIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = analyze_form_diagnostics(payload.diagnostics)

    record = models.FormAnalysisSession(
        user_id=payload.user_id,
        exercise_key=payload.exercise_key,
        model_name="movenet",
        model_version="mvp-rules-v1",
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        overall_score=result["overall_score"],
        issues=result["issues"],
        diagnostics=payload.diagnostics,
        feedback=result["feedback"],
    )
    db.add(record)
    db.commit()

    return FormAnalyzeOut(
        overall_score=result["overall_score"],
        depth_score=result["depth_score"],
        torso_angle_score=result["torso_angle_score"],
        symmetry_score=result["symmetry_score"],
        tempo_score=result["tempo_score"],
        bar_path_score=result["bar_path_score"],
        issues=result["issues"],
        feedback=result["feedback"],
        diagnostics=payload.diagnostics,
        model_name="movenet",
        model_version="mvp-rules-v1",
    )
