"""날짜 필터 + MMR 유사도 검색 retriever."""
from langchain_core.vectorstores import VectorStoreRetriever

from config.settings import RETRIEVAL_K
from src.vectorstore.store import get_vectorstore


def get_retriever(date: str) -> VectorStoreRetriever:
    """
    특정 날짜의 청크만 대상으로 MMR 검색하는 retriever 반환.

    Args:
        date: 'YYYY-MM-DD' 형식
    """
    vs = get_vectorstore()
    return vs.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": RETRIEVAL_K,
            "fetch_k": RETRIEVAL_K * 3,
            "filter": {"date": date},
        },
    )


def retrieve_context(date: str, query: str) -> str:
    """
    날짜 기반 retriever로 관련 청크를 검색해 하나의 문자열로 반환.

    Args:
        date: 검색 대상 날짜
        query: 검색 쿼리 (학습 목표 또는 주제)
    """
    retriever = get_retriever(date)
    docs = retriever.invoke(query)
    return "\n\n".join(doc.page_content for doc in docs)
