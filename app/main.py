"""LearnCraft - 강의 기반 복습 퀴즈 & 학습 가이드 자동 생성 데모."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging
import re
import time

_t_start = time.perf_counter()

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

from app.styles import inject_global_css
inject_global_css()

# 앱 시작 시 미인덱싱 강의 자동 처리
from src.ingestion.loader import get_available_dates, load_script, load_lecture_topics
from src.ingestion.chunker import chunk_text
from src.vectorstore.store import add_documents, get_indexed_dates

t0 = time.perf_counter()
available_dates = get_available_dates()
logger.debug("[TIMING] get_available_dates: %.2fs", time.perf_counter() - t0)

t0 = time.perf_counter()
indexed_dates = get_indexed_dates()
logger.debug("[TIMING] get_indexed_dates: %.2fs", time.perf_counter() - t0)

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

logger.info("[TIMING] 메인 화면 렌더링까지 총 소요: %.2fs", time.perf_counter() - _t_start)

st.title("LearnCraft")
st.subheader("강의 내용 기반 복습 퀴즈 & 학습 가이드 자동 생성")
st.markdown("강의 스크립트(STT)를 RAG 파이프라인으로 분석하여 **복습 퀴즈**와 **학습 가이드**를 자동으로 생성합니다.")

st.markdown("<br>", unsafe_allow_html=True)

# 기능 카드
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        '<div class="lc-feature-card">'
        '<h3>퀴즈 풀기</h3>'
        '<p>강의를 선택하고 난이도별 퀴즈를 생성해 복습합니다. 객관식, 단답형, 코드 완성 문제를 지원합니다.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        '<div class="lc-feature-card">'
        '<h3>학습 가이드</h3>'
        '<p>강의의 핵심 개념과 요약을 자동으로 정리합니다. 마크다운으로 내보낼 수 있습니다.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        '<div class="lc-feature-card">'
        '<h3>품질 평가</h3>'
        '<p>생성된 퀴즈의 품질을 자동으로 평가하고 리포트를 제공합니다.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)
st.caption("왼쪽 사이드바에서 페이지를 선택하세요.")

from config.settings import OPENAI_API_KEY
if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY가 설정되지 않았습니다. 프로젝트 루트에 `.env` 파일을 생성하세요.")
    st.code("OPENAI_API_KEY=sk-...")
else:
    st.success("OpenAI API 키 확인됨")
