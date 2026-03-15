import os
import sys
from google.cloud import discoveryengine_v1beta as discoveryengine

# 프로젝트 루트 경로 추가 및 환경변수 설정
sys.path.append(os.getcwd())
from config.settings import GCP_PROJECT_ID, GOOGLE_CREDENTIALS_PATH

if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GOOGLE_CREDENTIALS_PATH)

print("Project ID:", GCP_PROJECT_ID)
print("Credentials Path:", os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

# 클라이언트 생성
client = discoveryengine.GroundedGenerationServiceClient()

# 테스트 호출 (간단한 연결 확인용)
location = "us-central1"
grounding_config = f"projects/{GCP_PROJECT_ID}/locations/{location}/groundingConfigs/default_grounding_config"

request = discoveryengine.CheckGroundingRequest(
    grounding_config=grounding_config,
    answer_candidate="ByteBuffer.flip()은 쓰기 모드에서 읽기 모드로 전환한다",
    facts=[
        discoveryengine.GroundingFact(
            fact_text="ByteBuffer의 flip() 메서드는 버퍼를 쓰기 모드에서 읽기 모드로 전환한다. position을 0으로 리셋하고 limit을 이전 position으로 설정한다.",
        )
    ],
)

try:
    print("\nVerifying connection to Vertex AI Check Grounding...")
    response = client.check_grounding(request=request)
    print("✅ Connection Successful!")
    print("Support Score:", response.support_score)
except Exception as e:
    print("❌ Connection Failed:", e)