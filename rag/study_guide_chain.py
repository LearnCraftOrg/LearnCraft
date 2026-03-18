"""RAG 학습 가이드 생성 체인 모듈.

LCEL(LangChain Expression Language) 기반으로
벡터 검색 → 컨텍스트 구성 → LLM 호출 → 결과 반환 파이프라인 구성.

RAG 파이프라인 전체 흐름:
  쿼리 입력
    → Retriever (ChromaDB 유사도 검색)
    → Context 포맷팅 (Document 리스트 → 문자열)
    → Prompt 렌더링 (컨텍스트 + 쿼리 삽입)
    → LLM 호출 (gpt-4o-mini)
    → 학습 가이드 문자열 반환
"""

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

from config.settings import LLM_MODEL, OPENAI_API_KEY
from prompts.study_guide_prompt import get_study_guide_prompt
from rag.retriever import get_retriever

# LLM 온도 설정 (낮을수록 사실 기반, 일관된 답변)
TEMPERATURE: float = 0.3


def _format_context(docs: list[Document]) -> str:
    """
    검색된 Document 리스트를 LLM 컨텍스트 문자열로 변환.

    각 섹션을 구분선으로 분리하여 LLM이 내용을 명확히 구분하도록 합니다.

    Args:
        docs: Retriever가 반환한 Document 리스트

    Returns:
        구분선으로 분리된 강의 내용 문자열
    """
    # 각 강의 섹션을 구분선으로 분리하여 컨텍스트 구성
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def build_study_guide_chain(k: int = 5):
    """
    RAG 기반 학습 가이드 생성 LCEL 체인 구성.

    RetrievalQA 대신 LCEL을 사용하여 명시적인 파이프라인을 구성합니다.
    각 단계를 독립적으로 교체/수정할 수 있는 모듈형 구조입니다.

    파이프라인 구성:
    1. Retriever: 쿼리 → 관련 강의 섹션 k개 검색
    2. Context 구성: Document 리스트 → 구분선으로 연결된 문자열
    3. Prompt 렌더링: {context} + {question} → ChatPromptValue
    4. LLM 호출: ChatPromptValue → AIMessage
    5. 출력 파싱: AIMessage → 학습 가이드 문자열

    Args:
        k: 검색할 문서 수 (기본값: 5)

    Returns:
        실행 가능한 LCEL 체인 (chain.invoke(query) → str)
    """
    # LLM 초기화 (gpt-4o-mini, 낮은 온도로 사실 기반 생성)
    llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=TEMPERATURE,
        api_key=OPENAI_API_KEY,
    )

    # 학습 가이드 프롬프트 템플릿 로드 (6개 섹션 포맷)
    prompt = get_study_guide_prompt()

    # RAG Retriever 초기화 (k개 유사 섹션 검색 + section_content 변환)
    retriever = get_retriever(k=k)

    # LCEL 체인 구성:
    # - context: retriever로 검색 후 텍스트 포맷팅
    # - question: 사용자 쿼리 그대로 전달 (RunnablePassthrough)
    chain = (
        {
            "context": retriever | _format_context,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain
