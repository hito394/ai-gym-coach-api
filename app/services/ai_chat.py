from typing import List, Tuple, Optional
import json
from openai import OpenAI
from app.core.config import get_settings
from app.schemas.chat import ChatMessage
from app.utils.prompts import SYSTEM_PROMPT


settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)


def chat(messages: List[ChatMessage], diagnostics: Optional[dict] = None) -> Tuple[str, Optional[dict]]:
    if not settings.openai_api_key:
        return (
            "AI coach is not configured yet. Please add OPENAI_API_KEY on the server.",
            None,
        )

    payload = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Diagnostics: {diagnostics}"}
        if diagnostics
        else {"role": "system", "content": "Diagnostics: none"},
        *[{"role": m.role, "content": m.content} for m in messages],
    ]

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=payload,
            temperature=0.2,
            max_tokens=500,
        )
    except Exception:
        return (
            "AI coach is temporarily unavailable. Please try again in a moment.",
            None,
        )

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
