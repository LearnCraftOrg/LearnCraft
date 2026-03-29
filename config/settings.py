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

DATABASE_URL: str = f"sqlite:///{BASE_DIR}/data/learncraft.db"
SECRET_KEY: str = os.getenv("SECRET_KEY", "learncraft-secret-key-change-in-production")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7일

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"
LLM_MODEL: str = "gpt-4o-mini"
EVAL_MODEL: str = "models/gemini-2.5-flash-lite"

COLLECTION_NAME: str = "lecture_chunks_refined"
RETRIEVAL_K: int = 8
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID")
GOOGLE_CREDENTIALS_PATH = BASE_DIR / "config" / "google_credentials.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GOOGLE_CREDENTIALS_PATH)
