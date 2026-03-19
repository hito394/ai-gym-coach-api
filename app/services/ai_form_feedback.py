"""
AI-powered form feedback using Claude (claude-opus-4-6).

Generates personalised, contextual coaching cues that go beyond the
rule-based system by taking into account:
  - The user's experience level and training goal
  - All component scores (depth, torso, symmetry, tempo, bar path)
  - The specific issues detected and their relative severity
  - Historical trend data (improving / stable / declining)

The function is designed to be called *after* the rule-based analyser
has already run.  Claude's output replaces (or enriches) the static
feedback string when an Anthropic API key is configured.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Severity classification for detected issues
_ISSUE_SEVERITY: Dict[str, str] = {
    # High – direct injury risk
    "rounded_back": "high",
    "excessive_elbow_flare": "high",
    "excessive_layback": "high",
    "incomplete_lockout": "high",
    # Medium – form breakdown / performance limiter
    "shallow_depth": "medium",
    "forward_lean": "medium",
    "asymmetry_instability": "medium",
    "uneven_press": "medium",
    "pull_asymmetry": "medium",
    "bar_path_inconsistent": "medium",
    # Low – sub-optimal but not dangerous
    "tempo_inconsistent": "low",
    "low_capture_quality": "low",
}

_EXPERIENCE_LABELS = {
    "beginner": "beginner (< 1 year of consistent training)",
    "intermediate": "intermediate (1–3 years)",
    "advanced": "advanced (3+ years)",
}

_GOAL_LABELS = {
    "muscle_gain": "muscle gain / hypertrophy",
    "strength": "maximal strength",
    "fat_loss": "fat loss / conditioning",
}


def _build_prompt(
    exercise_key: str,
    scores: Dict[str, float],
    issues: List[str],
    experience_level: Optional[str],
    goal: Optional[str],
    trend: Optional[str],
) -> str:
    exp_label = _EXPERIENCE_LABELS.get(experience_level or "", experience_level or "unknown")
    goal_label = _GOAL_LABELS.get(goal or "", goal or "general fitness")

    issues_text = "None detected — form looks solid."
    if issues:
        issue_lines = []
        for issue in issues:
            severity = _ISSUE_SEVERITY.get(issue, "medium")
            issue_lines.append(f"  - {issue} [{severity} severity]")
        issues_text = "\n".join(issue_lines)

    trend_text = ""
    if trend and trend != "stable":
        trend_text = f"\nRecent trend: {trend} (based on last few sessions)\n"

    return f"""You are an expert strength and conditioning coach reviewing a gym exercise form analysis.

Exercise: {exercise_key.replace("_", " ").title()}
Athlete profile: {exp_label}, goal = {goal_label}

Component scores (0–100):
  Overall:          {scores.get("overall_score", 0):.1f}
  Depth:            {scores.get("depth_score", 0):.1f}
  Torso alignment:  {scores.get("torso_angle_score", 0):.1f}
  Symmetry:         {scores.get("symmetry_score", 0):.1f}
  Tempo:            {scores.get("tempo_score", 0):.1f}
  Bar path:         {scores.get("bar_path_score", 0):.1f}
{trend_text}
Issues detected:
{issues_text}

Write personalised coaching feedback for this athlete. Requirements:
1. Start with the most critical issue (if any) and explain WHY it matters for their specific goal.
2. Give 1–2 concrete, actionable cues they can apply on the next set.
3. If scores are high (≥ 80 overall) and no issues, acknowledge and suggest a progression challenge.
4. Calibrate language complexity to experience level (simpler for beginners, technical for advanced).
5. Keep the total response to 3–5 sentences. Do NOT use bullet points or headers — write in flowing prose.
6. Do NOT repeat the numbers or issue names verbatim; translate them into plain English.
"""


def generate_ai_feedback(
    exercise_key: str,
    scores: Dict[str, float],
    issues: List[str],
    experience_level: Optional[str] = None,
    goal: Optional[str] = None,
    trend: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Call Claude to generate personalised form feedback.

    Returns the feedback string, or None if the API key is not set /
    the call fails (caller should fall back to rule-based feedback).
    """
    if not api_key:
        return None

    try:
        import anthropic  # imported lazily to avoid hard dependency at startup

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_prompt(exercise_key, scores, issues, experience_level, goal, trend)

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the text block (skip any thinking blocks)
        for block in response.content:
            if block.type == "text":
                return block.text.strip()

        return None

    except Exception as exc:
        log.warning("AI form feedback failed: %s", exc)
        return None
