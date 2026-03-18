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

2. 분석 완료 후, ```json 블록 안에 최종 JSON만 출력하세요.

## MCQ 오답 설계 절대 규칙
- 오답은 반드시 위 4가지 패턴 중 하나여야 함
- 명백히 관련 없는 선택지, 강의에 한 번도 나오지 않은 생소한 용어 금지
- 정답과 선택지 길이가 크게 다르면 힌트가 되므로 길이 균일하게 조정
- "모두 정답", "해당 없음" 같은 선택지 금지

## 해설 작성 규칙
- MCQ explanation 형식: "✅ 정답 근거: [강의 원문 근거] | ❌ 오답 함정: [각 오답이 매력적인 이유]"
- 단답형 explanation 형식: "✅ 정답 근거: [강의 원문 근거] | 📌 핵심 포인트: [이 개념의 핵심 의미]"
- 강의 원문에 있는 표현 또는 코드를 인용해서 설명

## 절대 금지
- 강의 원문에 없는 내용으로 문제 생성 금지
- <thinking> 내용을 JSON에 포함 금지
- ```json 블록 외부에 텍스트 출력 금지
- source_indices는 참고한 강의 텍스트의 [Source N]에서 N 숫자 목록이다.
  예) Source 1만 참고했으면 [1], Source 1과 3을 참고했으면 [1, 3]
- 문항의 내용(질문, 정답, 해설)은 반드시 해당 source_indices에 명시된 텍스트만으로 구성해야 함. 다른 청크에 있는 정보나 상식으로 내용을 보충하지 마세요. 이는 Grounding 평가의 핵심 기준입니다.
- 정답이 항상 B가 되지 않도록 A/B/C/D를 고르게 분산할 것
"""

# ── 난이도별 문항 구성 ─────────────────────────────────────────────────────────

_DIFFICULTY_CONFIG = {
    "easy": {
        "label": "쉬움",
        "distribution": "| 정의형 (definition)     | 4 |\n| 비교형 (comparison)     | 2 |\n| 코드이해형 (code)       | 2 |\n| 결과예측형 (prediction) | 1 |\n| 개념적용형 (application)| 1 |",
        "instruction": "강의 원문에 직접 나오는 표현과 설명을 기반으로 출제하세요. 개념의 정확한 이해를 확인하는 기본적인 문제 위주로 구성하세요.",
    },
    "medium": {
        "label": "보통",
        "distribution": "| 정의형 (definition)     | 2 |\n| 비교형 (comparison)     | 2 |\n| 코드이해형 (code)       | 3 |\n| 결과예측형 (prediction) | 2 |\n| 개념적용형 (application)| 1 |",
        "instruction": "개념 이해와 코드 적용 능력을 균형 있게 평가하세요. 단순 암기보다는 개념 간의 관계와 적용 방식을 묻는 문제를 포함하세요.",
    },
    "hard": {
        "label": "어려움",
        "distribution": "| 정의형 (definition)     | 1 |\n| 비교형 (comparison)     | 1 |\n| 코드이해형 (code)       | 3 |\n| 결과예측형 (prediction) | 2 |\n| 개념적용형 (application)| 3 |",
        "instruction": "여러 개념을 연결하는 통합형 문제 위주로 구성하세요. 코드 문제는 실제 에러 상황, 엣지 케이스, 최적화 판단이 필요한 수준으로 출제하세요. 단순 정의 암기 문제는 최소화하세요.",
    },
}

# 두 user prompt가 공유하는 문항 요청 블록
_QUIZ_REQUEST_TEMPLATE = """## 난이도: {difficulty_label}
{difficulty_instruction}

## 문항 구성 (반드시 이 분포로 10문항 생성)
| 유형 | 개수 |
|------|------|
{distribution}

- 객관식(multiple_choice): 7문항, 선택지 4개 (A/B/C/D)
- 주관식(short_answer): 3문항

반드시 아래 JSON 구조로만 응답하세요:
```json
{{
  "quizzes": [
    {{
      "type": "multiple_choice",
      "style": "definition",
      "source_indices": [int, int, int],
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
      "source_indices": [int, int], 
      "question": "문제 내용",
      "answer": "정답",
      "explanation": "✅ 정답 근거: ... | 📌 핵심 포인트: ..."
    }}
  ]
}}
```"""



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
