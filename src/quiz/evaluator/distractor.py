"""Distractor 품질 평가 - 오답이 강의 내 개념인지 확인 (BM25 기반)."""

import re
from rank_bm25 import BM25Okapi

# ── 상수 ──────────────────────────────────────────────────────────────────────

THRESHOLD_IN_LECTURE = 0.5         # BM25 점수 0.5 이상 → 강의 내 개념 (Kiwipiepy 기반)
THRESHOLD_COVERAGE_RATIO = 0.5     # 오답 단어 중 50% 이상이 전체 청크 어딘가에 등장하면 통과 (짜깁기 방어율)
MIN_PASS_COUNT = 2                 # 오답 3개 중 최소 통과 수


# ── 토크나이저 초기화 ──────────────────────────────────────────────────────────

try:
    from kiwipiepy import Kiwi
    _kiwi = Kiwi()
except ImportError:
    import logging
    logging.warning("kiwipiepy가 설치되지 않았습니다. 결과가 부정확할 수 있습니다.")
    _kiwi = None

# 추출할 품사(POS): 명사, 동사, 형용사, 어근, 영단어, 숫자
TARGET_POS = {
    "NNG", "NNP", "NNB", "NR", "NP",  # 명사류
    "VV", "VA", "VX", "VCP", "VCN",   # 동사/형용사
    "XR",                             # 어근
    "SL",                             # 영단어
    "SN"                              # 숫자
}

def _tokenize(text: str) -> list[str]:
    """
    Kiwipiepy 기반 토크나이저.
    1. 형태소 단위 분석
    2. 의미 있는 품사(명사, 동사, 형용사, 영단어 등)만 추출.
    3. Unigram + 의미형태소 Bigram 조합.
    """
    if _kiwi is None:
        # Fallback (띄어쓰기)
        return re.split(r"[\s\.,;:!?\(\)\[\]{}<>\"'`/\\]+", text.lower())

    text = text.lower()
    tokens = _kiwi.tokenize(text)
    
    valid_tokens = []
    for t in tokens:
        if t.tag in TARGET_POS:
            valid_tokens.append(t.form)

    if not valid_tokens:
        return []

    # 3. N-gram (Unigram + Bigram) 생성
    ngrams = []
    ngrams.extend(valid_tokens)
    for i in range(len(valid_tokens) - 1):
        ngrams.append(f"{valid_tokens[i]}_{valid_tokens[i+1]}")
        
    return ngrams


# ── BM25 인덱스 구성 ──────────────────────────────────────────────────────────

def _build_bm25(retrieval_sources: list[dict]) -> tuple[BM25Okapi, list[str], set[str]]:
    """
    retrieval_sources로 BM25 인덱스 구성 및 전체 단어 집합(Vocabulary) 추출.

    Returns:
        (bm25, chunk_ids, corpus_vocab)
    """
    chunk_ids = []
    corpus = []
    corpus_vocab = set()
    
    for s in retrieval_sources:
        chunk_ids.append(s["chunk_id"])
        tokens = _tokenize(s["content"])
        corpus.append(tokens)
        corpus_vocab.update(tokens)
        
    bm25 = BM25Okapi(corpus)
    return bm25, chunk_ids, corpus_vocab


# ── Step 1: 강의 내 개념인지 확인 ─────────────────────────────────────────────

def _is_in_lecture(
    distractor: str,
    bm25: BM25Okapi,
    chunk_ids: list[str],
    corpus_vocab: set[str],
) -> dict:
    """
    오답이 강의 내 개념인지 확인 (BM25 + 커버리지 비율).

    1. BM25 최대 점수가 THRESHOLD_IN_LECTURE 이상이거나
    2. 단어 커버리지 비율이 THRESHOLD_COVERAGE_RATIO 이상이면 Pass.

    Returns:
        {
            "pass": bool,
            "max_score": float,
            "coverage_ratio": float,
            "matched_chunk_id": str | None,
        }
    """
    query_tokens = _tokenize(distractor)
    
    # Coverage Ratio 계산 (Bigram 대신 단일 단어(Unigram) 기준으로만 계산)
    query_unigrams = [t for t in query_tokens if "_" not in t]
    
    if not query_unigrams:
        coverage_ratio = 0.0
        uncovered_words = []
    else:
        uncovered_words = [t for t in query_unigrams if t not in corpus_vocab]
        overlap_count = len(query_unigrams) - len(uncovered_words)
        coverage_ratio = overlap_count / len(query_unigrams)
        
    # BM25 점수 계산
    scores = bm25.get_scores(query_tokens)
    max_score = float(max(scores)) if len(scores) > 0 else 0.0
    max_idx = int(scores.argmax()) if len(scores) > 0 else -1
    matched_chunk_id = chunk_ids[max_idx] if max_score > THRESHOLD_IN_LECTURE and max_idx >= 0 else None

    is_pass = (max_score > THRESHOLD_IN_LECTURE) or (coverage_ratio >= THRESHOLD_COVERAGE_RATIO)

    return {
        "pass": is_pass,
        "max_score": round(max_score, 4),
        "coverage_ratio": round(coverage_ratio, 4),
        "uncovered_words": uncovered_words,
        "matched_chunk_id": matched_chunk_id,
    }


# ── 문항 단위 Distractor 평가 ─────────────────────────────────────────────────

def evaluate_distractor(
    quiz: dict,
    bm25: BM25Okapi,
    chunk_ids: list[str],
    corpus_vocab: set[str],
) -> dict:
    """
    MCQ 문항 하나의 Distractor 품질 평가.
    MCQ가 아니면 스킵.

    Returns:
        {
            "quiz_id": str,
            "pass": bool,
            "skipped": bool,
            "errors": list[str],
            "distractor_results": dict,
        }
    """
    quiz_id = quiz.get("quiz_id", "unknown")
    quiz_type = quiz.get("type", "")

    # 단답형은 평가 스킵
    if quiz_type != "multiple_choice":
        return {
            "quiz_id": quiz_id,
            "pass": True,
            "skipped": True,
            "errors": [],
            "distractor_results": {},
        }

    errors = []
    options = quiz.get("options", {})
    answer = quiz.get("answer", "")

    # 오답 선택지만 추출
    distractors = {
        key: val
        for key, val in options.items()
        if key != answer and val.strip()
    }

    if not distractors:
        return {
            "quiz_id": quiz_id,
            "pass": False,
            "skipped": False,
            "errors": ["오답 선택지를 찾을 수 없음"],
            "distractor_results": {},
        }

    # Step 1: 각 오답이 강의 내 개념인지 확인
    distractor_results = {}
    pass_count = 0

    for key, text in distractors.items():
        res = _is_in_lecture(text, bm25, chunk_ids, corpus_vocab)
        distractor_results[key] = res
        if res["pass"]:
            pass_count += 1
        else:
            errors.append(f"오답 {key} → 강의 외부 개념 (BM25: {res['max_score']}, 커버리지: {res['coverage_ratio']*100:.0f}%)")

    # 최소 2개 pass 기준
    if pass_count < MIN_PASS_COUNT:
        errors.append(
            f"강의 내 개념 오답이 부족: {pass_count}개 pass "
            f"(기준: 최소 {MIN_PASS_COUNT}개)"
        )

    return {
        "quiz_id": quiz_id,
        "pass": len(errors) == 0,
        "skipped": False,
        "errors": errors,
        "distractor_results": distractor_results,
    }


# ── 세트 단위 Distractor 평가 ─────────────────────────────────────────────────

def evaluate_distractor_set(quiz_set: dict) -> dict:
    """
    퀴즈 세트 전체 Distractor 평가.

    BM25 인덱스를 먼저 한 번 구성 후 재사용.

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

    # BM25 인덱스 구성 및 단어 집합 추출
    bm25, chunk_ids, corpus_vocab = _build_bm25(retrieval_sources)

    item_results = []
    
    # 각 문제별 오답 평가
    for quiz in quizzes:
        item_res = evaluate_distractor(quiz, bm25, chunk_ids, corpus_vocab)
        item_results.append(item_res)

    failed = [r for r in item_results if not r["pass"] and not r["skipped"]]

    return {
        "quiz_set_id": quiz_set_id,
        "pass": len(failed) == 0,
        "item_results": item_results,
    }