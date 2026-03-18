"""Vertex AI Check Grounding API를 사용한 퀴즈 품질 검증 (Discovery Engine v1beta)."""
import os
import sys
from typing import List, Dict, Any

# Ensure project root is in path
sys.path.append(os.getcwd())

from google.cloud import discoveryengine_v1beta
from config.settings import GCP_PROJECT_ID, GOOGLE_CREDENTIALS_PATH

# 환경변수 설정 (세팅 파일이 로드되지 않았을 경우를 대비)
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GOOGLE_CREDENTIALS_PATH)

def check_quiz_grounding(
    answer_candidate: str,
    facts: List[str]
) -> Dict[str, Any]:
    """
    퀴즈의 정답/해설(answer_candidate)이 제공된 강의 내용(facts)에 근거하는지 확인.
    
    Returns:
        {
            "support_score": float, (0~1)
            "raw_response": str
        }
    """
    client = discoveryengine_v1beta.GroundedGenerationServiceClient()

    # Standalone Grounding API는 'global' 또는 'us-central1' 사용
    location = "us-central1"
    grounding_config = client.grounding_config_path(
        project=GCP_PROJECT_ID,
        location=location,
        grounding_config="default_grounding_config"
    )

    request = {
        "grounding_config": grounding_config,
        "answer_candidate": answer_candidate,
        "facts": [{"fact_text": fact} for fact in facts]
    }

    try:
        response = client.check_grounding(request=request)
        return {
            "support_score": response.support_score,
            "raw_response": str(response)
        }
    except Exception as e:
        print(f"Vertex AI Grounding Check failed: {e}")
        return {"error": str(e), "support_score": 0.0}