"""헤딩 임베딩 기반 검색 retriever.

두 가지 검색 모드:
- retrieve_by_date: 날짜 지정 → 해당 날짜의 ## 섹션 전체 반환 (semantic 필터 없음)
- retrieve_by_query: 쿼리 입력 → 쿼리 임베딩 ↔ 헤딩 임베딩 유사도 비교로 관련 섹션 검색
"""
from config.settings import RETRIEVAL_K
from src.vectorstore.store import get_vectorstore


def retrieve_by_date(date: str) -> str:
    """
    날짜 기반: 해당 날짜의 모든 ## 섹션 반환.
    단일 날짜 퀴즈/가이드 생성 시 완전한 강의 커버리지 보장.

    Args:
        date: 검색 대상 날짜 (YYYY-MM-DD)
    """
    vs = get_vectorstore()
    result = vs.get(where={"$and": [{"date": date}, {"heading_level": 2}]})
    return "\n\n".join(
        meta["section_content"]
        for meta in result["metadatas"]
        if meta.get("section_content")
    )


def retrieve_by_query(query: str, dates: list[str] | None = None) -> str:
    """
    내용 기반: 쿼리 임베딩과 ## / ### 헤딩 임베딩 유사도 비교 후 관련 섹션 반환.
    dates 지정 시 해당 날짜들로 검색 범위 제한.

    Args:
        query: 검색 쿼리
        dates: 검색 범위 날짜 목록. None 또는 빈 리스트면 전체 검색.
    """
    vs = get_vectorstore()
    search_kwargs: dict = {"k": RETRIEVAL_K}
    if dates:
        search_kwargs["filter"] = {"date": {"$in": dates}}
    docs = vs.similarity_search(query, **search_kwargs)

    seen: set[str] = set()
    results: list[str] = []
    for doc in docs:
        key = f"{doc.metadata['date']}::{doc.metadata['section_key']}"
        if key not in seen:
            seen.add(key)
            results.append(doc.metadata["section_content"])
    return "\n\n".join(results)
