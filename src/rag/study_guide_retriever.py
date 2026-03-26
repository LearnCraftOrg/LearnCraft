"""ChromaDB 기반 RAG Retriever 모듈.

벡터 유사도 검색으로 강의 관련 섹션을 검색하며,
헤딩 임베딩 구조에 맞게 section_content를 page_content로 변환합니다.

RAG 파이프라인 1단계: 쿼리 → 벡터 검색 → 관련 강의 섹션 반환
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langchain_openai import OpenAIEmbeddings

from config.settings import COLLECTION_NAME, EMBEDDING_MODEL, OPENAI_API_KEY, CHROMA_DIR

# ChromaDB 저장 경로
CHROMA_PATH: str = str(CHROMA_DIR)

# 유사도 검색 결과 수 (spec 요구사항: k=5)
RETRIEVAL_K: int = 5


def _get_vectorstore() -> Chroma:
    """
    ChromaDB 벡터스토어 인스턴스 반환.

    OpenAI text-embedding-3-small 모델로 임베딩 생성 후
    기존 lecture_chunks_refined 컬렉션에 연결합니다.

    Returns:
        langchain_chroma.Chroma 인스턴스
    """
    # OpenAI 임베딩 모델 초기화 (기존 벡터스토어와 동일한 모델 사용)
    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=OPENAI_API_KEY,
    )

    # 기존 ChromaDB 컬렉션에 연결 (새로 생성하지 않음)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )


def _extract_section_content(docs: list[Document]) -> list[Document]:
    """
    헤딩 임베딩 기반 문서에서 section_content를 page_content로 변환.

    기존 청킹 구조에서 page_content는 헤딩 텍스트(임베딩용)이며,
    실제 강의 내용은 metadata["section_content"]에 저장됩니다.
    LLM 컨텍스트로는 전체 섹션 내용이 필요하므로 변환을 수행합니다.

    동일한 section_key(## 헤딩)의 중복 문서를 제거하여
    LLM 토큰 낭비를 방지합니다.

    Args:
        docs: 벡터 검색으로 반환된 Document 리스트

    Returns:
        section_content가 page_content로 변환된 중복 제거 Document 리스트
    """
    seen: set[str] = set()
    results: list[Document] = []

    for doc in docs:
        # 날짜 + 섹션 키로 중복 제거 (## 헤딩 기준)
        key = (
            f"{doc.metadata.get('date', '')}::{doc.metadata.get('section_key', '')}"
        )
        if key not in seen:
            seen.add(key)
            # 헤딩 임베딩 대신 전체 섹션 내용을 page_content로 설정
            results.append(
                Document(
                    page_content=doc.metadata.get(
                        "section_content", doc.page_content
                    ),
                    metadata=doc.metadata,
                )
            )

    return results


def get_retriever(k: int = RETRIEVAL_K):
    """
    ChromaDB 유사도 검색 기반 Retriever 반환.

    RAG 파이프라인:
    1. 쿼리 텍스트를 OpenAI 임베딩으로 변환
    2. ChromaDB에서 코사인 유사도 기반 k개 섹션 검색
    3. 헤딩 텍스트 → section_content 변환 및 중복 제거

    Args:
        k: 검색할 최대 문서 수 (기본값: 5)

    Returns:
        LCEL Runnable retriever 체인 (str → list[Document])
    """
    # 벡터스토어 기반 기본 retriever 생성
    vectorstore = _get_vectorstore()
    base_retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )

    # section_content 변환 단계를 파이프라인으로 연결
    return base_retriever | RunnableLambda(_extract_section_content)
