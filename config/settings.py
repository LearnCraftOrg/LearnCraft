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
CHROMA_DIR = BASE_DIR / ".chroma"
GENERATED_QUIZ_DIR: str = str(DATA_DIR / "logs" / "quizzes")
QUIZ_EVAL_DIR: str = str(DATA_DIR / "logs" / "evaluations")
QUIZ_REPORT_DIR: str = str(DATA_DIR / "logs" / "reports")

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"
LLM_MODEL: str = "gpt-4o-mini"

COLLECTION_NAME: str = "lecture_chunks_refined"
RETRIEVAL_K: int = 8
GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID")
GOOGLE_CREDENTIALS_PATH = BASE_DIR / "config" / "google_credentials.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GOOGLE_CREDENTIALS_PATH)
