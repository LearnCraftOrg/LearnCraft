"""ChromaDB 컬렉션 관리 및 문서 인덱싱."""
import logging
import time
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config.settings import CHROMA_DIR, COLLECTION_NAME
from src.vectorstore.embedder import get_embeddings

logger = logging.getLogger(__name__)

_vectorstore_instance: Optional[Chroma] = None


def get_vectorstore() -> Chroma:
    """영구 저장되는 ChromaDB vectorstore 반환 (싱글톤)."""
    global _vectorstore_instance
    if _vectorstore_instance is None:
        t0 = time.perf_counter()
        _vectorstore_instance = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embeddings(),
            persist_directory=str(CHROMA_DIR),
        )
        logger.debug("[TIMING] vectorstore 초기화: %.2fs", time.perf_counter()-t0)
    return _vectorstore_instance


def is_date_indexed(date: str) -> bool:
    """특정 날짜의 문서가 이미 인덱싱되어 있는지 확인."""
    vs = get_vectorstore()
    results = vs.get(where={"date": date}, limit=1)
    return len(results["ids"]) > 0


def add_documents(docs: list[Document]) -> int:
    """문서 리스트를 벡터스토어에 추가. 추가된 문서 수 반환."""
    vs = get_vectorstore()
    t0 = time.perf_counter()
    vs.add_documents(docs)
    logger.debug("[TIMING] vectorstore add_documents (%d개): %.2fs", len(docs), time.perf_counter()-t0)
    return len(docs)


def delete_date(date: str) -> None:
    """특정 날짜의 모든 문서 삭제 (재인덱싱 용)."""
    vs = get_vectorstore()
    existing = vs.get(where={"date": date})
    if existing["ids"]:
        vs.delete(ids=existing["ids"])


def get_indexed_dates() -> list[str]:
    """인덱싱된 날짜 목록 반환."""
    vs = get_vectorstore()
    all_docs = vs.get(include=["metadatas"])
    dates = set()
    for meta in all_docs.get("metadatas", []):
        if meta and "date" in meta:
            dates.add(meta["date"])
    return sorted(dates)


def get_stt_curriculum(date: str) -> dict:
    """STT에서 추출된 커리큘럼 데이터를 ChromaDB 메타데이터에서 로드."""
    vs = get_vectorstore()
    result = vs.get(where={"$and": [{"date": date}, {"heading_level": 2}]}, limit=1)
    if result["metadatas"]:
        meta = result["metadatas"][0]
        content = meta.get("content", "")
        return {
            "subject": content,
            "content": content,
            "learning_goal": meta.get("learning_goal", ""),
        }
    return {"subject": "", "content": "", "learning_goal": ""}
