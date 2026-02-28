from typing import List
from openai import OpenAI
from app.core.config import get_settings
from app.schemas.chat import ChatMessage
from app.utils.prompts import SYSTEM_PROMPT


settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)


def chat(messages: List[ChatMessage]) -> str:
    payload = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *[{"role": m.role, "content": m.content} for m in messages],
    ]

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=payload,
        temperature=0.2,
        max_tokens=500,
    )

    return response.choices[0].message.content.strip()
