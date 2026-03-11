"""GPT-4o를 사용한 학습 가이드 생성."""
import json
from openai import OpenAI

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import GUIDE_SYSTEM_PROMPT, GUIDE_USER_PROMPT
from src.rag.pipeline import build_context

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def generate_guide(date: str) -> dict:
    """
    특정 날짜의 강의 내용으로 학습 가이드 생성.

    Args:
        date: 'YYYY-MM-DD' 형식

    Returns:
        {
            "key_concepts": [{"term": ..., "description": ...}],
            "summary": str,
            "review_points": [str, ...]
        }
    """
    ctx = build_context(date)
    curriculum = ctx["curriculum"]

    user_prompt = GUIDE_USER_PROMPT.format(
        date=date,
        subject=curriculum.get("subject", ""),
        content=curriculum.get("content", ""),
        learning_goal=curriculum.get("learning_goal", ""),
        lecture_context=ctx["lecture_context"],
    )

    response = _get_client().chat.completions.create(
        model=LLM_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": GUIDE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content)
