"""GPT-4o를 사용한 퀴즈 생성 엔진."""
import json
import re
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, ValidationError, model_validator

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import (
    QUIZ_SYSTEM_PROMPT, QUIZ_USER_PROMPT, QUIZ_MULTI_USER_PROMPT,
    _DIFFICULTY_CONFIG, _QUIZ_REQUEST_TEMPLATE,
)
from src.rag.pipeline import build_context_by_date, build_context_by_query

DifficultyLevel = Literal["easy", "medium", "hard"]


def get_quiz_request(difficulty: str = "medium") -> str:
    """난이도에 맞는 문항 요청 블록 반환."""
    cfg = _DIFFICULTY_CONFIG.get(difficulty, _DIFFICULTY_CONFIG["medium"])
    return _QUIZ_REQUEST_TEMPLATE.format(
        difficulty_label=cfg["label"],
        difficulty_instruction=cfg["instruction"],
        distribution=cfg["distribution"],
    )

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
    style: Literal["definition", "comparison", "code", "prediction", "application"]
    source_indices: list[int] = []
    chunk_id_valid: bool = False
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

# chunk_id 검증 로직
def _validate_chunk_ids(result: dict, retrieval_sources: list[dict]) -> dict:
    for quiz in result["quizzes"]:
        indices = quiz.get("source_indices", [])
        chunk_ids = []
        for idx in indices:
            if 1 <= idx <= len(retrieval_sources):
                chunk_ids.append(retrieval_sources[idx - 1]["chunk_id"])
        quiz["source_chunk_ids"] = chunk_ids
        quiz["chunk_id_valid"] = len(chunk_ids) > 0
    return result

def _save_quiz_log(record: dict) -> Path:
    """생성된 퀴즈 세트를 JSON 파일로 저장."""
    from config.settings import GENERATED_QUIZ_DIR
    os.makedirs(GENERATED_QUIZ_DIR, exist_ok=True)
    
    quiz_set_id = record["quiz_set_id"]
    file_path = Path(GENERATED_QUIZ_DIR) / f"quiz_{quiz_set_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return file_path

def _call_and_validate(messages: list[dict], max_retries: int = 2) -> dict:
    """LLM 호출 → JSON 추출 → Pydantic 검증 → dict 반환. 실패 시 1회 재시도."""
    current_messages = messages
    last_raw = ""
    for attempt in range(max_retries):
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=current_messages,
            temperature=0.7,
            max_tokens=4096,
        )
        last_raw = response.choices[0].message.content
        try:
            json_str = _extract_json(last_raw)
            data = json.loads(json_str)
            validated = QuizResponse.model_validate(data)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            if attempt == max_retries - 1:
                raise
            # 에러 내용을 포함해 재시도 요청
            current_messages = current_messages + [
                {"role": "assistant", "content": last_raw},
                {
                    "role": "user",
                    "content": (
                        f"JSON 파싱/검증 오류가 발생했습니다: {e}\n"
                        "올바른 JSON 형식으로 처음부터 다시 출력하세요. "
                        "```json 블록 외에 어떤 텍스트도 포함하지 마세요."
                    ),
                },
            ]
    raise RuntimeError("퀴즈 생성 실패: 최대 재시도 횟수 초과")


# ── Context-based API (로딩 화면 단계 분리용) ────────────────────────────────

def generate_quiz_from_context(
    ctx: dict, difficulty: DifficultyLevel = "medium"
) -> dict:
    """build_context_by_date() 결과를 받아 LLM 호출만 수행."""
    if not ctx.get("lecture_context", "").strip():
        raise ValueError(f"{ctx.get('date', '알 수 없는 날짜')}의 강의 데이터를 찾을 수 없습니다.")
    curriculum = ctx["curriculum"]
    date = ctx["date"]
    user_prompt = QUIZ_USER_PROMPT.format(
        date=date,
        subject=curriculum.get("subject", ""),
        content=curriculum.get("content", ""),
        learning_goal=curriculum.get("learning_goal", ""),
        lecture_context=ctx["lecture_context"],
        quiz_request=get_quiz_request(difficulty),
    )
    result = _call_and_validate([
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])

    # 각 문항에 고유 ID 부여
    for quiz in result["quizzes"]:
        quiz["quiz_id"] = str(uuid4())

    result = _validate_chunk_ids(result, ctx["retrieval_sources"])

    record = {
        "quiz_set_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lecture_date": date,
        "difficulty": difficulty,
        "retrieval_sources": ctx["retrieval_sources"],
        **result,
    }
    
    log_path = _save_quiz_log(record)
    
    # 자동 품질 평가 실행 (리포트 생성 포함)
    try:
        from src.quiz.evaluator.runner import run_evaluation_from_file
        run_evaluation_from_file(str(log_path))
    except Exception as e:
        print(f"⚠️ 자동 평가 실패: {e}")
    return record


def generate_quiz_multi_from_context(
    ctx: dict,
    user_query: str | None = None,
    difficulty: DifficultyLevel = "medium",
) -> dict:
    """build_context_by_query() 결과를 받아 LLM 호출만 수행."""
    if not ctx.get("lecture_context", "").strip():
        raise ValueError("검색 조건에 해당하는 강의 데이터를 찾을 수 없습니다.")
    user_query_section = ""
    if user_query and user_query.strip():
        user_query_section = f"## 문제 생성 요청\n{user_query.strip()}\n"
    user_prompt = QUIZ_MULTI_USER_PROMPT.format(
        curriculum_summary=ctx["curriculum_summary"] or "전체 강의",
        user_query_section=user_query_section,
        lecture_context=ctx["lecture_context"],
        quiz_request=get_quiz_request(difficulty),
    )
    result = _call_and_validate([
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])
    
    # 각 문항에 고유 ID 부여
    for quiz in result["quizzes"]:
        quiz["quiz_id"] = str(uuid4())
        
    result = _validate_chunk_ids(result, ctx["retrieval_sources"])

    record = {
        "quiz_set_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "difficulty": difficulty,
        "retrieval_sources": ctx["retrieval_sources"],
        **result,
    }
    
    log_path = _save_quiz_log(record)
    
    # 자동 품질 평가 실행 (리포트 생성 포함)
    try:
        from src.quiz.evaluator.runner import run_evaluation_from_file
        run_evaluation_from_file(str(log_path))
    except Exception as e:
        print(f"⚠️ 자동 평가 실패: {e}")
    return record



# ── Public API ────────────────────────────────────────────────────────────────

def generate_quiz(date: str, difficulty: DifficultyLevel = "medium") -> dict:
    """
    특정 날짜의 강의 내용으로 퀴즈 10문항 생성.

    Args:
        date: 'YYYY-MM-DD' 형식
        difficulty: 난이도 ('easy' | 'medium' | 'hard')

    Returns:
        {"quizzes": [...]} 구조의 dict
    """
    ctx = build_context_by_date(date)
    return generate_quiz_from_context(ctx, difficulty=difficulty)


def generate_quiz_multi(
    dates: list[str],
    user_query: str | None = None,
    difficulty: DifficultyLevel = "medium",
) -> dict:
    """
    다중 날짜 또는 텍스트 쿼리 기반으로 퀴즈 10문항 생성.

    Args:
        dates: 검색 대상 날짜 목록. 빈 리스트면 전체 검색.
        user_query: 사용자 입력 쿼리 (없으면 날짜 기반 학습목표 사용)
        difficulty: 난이도 ('easy' | 'medium' | 'hard')

    Returns:
        {"quizzes": [...]} 구조의 dict
    """
    ctx = build_context_by_query(dates, user_query)
    return generate_quiz_multi_from_context(ctx, user_query=user_query, difficulty=difficulty)
