"""GPT-4o를 사용한 학습 가이드 생성."""
import json
from openai import OpenAI

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import GUIDE_SYSTEM_PROMPT, GUIDE_USER_PROMPT
from src.rag.pipeline import build_context_by_date
from src.rag.retriever import retrieve_by_query

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
    ctx = build_context_by_date(date)
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


def generate_guide_by_query(query: str) -> dict:
    """
    쿼리 기반 학습 가이드 생성 (개인화 학습용).

    Args:
        query: 검색 쿼리 (취약 개념 키워드 등)

    Returns:
        {
            "key_concepts": [{"term": ..., "description": ...}],
            "summary": str,
            "review_points": [str, ...]
        }
    """
    docs = retrieve_by_query(query)
    lecture_context = "\n\n".join(
        f"### [Source {i}]\n{d['content']}" for i, d in enumerate(docs, 1)
    )

    user_prompt = GUIDE_USER_PROMPT.format(
        date="",
        subject="",
        content=query,
        learning_goal="",
        lecture_context=lecture_context,
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
