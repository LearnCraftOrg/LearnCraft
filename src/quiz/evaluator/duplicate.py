"""의미적 중복 평가 - 세트 내 유사한 문항 탐지 (임베딩 기반)."""

import numpy as np
from itertools import combinations
from openai import OpenAI
from config.settings import OPENAI_API_KEY, EMBEDDING_MODEL

# ── 상수 ──────────────────────────────────────────────────────────────────────

THRESHOLD_DUPLICATE_FAIL = 0.85  # 확실한 중복 (FAIL)
THRESHOLD_DUPLICATE_WARN = 0.75  # 유사함 (WARN - 사람 확인 필요)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ── 임베딩 ────────────────────────────────────────────────────────────────────

def _embed_batch(texts: list[str]) -> list[list[float]]:
    """여러 텍스트 임베딩 한 번에 반환."""
    response = _get_client().embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """코사인 유사도 계산."""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ── 세트 단위 의미적 중복 평가 ────────────────────────────────────────────────

def evaluate_duplicate_set(quiz_set: dict) -> dict:
    """
    퀴즈 세트 전체 의미적 중복 평가.

    문항 question 텍스트를 한 번에 임베딩 후
    모든 문항 쌍의 코사인 유사도 계산.

    0.75 이상 → 중복으로 간주 (FAIL)

    Returns:
        {
            "quiz_set_id": str,
            "pass": bool,
            "warnings": [],
            "errors": list[dict],     # 0.75 이상
            "pair_results": list[dict],
        }
    """
    quiz_set_id = quiz_set.get("quiz_set_id", "unknown")
    quizzes = quiz_set.get("quizzes", [])

    if len(quizzes) < 2:
        return {
            "quiz_set_id": quiz_set_id,
            "pass": True,
            "warnings": [],
            "errors": [],
            "pair_results": [],
        }

    # 문항 question과 answer 텍스트를 결합하여 임베딩
    quiz_ids = [q.get("quiz_id", f"unknown_{i}") for i, q in enumerate(quizzes)]
    questions = [q.get("question", "") for q in quizzes]
    
    # 임베딩용 텍스트 (질문 + 정답) 생성
    embed_texts = []
    for q in quizzes:
        question_text = q.get("question") or ""
        answer_text = q.get("answer") or ""
        
        # 정답(answer)이 선택지(options)의 키(A, B, C...)인 경우 선택지 내용으로 치환
        options = q.get("options") or {}
        if answer_text in options:
            answer_text = options[answer_text]
            
        embed_texts.append(f"Question: {question_text}\nAnswer: {answer_text}")
        
        embeddings = _embed_batch(embed_texts)

    # 모든 문항 쌍 유사도 계산
    errors = []
    warnings = []
    pair_results = []

    for i, j in combinations(range(len(quizzes)), 2):
        similarity = _cosine_similarity(embeddings[i], embeddings[j])
        similarity = round(similarity, 4)

        pair = {
            "quiz_id_a": quiz_ids[i],
            "quiz_id_b": quiz_ids[j],
            "question_a": questions[i],
            "question_b": questions[j],
            "similarity": similarity,
        }
        pair_results.append(pair)

        if similarity >= THRESHOLD_DUPLICATE_FAIL:
            errors.append(pair)
        elif similarity >= THRESHOLD_DUPLICATE_WARN:
            warnings.append(pair)

    # 임베딩 텍스트 매핑 저장
    embed_map = {quiz_ids[i]: embed_texts[i] for i in range(len(quizzes))}

    return {
        "quiz_set_id": quiz_set_id,
        "pass": len(errors) == 0,
        "warnings": warnings,
        "errors": errors,
        "pair_results": pair_results,
        "embed_map": embed_map,
    }