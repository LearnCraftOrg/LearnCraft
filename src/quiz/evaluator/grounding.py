"""Vertex AI Check Grounding API를 사용한 Grounding 평가."""

import re
import google.cloud.discoveryengine_v1alpha as discoveryengine
from config.settings import GCP_PROJECT_ID

# ── 상수 ──────────────────────────────────────────────────────────────────────

GROUNDING_CONFIG = f"projects/{GCP_PROJECT_ID}/locations/global/groundingConfigs/default_grounding_config"

# 임계값 (데이터 쌓이면 조정)
THRESHOLD_PASS = 0.5          # PASS 기준 (이상)
THRESHOLD_FAIL = 0.3          # FAIL 기준 (미만)
THRESHOLD_QA_COMPARISON = 0.4 # 비교형 문제 (기존 기준 유지)

# ── 해설 파싱 ─────────────────────────────────────────────────────────────────

def parse_explanation(explanation: str, quiz_type: str) -> dict:
    """
    해설에서 Grounding 검증 대상 텍스트만 추출.

    MCQ:    ✅ 정답 근거만 추출 (❌ 오답 함정 제외)
    단답형: ✅ 정답 근거만 추출

    Returns:
        {
            "grounding_target": str,  # 검증할 텍스트
            "skipped": str,           # 제외된 텍스트 (오답 함정)
        }
    """
    grounding_target = ""
    skipped = ""

    # ✅ 정답 근거 추출 (| 이전까지)
    match_correct = re.search(r"✅ 정답 근거:\s*(.*?)(?:\||$)", explanation, re.DOTALL)
    if match_correct:
        grounding_target += match_correct.group(1).strip()

    if quiz_type == "multiple_choice":
        # ❌ 오답 함정은 제외
        match_wrong = re.search(r"❌ 오답 함정:\s*(.*?)$", explanation, re.DOTALL)
        if match_wrong:
            skipped = match_wrong.group(1).strip()

    elif quiz_type == "short_answer":
        # 핵심 포인트는 검증 대상에서 제외 (사용자 요청)
        pass

    return {
        "grounding_target": grounding_target.strip(),
        "skipped": skipped,
    }


# ── Vertex AI API 호출 ────────────────────────────────────────────────────────

def _check_grounding(answer_candidate: str, fact_text: str) -> dict:
    """
    Vertex AI Check Grounding API 단일 호출.

    Returns:
        {
            "support_score": float,
            "cited_chunks": list,
            "uncited_claims": list,
        }
    """
    client = discoveryengine.GroundedGenerationServiceClient()

    request = discoveryengine.CheckGroundingRequest(
        grounding_config=GROUNDING_CONFIG,
        answer_candidate=answer_candidate,
        facts=[
            discoveryengine.GroundingFact(
                fact_text=fact_text,
            )
        ],
    )

    response = client.check_grounding(request=request)

    # 근거 없는 claim 추출
    uncited_claims = [
        claim.claim_text
        for claim in response.claims
        if not claim.citation_indices
    ]

    return {
        "support_score": response.support_score,
        "cited_chunks": list(response.cited_chunks),
        "uncited_claims": uncited_claims,
    }


# ── 문항 단위 Grounding 평가 ──────────────────────────────────────────────────

def evaluate_grounding(quiz: dict, retrieval_sources: list[dict]) -> dict:
    """
    문항 하나에 대해 Grounding 평가 수행.

    1번 호출: 문제 + 정답
    2번 호출: 해설 (정답 근거 + 핵심 포인트, 오답 함정 제외)

    Returns:
        {
            "quiz_id": str,
            "pass": bool,
            "errors": list[str],
            "warnings": list[str],    # 0.3 ~ 0.5 사이 (사람 검토 필요)
            "qa_score": float,
            "explanation_score": float,
            "qa_uncited_claims": list[str],
            "explanation_uncited_claims": list[str],
        }
    """
    errors = []
    warnings = []
    quiz_id = quiz.get("quiz_id", "unknown")
    quiz_type = quiz.get("type", "")

    # chunk_id_valid 확인 (structural에서 이미 걸러지지만 방어 코드)
    if not quiz.get("chunk_id_valid", False):
        return {
            "quiz_id": quiz_id,
            "pass": False,
            "errors": ["chunk_id_valid = False → Grounding 평가 불가"],
            "warnings": [],
            "qa_score": None,
            "explanation_score": None,
            "qa_uncited_claims": [],
            "explanation_uncited_claims": [],
        }

    # source_chunk_ids 합치기 (v2: 리스트, v1: 단일 문자열 호환)
    source_chunk_ids = quiz.get("source_chunk_ids")
    if source_chunk_ids is None:
        legacy_id = quiz.get("source_chunk_id")
        source_chunk_ids = [legacy_id] if legacy_id else []

    relevant_chunks = [
        s["content"] for s in retrieval_sources if s["chunk_id"] in source_chunk_ids
    ]
    source_context = "\n\n".join(relevant_chunks)

    if not source_context:
        return {
            "quiz_id": quiz_id,
            "pass": False,
            "errors": [f"source_chunk_ids {source_chunk_ids}에 해당하는 청크를 찾을 수 없음"],
            "warnings": [],
            "qa_score": None,
            "explanation_score": None,
            "qa_uncited_claims": [],
            "explanation_uncited_claims": [],
        }
    
    style = quiz.get("style", "")
    is_comparison = style == "comparison"

    # 스타일별 임계값 설정 (비교형은 0.4, 나머지는 0.5)
    current_threshold = THRESHOLD_QA_COMPARISON if style == "comparison" else THRESHOLD_PASS
    
    # code/prediction 유형은 문제+정답 Grounding 스킵
    # 정답이 코드이거나 코드 실행 결과(값)라 자연어 청크와 매칭 불가
    qa_result = {"support_score": None, "uncited_claims": []}
    qa_skipped = style in ("code", "prediction")
    
    # 실패 원인 상세 분류를 위한 헬퍼
    def categorize_fail(score, threshold):
        if score is None: return None
        if score < 0.1: return "mismatch" # 오매핑 의심
        if score < threshold - 0.1: return "hallucination" # 환각 의심
        return "threshold_miss" # 아슬아슬하게 미달

    qa_fail_reason = None
    explanation_fail_reason = None

    if not qa_skipped:
        question = quiz.get("question", "")
        answer = quiz.get("answer", "")
        if quiz_type == "multiple_choice":
            options = quiz.get("options", {})
            answer_text = options.get(answer, answer)
        else:
            answer_text = answer

        # Grounding API는 '주장(claims)'의 사실 여부를 판단함. 
        # 서술형 문장 구조로 전달하는 것이 더 정확함.
        qa_candidate = f"{question}에 대한 정답은 {answer_text}이다."

        try:
            qa_result = _check_grounding(qa_candidate, source_context)
            score = qa_result["support_score"]
            
            if is_comparison:
                # 비교형은 기존처럼 0.4 기준 (FAIL/PASS)
                if score < THRESHOLD_QA_COMPARISON:
                    errors.append(f"문제+정답 Grounding 점수 미달: {score:.2f} (기준: {THRESHOLD_QA_COMPARISON})")
            else:
                # 일반 문항: 3단계 평가
                if score < THRESHOLD_FAIL:
                    errors.append(f"문제+정답 Grounding 점수 미달 (FAIL): {score:.2f} (기준: {THRESHOLD_FAIL})")
                elif score < THRESHOLD_PASS:
                    warnings.append(f"문제+정답 Grounding 모호 (WARN - 사람 검토 필요): {score:.2f} (기준: {THRESHOLD_PASS})")

        except Exception as e:
            return {
                "quiz_id": quiz_id,
                "pass": False,
                "errors": [f"Grounding API 호출 실패 (문제+정답): {e}"],
                "warnings": [],
                "qa_score": None,
                "explanation_score": None,
                "qa_uncited_claims": [],
                "explanation_uncited_claims": [],
            }

    # ── 2번 호출: 해설 (스킵 - 사용자 요청) ──────────────────────────────────────
    explanation_result = {"support_score": None, "uncited_claims": []}

    return {
        "quiz_id": quiz_id,
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "qa_skipped": qa_skipped,
        "qa_score": qa_result["support_score"],
        "explanation_score": explanation_result.get("support_score"),
        "qa_uncited_claims": qa_result["uncited_claims"],
        "explanation_uncited_claims": explanation_result.get("uncited_claims", []),
    }



# ── 세트 단위 Grounding 평가 ──────────────────────────────────────────────────

def evaluate_grounding_set(quiz_set: dict) -> dict:
    """
    퀴즈 세트 전체 Grounding 평가.

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

    item_results = [
        evaluate_grounding(quiz, retrieval_sources)
        for quiz in quizzes
    ]

    failed = [r for r in item_results if not r["pass"]]

    return {
        "quiz_set_id": quiz_set_id,
        "pass": len(failed) == 0,
        "item_results": item_results,
    }