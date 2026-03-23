"""퀴즈 오답 기반 개인화 학습 가이드 생성."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.quiz.analyzer import concepts_to_query, parse_wrong_concepts_from_text
from src.guide.summarizer import generate_guide_by_query

st.set_page_config(page_title="개인화 학습 가이드", page_icon="🎯", layout="wide")
st.title("🎯 개인화 학습 가이드")
st.caption("퀴즈에서 틀린 개념들을 입력하면 해당 개념에 집중한 맞춤형 학습 가이드를 생성합니다.")

# 퀴즈 오답 자동 채우기
if "wrong_concepts_pending" in st.session_state:
    st.session_state["wrong_concepts_input"] = st.session_state.pop("wrong_concepts_pending")

quiz_wrong = st.session_state.get("quiz_wrong_concepts", [])
if quiz_wrong:
    st.success(f"퀴즈에서 오답 개념 {len(quiz_wrong)}개가 감지됐습니다: {', '.join(quiz_wrong[:5])}")
    if st.button("퀴즈 오답 개념 자동 채우기"):
        st.session_state["wrong_concepts_pending"] = ", ".join(quiz_wrong)
        st.rerun()

wrong_input = st.text_area(
    label="틀린 개념 입력 (쉼표 또는 줄바꿈으로 구분)",
    placeholder="예)\nORM, 세션 관리\n트랜잭션 처리\nFastAPI 의존성 주입",
    height=150,
    key="wrong_concepts_input",
)

if wrong_input and wrong_input.strip():
    parsed = parse_wrong_concepts_from_text(wrong_input)
    if parsed:
        st.info(f"인식된 개념 {len(parsed)}개: {', '.join(parsed)}")

st.divider()

if st.button("🎯 개인화 학습 가이드 생성", type="primary",
             disabled=not bool(wrong_input and wrong_input.strip())):
    concepts = parse_wrong_concepts_from_text(wrong_input)
    if not concepts:
        st.warning("유효한 개념이 입력되지 않았습니다.")
        st.stop()

    query = concepts_to_query(concepts)
    with st.spinner(f"{len(concepts)}개 오답 개념 분석 중..."):
        try:
            guide = generate_guide_by_query(query)
            st.session_state["personalized_guide"] = guide
            st.session_state["personalized_concepts"] = concepts
        except Exception as e:
            st.error(f"개인화 학습 가이드 생성 실패: {e}")
            st.stop()

if st.session_state.get("personalized_guide"):
    guide = st.session_state["personalized_guide"]
    used = st.session_state.get("personalized_concepts", [])
    label = ", ".join(used[:3]) + ("..." if len(used) > 3 else "")
    st.success(f"✅ [{label}] 개인화 학습 가이드 생성 완료!")

    st.divider()

    st.subheader("🔑 핵심 개념")
    concepts_list = guide.get("key_concepts", [])
    if concepts_list:
        cols = st.columns(min(len(concepts_list), 3))
        for i, concept in enumerate(concepts_list):
            with cols[i % 3]:
                st.markdown(f"**{concept.get('term', '')}**")
                st.caption(concept.get("description", ""))
    else:
        st.info("핵심 개념이 없습니다.")

    st.divider()

    st.subheader("📌 핵심 요약")
    summary = guide.get("summary", "")
    if summary:
        st.markdown(summary)

    st.divider()

    st.subheader("✅ 복습 포인트")
    review_points = guide.get("review_points", [])
    if review_points:
        for point in review_points:
            st.markdown(f"- {point}")

    st.divider()

    guide_md = f"""# 개인화 학습 가이드

## 분석 개념
{', '.join(used)}

## 핵심 개념
{chr(10).join(f"- **{c.get('term', '')}**: {c.get('description', '')}" for c in concepts_list)}

## 핵심 요약
{summary}

## 복습 포인트
{chr(10).join(f"- {p}" for p in review_points)}
"""
    st.download_button(
        label="⬇ Markdown으로 다운로드",
        data=guide_md.encode("utf-8"),
        file_name=f"개인화_학습가이드_{'_'.join(used[:2])}.md",
        mime="text/markdown",
    )
