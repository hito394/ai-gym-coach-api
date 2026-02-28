from app.schemas.progression import ProgressionInput, ProgressionDecision


def adjust_progression(payload: ProgressionInput) -> ProgressionDecision:
    deload = False
    weight_delta = 0.0
    volume_delta_sets = 0

    if payload.plateau_weeks >= 3:
        deload = True
        volume_delta_sets = -2
        message = "Plateau detected. Initiating deload week."
        return ProgressionDecision(
            action="deload",
            weight_delta=weight_delta,
            volume_delta_sets=volume_delta_sets,
            deload=deload,
            message=message,
        )

    if payload.fatigue_score > 0.7:
        volume_delta_sets = -1
        message = "High fatigue. Reduce volume slightly."
        return ProgressionDecision(
            action="reduce_volume",
            weight_delta=weight_delta,
            volume_delta_sets=volume_delta_sets,
            deload=False,
            message=message,
        )

    if payload.readiness_score >= 0.75 and payload.last_week_avg_rpe <= 8.0:
        weight_delta = 2.5
        volume_delta_sets = 1 if payload.last_week_volume < 16 else 0
        message = "Good readiness. Increase load and/or volume."
        return ProgressionDecision(
            action="increase",
            weight_delta=weight_delta,
            volume_delta_sets=volume_delta_sets,
            deload=False,
            message=message,
        )

    message = "Maintain current load and volume."
    return ProgressionDecision(
        action="maintain",
        weight_delta=weight_delta,
        volume_delta_sets=volume_delta_sets,
        deload=False,
        message=message,
    )
