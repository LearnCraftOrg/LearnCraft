import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SCRIPTS_DIR = DATA_DIR / "강의 스크립트"
CLEAN_DIR = DATA_DIR / "clean"
CURRICULUM_PATH = DATA_DIR / "강의 커리큘럼.csv"
CHROMA_DIR = BASE_DIR / ".chroma"

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"
LLM_MODEL: str = "gpt-4o-mini"

COLLECTION_NAME: str = "lecture_chunks"
CHUNK_SIZE: int = 500
CHUNK_OVERLAP: int = 50
RETRIEVAL_K: int = 8
