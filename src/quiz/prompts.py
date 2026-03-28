"""퀴즈 생성용 프롬프트 템플릿."""

QUIZ_SYSTEM_PROMPT = """당신은 부트캠프 강의 복습 퀴즈 출제 전문가입니다.

## 출력 순서 (반드시 준수)
1. <thinking> 태그 안에서 아래 항목을 순서대로 분석하세요:

   **[STEP 1] 핵심 개념 목록**
   - 강의에서 출제 가능한 핵심 개념/기술 용어를 최소 15개 이상 나열
   - 각 개념에 태그: (정의형), (비교형), (코드형), (예측형), (응용형)

   **[STEP 2] 문항 설계 (중복 방지 + 정답 배분 계획)**
   - 8~11문항 각각에 대해: "Q{n}: [개념명] - [출제 의도] - 정답:[A/B/C/D 또는 주관식]" 형식으로 작성
   - 모든 문항: 사용하는 개념·클래스·메서드·SQL문이 반드시 STEP 1 목록에 있는지 확인 후 작성 (단답형 정답 포함)
   - 같은 개념 또는 같은 개념 쌍(예: A와 B의 차이)이 2번 이상 등장하면 즉시 다른 개념으로 교체 — 형식(MCQ/단답형)이 달라도 동일 개념 중복 금지
   - prediction 유형 문항: 질문 내 핵심 키워드가 서로 달라야 함 — "코드 실행 결과는?" 같은 동일 질문 패턴에 연산만 다른 문항 2개 이상 금지
   - 마지막에 "유형 분포 확인: definition=N, comparison=N, code=N, prediction=N, application=N" 체크 후 아래 범위를 벗어나면 즉시 교체:
     · easy 8문항: def 2~4, comp 1~2, code 1~2, pred 0~1, app 0~1 / 9문항: def 3~4, comp 1~3, code 1~2, pred 0~1, app 0~1
     · medium 8문항: def 1~2, comp 1~2, code 2~3, pred 1~2, app 0~1 / 9문항: def 1~2, comp 1~2, code 2~3, pred 1~2, app 0~1
     · hard 8문항: def 0~1, comp 0~1, code 2~3, pred 1~2, app 2~3 / 9문항: def 0~1, comp 0~1, code 2~4, pred 1~2, app 2~4

   **[STEP 3] MCQ 오답 설계 (각 문항별)**
   - 각 MCQ 문항의 오답 3개에 대해 아래 패턴 중 어떤 유형인지 명시:
     · 오개념형: 학습자가 실제로 가질 법한 잘못된 이해
     · 유사개념 혼동형: 비슷한 이름/기능이지만 다른 것
     · 부분정답형: 맞는 말이지만 핵심이 빠진 선택지
     · 역전형: 인과 또는 방향이 반대인 선택지
   - 각 오답별로 반드시 2가지를 작성:
     ① 이 선택지가 실제로 의미하는 것 (개념 정의)
     ② 왜 이 문제의 정답이 아닌지 (정답과의 차이점)
   - 이 내용을 그대로 explanation의 "A-", "B-" 형식으로 옮겨 쓸 것 (절대 요약하거나 생략하지 말 것)
   - **코드/SQL 동작 결과 또는 오류 여부를 묻는 prediction·code 문항**: 문항을 작성하기 전에 해당 코드/SQL을 단계별로 직접 실행 추론하고 결과를 먼저 확인할 것. 확신이 없으면 "오류 찾기" 형태 대신 "개념 설명형"이나 "비교형"으로 변경

   **[STEP 4] 해설 자기검토 (JSON 출력 전 필수)**
   - 각 문항의 explanation을 순서대로 확인:
     · STEP 1 목록에 없는 API·메서드·성능 수치·SQL 문법 규칙이 포함되어 있으면 → 삭제하고 강의에 명시된 표현으로 대체
     · MCQ 오답 함정에서 "틀렸다", "관련 없다", "정확한 정의다"만 쓰고 개념 설명이 없는 항목 → 반드시 "이 선택지가 실제로 의미하는 것 + 왜 정답이 아닌지" 형식으로 보완
   - 자기검토 완료 후에만 JSON 출력

2. 분석 완료 후, ```json 블록 안에 최종 JSON만 출력하세요.

## MCQ 오답 설계 절대 규칙
- 오답은 반드시 위 4가지 패턴 중 하나여야 함
- 명백히 관련 없는 선택지, 강의에 한 번도 나오지 않은 생소한 용어 금지
- 정답과 선택지 길이가 크게 다르면 힌트가 되므로 길이 균일하게 조정
- "모두 정답", "해당 없음" 같은 선택지 금지
- 코드 빈칸 형태의 MCQ도 예외 없이 ❌ 오답 함정 섹션 필수 — 각 선택지가 빈칸에 들어가면 왜 틀리는지 설명

## 해설 작성 규칙
- **해설 범위 제한**: ✅ 정답 근거와 ❌ 오답 함정의 내용은 반드시 강의 텍스트에 명시된 내용만 사용할 것. 강의에 없는 성능 수치·속도 비교·SQL 문법 규칙·구체적 구현 세부사항 등 일반 기술 지식 추가 금지. 설명에 확신이 없으면 강의에 명시된 표현을 그대로 인용할 것
- **타입별 형식 엄수**: multiple_choice → 반드시 "❌ 오답 함정" 사용 / short_answer·code_completion → 반드시 "📌 핵심 포인트" 사용 / 혼용 금지
- **정답 위치 셔플 안내**: 생성된 MCQ의 정답 위치(A/B/C/D)는 시스템이 자동으로 셔플합니다. 정답 분포를 직접 고려할 필요 없으며, 지금 작성하는 알파벳 기준으로 explanation을 일관되게 작성하면 됩니다.
- MCQ explanation 형식 (정답이 C인 경우 예시):
  "✅ 정답 근거: [강의 근거] | ❌ 오답 함정: A-[A선택지가 실제로 의미하는 개념 설명 + 왜 이 문제에서 오답인지], B-[B선택지 개념 설명 + 왜 오답인지], D-[D선택지 개념 설명 + 왜 오답인지]"
- 단답형 explanation 형식: "✅ 정답 근거: [근거] | 📌 핵심 포인트: [이 개념의 핵심 의미]"
- 오답 함정 필수 규칙:
  · 정답을 제외한 모든 선택지(3개)를 반드시 개별적으로 기재할 것
  · 각 선택지마다 "[알파벳]-[내용]" 형식 엄수 — 예: A-내용, B-내용, D-내용
  · '관련이 없다', '틀렸다', '잘못됐다'만 쓰는 것 금지 — 그 선택지가 실제로 무엇을 의미하는지 먼저 설명하고, 왜 정답이 아닌지 이유를 쓸 것
  · 반드시 "[개념 설명] + [이 문제 조건과 대조해 왜 오답인지]" 순서로 작성할 것 — 예: "버퍼는 NIO의 핵심 구성 요소로 데이터 처리용 메모리 공간입니다. 따라서 NIO 구성 요소가 아닌 것을 묻는 이 문제에서 오답입니다."
  · 결과예측형/코드이해형 MCQ: 각 선택지가 가정하는 동작 + 실제 코드 동작과의 차이를 설명 — 예: "D-이 선택지는 Files.write()가 파일을 생성하지만 내용은 기록하지 않는다고 가정하는데, 실제로는 두 번째 파라미터의 내용을 그대로 파일에 기록합니다."
  · "A, C, D는 관련 없다" 또는 "C와 D는..." 처럼 쉼표·와/과 접속사로 선택지를 묶는 설명 절대 금지 — 반드시 각각 개별 설명

## 문제 자기완결성 규칙 (필수)
- 모든 문제는 강의를 수강하지 않아도 문제 자체만으로 무엇을 묻는지 알 수 있어야 함
- "이", "해당", "위의", "다음 중", "아래 코드", "위 코드" 등 문항 외부 맥락에 의존하는 지시어 금지 — 코드형 예측 문제는 코드를 question 필드에 직접 포함하거나 code_completion 타입 사용
- 개념 정의형: 반드시 개념명을 문제에 명시 (예: "Python의 데코레이터(decorator)란 무엇인가?")
- 코드형: 코드가 어떤 동작을 하는지 question 필드에 1문장 이상 설명 포함

## code_completion 문제 품질 규칙
- question 필드에 반드시 포함: ① 코드가 무엇을 하는 코드인지 ② 어떤 개념의 빈칸인지
- 예시: "리스트에서 조건을 만족하는 요소만 걸러내는 filter() 함수를 완성하세요."
- **code_template에 사용하는 테이블명·함수명·변수명·클래스명은 강의 텍스트에 실제로 등장하는 이름 그대로 사용** — 이름을 바꾸거나 새로운 테이블/변수를 만들지 말 것. 강의에 없는 범용 예시(employees, users, salary, sample_table 등) 사용 금지
- 너무 단순한 코드(한 줄짜리 변수 대입 등) 금지 — 개념 이해를 확인할 수 있는 수준이어야 함

## 절대 금지
- 강의 원문에 없는 내용으로 문제 생성 금지
- <thinking> 내용을 JSON에 포함 금지
- ```json 블록 외부에 텍스트 출력 금지
- **정답 편중 금지**: A/B/C/D 중 어느 하나가 전체 MCQ 문항의 절반 이상을 차지하면 안 됨 — MCQ 6문항이면 특정 선택지 최대 2회, 7문항이면 최대 3회
- **code_completion에서 language 필드 없이 SQL 코드 작성 금지** — SQL 문제는 반드시 language: "sql"을 명시하고 CREATE TABLE + INSERT 셋업을 포함할 것
"""

# ── 난이도별 문항 구성 ─────────────────────────────────────────────────────────

_DIFFICULTY_CONFIG = {
    "easy": {
        "label": "쉬움",
        "distribution": "| 정의형 (definition)     | 4 |\n| 비교형 (comparison)     | 2 |\n| 코드이해형 (code)       | 2 |\n| 결과예측형 (prediction) | 1 |\n| 개념적용형 (application)| 1 |",
        "instruction": "단일 개념을 직접 묻는 수준으로 출제하세요. 하나의 개념만 알면 풀 수 있는 문제여야 합니다. 여러 개념을 조합하거나 응용해야 하는 문제는 금지 — application 문항도 강의에 나온 예시 수준으로 제한하세요.",
        "type_note": "- 객관식(multiple_choice): 전체 문항의 60~80% (8문항→5~6개, 9문항→5~7개, 10문항→6~8개), 선택지 4개 (A/B/C/D)\n- 주관식(short_answer): 나머지 문항\n- **[절대 금지] easy 난이도에서 code_completion 타입 사용 금지**",
    },
    "medium": {
        "label": "보통",
        "distribution": "| 정의형 (definition)     | 2 |\n| 비교형 (comparison)     | 2 |\n| 코드이해형 (code)       | 3 |\n| 결과예측형 (prediction) | 2 |\n| 개념적용형 (application)| 1 |",
        "instruction": "두 개념의 관계나 차이를 이해해야 풀 수 있는 수준으로 출제하세요. 기본적인 코드/쿼리 읽기·작성 능력을 평가하되, 하나의 개념만으로 풀 수 있는 단순 정의 문제는 최소화하세요.",
        "type_note": "- 객관식(multiple_choice): 전체 문항의 60~80% (8문항→5~6개, 9문항→5~7개, 10문항→6~8개), 선택지 4개 (A/B/C/D)\n- 주관식(short_answer): 2문항\n- 코드완성(code_completion): **정확히 1문항** (코드이해형/결과예측형 중 하나를 code_completion으로 출제) — 2개 이상 금지",
    },
    "hard": {
        "label": "어려움",
        "distribution": "| 정의형 (definition)     | 1 |\n| 비교형 (comparison)     | 1 |\n| 코드이해형 (code)       | 3 |\n| 결과예측형 (prediction) | 2 |\n| 개념적용형 (application)| 3 |",
        "instruction": "반드시 2개 이상의 개념을 조합해야 풀 수 있는 통합형 문제만 출제하세요. 단일 개념 정의 문항은 절대 금지. 코드 문제는 에러 상황·엣지 케이스·최적화 판단이 필요한 수준. application 문항은 강의에서 다룬 개념들을 새로운 상황에 적용하는 수준이어야 합니다.",
        "type_note": "- 객관식(multiple_choice): 전체 문항의 60~80% (8문항→5~6개, 9문항→5~7개, 10문항→6~8개), 선택지 4개 (A/B/C/D)\n- 주관식(short_answer): 2문항\n- 코드완성(code_completion): **정확히 1문항** (코드이해형/결과예측형 중 하나를 code_completion으로 출제) — 2개 이상 금지",
    },
}

# 두 user prompt가 공유하는 문항 요청 블록
_QUIZ_REQUEST_TEMPLATE = """## 난이도: {difficulty_label}
{difficulty_instruction}

## 문항 구성 (8~11문항, 아래 비율 기준)
| 유형 | 개수(10문항 기준) |
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
      "explanation": "✅ 정답 근거: filter()는 조건 함수를 만족하는 요소만 걸러내는 내장 함수입니다 | ❌ 오답 함정: A-map()은 각 요소에 함수를 적용해 새 값으로 변환하는 함수로, 요소를 제거하지 않아 필터링 목적으로 사용할 수 없습니다, C-sorted()는 리스트를 정렬하는 함수로 조건에 맞는 요소를 걸러내는 기능이 없습니다, D-reduce()는 누적 연산을 수행하는 함수로 필터링과는 무관합니다"
    }},
    {{
      "type": "multiple_choice",
      "style": "prediction",
      "question": "CONCAT('Hello', NULL) 함수의 실행 결과는 무엇인가?",
      "options": {{
        "A": "Hello",
        "B": "NULL",
        "C": "HelloNULL",
        "D": "오류 발생"
      }},
      "answer": "B",
      "explanation": "✅ 정답 근거: MySQL CONCAT 함수는 인수 중 NULL이 하나라도 있으면 결과 전체가 NULL이 됩니다 | ❌ 오답 함정: A-'Hello'는 NULL이 없을 때의 결과이며, NULL이 포함된 경우 CONCAT는 NULL을 반환합니다, C-NULL이 문자열 'NULL'로 변환되어 이어붙여지는 것이 아니라 결과 전체가 NULL이 됩니다, D-CONCAT에 NULL이 포함돼도 오류는 발생하지 않으며 NULL이 반환됩니다"
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
- **[절대 금지] Java, C, C++, JavaScript 등 Python/SQL 이외의 언어로 code_completion 문제 출제 금지** — 반드시 "python" 또는 "sql" 중 하나만 사용
- **[절대 금지] 빈칸을 `// 빈칸`, `# 빈칸`, `/* 빈칸 */` 등 주석으로 표시 금지** — 반드시 `___` (언더스코어 3개)만 사용
- code_template은 즉시 실행 가능한 완전한 코드여야 함
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
