"""구조적 유효성 평가 - 퀴즈 세트 및 문항 단위 검증."""

import math
import re
from typing import Any

# ── 상수 ──────────────────────────────────────────────────────────────────────

VALID_TYPES = {"multiple_choice", "short_answer", "code_completion"}
VALID_STYLES = {"definition", "comparison", "code", "prediction", "application"}
VALID_ANSWER_OPTIONS = {"A", "B", "C", "D"}

STYLE_DISTRIBUTION = {
    "easy":   {"definition": 4, "comparison": 2, "code": 2, "prediction": 1, "application": 1},
    "medium": {"definition": 2, "comparison": 2, "code": 3, "prediction": 2, "application": 1},
    "hard":   {"definition": 1, "comparison": 1, "code": 3, "prediction": 2, "application": 3},
}

# 난이도별 문항 수 기대값 (기준: 10문항)
TYPE_COUNTS = {
    "easy":   {"multiple_choice": 7, "short_answer": 3, "code_completion": 0},
    "medium": {"multiple_choice": 7, "short_answer": 2, "code_completion": 1},
    "hard":   {"multiple_choice": 7, "short_answer": 2, "code_completion": 1},
}

# 허용 문항 수 범위
MIN_QUESTIONS = 8
MAX_QUESTIONS = 11


# ── 문항 단위 검증 ─────────────────────────────────────────────────────────────

def validate_quiz_item(quiz: dict) -> dict:
    """
    문항 하나를 검증.

    Returns:
        {
            "quiz_id": str,
            "pass": bool,
            "errors": list[str],      # critical: 자동 FAIL
            "warnings": list[str],    # 기록용
        }
    """
    errors = []
    warnings = []
    quiz_id = quiz.get("quiz_id", "unknown")

    # ── 공통 필수 필드 ────────────────────────────────────────────────────────

    # question
    question = quiz.get("question", "")
    if not question:
        errors.append("question 필드가 없음")
    elif len(question) < 10:
        warnings.append(f"question이 10자 미만 ({len(question)}자)")

    # answer
    answer = quiz.get("answer", "")
    if not answer:
        errors.append("answer 필드가 없거나 비어있음")

    # type
    quiz_type = quiz.get("type", "")
    if quiz_type not in VALID_TYPES:
        errors.append(f"type이 유효하지 않음: '{quiz_type}'")

    # style
    style = quiz.get("style", "")
    if style not in VALID_STYLES:
        errors.append(f"style이 유효하지 않음: '{style}'")

    # source_chunk_ids + chunk_id_valid (v1/v2 호환)
    source_chunk_ids = quiz.get("source_chunk_ids")
    source_chunk_id = quiz.get("source_chunk_id")
    chunk_id_valid = quiz.get("chunk_id_valid", False)
    
    if not source_chunk_ids and not source_chunk_id:
        errors.append("source_chunk_ids 또는 source_chunk_id가 없음 → Grounding 평가 불가")
    elif not chunk_id_valid:
        errors.append("chunk_id_valid = False → 유효하지 않은 근거 참조, 자동 FAIL")

    # explanation
    explanation = quiz.get("explanation", "")
    if not explanation:
        errors.append("explanation 필드가 없거나 비어있음")
    else:
        # 1. 공통: 정답 근거 존재 여부 확인
        if "✅ 정답 근거" not in explanation:
            errors.append("해설 내 '✅ 정답 근거' 섹션 누락")

        # 2. MCQ: 오답 함정 상세 존재 여부 확인
        if quiz_type == "multiple_choice":
            m = re.search(r"❌ 오답 함정:\s*(.*?)(?=\||✅|📌|$)", explanation, re.DOTALL)
            if not m:
                errors.append("해설 내 '❌ 오답 함정' 섹션 누락")
            else:
                distractor_text = m.group(1).strip()
                distractor_reasons = {}
                # A-이유, A는 이유, A: 이유 등 패턴 처리
                for dm in re.finditer(r"\b([A-D])(?:[–\-]|는|:)\s*(.+?)(?=(?:,\s*)?[A-D](?:[–\-]|는|:)|$)", distractor_text, re.DOTALL):
                    distractor_reasons[dm.group(1)] = dm.group(2).strip().rstrip(",").strip()
                
                # 정답을 제외한 모든 선택지에 대한 해설이 있는지 확인
                options = quiz.get("options", {})
                answer = quiz.get("answer", "")
                missing_reasons = []
                for k in options:
                    if k != answer and k not in distractor_reasons:
                        missing_reasons.append(k)
                
                if missing_reasons:
                    errors.append(f"오답 해설 누락: {', '.join(missing_reasons)} (해설 내 '❌ 오답 함정' 섹션에 기재 필요)")

    # ── MCQ 추가 필드 ─────────────────────────────────────────────────────────

    if quiz_type == "multiple_choice":

        # options A/B/C/D
        options = quiz.get("options", {})
        if not options:
            errors.append("options 필드가 없음")
        else:
            for key in VALID_ANSWER_OPTIONS:
                if not options.get(key, "").strip():
                    errors.append(f"options.{key}가 없거나 비어있음")

        # answer ∈ {A, B, C, D}
        if answer and answer not in VALID_ANSWER_OPTIONS:
            errors.append(f"MCQ answer가 A/B/C/D가 아님: '{answer}'")


    return {
        "quiz_id": quiz_id,
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ── 세트 단위 검증 ─────────────────────────────────────────────────────────────

def validate_quiz_set(quiz_set: dict) -> dict:
    """
    퀴즈 세트 전체를 검증.

    Returns:
        {
            "quiz_set_id": str,
            "pass": bool,
            "set_errors": list[str],
            "set_warnings": list[str],
            "item_results": list[dict],
        }
    """
    set_errors = []
    set_warnings = []

    quiz_set_id = quiz_set.get("quiz_set_id", "unknown")
    difficulty = quiz_set.get("difficulty", "medium")
    quizzes = quiz_set.get("quizzes", [])

    # ── 총 문항 수 ────────────────────────────────────────────────────────────

    total = len(quizzes)
    if not (MIN_QUESTIONS <= total <= MAX_QUESTIONS):
        set_errors.append(
            f"총 문항 수 오류: {total}문항 (허용 범위: {MIN_QUESTIONS}~{MAX_QUESTIONS}문항)"
        )

    # ── MCQ / 단답형 / 코드완성 수 (비율 기반, ±1 허용) ─────────────────────

    counts: dict[str, int] = {"multiple_choice": 0, "short_answer": 0, "code_completion": 0}
    for q in quizzes:
        q_type = q.get("type", "")
        if q_type in counts:
            counts[q_type] += 1
    mcq_count = counts["multiple_choice"]
    sa_count = counts["short_answer"]
    cc_count = counts["code_completion"]

    # MCQ: 총 문항의 60~80% 사이여야 함
    mcq_min = max(1, round(total * 0.6))
    mcq_max = round(total * 0.8)
    if not (mcq_min <= mcq_count <= mcq_max):
        set_errors.append(f"MCQ 수 오류: {mcq_count}문항 (기대 범위: {mcq_min}~{mcq_max}문항)")

    # code_completion: easy는 0개, medium/hard는 0~1개
    if difficulty == "easy":
        if cc_count > 0:
            set_errors.append(f"코드완성 수 오류: easy 난이도에서 {cc_count}개 (기대: 0개)")
    else:
        if cc_count > 1:
            set_errors.append(f"코드완성 수 오류: {cc_count}개 (기대: 최대 1개)")

    # ── 유형 분포 검증 (실제 문항 수에 비례 스케일, ±1 허용) ──────────────────

    base_dist = STYLE_DISTRIBUTION.get(difficulty, STYLE_DISTRIBUTION["medium"])
    base_total = sum(base_dist.values())  # 10
    actual_dist: dict[str, int] = {style: 0 for style in VALID_STYLES}
    for q in quizzes:
        style = q.get("style", "")
        if style in actual_dist:
            actual_dist[style] += 1

    for style, base_count in base_dist.items():
        # floor 사용: 8문항일 때 prediction 기대값 floor(1.6)=1, ±1 → [0,2]
        scaled = math.floor(base_count * total / base_total)
        actual_count = actual_dist[style]
        if abs(actual_count - scaled) > 1:
            set_warnings.append(
                f"유형 분포 권고 [{style}]: {actual_count}개 (권장: {scaled}개, ±1)"
            )

    # ── 정답 분포 검증 ────────────────────────────────────────────────────────

    answer_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
    for q in quizzes:
        if q.get("type") == "multiple_choice":
            ans = q.get("answer")
            if ans in answer_dist:
                answer_dist[ans] += 1

    bias_threshold_error = max(5, round(mcq_count * 0.7))
    bias_threshold_warn = max(4, round(mcq_count * 0.55))
    for label, cnt in answer_dist.items():
        if cnt >= bias_threshold_error:
            set_errors.append(f"정답 분포 심각한 편중: '{label}'이 {cnt}회 등장 ({mcq_count}문항 중 {bias_threshold_error}회 이상)")
        elif cnt >= bias_threshold_warn:
            set_warnings.append(f"정답 분포 편중 주의: '{label}'이 {cnt}회 등장 ({mcq_count}문항 중 {bias_threshold_warn}회 이상)")

    # ── 문항 단위 검증 ────────────────────────────────────────────────────────

    item_results = [validate_quiz_item(q) for q in quizzes]
    failed_items = [r for r in item_results if not r["pass"]]

    # 세트 자체 에러와 문항 단위 에러 중 하나라도 있으면 세트 fail
    overall_pass = (len(set_errors) == 0) and (len(failed_items) == 0)

    return {
        "quiz_set_id": quiz_set_id,
        "pass": overall_pass,
        "set_errors": set_errors,
        "set_warnings": set_warnings,
        "item_results": item_results,
    }


# ── 리포트 출력 ───────────────────────────────────────────────────────────────

def print_report(result: dict) -> None:
    """검증 결과를 사람이 읽기 좋게 출력."""
    status = "✅ PASS" if result["pass"] else "❌ FAIL"
    print(f"\n{'='*60}")
    print(f"퀴즈 세트: {result['quiz_set_id']}")
    print(f"결과: {status}")

    if result["set_errors"]:
        print("\n[세트 오류]")
        for e in result["set_errors"]:
            print(f"  ❌ {e}")

    if result["set_warnings"]:
        print("\n[세트 경고]")
        for w in result["set_warnings"]:
            print(f"  ⚠️  {w}")

    print("\n[문항별 결과]")
    for item in result["item_results"]:
        item_status = "✅" if item["pass"] else "❌"
        print(f"  {item_status} {item['quiz_id']}")
        for e in item["errors"]:
            print(f"      ❌ {e}")
        for w in item["warnings"]:
            print(f"      ⚠️  {w}")

    print(f"{'='*60}\n")


# ── 실행 예시 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("사용법: python structural_validator.py <quiz_json_path>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        quiz_set = json.load(f)

    result = validate_quiz_set(quiz_set)
    print_report(result)
