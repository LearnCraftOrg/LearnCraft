"""학습 가이드 생성 서비스 레이어.

외부(UI, main.py 등)에서 호출하는 진입점으로,
RAG 체인을 활용해 일반 학습 가이드 및 개인화 학습 가이드를 생성합니다.

서비스 레이어 책임:
- 입력값 유효성 검사
- RAG 체인 싱글턴 관리 (최초 호출 시 초기화)
- 일반 학습 가이드 생성: generate_study_guide(query)
- 개인화 학습 가이드 생성: generate_personalized_study_guide(wrong_concepts)
"""

from rag.study_guide_chain import build_study_guide_chain
from quiz.quiz_analyzer import concepts_to_query

# RAG 체인 싱글턴 (최초 호출 시 초기화, 이후 재사용)
_chain = None


def _get_chain():
    """
    RAG 학습 가이드 체인 반환 (싱글턴 패턴).

    최초 호출 시 ChromaDB 연결 및 LLM 설정을 포함한 체인을 초기화합니다.
    이후 호출에서는 기존 체인 인스턴스를 재사용하여 성능을 최적화합니다.

    Returns:
        build_study_guide_chain()으로 생성된 LCEL 체인
    """
    global _chain
    if _chain is None:
        # 체인 초기화: ChromaDB 연결 + OpenAI LLM 설정 + 프롬프트 로드
        _chain = build_study_guide_chain(k=5)
    return _chain


def generate_study_guide(query: str) -> str:
    """
    강의 주제를 입력받아 RAG 기반 학습 가이드 생성.

    RAG 파이프라인:
    1. 쿼리 임베딩 → ChromaDB 유사도 검색 (k=5)
    2. 검색된 강의 섹션으로 컨텍스트 구성
    3. 학습 가이드 프롬프트에 컨텍스트 삽입
    4. GPT-4o-mini 호출 → 6개 섹션 학습 가이드 반환

    Args:
        query: 학습 가이드를 생성할 강의 주제 또는 키워드
               예) "FastAPI 라우터", "ORM과 SQLAlchemy", "비동기 처리"

    Returns:
        6개 섹션으로 구성된 한국어 학습 가이드 문자열

    Raises:
        ValueError: 쿼리가 비어 있을 경우
    """
    # 입력값 유효성 검사
    if not query or not query.strip():
        raise ValueError("쿼리가 비어 있습니다. 학습 주제를 입력하세요.")

    # RAG 체인 실행: 쿼리 → 벡터 검색 → LLM → 학습 가이드
    chain = _get_chain()
    return chain.invoke(query.strip())


def generate_personalized_study_guide(wrong_concepts: list[str]) -> str:
    """
    퀴즈 오답 개념 목록을 기반으로 개인화 학습 가이드 생성.

    퀴즈에서 틀린 개념들을 분석하여 해당 개념에 집중한
    맞춤형 학습 가이드를 생성합니다.

    개인화 파이프라인:
    1. 오답 개념 목록 → 검색 쿼리 변환 (concepts_to_query)
    2. 해당 개념 관련 강의 섹션 벡터 검색
    3. 개인화 컨텍스트로 학습 가이드 생성

    Args:
        wrong_concepts: 퀴즈에서 틀린 문항의 개념 키워드 목록
                        예) ["ORM", "세션 관리", "트랜잭션"]

    Returns:
        오답 개념에 집중한 한국어 개인화 학습 가이드 문자열

    Raises:
        ValueError: 오답 개념 목록이 비어 있을 경우
    """
    # 입력값 유효성 검사
    if not wrong_concepts:
        raise ValueError("오답 개념 목록이 비어 있습니다.")

    # 오답 개념들을 하나의 검색 쿼리로 변환
    query = concepts_to_query(wrong_concepts)

    # 변환된 쿼리로 학습 가이드 생성
    chain = _get_chain()
    return chain.invoke(query)
