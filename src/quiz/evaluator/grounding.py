"""GPT-4o 기반 Grounding(할루시네이션) + 해설 품질 평가."""

import json
import logging
import re
import time

from openai import OpenAI
from config.settings import GEMINI_API_KEY, EVAL_MODEL

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return _client


# ── 프롬프트 ──────────────────────────────────────────────────────────────────

_EVAL_SYSTEM = """당신은 퀴즈 품질 평가 전문가입니다.
주어진 강의 청크만을 근거로 퀴즈 문항의 할루시네이션 여부와 해설 품질을 평가합니다.
반드시 JSON 형식으로만 응답하세요."""

_EVAL_USER = """아래 강의 청크를 근거 자료로 삼아 퀴즈 문항을 평가하세요.

## 강의 청크 (근거 자료)
{source_context}

## 퀴즈 문항
- 문항 타입: {quiz_type}
- 유형: {style}
- 문제: {question}
- 정답: {answer_text}
- 해설: {explanation}
{options_section}

## 평가 항목

### 1. Grounding (할루시네이션 감지)

**코드 관련(type=code_completion 또는 style=code)인 경우**:
- 판단 기준은 단 하나: 문제에서 사용한 함수·키워드·개념이 강의 청크에서 다루는 범위 안에 있는가?
- PASS: 강의 청크에서 다루는 개념·문법·명령어를 활용한 문항 (실행 결과나 세부 동작이 청크에 명시되지 않아도 무조건 PASS)
- FAIL: 강의 청크에서 전혀 등장하지 않은 새로운 API·라이브러리·함수를 사용한 경우만 FAIL

**그 외 타입(multiple_choice, short_answer)인 경우**:
- PASS: 문제와 정답이 강의 청크 내용에 근거함
- FAIL: 강의 청크에 없는 외부 개념이나 사실을 사용함

### 2. 해설 품질
정답 근거가 강의 청크 내용과 일치하는가?

**객관식(multiple_choice)인 경우에만** 오답 함정도 평가한다:
- PASS: ✅ 정답 근거가 강의 청크와 일치하고, 각 오답이 "실제로 무엇인지" / "왜 이 문제에 맞지 않는지"까지 설명함
- FAIL 조건 (하나라도 해당하면 FAIL):
  · "A는 잘못됐다", "C는 관련이 없다", "D는 다른 기능이다" 처럼 틀렸다는 결론만 말하고 실제 개념 설명이 없음
  · 오답이 실제로 무엇을 의미하는지 설명하지 않음
  · 여러 선택지를 묶어서 "A, C, D는 관련이 없다"처럼 처리
  · 정답 근거가 강의 청크 내용과 다르거나 지나치게 추상적

**코드완성(code_completion)인 경우**:
- PASS: 해설 내용이 강의 청크와 충돌하지 않음 (청크에 없는 기술적 세부 설명을 추가해도 PASS)
- FAIL: 해설이 강의 청크의 내용과 직접 모순되거나 반대되는 설명을 함

**주관식(short_answer)인 경우**: 오답 선택지가 없으므로 오답 함정은 평가하지 않는다. ✅ 정답 근거가 강의 청크 내용과 일치하면 PASS.

반드시 아래 JSON 구조로만 응답하세요:
```json
{{
  "grounding": {{
    "pass": true,
    "reason": "판단 이유를 한 문장으로"
  }},
  "explanation": {{
    "pass": true,
    "reason": "판단 이유를 한 문장으로"
  }}
}}
```"""


# ── 문항 단위 평가 ────────────────────────────────────────────────────────────

def evaluate_grounding(quiz: dict, retrieval_sources: list[dict]) -> dict:
    """
    문항 하나에 대해 Grounding + 해설 품질 평가.

    Returns:
        {
            "quiz_id": str,
            "pass": bool,
            "errors": list[str],
            "warnings": list[str],
            "grounding_pass": bool | None,
            "grounding_reason": str | None,
            "explanation_pass": bool | None,
            "explanation_reason": str | None,
        }
    """
    quiz_id = quiz.get("quiz_id", "unknown")
    style = quiz.get("style", "")
    quiz_type = quiz.get("type", "")

    # 소스 청크 조회 (BM25 매칭 결과 우선, fallback으로 source_chunk_ids)
    source_chunks_bm25 = quiz.get("source_chunks_bm25")
    if source_chunks_bm25 is None:
        raw_ids = quiz.get("source_chunk_ids") or []
        if not raw_ids:
            legacy_id = quiz.get("source_chunk_id")
            raw_ids = [legacy_id] if legacy_id else []
        source_chunks_bm25 = [{"chunk_id": sid, "bm25_score": None} for sid in raw_ids]

    source_chunk_ids = [m["chunk_id"] for m in source_chunks_bm25]
    relevant_chunks = [s["content"] for s in retrieval_sources if s["chunk_id"] in source_chunk_ids]
    source_context = "\n\n".join(relevant_chunks)

    if not source_context:
        return {
            "quiz_id": quiz_id,
            "pass": False,
            "errors": ["참조 청크를 찾을 수 없음 → 평가 불가"],
            "warnings": [],
            "grounding_pass": None,
            "grounding_reason": None,
            "explanation_pass": None,
            "explanation_reason": None,
        }

    question = quiz.get("question", "")
    answer = quiz.get("answer", "")
    options = quiz.get("options", {})
    explanation = quiz.get("explanation", "")

    answer_text = options.get(answer, answer) if quiz_type == "multiple_choice" else answer

    options_section = ""
    if quiz_type == "multiple_choice" and options:
        options_lines = "\n".join(f"  {k}: {v}" for k, v in options.items())
        options_section = f"- 선택지:\n{options_lines}"

    user_prompt = _EVAL_USER.format(
        source_context=source_context,
        quiz_type=quiz_type,
        style=style,
        question=question,
        answer_text=answer_text,
        explanation=explanation,
        options_section=options_section,
    )

    try:
        t_llm = time.perf_counter()
        response = _get_client().chat.completions.create(
            model=EVAL_MODEL,
            messages=[
                {"role": "system", "content": _EVAL_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=512,
        )
        logger.debug("[TIMING] grounding LLM 평가 (quiz_id=%s): %.2fs", quiz_id, time.perf_counter()-t_llm)
        raw = response.choices[0].message.content
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        result = json.loads(match.group(1) if match else raw)

        g = result.get("grounding", {})
        grounding_pass = g.get("pass", False)
        grounding_reason = g.get("reason", "")

        # prediction/code 스타일: 오답이 코드 실행 결과·숫자 등이라 해설 품질 평가 제외
        if style in ("prediction", "code"):
            explanation_pass = None
            explanation_reason = f"{style} 스타일 — 해설 품질 평가 제외"
        else:
            e = result.get("explanation", {})
            explanation_pass = e.get("pass", False)
            explanation_reason = e.get("reason", "")

        errors = []
        if not grounding_pass:
            errors.append(f"Grounding FAIL: {grounding_reason}")
        if explanation_pass is False:
            errors.append(f"해설 FAIL: {explanation_reason}")

        return {
            "quiz_id": quiz_id,
            "pass": len(errors) == 0,
            "errors": errors,
            "warnings": [],
            "grounding_pass": grounding_pass,
            "grounding_reason": grounding_reason,
            "explanation_pass": explanation_pass,
            "explanation_reason": explanation_reason,
        }

    except Exception as e:
        return {
            "quiz_id": quiz_id,
            "pass": False,
            "errors": [f"LLM 평가 호출 실패: {e}"],
            "warnings": [],
            "grounding_pass": None,
            "grounding_reason": None,
            "explanation_pass": None,
            "explanation_reason": None,
        }


# ── 세트 단위 평가 ────────────────────────────────────────────────────────────

def evaluate_grounding_set(quiz_set: dict) -> dict:
    """
    퀴즈 세트 전체 Grounding + 해설 품질 평가.

    Returns:
        {
            "quiz_set_id": str,
            "pass": bool,
            "item_results": list[dict],
        }
    """
    quiz_set_id = quiz_set.get("quiz_set_id", "unknown")
    quizzes = quiz_set.get("quizzes", [])
    retrieval_sources = quiz_set.get("retrieval_sources", [])

    t_set = time.perf_counter()
    item_results = []
    for i, quiz in enumerate(quizzes):
        if i > 0:
            time.sleep(4)  # Gemini free tier: 15 RPM 제한 대응
        item_results.append(evaluate_grounding(quiz, retrieval_sources))
    failed = [r for r in item_results if not r["pass"]]
    logger.debug("[TIMING] grounding 세트 전체 (%d문항, 순차): %.2fs", len(quizzes), time.perf_counter()-t_set)

    return {
        "quiz_set_id": quiz_set_id,
        "pass": len(failed) == 0,
        "item_results": item_results,
    }
