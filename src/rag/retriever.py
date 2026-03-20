"""헤딩 임베딩 기반 검색 retriever.

두 가지 검색 모드:
- retrieve_by_date: 날짜 지정 → 해당 날짜의 ## 섹션 전체 반환 (semantic 필터 없음)
- retrieve_by_query: 쿼리 입력 → 쿼리 임베딩 ↔ 헤딩 임베딩 유사도 비교로 관련 섹션 검색 (chunk_id 포함)
"""
from __future__ import annotations

from typing import Optional

from config.settings import RETRIEVAL_K
from src.vectorstore.store import get_vectorstore


def retrieve_by_date(date: str) -> list[dict]:
    """
    날짜 기반: 해당 날짜의 모든 ## 섹션 반환.
    단일 날짜 퀴즈/가이드 생성 시 완전한 강의 커버리지 보장.

    Args:
        date: 검색 대상 날짜 (YYYY-MM-DD)
        
    Returns:
        [{"content": str, "chunk_id": str, "metadata": dict}, ...]
    """
    vs = get_vectorstore()
    result = vs.get(where={"$and": [{"date": date}, {"heading_level": 2}]})
    
    docs = []
    for i, meta in enumerate(result["metadatas"]):
        if meta.get("section_content"):
            docs.append({
                "content": meta["section_content"],
                "chunk_id": result["ids"][i],
                "metadata": meta
            })
    return docs


def retrieve_by_query(query: str, dates: [list[str]] = None) -> list[dict]:
    """
    내용 기반: 쿼리 임베딩과 ## / ### 헤딩 임베딩 유사도 비교 후 관련 섹션 반환 (chunk_id 포함).
    dates 지정 시 해당 날짜들로 검색 범위 제한.

    Args:
        query: 검색 쿼리
        dates: 검색 범위 날짜 목록. None 또는 빈 리스트면 전체 검색.
        
    Returns:
        [{"content": str, "chunk_id": str, "metadata": dict}, ...]
    """
    vs = get_vectorstore()
    
    # Chroma ID를 직접 가져오기 위해 _collection.query 사용 (LangChain 인터페이스 보완)
    embeddings = vs._embedding_function.embed_query(query)
    
    where_filter = None
    if dates:
        where_filter = {"date": {"$in": dates}}
        
    results = vs._collection.query(
        query_embeddings=[embeddings],
        n_results=RETRIEVAL_K,
        where=where_filter
    )

    docs = []
    seen = set()
    for i in range(len(results["ids"][0])):
        chunk_id = results["ids"][0][i]
        meta = results["metadatas"][0][i]
        content = meta.get("section_content", "")
        
        # 중복 섹션 제거 (동일 날짜/Heading 방지)
        key = f"{meta['date']}::{meta['section_key']}"
        if key not in seen:
            seen.add(key)
            docs.append({
                "content": content,
                "chunk_id": chunk_id,
                "metadata": meta
            })
    return docs
