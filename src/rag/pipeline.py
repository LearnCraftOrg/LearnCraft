"""강의 날짜 기반 RAG 컨텍스트 구성 파이프라인."""
from src.ingestion.loader import load_curriculum
from src.rag.retriever import retrieve_context


def build_context(date: str) -> dict:
    """
    특정 날짜에 대한 RAG 컨텍스트를 구성.

    Returns:
        {
            "date": str,
            "curriculum": dict,       # 커리큘럼 메타데이터
            "lecture_context": str,   # 검색된 강의 청크
            "query": str,             # 검색에 사용한 쿼리
        }
    """
    curriculum_map = load_curriculum()
    curriculum = curriculum_map.get(date, {})

    # 학습목표를 검색 쿼리로 사용 (없으면 날짜로 폴백)
    query = curriculum.get("learning_goal", date)
    if not query:
        query = curriculum.get("content", date)

    lecture_context = retrieve_context(date, query)

    return {
        "date": date,
        "curriculum": curriculum,
        "lecture_context": lecture_context,
        "query": query,
    }
