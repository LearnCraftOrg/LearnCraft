"""AI 학습 가이드 생성기 - 실행 예시.

RAG 파이프라인 동작 확인을 위한 예시 실행 스크립트입니다.
일반 학습 가이드 생성과 개인화 학습 가이드 생성을 각각 테스트합니다.

실행 방법:
    python main.py

사전 조건:
    - .env 파일에 OPENAI_API_KEY 설정
    - ./chroma_db 디렉터리에 벡터 데이터 존재
"""

from services.study_guide_service import (
    generate_study_guide,
    generate_personalized_study_guide,
)


def run_general_guide_example() -> None:
    """
    일반 학습 가이드 생성 예시 실행.

    강의 주제 쿼리를 입력하여 RAG 파이프라인이
    관련 강의 섹션을 검색하고 학습 가이드를 생성하는지 확인합니다.
    """
    print("=" * 60)
    print("[ 일반 학습 가이드 생성 예시 ]")
    print("=" * 60)

    # 테스트 쿼리: 강의에서 다룬 주제 입력
    query = "FastAPI 라우터와 의존성 주입"
    print(f"\n쿼리: {query}\n")
    print("RAG 파이프라인 실행 중...")
    print("  1. 쿼리 임베딩 생성")
    print("  2. ChromaDB 유사도 검색 (k=5)")
    print("  3. 강의 섹션 컨텍스트 구성")
    print("  4. GPT-4o-mini 학습 가이드 생성")
    print("-" * 60)

    # 학습 가이드 생성 실행
    guide = generate_study_guide(query)

    print("\n[ 생성된 학습 가이드 ]\n")
    print(guide)
    print("\n" + "=" * 60)


def run_personalized_guide_example() -> None:
    """
    퀴즈 오답 기반 개인화 학습 가이드 생성 예시 실행.

    퀴즈에서 틀린 개념 목록을 입력하여
    해당 개념에 집중한 맞춤형 학습 가이드를 생성합니다.
    """
    print("=" * 60)
    print("[ 개인화 학습 가이드 생성 예시 ]")
    print("=" * 60)

    # 테스트 오답 개념 목록
    wrong_concepts = ["ORM", "세션 관리", "트랜잭션"]
    print(f"\n오답 개념: {wrong_concepts}\n")
    print("개인화 파이프라인 실행 중...")
    print("  1. 오답 개념 → 검색 쿼리 변환")
    print("  2. ChromaDB 개념 관련 섹션 검색")
    print("  3. 개념 특화 학습 가이드 생성")
    print("-" * 60)

    # 개인화 학습 가이드 생성 실행
    guide = generate_personalized_study_guide(wrong_concepts)

    print("\n[ 생성된 개인화 학습 가이드 ]\n")
    print(guide)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("\n🚀 AI 학습 가이드 생성기 실행\n")

    # 예시 1: 일반 학습 가이드 생성
    run_general_guide_example()

    print()

    # 예시 2: 개인화 학습 가이드 생성
    run_personalized_guide_example()

    print("\n✅ 실행 완료")
    print("\nStreamlit UI 실행:")
    print("  streamlit run ui/streamlit_app.py")
