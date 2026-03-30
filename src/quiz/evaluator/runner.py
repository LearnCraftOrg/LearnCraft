import sys
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (config, src 접근용)
ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import GENERATED_QUIZ_DIR, QUIZ_EVAL_DIR
from src.quiz.evaluator.structural import validate_quiz_set
from src.quiz.evaluator.grounding import evaluate_grounding_set
from src.quiz.evaluator.distractor import evaluate_distractor_set
from src.quiz.evaluator.duplicate import evaluate_duplicate_set
from src.quiz.evaluator.report import save_report

logger = logging.getLogger(__name__)

# ── 전체 평가 실행 ────────────────────────────────────────────────────────────

def run_evaluation(quiz_set: dict) -> dict:
    """
    퀴즈 세트 하나에 대해 전체 평가 실행.

    평가 순서:
      1. 구조적 유효성  → critical fail이면 이후 평가 스킵
      2. Grounding      → Vertex AI
      3. Distractor     → BM25
      4. 의미적 중복    → 임베딩

    Returns:
        {
            "quiz_set_id": str,
            "evaluated_at": str,
            "overall_pass": bool,
            "fail_reasons": list[str],
            "structural": dict,
            "grounding": dict | None,
            "distractor": dict | None,
            "duplicate": dict | None,
        }
    """
    quiz_set_id = quiz_set.get("quiz_set_id", "unknown")
    fail_reasons = []
    t_eval_total = time.perf_counter()

    # ── 1. 구조적 유효성 ──────────────────────────────────────────────────────
    t1 = time.perf_counter()
    structural_result = validate_quiz_set(quiz_set)
    logger.debug("[TIMING] 평가 structural: %.2fs | %s", time.perf_counter()-t1, "PASS" if structural_result["pass"] else "FAIL")
    if not structural_result["pass"]:
        fail_reasons.append("structural")

    # 구조적 유효성 실패하더라도 나머지 평가를 계속 진행 (사용자 요청)

    # ── 2. Grounding ──────────────────────────────────────────────────────────
    try:
        t2 = time.perf_counter()
        grounding_result = evaluate_grounding_set(quiz_set)
        logger.debug("[TIMING] 평가 grounding: %.2fs | %s", time.perf_counter()-t2, "PASS" if grounding_result["pass"] else "FAIL")
        if not grounding_result["pass"]:
            fail_reasons.append("grounding")
    except Exception as e:
        grounding_result = {"pass": False, "error": str(e)}
        fail_reasons.append("grounding")

    # ── 3. Distractor 품질 ────────────────────────────────────────────────────
    try:
        t3 = time.perf_counter()
        distractor_result = evaluate_distractor_set(quiz_set)
        logger.debug("[TIMING] 평가 distractor: %.2fs | %s", time.perf_counter()-t3, "PASS" if distractor_result["pass"] else "FAIL")
        if not distractor_result["pass"]:
            fail_reasons.append("distractor")
    except Exception as e:
        distractor_result = {"pass": False, "error": str(e)}
        fail_reasons.append("distractor")

    # ── 4. 의미적 중복 ────────────────────────────────────────────────────────
    try:
        t4 = time.perf_counter()
        duplicate_result = evaluate_duplicate_set(quiz_set)
        logger.debug("[TIMING] 평가 duplicate: %.2fs | %s", time.perf_counter()-t4, "PASS" if duplicate_result["pass"] else "FAIL")
        if not duplicate_result["pass"]:
            fail_reasons.append("duplicate")
    except Exception as e:
        duplicate_result = {"pass": False, "error": str(e)}
        fail_reasons.append("duplicate")

    eval_result = {
        "quiz_set_id": quiz_set_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "fail_reasons": fail_reasons,
        "structural": structural_result,
        "grounding": grounding_result,
        "distractor": distractor_result,
        "duplicate": duplicate_result,
    }
    score_info = compute_score(eval_result)
    eval_result["overall_score"] = score_info["score"]
    eval_result["grade"] = score_info["grade"]

    logger.info("[TIMING] 평가 전체 (quiz_set_id=%s): %.2fs | 점수=%d(%s) 실패=%s",
                quiz_set_id, time.perf_counter()-t_eval_total,
                score_info["score"], score_info["grade"],
                ", ".join(fail_reasons) if fail_reasons else "없음")
    return eval_result


# ── 점수 산출 ─────────────────────────────────────────────────────────────────

def compute_score(eval_result: dict) -> dict:
    """
    100점 차감제 점수 산출.

    차감 기준:
      - Structural 세트 오류: -4 per error
      - Structural 문항 오류: -2 per item error
      - Grounding fail (hallucination): -10 per item  ← 가중치 최우선
      - Explanation fail: -4 per item
      - Distractor fail (비예측형 MCQ): -3 per item
      - Duplicate warn (0.75~0.85): -2 per pair
      - Duplicate fail (≥0.85): -5 per pair

    Returns:
        {"score": int, "grade": str}  grade = A/B/C/D
    """
    deductions = 0

    s = eval_result.get("structural", {})
    deductions += len(s.get("set_errors", [])) * 4
    for item in s.get("item_results", []):
        deductions += len(item.get("errors", [])) * 2

    g = eval_result.get("grounding", {})
    for item in g.get("item_results", []):
        if item.get("grounding_pass") is False:
            deductions += 10
        if item.get("explanation_pass") is False:
            deductions += 4

    d = eval_result.get("distractor", {})
    for item in d.get("item_results", []):
        if not item.get("skipped") and not item.get("pass"):
            deductions += 3

    dup = eval_result.get("duplicate", {})
    deductions += len(dup.get("warnings", [])) * 2
    deductions += len(dup.get("errors", [])) * 5

    score = max(0, 100 - deductions)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"
    return {"score": score, "grade": grade}


# ── eval JSON 저장 ────────────────────────────────────────────────────────────

def save_eval_result(eval_result: dict) -> Path:
    """평가 결과를 eval JSON 파일로 저장."""
    os.makedirs(QUIZ_EVAL_DIR, exist_ok=True)
    quiz_set_id = eval_result["quiz_set_id"]
    file_path = Path(QUIZ_EVAL_DIR) / f"eval_{quiz_set_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(eval_result, f, indent=2, ensure_ascii=False)
    return file_path


# ── 파일 기반 실행 ────────────────────────────────────────────────────────────

def run_evaluation_from_file(quiz_json_path: str) -> dict:
    """
    quiz JSON 파일 경로를 받아 평가 실행 후 eval JSON 저장.

    Returns: 평가 결과 dict
    """
    with open(quiz_json_path, encoding="utf-8") as f:
        quiz_set = json.load(f)

    eval_result = run_evaluation(quiz_set)
    saved_path = save_eval_result(eval_result)
    save_report(eval_result, quiz_set)

    logger.info("평가 완료: %d점 (%s등급)", eval_result["overall_score"], eval_result["grade"])
    logger.info("저장 위치: %s", saved_path)
    if eval_result["fail_reasons"]:
        logger.warning("실패 원인: %s", ", ".join(eval_result["fail_reasons"]))

    return eval_result


def run_evaluation_all() -> list[dict]:
    """
    GENERATED_QUIZ_DIR 내 모든 quiz JSON 파일 평가 실행.

    Returns: 전체 평가 결과 리스트
    """
    quiz_dir = Path(GENERATED_QUIZ_DIR)
    quiz_files = sorted(quiz_dir.glob("quiz_*.json"))

    if not quiz_files:
        logger.info("평가할 퀴즈 파일이 없습니다: %s", quiz_dir)
        return []

    results = []
    for quiz_file in quiz_files:
        logger.info("평가 중: %s", quiz_file.name)
        result = run_evaluation_from_file(str(quiz_file))
        results.append(result)

    # 요약 출력
    total = len(results)
    a_count = sum(1 for r in results if r.get("grade") == "A")
    logger.info("전체 %d개 세트 평가 완료 | A등급: %d / 나머지: %d", total, a_count, total - a_count)

    return results


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="퀴즈 품질 평가 러너")
    parser.add_argument("file", nargs="?", help="평가할 특정 quiz JSON 파일 경로")
    parser.add_argument("--all", action="store_true", help="모든 생성된 퀴즈 평가 실행")

    args = parser.parse_args()

    if args.all:
        run_evaluation_all()
    elif args.file:
        run_evaluation_from_file(args.file)
    else:
        parser.print_help()
        sys.exit(1)
