"""OpenAI 임베딩 모델 래퍼."""
from functools import lru_cache
from langchain_openai import OpenAIEmbeddings
from config.settings import EMBEDDING_MODEL, OPENAI_API_KEY


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
    )
