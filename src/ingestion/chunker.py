"""마크다운 헤딩 기반 LangChain Document 청크 생성."""
import re
from langchain_core.documents import Document


def chunk_text(text: str, metadata: dict) -> list[Document]:
    """
    ## 헤딩 기준으로 섹션 분할. ## 및 ### 헤딩 텍스트를 임베딩 대상으로 사용.

    Args:
        text: {date}_refined.md 전체 텍스트
        metadata: {date, week, subject, content, learning_goal} 등
    Returns:
        LangChain Document 리스트.
        - ## 헤딩: page_content = "## 제목" (임베딩), metadata["section_content"] = ## 블록 전체
        - ### 헤딩: page_content = "### 소제목" (임베딩), metadata["section_content"] = 부모 ## 블록 전체
        두 경우 모두 metadata["section_key"] = 부모 ## 헤딩 텍스트 (중복 제거 키)
    """
    blocks = re.split(r'(?:^|\n)(?=## )', text)
    docs = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        first_line = block.splitlines()[0]
        heading_text = first_line.lstrip('#').strip()

        # ## 헤딩 Document
        docs.append(Document(
            page_content=f"## {heading_text}",
            metadata={
                **metadata,
                "heading_level": 2,
                "section_key": heading_text,
                "section_content": block,
            },
        ))

        # ### 헤딩 Documents (부모 ## 섹션 전체를 section_content로 공유)
        for sub in re.findall(r'^### (.+)$', block, re.MULTILINE):
            docs.append(Document(
                page_content=f"### {sub}",
                metadata={
                    **metadata,
                    "heading_level": 3,
                    "section_key": heading_text,
                    "section_content": block,
                },
            ))

    return docs
