from typing import List, Tuple, Optional, Any
import json
import logging
from openai import OpenAI
from app.core.config import get_settings
from app.schemas.chat import ChatMessage
from app.utils.prompts import SYSTEM_PROMPT


settings = get_settings()
logger = logging.getLogger(__name__)


def _last_user_message(messages: List[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content.strip()
    return ""


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _fallback_chat(messages: List[ChatMessage], diagnostics: Optional[dict]) -> str:
    user_msg = _last_user_message(messages)
    tips: List[str] = []

    if diagnostics:
        quality = _safe_float(diagnostics.get("quality"))
        jitter = _safe_float(diagnostics.get("pose_jitter"))
        knee_valgus = _safe_float(diagnostics.get("knee_valgus_norm"))
        depth = _safe_float(diagnostics.get("depth_norm"))

        if quality is not None and quality < 70:
            tips.append("姿勢品質が低めです。横向き・全身・明るい環境で再計測してください。")
        if jitter is not None and jitter > 0.03:
            tips.append("手ぶれが大きいです。スマホを固定すると判定が安定します。")
        if knee_valgus is not None and knee_valgus > 0.12:
            tips.append("膝が内側に入りやすい傾向です。つま先方向へ膝を開く意識を持ってください。")
        if depth is not None and depth < 0.18:
            tips.append("しゃがみの深さが浅めです。可動域を痛みのない範囲で少しずつ増やしましょう。")

        rep_issues = diagnostics.get("rep_issues")
        if isinstance(rep_issues, list) and rep_issues:
            top = ", ".join(str(x) for x in rep_issues[:2])
            tips.append(f"検出された課題: {top}")

    if not tips:
        tips = [
            "次回は同重量でフォーム優先、RPE 7-8を維持してください。",
            "セット間休憩は90-120秒を目安に。",
            "最後の1セットだけ+1 repを狙うと安全に漸進できます。",
        ]

    if user_msg:
        tips.insert(0, f"質問の要点: {user_msg[:80]}")

    return "- " + "\n- ".join(tips)


def _build_client() -> Optional[OpenAI]:
    if not settings.openai_api_key:
        return None
    return OpenAI(api_key=settings.openai_api_key)


def chat(messages: List[ChatMessage], diagnostics: Optional[dict] = None) -> Tuple[str, Optional[dict]]:
    client = _build_client()
    if client is None:
        return _fallback_chat(messages, diagnostics), None

    payload = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Diagnostics: {diagnostics}"}
        if diagnostics
        else {"role": "system", "content": "Diagnostics: none"},
        *[{"role": m.role, "content": m.content} for m in messages],
    ]

    model_candidates = [settings.openai_model, "gpt-4o-mini"]
    # Keep order but avoid duplicate calls when configured model is already gpt-4o-mini.
    model_candidates = list(dict.fromkeys(model_candidates))

    response = None
    for model_name in model_candidates:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=payload,
                temperature=0.2,
                max_tokens=500,
            )
            break
        except Exception as exc:
            logger.warning("OpenAI call failed for model %s: %s", model_name, exc)

    if response is None:
        return _fallback_chat(messages, diagnostics), None

    content = response.choices[0].message.content.strip()
    structured = None
    try:
        json_start = content.find('{')
        json_blob = content[json_start:]
        structured = json.loads(json_blob)
        reply = content[:json_start].strip() or ""
    except Exception:
        reply = content
        structured = None

    return reply, structured
