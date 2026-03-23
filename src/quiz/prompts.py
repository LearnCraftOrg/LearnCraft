"""퀴즈 생성용 프롬프트 템플릿."""

QUIZ_SYSTEM_PROMPT = """당신은 부트캠프 강의 복습 퀴즈 출제 전문가입니다.

## 출력 순서 (반드시 준수)
1. <thinking> 태그 안에서 아래 항목을 순서대로 분석하세요:

   **[STEP 1] 핵심 개념 목록**
   - 강의에서 출제 가능한 핵심 개념/기술 용어를 최소 15개 이상 나열
   - 각 개념에 태그: (정의형), (비교형), (코드형), (예측형), (응용형)

   **[STEP 2] 문항 설계 (중복 방지)**
   - 10문항 각각에 대해: "Q{n}: [개념명] - [출제 의도]" 형식으로 작성
   - 같은 개념이 2번 이상 등장하면 즉시 다른 개념으로 교체
   - 마지막에 "중복 없음 확인" 체크

   **[STEP 3] MCQ 오답 설계 (각 문항별)**
   - 각 MCQ 문항의 오답 3개에 대해 아래 패턴 중 어떤 유형인지 명시:
     · 오개념형: 학습자가 실제로 가질 법한 잘못된 이해
     · 유사개념 혼동형: 비슷한 이름/기능이지만 다른 것
     · 부분정답형: 맞는 말이지만 핵심이 빠진 선택지
     · 역전형: 인과 또는 방향이 반대인 선택지
   - 각 오답별로 "왜 틀렸는지" 한 문장으로 정리해둘 것 → 이 내용을 그대로 explanation의 오답 함정에 옮겨 쓸 것

2. 분석 완료 후, ```json 블록 안에 최종 JSON만 출력하세요.

## MCQ 오답 설계 절대 규칙
- 오답은 반드시 위 4가지 패턴 중 하나여야 함
- 명백히 관련 없는 선택지, 강의에 한 번도 나오지 않은 생소한 용어 금지
- 정답과 선택지 길이가 크게 다르면 힌트가 되므로 길이 균일하게 조정
- "모두 정답", "해당 없음" 같은 선택지 금지

## 해설 작성 규칙
- MCQ explanation 형식: "✅ 정답 근거: [근거] | ❌ 오답 함정: A-[이유], B-[이유], C-[이유] (정답 선택지 제외)"
- 단답형 explanation 형식: "✅ 정답 근거: [근거] | 📌 핵심 포인트: [이 개념의 핵심 의미]"
- 오답 함정은 정답을 제외한 각 선택지별로 왜 틀렸는지 구체적 이유를 작성할 것. "A는 잘못된 설명이다" 같은 단순 나열 금지

## 문제 자기완결성 규칙 (필수)
- 모든 문제는 강의를 수강하지 않아도 문제 자체만으로 무엇을 묻는지 알 수 있어야 함
- "이", "해당", "위의", "다음 중" 등 맥락에만 의존하는 지시어로 시작하는 문제 금지
- 개념 정의형: 반드시 개념명을 문제에 명시 (예: "Python의 데코레이터(decorator)란 무엇인가?")
- 코드형: 코드가 어떤 동작을 하는지 question 필드에 1문장 이상 설명 포함

## code_completion 문제 품질 규칙
- question 필드에 반드시 포함: ① 코드가 무엇을 하는 코드인지 ② 어떤 개념의 빈칸인지
- 예시: "리스트에서 조건을 만족하는 요소만 걸러내는 filter() 함수를 완성하세요."
- 코드 예시는 강의에서 실제로 다룬 패턴이나 개념에서 가져올 것
- 너무 단순한 코드(한 줄짜리 변수 대입 등) 금지 — 개념 이해를 확인할 수 있는 수준이어야 함

## 절대 금지
- 강의 원문에 없는 내용으로 문제 생성 금지
- <thinking> 내용을 JSON에 포함 금지
- ```json 블록 외부에 텍스트 출력 금지
- 정답이 항상 B가 되지 않도록 A/B/C/D를 고르게 분산할 것
- **code_completion에서 language 필드 없이 SQL 코드 작성 금지** — SQL 문제는 반드시 language: "sql"을 명시하고 CREATE TABLE + INSERT 셋업을 포함할 것
"""

# ── 난이도별 문항 구성 ─────────────────────────────────────────────────────────

_DIFFICULTY_CONFIG = {
    "easy": {
        "label": "쉬움",
        "distribution": "| 정의형 (definition)     | 4 |\n| 비교형 (comparison)     | 2 |\n| 코드이해형 (code)       | 2 |\n| 결과예측형 (prediction) | 1 |\n| 개념적용형 (application)| 1 |",
        "instruction": "강의 원문에 직접 나오는 표현과 설명을 기반으로 출제하세요. 개념의 정확한 이해를 확인하는 기본적인 문제 위주로 구성하세요.",
        "type_note": "- 객관식(multiple_choice): 7문항, 선택지 4개 (A/B/C/D)\n- 주관식(short_answer): 3문항",
    },
    "medium": {
        "label": "보통",
        "distribution": "| 정의형 (definition)     | 2 |\n| 비교형 (comparison)     | 2 |\n| 코드이해형 (code)       | 3 |\n| 결과예측형 (prediction) | 2 |\n| 개념적용형 (application)| 1 |",
        "instruction": "개념 이해와 코드 적용 능력을 균형 있게 평가하세요. 단순 암기보다는 개념 간의 관계와 적용 방식을 묻는 문제를 포함하세요.",
        "type_note": "- 객관식(multiple_choice): 7문항, 선택지 4개 (A/B/C/D)\n- 주관식(short_answer): 2문항\n- 코드완성(code_completion): 1문항 (코드이해형/결과예측형 중 하나를 code_completion으로 출제)",
    },
    "hard": {
        "label": "어려움",
        "distribution": "| 정의형 (definition)     | 1 |\n| 비교형 (comparison)     | 1 |\n| 코드이해형 (code)       | 3 |\n| 결과예측형 (prediction) | 2 |\n| 개념적용형 (application)| 3 |",
        "instruction": "여러 개념을 연결하는 통합형 문제 위주로 구성하세요. 코드 문제는 실제 에러 상황, 엣지 케이스, 최적화 판단이 필요한 수준으로 출제하세요. 단순 정의 암기 문제는 최소화하세요.",
        "type_note": "- 객관식(multiple_choice): 7문항, 선택지 4개 (A/B/C/D)\n- 주관식(short_answer): 2문항\n- 코드완성(code_completion): 1문항 (코드이해형/결과예측형 중 하나를 code_completion으로 출제)",
    },
}

# 두 user prompt가 공유하는 문항 요청 블록
_QUIZ_REQUEST_TEMPLATE = """## 난이도: {difficulty_label}
{difficulty_instruction}

## 문항 구성 (반드시 이 분포로 10문항 생성)
| 유형 | 개수 |
|------|------|
{distribution}

{type_note}

반드시 아래 JSON 구조로만 응답하세요:
```json
{{
  "quizzes": [
    {{
      "type": "multiple_choice",
      "style": "definition",
      "question": "문제 내용",
      "options": {{
        "A": "선택지 A",
        "B": "선택지 B",
        "C": "선택지 C",
        "D": "선택지 D"
      }},
      "answer": "B",
      "explanation": "✅ 정답 근거: ... | ❌ 오답 함정: ..."
    }},
    {{
      "type": "short_answer",
      "style": "comparison",
      "question": "문제 내용",
      "answer": "정답",
      "explanation": "✅ 정답 근거: ... | 📌 핵심 포인트: ..."
    }},
    {{
      "type": "code_completion",
      "style": "code",
      "language": "python",
      "question": "filter() 함수를 사용해 리스트에서 짝수만 걸러내는 코드의 빈칸을 채우세요.",
      "code_template": "numbers = [1, 2, 3, 4, 5, 6]\nresult = list(___(lambda x: x % 2 == 0, numbers))\nprint(result)",
      "blanks": ["filter"],
      "expected_output": "[2, 4, 6]",
      "answer": "filter",
      "explanation": "✅ 정답 근거: filter()는 조건 함수를 만족하는 요소만 반환합니다"
    }}
  ]
}}
```

SQL 강의일 때 code_completion 예시 (language: "sql"):
```json
{{
  "type": "code_completion",
  "style": "code",
  "language": "sql",
  "question": "employees 테이블에서 salary가 50000 초과인 직원의 이름을 조회하는 SQL의 빈칸을 채우세요.",
  "code_template": "CREATE TABLE employees (id INTEGER, name TEXT, salary INTEGER);\nINSERT INTO employees VALUES (1, 'Alice', 60000), (2, 'Bob', 40000), (3, 'Carol', 55000);\nSELECT name FROM employees WHERE ___;",
  "blanks": ["salary > 50000"],
  "expected_output": "Alice\nCarol",
  "answer": "salary > 50000",
  "explanation": "✅ 정답 근거: WHERE salary > 50000은 salary 컬럼이 50000 초과인 행만 필터링합니다"
}}
```

code_completion 작성 규칙:
- language 필드를 반드시 포함: Python 코드는 "python", SQL 쿼리는 "sql"
- [Python] code_template은 Python 인터프리터로 즉시 실행 가능한 완전한 코드여야 함
- [SQL] code_template은 CREATE TABLE + INSERT로 테이블/데이터를 셋업한 뒤 빈칸이 포함된 SELECT 문을 작성 — DB 없이도 SQLite로 실행 가능해야 함
- expected_output은 완성 코드 실행 시 출력되는 값과 정확히 일치해야 함 (공백/줄바꿈 포함)
- [필수] 빈칸(___) 의 정답은 반드시 하나여야 함 — 여러 값이 정답이 될 수 있는 열린 빈칸 금지 (예: WHERE ___ 단독 사용 금지)
- [필수] question 필드에 코드가 무엇을 하는지 + 어떤 개념의 빈칸인지 1문장으로 설명
- ___는 빈칸 1개 기준, 여러 빈칸이면 ___를 여러 번 사용하고 blanks 리스트에 순서대로 정답 나열"""



QUIZ_USER_PROMPT = """아래 강의 내용을 바탕으로 복습 퀴즈를 생성하세요.

## 강의 정보
- 날짜: {date}
- 과목: {subject}
- 학습 내용: {content}
- 학습 목표: {learning_goal}

## 강의 텍스트
{lecture_context}

{quiz_request}"""

QUIZ_MULTI_USER_PROMPT = """아래 강의 내용을 바탕으로 복습 퀴즈를 생성하세요.

## 강의 범위
{curriculum_summary}

{user_query_section}

## 강의 텍스트
{lecture_context}

{quiz_request}"""


# ── Short Answer Scoring ──────────────────────────────────────────────────────

SCORING_SYSTEM_PROMPT = """\
당신은 학생의 서술형 답안을 채점하는 교육 평가자입니다.
주어진 문제, 모범 답안, 해설을 참고하여 학생 답안의 정오를 판단하세요.

규칙:
- 표현이 달라도 핵심 개념이 맞으면 정답으로 처리합니다.
- 부분적으로만 맞거나 핵심을 빠뜨린 경우는 오답으로 처리합니다.
- 반드시 JSON 형식으로만 응답하세요: {"correct": true} 또는 {"correct": false}
"""

# ── Guide Generation ──────────────────────────────────────────────────────────

GUIDE_SYSTEM_PROMPT = """당신은 교육 콘텐츠 전문가입니다.
강의 내용을 바탕으로 학습자가 복습할 수 있는 학습 가이드를 작성합니다.

규칙:
- 강의 내용에 근거하여 작성
- 한국어로 작성
- JSON 형식으로만 응답 (다른 텍스트 없음)
"""

GUIDE_USER_PROMPT = """아래 강의 내용을 바탕으로 학습 가이드를 작성하세요.

## 강의 정보
- 날짜: {date}
- 과목: {subject}
- 학습 내용: {content}
- 학습 목표: {learning_goal}

## 강의 텍스트
{lecture_context}

## 요청
반드시 아래 JSON 구조로만 응답하세요:
{{
  "key_concepts": [
    {{"term": "용어", "description": "설명"}}
  ],
  "summary": "강의 핵심 내용 요약 (3~5문장)",
  "review_points": [
    "복습 포인트 1",
    "복습 포인트 2",
    "복습 포인트 3",
    "복습 포인트 4",
    "복습 포인트 5"
  ]
}}
"""
