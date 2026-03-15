"""AI 학습 가이드 생성기 - Streamlit UI.

RAG 기반 학습 가이드 생성 및 퀴즈 오답 기반 개인화 학습 가이드를
제공하는 Streamlit 웹 인터페이스입니다.

UI 구성:
- 탭 1: 일반 학습 가이드 (강의 주제 입력 → 학습 가이드 생성)
- 탭 2: 개인화 학습 가이드 (퀴즈 오답 개념 입력 → 맞춤 가이드 생성)
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (모듈 임포트 경로 설정)
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from config.settings import OPENAI_API_KEY, LLM_MODEL
from quiz.quiz_analyzer import parse_wrong_concepts_from_text
from services.study_guide_service import (
    generate_study_guide,
    generate_personalized_study_guide,
)

# ── Streamlit 페이지 설정 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI 학습 가이드 생성기",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── API 키 확인 ──────────────────────────────────────────────────────────────
def _check_api_key() -> bool:
    """OpenAI API 키 설정 여부 확인."""
    if not OPENAI_API_KEY:
        st.error(
            "⚠️ OpenAI API 키가 설정되지 않았습니다.\n\n"
            "프로젝트 루트에 `.env` 파일을 생성하고 아래 내용을 추가하세요:"
        )
        st.code("OPENAI_API_KEY=sk-...")
        return False
    return True


# ── 학습 가이드 렌더링 ───────────────────────────────────────────────────────
def _render_guide_result(guide_text: str, date_label: str = "") -> None:
    """
    생성된 학습 가이드를 Streamlit UI에 렌더링.

    마크다운 형식의 학습 가이드를 섹션별로 표시하고
    다운로드 버튼을 제공합니다.

    Args:
        guide_text: 6개 섹션으로 구성된 학습 가이드 문자열
        date_label: 다운로드 파일명에 사용할 레이블 (선택)
    """
    st.divider()
    # 학습 가이드 내용 렌더링 (마크다운 지원)
    st.markdown(guide_text)

    # 학습 가이드 다운로드 버튼
    st.divider()
    filename = f"학습가이드_{date_label}.md" if date_label else "학습가이드.md"
    st.download_button(
        label="⬇ 학습 가이드 다운로드 (Markdown)",
        data=guide_text.encode("utf-8"),
        file_name=filename,
        mime="text/markdown",
        use_container_width=True,
    )


# ── 탭 1: 일반 학습 가이드 ───────────────────────────────────────────────────
def render_general_guide_tab() -> None:
    """
    일반 학습 가이드 탭 렌더링.

    사용자가 강의 주제를 입력하면 RAG 파이프라인을 통해
    관련 강의 섹션을 검색하고 6개 섹션 학습 가이드를 생성합니다.
    """
    st.subheader("강의 주제로 학습 가이드 생성")
    st.caption(
        "학습하고 싶은 강의 주제나 키워드를 입력하세요. "
        "관련 강의 내용을 자동으로 검색하여 학습 가이드를 생성합니다."
    )

    # 강의 주제 입력
    query = st.text_input(
        label="강의 주제 또는 키워드",
        placeholder="예) FastAPI 라우터, ORM과 SQLAlchemy, 비동기 처리, REST API 설계",
        key="general_query",
    )

    # 예시 쿼리 버튼
    st.caption("예시:")
    col1, col2, col3 = st.columns(3)
    example_queries = [
        "FastAPI 의존성 주입",
        "SQLAlchemy ORM 세션",
        "비동기 async await",
    ]
    # 예시 버튼 클릭 시 입력창에 값 설정
    for col, example in zip([col1, col2, col3], example_queries):
        if col.button(example, key=f"example_{example}"):
            st.session_state["general_query"] = example
            st.rerun()

    st.divider()

    # 학습 가이드 생성 버튼
    generate_btn = st.button(
        "📝 학습 가이드 생성",
        type="primary",
        disabled=not bool(query and query.strip()),
        use_container_width=True,
        key="btn_general",
    )

    # 생성 실행
    if generate_btn and query and query.strip():
        with st.spinner(f'"{query}" 관련 강의 섹션 검색 및 학습 가이드 생성 중...'):
            try:
                # RAG 파이프라인 실행: 쿼리 → 검색 → LLM → 학습 가이드
                guide = generate_study_guide(query.strip())
                # 세션 상태에 결과 저장
                st.session_state["general_guide"] = guide
                st.session_state["general_query_used"] = query.strip()
            except Exception as e:
                st.error(f"학습 가이드 생성 실패: {e}")
                return

    # 저장된 결과 표시
    if st.session_state.get("general_guide"):
        used_query = st.session_state.get("general_query_used", "")
        st.success(f'✅ "{used_query}" 학습 가이드 생성 완료!')
        _render_guide_result(
            st.session_state["general_guide"],
            date_label=used_query.replace(" ", "_")[:20],
        )


# ── 탭 2: 개인화 학습 가이드 ─────────────────────────────────────────────────
def render_personalized_guide_tab() -> None:
    """
    개인화 학습 가이드 탭 렌더링.

    퀴즈에서 틀린 개념을 입력하면 해당 개념들을 벡터 검색하여
    취약점에 집중한 맞춤형 학습 가이드를 생성합니다.

    개인화 파이프라인:
    1. 사용자가 오답 개념 입력 (텍스트 영역)
    2. 개념 파싱 (쉼표/줄바꿈 구분)
    3. 검색 쿼리 변환
    4. 개인화 학습 가이드 생성
    """
    st.subheader("퀴즈 오답 기반 개인화 학습 가이드")
    st.caption(
        "퀴즈에서 틀린 개념들을 입력하면 해당 개념에 집중한 맞춤형 학습 가이드를 생성합니다."
    )

    # 오답 개념 입력 (쉼표 또는 줄바꿈 구분)
    wrong_input = st.text_area(
        label="틀린 개념 입력 (쉼표 또는 줄바꿈으로 구분)",
        placeholder=(
            "예)\n"
            "ORM, 세션 관리\n"
            "트랜잭션 처리\n"
            "FastAPI 의존성 주입"
        ),
        height=150,
        key="wrong_concepts_input",
    )

    # 입력된 개념 파싱 결과 미리보기
    if wrong_input and wrong_input.strip():
        parsed = parse_wrong_concepts_from_text(wrong_input)
        if parsed:
            st.info(f"인식된 개념 {len(parsed)}개: {', '.join(parsed)}")

    st.divider()

    # 개인화 학습 가이드 생성 버튼
    can_generate = bool(wrong_input and wrong_input.strip())
    personalized_btn = st.button(
        "🎯 개인화 학습 가이드 생성",
        type="primary",
        disabled=not can_generate,
        use_container_width=True,
        key="btn_personalized",
    )

    # 생성 실행
    if personalized_btn and wrong_input and wrong_input.strip():
        # 입력 텍스트를 개념 키워드 목록으로 파싱
        concepts = parse_wrong_concepts_from_text(wrong_input)
        if not concepts:
            st.warning("유효한 개념이 입력되지 않았습니다.")
            return

        with st.spinner(
            f"{len(concepts)}개 오답 개념 분석 및 개인화 학습 가이드 생성 중..."
        ):
            try:
                # 오답 개념 → 벡터 검색 → 개인화 학습 가이드 생성
                guide = generate_personalized_study_guide(concepts)
                st.session_state["personalized_guide"] = guide
                st.session_state["personalized_concepts"] = concepts
            except Exception as e:
                st.error(f"개인화 학습 가이드 생성 실패: {e}")
                return

    # 저장된 결과 표시
    if st.session_state.get("personalized_guide"):
        used_concepts = st.session_state.get("personalized_concepts", [])
        st.success(
            f"✅ [{', '.join(used_concepts[:3])}{'...' if len(used_concepts) > 3 else ''}] "
            "개인화 학습 가이드 생성 완료!"
        )
        _render_guide_result(
            st.session_state["personalized_guide"],
            date_label="개인화_" + "_".join(used_concepts[:2]),
        )


# ── 사이드바 ─────────────────────────────────────────────────────────────────
def render_sidebar() -> None:
    """사이드바: 시스템 정보 및 사용 안내 렌더링."""
    with st.sidebar:
        st.title("📖 AI 학습 가이드")
        st.divider()

        # API 키 상태 표시
        if OPENAI_API_KEY:
            st.success("✅ OpenAI API 연결됨")
        else:
            st.error("❌ API 키 미설정")

        # 모델 정보
        st.caption(f"🤖 모델: {LLM_MODEL}")

        st.divider()

        # 사용 안내
        st.markdown("""
**사용 방법**

**일반 학습 가이드**
1. 강의 주제 또는 키워드 입력
2. "학습 가이드 생성" 버튼 클릭
3. 6개 섹션 학습 가이드 확인

**개인화 학습 가이드**
1. 퀴즈에서 틀린 개념 입력
2. "개인화 학습 가이드 생성" 클릭
3. 오답 개념 집중 학습 가이드 확인
        """)

        st.divider()

        # RAG 파이프라인 설명
        with st.expander("🔧 시스템 정보"):
            st.markdown("""
- **벡터 DB**: ChromaDB
- **임베딩**: text-embedding-3-small
- **검색 방식**: 코사인 유사도 (k=5)
- **출력 형식**: 6개 섹션 한국어 가이드
            """)


# ── 메인 앱 ──────────────────────────────────────────────────────────────────
def main() -> None:
    """Streamlit 앱 메인 진입점."""
    # 사이드바 렌더링
    render_sidebar()

    # 앱 헤더
    st.title("📖 AI 학습 가이드 생성기")
    st.markdown(
        "강의 주제를 입력하거나 퀴즈 오답 개념을 입력하여 "
        "**RAG 기반 맞춤형 학습 가이드**를 생성하세요."
    )

    # API 키 확인 (없으면 앱 중단)
    if not _check_api_key():
        st.stop()

    st.divider()

    # 탭 구성: 일반 학습 가이드 / 개인화 학습 가이드
    tab_general, tab_personalized = st.tabs([
        "📝 일반 학습 가이드",
        "🎯 개인화 학습 가이드 (오답 기반)",
    ])

    # 세션 상태 초기화
    for key, default in [
        ("general_guide", None),
        ("general_query_used", ""),
        ("personalized_guide", None),
        ("personalized_concepts", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 탭 렌더링
    with tab_general:
        render_general_guide_tab()

    with tab_personalized:
        render_personalized_guide_tab()


if __name__ == "__main__":
    main()
