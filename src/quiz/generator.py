"""GPT-4o를 사용한 퀴즈 생성 엔진."""
import json
import re
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, model_validator

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import QUIZ_SYSTEM_PROMPT, QUIZ_USER_PROMPT, QUIZ_MULTI_USER_PROMPT
from src.rag.pipeline import build_context_by_date, build_context_by_query

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ── Pydantic schema ───────────────────────────────────────────────────────────

class QuizOptions(BaseModel):
    A: str
    B: str
    C: str
    D: str


class QuizItem(BaseModel):
    type: Literal["multiple_choice", "short_answer"]
    question: str
    options: QuizOptions | None = None
    answer: str
    explanation: str

    @model_validator(mode="after")
    def check_mcq(self) -> "QuizItem":
        if self.type == "multiple_choice":
            if self.options is None:
                raise ValueError("multiple_choice requires options A/B/C/D")
            if self.answer not in ("A", "B", "C", "D"):
                raise ValueError(f"answer must be A/B/C/D for MCQ, got '{self.answer}'")
        return self


class QuizResponse(BaseModel):
    quizzes: list[QuizItem]


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """<thinking> 블록 제거 후 ```json 코드 블록 추출."""
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()

    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    # fallback: 중괄호로 감싸진 JSON 객체 탐색
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)

    raise ValueError("LLM 응답에서 JSON 블록을 찾을 수 없습니다.")


def _call_and_validate(messages: list[dict]) -> dict:
    """LLM 호출 → JSON 추출 → Pydantic 검증 → dict 반환."""
    response = _get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.7,
    )
    raw_text = response.choices[0].message.content
    json_str = _extract_json(raw_text)
    data = json.loads(json_str)
    validated = QuizResponse.model_validate(data)
    return validated.model_dump()


# ── Context-based API (로딩 화면 단계 분리용) ────────────────────────────────

def generate_quiz_from_context(ctx: dict) -> dict:
    """build_context_by_date() 결과를 받아 LLM 호출만 수행."""
    curriculum = ctx["curriculum"]
    date = ctx["date"]
    user_prompt = QUIZ_USER_PROMPT.format(
        date=date,
        subject=curriculum.get("subject", ""),
        content=curriculum.get("content", ""),
        learning_goal=curriculum.get("learning_goal", ""),
        lecture_context=ctx["lecture_context"],
    )
    return _call_and_validate([
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])


def generate_quiz_multi_from_context(ctx: dict, user_query: str | None = None) -> dict:
    """build_context_by_query() 결과를 받아 LLM 호출만 수행."""
    user_query_section = ""
    if user_query and user_query.strip():
        user_query_section = f"## 문제 생성 요청\n{user_query.strip()}\n"
    user_prompt = QUIZ_MULTI_USER_PROMPT.format(
        curriculum_summary=ctx["curriculum_summary"] or "전체 강의",
        user_query_section=user_query_section,
        lecture_context=ctx["lecture_context"],
    )
    return _call_and_validate([
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])


# ── Public API ────────────────────────────────────────────────────────────────

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

    return _call_and_validate([
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])


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

    return _call_and_validate([
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])
