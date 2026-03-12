"""퀴즈 생성용 프롬프트 템플릿."""

QUIZ_SYSTEM_PROMPT = """당신은 KDT 백엔드 부트캠프 강의 복습 퀴즈 출제 전문가입니다.

## 출력 순서 (반드시 준수)
1. <thinking> 태그 안에서 아래 항목을 분석하세요:
   - 강의에서 출제 가능한 핵심 개념 및 기술 용어 목록
   - 각 문항의 출제 의도 (어떤 오개념/혼동 포인트를 짚을 것인지)
   - MCQ 오답 선택지 설계 근거 (왜 그럴듯하게 보이는지)

2. 분석 완료 후, ```json 블록 안에 최종 JSON만 출력하세요.

## MCQ 오답 설계 규칙
- 오답은 같은 강의에서 등장한 다른 개념/용어로 구성
- 학습자가 실제로 혼동하기 쉬운 선택지 (너무 뻔하거나 관계없는 선택지 금지)
- 정답과 유사한 형태이나 핵심 부분이 다른 선택지 포함

## 절대 금지
- 강의 원문에 없는 내용으로 문제 생성 금지
- <thinking> 내용을 JSON에 포함 금지
- ```json 블록 외부에 텍스트 출력 금지
"""

# 두 user prompt가 공유하는 문항 요청 블록
_QUIZ_REQUEST = """## 문항 구성 (반드시 이 분포로 10문항 생성)
| 유형 | 개수 | 형태 예시 |
|------|------|-----------|
| 정의형 (definition)     | 2 | "{용어}란 무엇인가?" |
| 비교형 (comparison)     | 2 | "{A}와 {B}의 차이로 옳은 것은?" |
| 코드이해형 (code)       | 3 | 코드 스니펫 또는 API 동작 이해 |
| 결과예측형 (prediction) | 2 | "다음 코드 실행 결과는?" |
| 개념적용형 (application)| 1 | 실제 상황에 개념 적용 |

- 객관식(multiple_choice): 7문항, 선택지 4개 (A/B/C/D)
- 주관식(short_answer): 3문항

반드시 아래 JSON 구조로만 응답하세요:
```json
{{
  "quizzes": [
    {{
      "type": "multiple_choice",
      "question": "문제 내용",
      "options": {{
        "A": "선택지 A",
        "B": "선택지 B",
        "C": "선택지 C",
        "D": "선택지 D"
      }},
      "answer": "A",
      "explanation": "정답 해설 (강의 원문 근거 포함)"
    }},
    {{
      "type": "short_answer",
      "question": "문제 내용",
      "answer": "정답",
      "explanation": "정답 해설"
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

""" + _QUIZ_REQUEST

QUIZ_MULTI_USER_PROMPT = """아래 강의 내용을 바탕으로 복습 퀴즈를 생성하세요.

## 강의 범위
{curriculum_summary}

{user_query_section}

## 강의 텍스트
{lecture_context}

""" + _QUIZ_REQUEST


# ── Guide Generation (기존 유지) ──────────────────────────────────────────────

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
