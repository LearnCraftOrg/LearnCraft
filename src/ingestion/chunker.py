"""정제된 텍스트를 LangChain Document 청크로 분할."""
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config.settings import CHUNK_SIZE, CHUNK_OVERLAP


def chunk_text(text: str, metadata: dict) -> list[Document]:
    """
    Args:
        text: preprocess() 를 거친 정제 텍스트
        metadata: {date, week, subject, content, learning_goal} 등
    Returns:
        LangChain Document 리스트 (각 청크에 metadata 포함)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", ". ", " ", ""],
    )
    texts = splitter.split_text(text)
    return [
        Document(page_content=t, metadata={**metadata, "chunk_index": i})
        for i, t in enumerate(texts)
    ]
