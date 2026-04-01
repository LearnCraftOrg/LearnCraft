import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SCRIPTS_DIR = DATA_DIR / "강의 스크립트"
CLEAN_DIR = DATA_DIR / "clean"
REFINED_DIR = DATA_DIR / "refined"
CURRICULUM_PATH = DATA_DIR / "강의 커리큘럼.csv"
TOPICS_PATH = DATA_DIR / "topics.json"
CHROMA_DIR = DATA_DIR / ".chroma"
GENERATED_QUIZ_DIR: str = str(DATA_DIR / "logs" / "quizzes")
QUIZ_EVAL_DIR: str = str(DATA_DIR / "logs" / "evaluations")
QUIZ_REPORT_DIR: str = str(DATA_DIR / "logs" / "reports")

# ── 서버 ─────────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# CORS 허용 출처 — 쉼표로 구분된 문자열을 리스트로 변환
# 예: CORS_ORIGINS=http://localhost:3000,https://myapp.com
CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

# ── 데이터베이스 ──────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/data/learncraft.db")
GUEST_EMAIL: str = os.getenv("GUEST_EMAIL", "guest@learncraft.local")

# ── 인증 ─────────────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("SECRET_KEY", "learncraft-secret-key-change-in-production")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))

# ── LLM / 임베딩 ──────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
EVAL_MODEL: str = os.getenv("EVAL_MODEL", "models/gemini-2.5-flash-lite")

# ── 벡터스토어 ────────────────────────────────────────────────────────────────
COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "lecture_chunks_refined")
RETRIEVAL_K: int = int(os.getenv("RETRIEVAL_K", "8"))

# ── 퀴즈 ─────────────────────────────────────────────────────────────────────
QUIZ_COUNT: int = int(os.getenv("QUIZ_COUNT", "10"))

# ── GCP ───────────────────────────────────────────────────────────────────────
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID")
GOOGLE_CREDENTIALS_PATH = BASE_DIR / "config" / "google_credentials.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GOOGLE_CREDENTIALS_PATH)
