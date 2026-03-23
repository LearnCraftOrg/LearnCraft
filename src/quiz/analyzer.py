"""퀴즈 결과 분석 모듈.

퀴즈 오답 문항을 분석하여 취약한 개념을 추출하고,
개인화 학습 가이드 생성을 위한 검색 쿼리를 만듭니다.

개인화 학습 흐름:
  퀴즈 결과
    → 오답 문항 필터링 (analyze_wrong_answers)
    → 개념 키워드 추출 (_extract_tech_terms)
    → 검색 쿼리 변환 (concepts_to_query)
    → ChromaDB 벡터 검색
    → 개념 특화 학습 가이드 생성
"""

import re
from typing import TypedDict


class QuizResult(TypedDict):
    """퀴즈 문항 결과 데이터 구조."""

    question: str       # 문제 내용
    answer: str         # 정답
    user_answer: str    # 사용자 답변
    is_correct: bool    # 정오 여부
    explanation: str    # 해설


def analyze_wrong_answers(quiz_results: list[QuizResult]) -> list[str]:
    """
    퀴즈 결과에서 오답 문항의 개념 키워드를 추출.

    오답 문항의 문제 텍스트와 해설에서 기술 용어를 추출하여
    학습자의 취약 개념을 식별합니다.

    추출 우선순위:
    1. 따옴표/백틱/굵은 글씨로 강조된 기술 용어
    2. 영문 기술 키워드 (ORM, FastAPI 등)
    3. 추출 실패 시 문제 텍스트 앞 50자

    Args:
        quiz_results: 퀴즈 결과 딕셔너리 리스트

    Returns:
        오답 문항에서 추출한 개념 키워드 목록 (중복 제거)
    """
    wrong_concepts: list[str] = []

    for result in quiz_results:
        # 정답 문항은 건너뜀
        if result.get("is_correct", True):
            continue

        question = result.get("question", "")
        explanation = result.get("explanation", "")

        # 문제 텍스트와 해설에서 기술 용어 추출
        tech_terms = _extract_tech_terms(question + " " + explanation)

        if tech_terms:
            # 추출된 기술 용어를 취약 개념 목록에 추가
            wrong_concepts.extend(tech_terms)
        elif question:
            # 기술 용어를 찾지 못한 경우 문제 텍스트 앞부분 사용
            wrong_concepts.append(question[:50])

    # 삽입 순서를 유지하면서 중복 제거
    return list(dict.fromkeys(wrong_concepts))


def _extract_tech_terms(text: str) -> list[str]:
    """
    텍스트에서 기술 용어 추출.

    강의 자료에서 사용되는 마크다운 강조 패턴으로 기술 용어를 식별합니다:
    - 따옴표: "FastAPI", 'ORM'
    - 백틱: `session`, `async def`
    - 굵은 글씨: **SQLAlchemy**, **트랜잭션**

    Args:
        text: 분석할 텍스트 (문제 + 해설 결합)

    Returns:
        추출된 기술 용어 리스트 (중복 포함, 순서 유지)
    """
    terms: list[str] = []

    # 따옴표로 감싸진 용어: "FastAPI", 'ORM' 등
    terms.extend(
        re.findall(
            r'["\']([A-Za-z가-힣][A-Za-z가-힣0-9\s\-_]{1,30})["\']', text
        )
    )

    # 백틱으로 감싸진 코드/용어: `session`, `async def` 등
    terms.extend(
        re.findall(r'`([A-Za-z][A-Za-z0-9_\s\.]{1,30})`', text)
    )

    # 굵은 글씨 (마크다운): **ORM**, **FastAPI** 등
    terms.extend(
        re.findall(
            r'\*\*([A-Za-z가-힣][A-Za-z가-힣0-9\s\-_]{1,30})\*\*', text
        )
    )

    # 앞뒤 공백 제거 후 비어 있지 않은 용어만 반환
    return [t.strip() for t in terms if t.strip()]


def concepts_to_query(concepts: list[str]) -> str:
    """
    취약 개념 키워드 목록을 RAG 검색 쿼리 문자열로 변환.

    여러 개념을 하나의 의미 있는 공백 구분 쿼리로 조합합니다.
    너무 많은 개념은 검색 정확도를 저하시키므로 최대 5개로 제한합니다.

    Args:
        concepts: 취약 개념 키워드 목록

    Returns:
        ChromaDB 유사도 검색에 사용할 쿼리 문자열
        빈 리스트 입력 시 빈 문자열 반환
    """
    if not concepts:
        return ""

    # 최대 5개 개념만 사용 (검색 정확도 최적화)
    top_concepts = concepts[:5]
    return " ".join(top_concepts)


def extract_wrong_concept_keywords(quiz_results: list[QuizResult]) -> str:
    """
    퀴즈 결과에서 개인화 학습 가이드용 검색 쿼리 생성 (편의 함수).

    analyze_wrong_answers와 concepts_to_query를 한 번에 수행하는
    편의 함수입니다. UI 레이어에서 직접 호출 시 사용합니다.

    Args:
        quiz_results: 퀴즈 결과 리스트

    Returns:
        개인화 학습 가이드 생성에 사용할 검색 쿼리 문자열
    """
    wrong_concepts = analyze_wrong_answers(quiz_results)
    return concepts_to_query(wrong_concepts)


def parse_wrong_concepts_from_text(raw_text: str) -> list[str]:
    """
    사용자가 직접 입력한 오답 개념 텍스트를 키워드 목록으로 파싱.

    UI에서 사용자가 쉼표 또는 줄바꿈으로 구분하여 입력한
    오답 개념 텍스트를 키워드 리스트로 변환합니다.

    Args:
        raw_text: 쉼표 또는 줄바꿈으로 구분된 오답 개념 텍스트
                  예) "ORM, 세션 관리\n트랜잭션 처리"

    Returns:
        공백 제거된 개념 키워드 목록 (빈 항목 제외)
    """
    if not raw_text or not raw_text.strip():
        return []

    # 쉼표 또는 줄바꿈으로 분리 후 공백 제거
    concepts = re.split(r"[,\n]+", raw_text)
    return [c.strip() for c in concepts if c.strip()]
