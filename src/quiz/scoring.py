"""LLM을 이용한 서술형 답안 평가."""
import json

from config.settings import LLM_MODEL, OPENAI_API_KEY
from src.quiz.prompts import SCORING_SYSTEM_PROMPT

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def evaluate_short_answer(
    question: str,
    correct_answer: str,
    user_answer: str,
    explanation: str,
) -> bool:
    """LLM을 이용해 서술형 답안이 정답인지 평가. 오류 시 False 반환."""
    if not user_answer or not user_answer.strip():
        return False
    user_prompt = (
        f"문제: {question}\n"
        f"모범 답안: {correct_answer}\n"
        f"해설: {explanation}\n"
        f"학생 답안: {user_answer}\n\n"
        '정답 여부를 JSON으로만 응답하세요: {"correct": true} 또는 {"correct": false}'
    )
    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return bool(data.get("correct", False))
    except Exception:
        # 평가 실패 시 양방향 포함 검사로 폴백
        ca = correct_answer.lower().strip()
        ua = user_answer.lower().strip()
        if not ua:
            return False
        return ca in ua or ua in ca
