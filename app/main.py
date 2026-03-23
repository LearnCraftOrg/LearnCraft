"""LearnCraft - 강의 기반 복습 퀴즈 & 학습 가이드 자동 생성 데모."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging
import re
import time

import streamlit as st

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# openai/_base_client.py calls model_dump(by_alias=None) at DEBUG level,
# which breaks Pydantic 2.7+. Silence noisy third-party loggers.
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="LearnCraft",
    page_icon="📚",
    layout="wide",
)

# 앱 시작 시 미인덱싱 강의 자동 처리
from src.ingestion.loader import get_available_dates, load_script, load_lecture_topics
from src.ingestion.chunker import chunk_text
from src.vectorstore.store import add_documents, get_indexed_dates

available_dates = get_available_dates()
indexed_dates = get_indexed_dates()
unindexed = [d for d in available_dates if d not in indexed_dates]

if unindexed:
    from concurrent.futures import ThreadPoolExecutor

    def _index_date(date: str):
        t0 = time.perf_counter()
        text = load_script(date)
        if text:
            headings = re.findall(r'^## (.+)', text, re.MULTILINE)
            meta = {
                "subject": "",
                "content": load_lecture_topics(date),
                "learning_goal": " / ".join(headings),
            }
            logger.debug("[TIMING] %s load+meta: %.2fs", date, time.perf_counter()-t0)

            t1 = time.perf_counter()
            docs = chunk_text(text, {"date": date, **meta})
            logger.debug("[TIMING] %s chunk: %.2fs", date, time.perf_counter()-t1)

            t2 = time.perf_counter()
            add_documents(docs)
            logger.debug("[TIMING] %s add_documents: %.2fs", date, time.perf_counter()-t2)

    t_total = time.perf_counter()
    with st.spinner(f"강의 {len(unindexed)}개 자동 인덱싱 중..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(_index_date, unindexed))
    logger.info("[TIMING] 전체 인덱싱: %.2fs", time.perf_counter()-t_total)

st.title("📚 LearnCraft")
st.subheader("강의 내용 기반 복습 퀴즈 & 학습 가이드 자동 생성")

st.markdown("""
LearnCraft는 강의 스크립트(STT)를 RAG 파이프라인으로 분석하여
**복습 퀴즈**와 **학습 가이드**를 자동으로 생성합니다.

---

### 사용 방법

| 단계 | 페이지 | 설명 |
|------|--------|------|
| 1️⃣ | **퀴즈 풀기** | 강의를 선택하고 퀴즈 생성 후 학습 |
| 2️⃣ | **학습 가이드** | 핵심 개념 요약 및 복습 포인트 확인 |
| 3️⃣ | **품질 평가** | 생성된 퀴즈의 자동 평가 리포트 확인 |

---

왼쪽 사이드바에서 페이지를 선택하세요.
""")

from config.settings import OPENAI_API_KEY
if not OPENAI_API_KEY:
    st.error("⚠️ OPENAI_API_KEY가 설정되지 않았습니다. 프로젝트 루트에 `.env` 파일을 생성하세요.")
    st.code("OPENAI_API_KEY=sk-...")
else:
    st.success("✅ OpenAI API 키 확인됨")
