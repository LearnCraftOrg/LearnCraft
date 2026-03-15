"""학습 가이드 생성용 LangChain PromptTemplate 정의.

6개 섹션(핵심 개념, 개념 설명, 핵심 요약, 흔한 오해, 복습 문제, 실용적 응용)으로
구성된 한국어 학습 가이드 출력 형식을 강제합니다.

프롬프트 구성:
- 시스템 프롬프트: LLM 역할 및 핵심 규칙 설정
- 사용자 프롬프트: 강의 컨텍스트 + 쿼리 + 출력 형식 지정
"""

from langchain_core.prompts import ChatPromptTemplate

# 시스템 프롬프트: LLM의 역할 및 출력 규칙 정의
_SYSTEM_PROMPT = """당신은 KDT 백엔드 부트캠프 강의 내용을 분석하여
학습자에게 최적화된 학습 가이드를 작성하는 교육 콘텐츠 전문가입니다.

## 핵심 규칙
- 반드시 제공된 강의 내용(컨텍스트)에 근거하여 작성하세요.
- 강의에 없는 내용을 임의로 추가하지 마세요.
- 모든 출력 내용은 한국어로 작성하세요.
- 아래 지정된 6개 섹션 형식을 정확히 따르세요.
- 각 섹션은 명확하고 간결하게 작성하세요."""

# 출력 형식: 6개 섹션 학습 가이드 구조 (spec 요구사항 준수)
_GUIDE_OUTPUT_FORMAT = """
---
## 학습 가이드

### 1. 핵심 개념 (Key Concepts)
강의에서 등장한 중요 개념을 5~8개 목록으로 나열하세요.
- 개념1
- 개념2
- 개념3
(계속...)

### 2. 개념 설명 (Concept Explanations)
위의 각 핵심 개념을 2~3문장으로 간결하게 설명하세요.

**개념명**: 설명...

### 3. 핵심 요약 (Key Summary)
강의 전체 내용을 4~6개의 핵심 포인트로 요약하세요.
- 포인트1
- 포인트2
- 포인트3
(계속...)

### 4. 흔한 오해 (Common Confusions)
학습자들이 자주 혼동하거나 오해하기 쉬운 개념을 나열하세요.
각 항목에 혼동 포인트와 올바른 이해 방향을 함께 제시하세요.
- [오해]: ... / [올바른 이해]: ...

### 5. 복습 문제 (Review Questions)
강의 내용을 복습할 수 있는 단답형 문제 3~5개를 만드세요.
Q1. 문제 내용...
Q2. 문제 내용...
Q3. 문제 내용...

### 6. 실용적 응용 (Practical Applications)
강의에서 다룬 개념들이 실제 백엔드 개발에서 어떻게 활용되는지 예시를 들어 설명하세요.
- 활용 예시1
- 활용 예시2
---"""

# 사용자 프롬프트: 컨텍스트와 쿼리를 삽입하는 템플릿
_USER_PROMPT = """다음은 강의에서 검색된 관련 내용입니다:

=== 강의 내용 시작 ===
{context}
=== 강의 내용 끝 ===

## 학습 주제 또는 키워드
{question}

위 강의 내용을 바탕으로 아래 6개 섹션 형식에 맞게 한국어로 학습 가이드를 작성하세요:
""" + _GUIDE_OUTPUT_FORMAT


def get_study_guide_prompt() -> ChatPromptTemplate:
    """
    학습 가이드 생성용 ChatPromptTemplate 반환.

    context(검색된 강의 내용)와 question(학습 주제)을 입력받아
    6개 섹션으로 구성된 한국어 학습 가이드를 생성하는 프롬프트입니다.

    Returns:
        {context}와 {question} 변수를 포함하는 ChatPromptTemplate 인스턴스
    """
    return ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])
