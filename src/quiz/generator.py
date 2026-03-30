"""GPT-4o-mini를 사용한 퀴즈 생성 엔진."""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re
import threading
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, ValidationError, model_validator

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import (
    QUIZ_SYSTEM_PROMPT, QUIZ_USER_PROMPT, QUIZ_MULTI_USER_PROMPT,
    EXPLANATION_SYSTEM_PROMPT, EXPLANATION_USER_PROMPT,
    _DIFFICULTY_CONFIG, _QUIZ_REQUEST_TEMPLATE,
    get_quiz_request_no_expl,
)
from src.rag.pipeline import build_context_by_date, build_context_by_query

logger = logging.getLogger(__name__)

DifficultyLevel = Literal["easy", "medium", "hard"]


def get_quiz_request(difficulty: str = "medium") -> str:
    """난이도에 맞는 문항 요청 블록 반환."""
    cfg = _DIFFICULTY_CONFIG.get(difficulty, _DIFFICULTY_CONFIG["medium"])
    return _QUIZ_REQUEST_TEMPLATE.format(
        difficulty_label=cfg["label"],
        difficulty_instruction=cfg["instruction"],
        distribution=cfg["distribution"],
        type_note=cfg["type_note"],
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
    type: Literal["multiple_choice", "short_answer", "code_completion"]
    style: Literal["definition", "comparison", "code", "prediction", "application"]
    source_indices: list[int] = []  # LLM 반환값 (사용 안 함, 하위 호환 유지)
    chunk_id_valid: bool = False
    question: str
    options: Optional[QuizOptions] = None
    answer: str
    explanation: str = ""
    # code_completion 전용 필드
    code_template: Optional[str] = None    # 빈칸(___)이 포함된 실행 가능한 전체 코드
    blanks: Optional[list[str]] = None     # 정답 목록 (빈칸 순서와 일치)
    expected_output: Optional[str] = None  # 정답 코드 실행 시 기대되는 stdout
    language: Optional[str] = "python"     # 실행 언어: "python" | "sql"

    @model_validator(mode="after")
    def check_mcq(self) -> "QuizItem":
        if self.type == "multiple_choice":
            if self.options is None:
                raise ValueError("multiple_choice requires options A/B/C/D")
            if self.answer not in ("A", "B", "C", "D"):
                raise ValueError(f"answer must be A/B/C/D for MCQ, got '{self.answer}'")
        elif self.type == "code_completion":
            if not self.code_template:
                raise ValueError("code_completion requires code_template")
            if not self.blanks:
                raise ValueError("code_completion requires blanks")
            # expected_output이 없으면 코드 실행으로 자동 생성 (아래 _fill_missing_expected_output)
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

# BM25 기반 소스 청크 매칭
def _match_sources_by_bm25(quiz: dict, retrieval_sources: list[dict], top_k: int = 2) -> list[dict]:
    """
    문제+정답 텍스트와 retrieval_sources를 BM25로 비교해 유사도 높은 청크 top_k개 반환.

    Returns:
        [{"chunk_id": str, "bm25_score": float}, ...] (점수 내림차순)
    """
    from src.quiz.evaluator.distractor import _tokenize, _build_bm25

    question = quiz.get("question", "")
    answer = quiz.get("answer", "")
    quiz_type = quiz.get("type", "")
    options = quiz.get("options", {})

    answer_text = options.get(answer, answer) if quiz_type == "multiple_choice" else answer
    query = f"{question} {answer_text}"

    bm25, chunk_ids, _ = _build_bm25(retrieval_sources)
    query_tokens = _tokenize(query)
    scores = bm25.get_scores(query_tokens)

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [
        {"chunk_id": chunk_ids[i], "bm25_score": round(float(scores[i]), 4)}
        for i in top_indices
        if scores[i] > 0
    ]


def _shuffle_mcq_options(result: dict) -> dict:
    """MCQ 선택지 순서를 랜덤 셔플해 정답 편중을 제거. explanation 내 알파벳 참조도 리매핑."""
    for quiz in result["quizzes"]:
        if quiz.get("type") != "multiple_choice":
            continue
        options = quiz.get("options", {})
        answer = quiz.get("answer", "")
        if not options or answer not in options:
            continue

        keys = list("ABCD")
        old_values = [options[k] for k in keys]

        shuffled_indices = list(range(4))
        random.shuffle(shuffled_indices)

        new_values = [old_values[i] for i in shuffled_indices]
        quiz["options"] = dict(zip(keys, new_values))

        # old_letter → new_letter 매핑 구성
        old_to_new = {keys[old_i]: keys[new_i] for new_i, old_i in enumerate(shuffled_indices)}
        quiz["answer"] = old_to_new[answer]

        # explanation 내 알파벳 참조도 리매핑 (A-, A는, A: 패턴)
        explanation = quiz.get("explanation", "")
        if explanation:
            placeholder = {k: f"__LETTER_{k}__" for k in keys}
            for old, ph in placeholder.items():
                explanation = re.sub(rf'\b{old}(?=[-는:가-힣])', ph, explanation)
            for old, ph in placeholder.items():
                explanation = explanation.replace(ph, old_to_new[old])
            quiz["explanation"] = explanation
    return result


def _apply_bm25_sources(result: dict, retrieval_sources: list[dict]) -> dict:
    """각 문항에 BM25 매칭 결과를 source_chunk_ids / source_chunks_bm25 / chunk_id_valid로 저장."""
    for quiz in result["quizzes"]:
        matched = _match_sources_by_bm25(quiz, retrieval_sources, top_k=2)
        quiz["source_chunks_bm25"] = matched
        quiz["source_chunk_ids"] = [m["chunk_id"] for m in matched]
        quiz["chunk_id_valid"] = len(matched) > 0
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

def generate_explanations(quiz_set_id: str, quizzes: list[dict], lecture_context: str) -> dict:
    """문제+정답을 받아 해설을 별도 LLM 호출로 생성.

    Returns:
        {quiz_id: explanation_str} 형태의 dict
    """
    quiz_items_for_prompt = []
    for q in quizzes:
        item = {
            "quiz_id": q["quiz_id"],
            "type": q["type"],
            "question": q["question"],
            "answer": q["answer"],
        }
        if q.get("options"):
            item["options"] = q["options"]
        if q.get("code_template"):
            item["code_template"] = q["code_template"]
        quiz_items_for_prompt.append(item)

    user_prompt = EXPLANATION_USER_PROMPT.format(
        lecture_context=lecture_context,
        quiz_items_json=json.dumps(quiz_items_for_prompt, ensure_ascii=False, indent=2),
    )
    t = time.perf_counter()
    response = _get_client().chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
        max_tokens=4096,
    )
    logger.debug("[TIMING] 해설 LLM 호출: %.2fs", time.perf_counter() - t)
    raw = response.choices[0].message.content
    json_str = _extract_json(raw)
    data = json.loads(json_str)
    return {item["quiz_id"]: item["explanation"] for item in data["explanations"]}


def _update_quiz_file_with_explanations(file_path: Path, explanations_map: dict) -> None:
    """생성된 해설을 quiz JSON에 병합하고 explanations_status를 'complete'로 업데이트."""
    with open(file_path, "r", encoding="utf-8") as f:
        record = json.load(f)
    for quiz in record["quizzes"]:
        qid = quiz.get("quiz_id", "")
        if qid in explanations_map:
            quiz["explanation"] = explanations_map[qid]
    record["explanations_status"] = "complete"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)


def _spawn_background_pipeline(
    log_path: Path, quizzes: list[dict], lecture_context: str, quiz_set_id: str
) -> None:
    """백그라운드 스레드: 해설 생성 → 파일 업데이트 → 품질 평가."""
    import threading

    def _run():
        try:
            t = time.perf_counter()
            explanations_map = generate_explanations(quiz_set_id, quizzes, lecture_context)
            _update_quiz_file_with_explanations(log_path, explanations_map)
            logger.info("[TIMING] 해설 생성+저장 완료: %.2fs", time.perf_counter() - t)
            from src.quiz.evaluator.runner import run_evaluation_from_file
            run_evaluation_from_file(str(log_path))
        except Exception as e:
            logger.warning("백그라운드 파이프라인 실패: %s", e)
            try:
                _update_quiz_file_with_explanations(log_path, {})
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def _call_and_validate(messages: list[dict], max_retries: int = 2) -> dict:
    """LLM 호출 → JSON 추출 → Pydantic 검증 → dict 반환. 실패 시 1회 재시도."""
    current_messages = messages
    last_raw = ""
    for attempt in range(max_retries):
        t_llm = time.perf_counter()
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=current_messages,
            temperature=0.7,
            max_tokens=16000,
        )
        logger.debug("[TIMING] 퀴즈 LLM 호출 (attempt %d): %.2fs", attempt+1, time.perf_counter()-t_llm)
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
                        "응답이 너무 길어 중간에 잘렸을 수 있습니다. "
                        "올바른 JSON 형식으로 처음부터 다시 출력하세요. "
                        "```json 블록 외에 어떤 텍스트도 포함하지 마세요."
                    ),
                },
            ]
    raise RuntimeError("퀴즈 생성 실패: 최대 재시도 횟수 초과")


def _top_up_quizzes(messages: list[dict], existing: list[dict], min_count: int = 8) -> list[dict]:
    """기존 문항이 min_count 미만이면 추가 문항을 생성해 반환. 이미 충분하면 빈 리스트."""
    needed = min_count - len(existing)
    if needed <= 0:
        return []

    style_counts = Counter(q.get("style", "") for q in existing)
    existing_summary_lines = [
        f"- Q{i+1} [{q.get('type','')} / {q.get('style','')}]: {q.get('question', '')[:80]}"
        for i, q in enumerate(existing)
    ]
    style_dist_str = ", ".join(f"{s}:{c}개" for s, c in style_counts.items())
    retry_user = (
        f"현재까지 {len(existing)}문항이 생성되었습니다. 최소 {min_count}문항이 필요합니다.\n\n"
        f"아래는 이미 생성된 문항입니다 (동일하거나 유사한 문항 생성 금지):\n"
        + "\n".join(existing_summary_lines)
        + f"\n\n현재 유형 분포: {style_dist_str}\n"
        f"이미 많은 유형은 피하고, 부족한 유형(prediction, application, code 등)을 우선 생성하세요.\n\n"
        f"위 문항들과 겹치지 않는 새로운 문항을 {needed}개 추가로 생성하세요. "
        "동일한 JSON 구조로, ```json 블록 안에만 출력하세요:\n"
        '```json\n{"quizzes": [...]}\n```'
    )
    topup_messages = messages[:-1] + [
        {"role": "user", "content": messages[-1]["content"] + "\n\n---\n" + retry_user},
    ]
    additional = _call_and_validate(topup_messages)
    return additional.get("quizzes", [])


def _run_background(log_path: Path, messages: list[dict], retrieval_sources: list[dict]) -> None:
    """저장된 퀴즈 파일에 top-up 적용 후 품질 평가 실행 (백그라운드 스레드용)."""
    try:
        with open(log_path, encoding="utf-8") as f:
            saved = json.load(f)

        existing = saved.get("quizzes", [])
        new_quizzes = _top_up_quizzes(messages, existing)
        if new_quizzes:
            for q in new_quizzes:
                q["quiz_id"] = str(uuid4())
            new_quizzes = _shuffle_mcq_options({"quizzes": new_quizzes})["quizzes"]
            new_quizzes = _apply_bm25_sources({"quizzes": new_quizzes}, retrieval_sources)["quizzes"]
            saved["quizzes"] = existing + new_quizzes
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(saved, f, indent=2, ensure_ascii=False)
            logger.info("[TOP-UP bg] %d→%d문항", len(existing), len(saved["quizzes"]))

        from src.quiz.evaluator.runner import run_evaluation_from_file
        run_evaluation_from_file(str(log_path))
    except Exception as e:
        logger.warning("백그라운드 처리 실패: %s", e)


# ── Context-based API (로딩 화면 단계 분리용) ────────────────────────────────

def generate_quiz_from_context(
    ctx: dict, difficulty: DifficultyLevel = "medium"
) -> dict:
    """build_context_by_date() 결과를 받아 LLM 호출만 수행."""
    if not ctx.get("lecture_context", "").strip():
        raise ValueError(f"{ctx.get('date', '알 수 없는 날짜')}의 강의 데이터를 찾을 수 없습니다.")
    t_total = time.perf_counter()
    curriculum = ctx["curriculum"]
    date = ctx["date"]
    user_prompt = QUIZ_USER_PROMPT.format(
        date=date,
        subject=curriculum.get("subject", ""),
        content=curriculum.get("content", ""),
        learning_goal=curriculum.get("learning_goal", ""),
        lecture_context=ctx["lecture_context"],
        quiz_request=get_quiz_request_no_expl(difficulty),
    )
    messages = [
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = _call_and_validate(messages)

    for quiz in result["quizzes"]:
        quiz["quiz_id"] = str(uuid4())

    t_bm25 = time.perf_counter()
    result = _shuffle_mcq_options(result)
    result = _apply_bm25_sources(result, ctx["retrieval_sources"])
    logger.debug("[TIMING] 퀴즈 BM25 소스 매칭: %.2fs", time.perf_counter()-t_bm25)

    record = {
        "quiz_set_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lecture_date": date,
        "difficulty": difficulty,
        "explanations_status": "pending",
        "retrieval_sources": ctx["retrieval_sources"],
        **result,
    }


    log_path = _save_quiz_log(record)
    logger.info("[TIMING] 퀴즈 생성 전체 (date=%s): %.2fs | %d문항", date, time.perf_counter()-t_total, len(result['quizzes']))

    # top-up(8문항 미만 시 추가) + 품질 평가 백그라운드 실행
    threading.Thread(
        target=_run_background,
        args=(log_path, messages, ctx["retrieval_sources"]),
        daemon=True,
    ).start()
    # 백그라운드: 해설 생성 → 파일 업데이트 → 품질 평가
    _spawn_background_pipeline(log_path, result["quizzes"], ctx["lecture_context"], record["quiz_set_id"])

    return record


def generate_quiz_multi_from_context(
    ctx: dict,
    user_query: Optional[str] = None,
    difficulty: DifficultyLevel = "medium",
) -> dict:
    """build_context_by_query() 결과를 받아 LLM 호출만 수행."""
    if not ctx.get("lecture_context", "").strip():
        raise ValueError("검색 조건에 해당하는 강의 데이터를 찾을 수 없습니다.")
    t_total = time.perf_counter()
    user_query_section = ""
    if user_query and user_query.strip():
        user_query_section = f"## 문제 생성 요청\n{user_query.strip()}\n"
    user_prompt = QUIZ_MULTI_USER_PROMPT.format(
        curriculum_summary=ctx["curriculum_summary"] or "전체 강의",
        user_query_section=user_query_section,
        lecture_context=ctx["lecture_context"],
        quiz_request=get_quiz_request_no_expl(difficulty),
    )
    messages = [
        {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    result = _call_and_validate(messages)

    for quiz in result["quizzes"]:
        quiz["quiz_id"] = str(uuid4())

    t_bm25 = time.perf_counter()
    result = _shuffle_mcq_options(result)
    result = _apply_bm25_sources(result, ctx["retrieval_sources"])
    logger.debug("[TIMING] 퀴즈(multi) BM25 소스 매칭: %.2fs", time.perf_counter()-t_bm25)

    record = {
        "quiz_set_id": str(uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "difficulty": difficulty,
        "explanations_status": "pending",
        "retrieval_sources": ctx["retrieval_sources"],
        **result,
    }


    log_path = _save_quiz_log(record)
    logger.info("[TIMING] 퀴즈(multi) 생성 전체: %.2fs | %d문항", time.perf_counter()-t_total, len(result['quizzes']))

    threading.Thread(
        target=_run_background,
        args=(log_path, messages, ctx["retrieval_sources"]),
        daemon=True,
    ).start()
    # 백그라운드: 해설 생성 → 파일 업데이트 → 품질 평가
    _spawn_background_pipeline(log_path, result["quizzes"], ctx["lecture_context"], record["quiz_set_id"])

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
    user_query: Optional[str] = None,
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
