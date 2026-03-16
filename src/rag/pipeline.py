"""강의 RAG 컨텍스트 구성 파이프라인 (chunk_id 지원)."""
from src.ingestion.loader import load_curriculum
from src.rag.retriever import retrieve_by_query


def build_context_by_date(date: str) -> dict:
    """
    단일 날짜 기반 컨텍스트 구성. 커리큘럼 학습목표로 semantic search하여 관련 섹션 반환.

    Returns:
        {
            "date": str,
            "curriculum": dict,
            "lecture_context": str,
            "retrieval_sources": list,
        }
    """
    curriculum_map = load_curriculum()
    curriculum = curriculum_map.get(date, {})
    query = curriculum.get("learning_goal", "") or curriculum.get("content", date)
    
    # retriever가 list[dict]를 반환함
    retrieved_docs = retrieve_by_query(query, dates=[date])
    
    # LLM 프롬프트용 텍스트 구성 및 소스 메타데이터 보존
    formatted_context = ""
    retrieval_sources = []
    for i, doc in enumerate(retrieved_docs, 1):
        formatted_context += f"### [Source {i}] (chunk_id: {doc['chunk_id']})\n{doc['content']}\n\n"
        retrieval_sources.append({
            "index": i,
            "chunk_id": doc["chunk_id"],
            "metadata": doc["metadata"]
        })

    return {
        "date": date,
        "curriculum": curriculum,
        "lecture_context": formatted_context,
        "retrieval_sources": retrieval_sources
    }


def build_context_by_query(dates: list[str], user_query: str | None = None) -> dict:
    """
    쿼리 기반 컨텍스트 구성. 쿼리와 헤딩 임베딩 유사도로 관련 섹션 검색.

    Args:
        dates: 검색 범위 날짜 목록. 빈 리스트면 전체 검색.
        user_query: 검색 쿼리 (없으면 첫 날짜의 학습목표 사용)

    Returns:
        {dates, curriculum_summary, lecture_context, query, retrieval_sources}
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

    # retriever가 list[dict]를 반환함
    retrieved_docs = retrieve_by_query(query, dates or None)
    
    formatted_context = ""
    retrieval_sources = []
    for i, doc in enumerate(retrieved_docs, 1):
        formatted_context += f"### [Source {i}] (chunk_id: {doc['chunk_id']})\n{doc['content']}\n\n"
        retrieval_sources.append({
            "index": i,
            "chunk_id": doc["chunk_id"],
            "metadata": doc["metadata"]
        })

    return {
        "dates": dates,
        "curriculum_summary": curriculum_summary,
        "lecture_context": formatted_context,
        "query": query,
        "retrieval_sources": retrieval_sources
    }
