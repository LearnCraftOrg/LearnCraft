"""GPT-4o를 사용한 퀴즈 생성 엔진."""
import json
from openai import OpenAI

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import QUIZ_SYSTEM_PROMPT, QUIZ_USER_PROMPT, QUIZ_MULTI_USER_PROMPT
from src.rag.pipeline import build_context_by_date, build_context_by_query

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def generate_quiz(date: str) -> dict:
    """
    특정 날짜의 강의 내용으로 퀴즈 10문항 생성.

    Args:
        date: 'YYYY-MM-DD' 형식

    Returns:
        {"quizzes": [...]} 구조의 dict
        각 quiz: {type, question, options(MCQ만), answer, explanation}
    """
    ctx = build_context_by_date(date)
    curriculum = ctx["curriculum"]

    user_prompt = QUIZ_USER_PROMPT.format(
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
            {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    return json.loads(response.choices[0].message.content)


def generate_quiz_multi(dates: list[str], user_query: str | None = None) -> dict:
    """
    다중 날짜 또는 텍스트 쿼리 기반으로 퀴즈 10문항 생성.

    Args:
        dates: 검색 대상 날짜 목록. 빈 리스트면 전체 검색.
        user_query: 사용자 입력 쿼리 (없으면 날짜 기반 학습목표 사용)

    Returns:
        {"quizzes": [...]} 구조의 dict
    """
    ctx = build_context_by_query(dates, user_query)

    user_query_section = ""
    if user_query and user_query.strip():
        user_query_section = f"## 문제 생성 요청\n{user_query.strip()}\n"

    user_prompt = QUIZ_MULTI_USER_PROMPT.format(
        curriculum_summary=ctx["curriculum_summary"] or "전체 강의",
        user_query_section=user_query_section,
        lecture_context=ctx["lecture_context"],
    )

    response = _get_client().chat.completions.create(
        model=LLM_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    return json.loads(response.choices[0].message.content)
