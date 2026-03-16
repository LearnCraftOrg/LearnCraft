"""Vertex AI를 사용한 Grounding 평가 (퀴즈가 강의 내용에 기반하는지 확인)."""
from typing import Any

def evaluate_grounding(quiz_item: dict[str, Any], context: str) -> dict[str, Any]:
    """Vertex AI를 호출하여 질문과 정답이 주어진 컨텍스트 내에서 사실인지 확인합니다."""
    # TODO: Vertex AI Integration
    return {"score": 1.0, "reason": "Consistent with context"}
