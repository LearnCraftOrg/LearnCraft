"""학습 가이드 생성 및 뷰어."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time

import streamlit as st

from src.vectorstore.store import get_indexed_dates, get_stt_curriculum
from src.guide.summarizer import generate_guide

st.set_page_config(page_title="학습 가이드", page_icon="📖", layout="wide")
st.title("📖 학습 가이드")

indexed_dates = get_indexed_dates()

if not indexed_dates:
    st.warning("인덱싱된 강의가 없습니다. **강의 인덱싱** 페이지에서 먼저 인덱싱하세요.")
    st.stop()

# 날짜 선택
selected_date = st.selectbox("강의 날짜 선택", options=indexed_dates)

info = get_stt_curriculum(selected_date)

# 강의 정보
with st.expander("📋 강의 정보", expanded=True):
    col1, col2 = st.columns(2)
    col1.markdown(f"**주제:** {info.get('subject', '-')}")
    col1.markdown(f"**내용:** {info.get('content', '-')}")
    col2.markdown(f"**학습 목표:**")
    col2.info(info.get("learning_goal", "-"))

# 가이드 생성
if st.button("📝 학습 가이드 생성", type="primary"):
    with st.spinner("GPT-4o가 학습 가이드를 생성 중입니다..."):
        try:
            t0 = time.perf_counter()
            guide = generate_guide(selected_date)
            print(f"[TIMING] generate_guide: {time.perf_counter()-t0:.2f}s")
            st.session_state["guide_data"] = guide
            st.session_state["guide_date"] = selected_date
        except Exception as e:
            st.error(f"학습 가이드 생성 실패: {e}")

# 가이드 표시
if st.session_state.get("guide_data") and st.session_state.get("guide_date") == selected_date:
    guide = st.session_state["guide_data"]

    st.divider()

    # 핵심 개념
    st.subheader("🔑 핵심 개념")
    concepts = guide.get("key_concepts", [])
    if concepts:
        cols = st.columns(min(len(concepts), 3))
        for i, concept in enumerate(concepts):
            with cols[i % 3]:
                st.markdown(f"**{concept.get('term', '')}**")
                st.caption(concept.get("description", ""))
    else:
        st.info("핵심 개념이 없습니다.")

    st.divider()

    # 핵심 요약
    st.subheader("📌 핵심 요약")
    summary = guide.get("summary", "")
    if summary:
        st.markdown(summary)
    else:
        st.info("요약이 없습니다.")

    st.divider()

    # 복습 포인트
    st.subheader("✅ 복습 포인트")
    review_points = guide.get("review_points", [])
    if review_points:
        for point in review_points:
            st.markdown(f"- {point}")
    else:
        st.info("복습 포인트가 없습니다.")

    # 다운로드 버튼
    st.divider()
    guide_md = f"""# {selected_date} 학습 가이드

## 강의 정보
- **과목**: {info.get('subject', '-')}
- **내용**: {info.get('content', '-')}
- **학습 목표**: {info.get('learning_goal', '-')}

## 핵심 개념
{chr(10).join(f"- **{c.get('term', '')}**: {c.get('description', '')}" for c in concepts)}

## 핵심 요약
{summary}

## 복습 포인트
{chr(10).join(f"- {p}" for p in review_points)}
"""
    st.download_button(
        label="⬇ Markdown으로 다운로드",
        data=guide_md.encode("utf-8"),
        file_name=f"{selected_date}_학습가이드.md",
        mime="text/markdown",
    )
