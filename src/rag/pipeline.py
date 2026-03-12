"""강의 날짜 기반 RAG 컨텍스트 구성 파이프라인."""
from src.ingestion.loader import load_curriculum
from src.rag.retriever import retrieve_context, retrieve_context_multi


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


def build_context_multi(dates: list[str], user_query: str | None = None) -> dict:
    """
    다중 날짜 또는 텍스트 쿼리 기반 RAG 컨텍스트 구성.

    Args:
        dates: 검색 대상 날짜 목록. 빈 리스트면 전체 검색.
        user_query: 사용자가 직접 입력한 쿼리 (없으면 첫 날짜의 학습목표 사용)

    Returns:
        {dates, curriculum_summary, lecture_context, query}
    """
    curriculum_map = load_curriculum()
    curriculum_summary = "\n".join(
        f"{d}: {curriculum_map.get(d, {}).get('subject', '')} - {curriculum_map.get(d, {}).get('content', '')}"
        for d in dates
    )
    if user_query and user_query.strip():
        query = user_query.strip()
    elif dates:
        first = curriculum_map.get(dates[0], {})
        query = first.get("learning_goal", "") or first.get("content", dates[0])
    else:
        query = user_query or ""

    lecture_context = retrieve_context_multi(dates, query)
    return {
        "dates": dates,
        "curriculum_summary": curriculum_summary,
        "lecture_context": lecture_context,
        "query": query,
    }
