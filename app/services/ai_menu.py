"""
AI-powered workout menu generation using Claude (claude-opus-4-6).

Generates a fully personalised training plan as JSON, then parses it into
the existing WorkoutPlanOut schema so it is compatible with the rest of
the API.  Falls back to the rule-based generator if the API key is absent
or the call fails.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert strength and conditioning coach.
Output ONLY valid JSON — no markdown, no prose, no code fences.
"""

_EQUIPMENT_LABELS = {
    "barbell":    "barbell and squat rack",
    "dumbbell":   "dumbbells",
    "cable":      "cable machine",
    "machine":    "plate-loaded machines",
    "bodyweight": "bodyweight only",
    "kettlebell": "kettlebells",
    "bands":      "resistance bands",
}

_SPLIT_DESC = {
    "ppl":         "Push / Pull / Legs",
    "upper_lower": "Upper / Lower",
    "full_body":   "Full-Body",
}

_EXPERIENCE_LABELS = {
    "beginner":     "beginner (< 1 year)",
    "intermediate": "intermediate (1–3 years)",
    "advanced":     "advanced (3+ years)",
}

_GOAL_LABELS = {
    "muscle_gain": "muscle gain / hypertrophy",
    "strength":    "maximal strength",
    "fat_loss":    "fat loss / body recomposition",
}


def _build_prompt(
    split: str,
    training_days: int,
    experience: str,
    goal: str,
    equipment: List[str],
    week_index: int,
    block_index: int,
    readiness_score: float,
    recent_muscle_groups: Optional[List[str]] = None,
) -> str:
    eq_desc = ", ".join(
        _EQUIPMENT_LABELS.get(e, e) for e in (equipment or ["barbell", "dumbbell"])
    )
    recent_note = ""
    if recent_muscle_groups:
        recent_note = (
            f"\nAvoid high-volume work on {', '.join(set(recent_muscle_groups))} "
            "as they were trained in the last 48 h."
        )

    fatigue_note = ""
    if readiness_score < 0.5:
        fatigue_note = "\nThe athlete is fatigued today — reduce volume by ~15% and keep RPE ≤ 7."

    return f"""\
Generate a {_SPLIT_DESC.get(split, split)} workout plan for an {_EXPERIENCE_LABELS.get(experience, experience)} athlete.
Goal: {_GOAL_LABELS.get(goal, goal)}
Available equipment: {eq_desc}
Training days this week: {training_days}
Week {week_index} of block {block_index} (progress load/volume week-over-week).{recent_note}{fatigue_note}

Return a JSON object with this exact structure — do NOT add extra keys:
{{
  "plan_name": "<string>",
  "split": "{split}",
  "week_index": {week_index},
  "block_index": {block_index},
  "readiness_score": {readiness_score},
  "fatigue_score": {round(1.0 - readiness_score, 2)},
  "volume_landmarks": {{"mev": <int>, "mav": <int>, "mrv": <int>}},
  "days": [
    {{
      "day_index": <int>,
      "focus": "<push|pull|legs|upper|lower|full_body>",
      "exercises": [
        {{
          "name": "<exercise name>",
          "exercise_key": "<snake_case_key>",
          "sets": <int>,
          "rep_range": "<e.g. 3-5 or 8-12>",
          "rpe_target": <float 6.0–9.5>,
          "rest_seconds": <int>,
          "notes": "<short coaching note>"
        }}
      ]
    }}
  ]
}}

Rules:
- Include {training_days} days, each with 4–7 exercises.
- exercise_key must be snake_case (e.g. "barbell_bench_press").
- Use only exercises achievable with the available equipment.
- rep_range format: "low-high" (e.g. "4-6" for strength, "8-12" for hypertrophy).
- rpe_target between 7.0 and 9.0 for most sets; deload if week_index ≥ 5.
- volume_landmarks: mev < mav < mrv (reasonable weekly set counts per muscle group).
"""


def generate_ai_menu(
    split: str,
    training_days: int,
    experience: str,
    goal: str,
    equipment: List[str],
    week_index: int,
    block_index: int,
    readiness_score: float,
    recent_muscle_groups: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Call Claude to produce a personalised workout plan dict.
    Returns None on failure (caller should fall back to rule-based).
    """
    if not api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_prompt(
            split, training_days, experience, goal, equipment,
            week_index, block_index, readiness_score, recent_muscle_groups,
        )
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = next(
            (b.text for b in response.content if b.type == "text"),
            None,
        )
        if not raw:
            return None
        return json.loads(raw)
    except Exception as exc:
        log.warning("AI menu generation failed: %s", exc)
        return None
