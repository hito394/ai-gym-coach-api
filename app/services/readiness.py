from app.schemas.progression import ReadinessInput, ReadinessOutput


def compute_readiness(payload: ReadinessInput) -> ReadinessOutput:
    sleep_score = min(payload.sleep_hours / 8.0, 1.0)
    soreness_score = 1.0 - (payload.soreness - 1) / 9.0
    stress_score = 1.0 - (payload.stress - 1) / 9.0
    motivation_score = (payload.motivation - 1) / 9.0

    readiness = (sleep_score * 0.35) + (soreness_score * 0.25) + (stress_score * 0.2) + (motivation_score * 0.2)
    fatigue = 1.0 - readiness

    note = "Proceed with normal volume."
    if readiness < 0.5:
        note = "Consider a lighter session or extra warm-up."

    return ReadinessOutput(
        readiness_score=round(readiness, 2),
        fatigue_score=round(fatigue, 2),
        note=note,
    )
