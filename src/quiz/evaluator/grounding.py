"""GPT-4o 기반 Grounding(할루시네이션) + 해설 품질 평가."""

import json
import re

from openai import OpenAI
from config.settings import OPENAI_API_KEY

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ── 프롬프트 ──────────────────────────────────────────────────────────────────

_EVAL_SYSTEM = """당신은 퀴즈 품질 평가 전문가입니다.
주어진 강의 청크만을 근거로 퀴즈 문항의 할루시네이션 여부와 해설 품질을 평가합니다.
반드시 JSON 형식으로만 응답하세요."""

_EVAL_USER = """아래 강의 청크를 근거 자료로 삼아 퀴즈 문항을 평가하세요.

## 강의 청크 (근거 자료)
{source_context}

## 퀴즈 문항
- 유형: {style}
- 문제: {question}
- 정답: {answer_text}
- 해설: {explanation}
{options_section}

## 평가 항목

### 1. Grounding (할루시네이션 감지)
문제와 정답이 강의 청크에 근거하는가?
- PASS: 문제와 정답이 강의 청크 내용에 근거함
- FAIL: 강의 청크에 없는 외부 개념이나 사실을 사용함

### 2. 해설 품질
정답 근거가 강의 청크 내용과 일치하는가? 객관식의 경우 오답 함정이 각 선택지별로 구체적 이유를 설명하는가?
- PASS: 해설이 정확하고 구체적임
- FAIL: 해설이 부정확하거나 지나치게 모호함 (예: "A는 잘못된 설명이다" 수준)

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
        style=style,
        question=question,
        answer_text=answer_text,
        explanation=explanation,
        options_section=options_section,
    )

    try:
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _EVAL_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=512,
        )
        raw = response.choices[0].message.content
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        result = json.loads(match.group(1) if match else raw)

        g = result.get("grounding", {})
        grounding_pass = g.get("pass", False)
        grounding_reason = g.get("reason", "")

        e = result.get("explanation", {})
        explanation_pass = e.get("pass", False)
        explanation_reason = e.get("reason", "")

        errors = []
        if not grounding_pass:
            errors.append(f"Grounding FAIL: {grounding_reason}")
        if not explanation_pass:
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

    item_results = [evaluate_grounding(quiz, retrieval_sources) for quiz in quizzes]
    failed = [r for r in item_results if not r["pass"]]

    return {
        "quiz_set_id": quiz_set_id,
        "pass": len(failed) == 0,
        "item_results": item_results,
    }
