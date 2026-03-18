"""LearnCraft - 복습 퀴즈 & AI 학습 가이드 통합 Streamlit UI.

UI 구성 (탭 3개):
- 탭 1: 복습 퀴즈      (강의 선택 → 문제 생성 → 풀기)
- 탭 2: 학습 가이드    (강의 주제 입력 → RAG 6섹션 가이드 생성)
- 탭 3: 개인화 가이드  (퀴즈 오답 개념 입력 → 맞춤 가이드 생성)
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from config.settings import OPENAI_API_KEY, LLM_MODEL
from src.vectorstore.store import get_indexed_dates, add_documents
from src.ingestion.loader import get_available_dates, load_script, extract_stt_metadata
from src.ingestion.chunker import chunk_text
from src.rag.pipeline import build_context_by_date, build_context_by_query
from src.quiz.generator import generate_quiz_from_context, generate_quiz_multi_from_context
from quiz.quiz_analyzer import parse_wrong_concepts_from_text, analyze_wrong_answers
from services.study_guide_service import (
    generate_study_guide,
    generate_personalized_study_guide,
)

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LearnCraft",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── 자동 인덱싱 (앱 시작 시 미인덱싱 강의 처리) ──────────────────────────────
@st.experimental_singleton
def _auto_index():
    """미인덱싱 강의 자동 인덱싱 (최초 1회만 실행)."""
    available = get_available_dates()
    indexed = get_indexed_dates()
    unindexed = [d for d in available if d not in indexed]
    for date in unindexed:
        text = load_script(date)
        if text:
            meta = extract_stt_metadata(date)
            docs = chunk_text(text, {"date": date, **meta})
            add_documents(docs)
    return True


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


# ══════════════════════════════════════════════════════════════════════════════
# 탭 1: 복습 퀴즈
# ══════════════════════════════════════════════════════════════════════════════

def _quiz_session_init() -> None:
    """퀴즈 관련 세션 상태 초기화."""
    for key, default in [
        ("quiz_view", "selection"),
        ("quiz_data", []),
        ("quiz_selected_dates", []),
        ("quiz_user_query", ""),
        ("quiz_difficulty", "medium"),
        ("quiz_idx", 0),
        ("quiz_answers", {}),
        ("quiz_checked", {}),
        ("quiz_wrong_concepts", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def _render_quiz_selection(indexed_dates: list[str]) -> None:
    """퀴즈 탭 - 뷰 1: 강의 선택."""
    st.subheader("강의 선택")

    # 강의 목록
    options = []
    for date in indexed_dates:
        meta = extract_stt_metadata(date)
        topic = meta["content"][:40] if meta.get("content") else ""
        options.append(f"{date}  {topic}" if topic else date)

    date_map = {opt: date for opt, date in zip(options, indexed_dates)}
    selected_opts = st.multiselect(
        "강의 날짜 선택 (복수 선택 가능)",
        options=options,
        key="lecture_multiselect",
    )
    selected_dates = [date_map[o] for o in selected_opts]

    st.markdown("---")

    # 난이도 선택
    difficulty = st.radio(
        "난이도",
        options=["easy", "medium", "hard"],
        format_func=lambda x: {"easy": "🟢 쉬움", "medium": "🟡 보통", "hard": "🔴 어려움"}[x],
        index=1,
        key="difficulty_radio",
    )

    # 추가 쿼리 입력
    user_query = st.text_area(
        label="문제 생성 범위 (선택사항)",
        placeholder="문제 생성 주제를 입력하세요\n예) 특정 기간 내 범위에 대한 문제를 생성해줘",
        height=100,
        key="user_query_input",
    )

    can_submit = len(selected_dates) > 0 or bool(user_query.strip())
    if st.button("🎲 문제 생성", disabled=not can_submit):
        st.session_state["quiz_selected_dates"] = selected_dates
        st.session_state["quiz_user_query"] = user_query.strip()
        st.session_state["quiz_difficulty"] = difficulty
        st.session_state["quiz_view"] = "loading"
        st.experimental_rerun()


def _render_quiz_loading() -> None:
    """퀴즈 탭 - 뷰 2: 로딩."""
    st.markdown("""
    <style>
    @keyframes pulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.25); opacity: 0.65; }
    }
    .loading-icon {
        font-size: 5rem;
        animation: pulse 1.4s ease-in-out infinite;
        display: block;
        text-align: center;
        margin: 1.5rem 0;
    }
    </style>
    <span class="loading-icon">📚</span>
    """, unsafe_allow_html=True)

    dates = st.session_state["quiz_selected_dates"]
    query = st.session_state["quiz_user_query"]
    difficulty = st.session_state["quiz_difficulty"]
    has_text = bool(query)
    is_single = len(dates) == 1 and not has_text

    with st.spinner("퀴즈 준비 중..."):
        try:
            if is_single:
                ctx = build_context_by_date(dates[0])
            else:
                ctx = build_context_by_query(dates, query if has_text else None)
            if is_single:
                result = generate_quiz_from_context(ctx, difficulty=difficulty)
            else:
                result = generate_quiz_multi_from_context(
                    ctx, query if has_text else None, difficulty=difficulty
                )
        except Exception as e:
            st.error(f"퀴즈 생성 실패: {e}")
            if st.button("선택 화면으로 돌아가기"):
                st.session_state["quiz_view"] = "selection"
                st.experimental_rerun()
            return

    st.session_state["quiz_data"] = result.get("quizzes", [])
    st.session_state["quiz_idx"] = 0
    st.session_state["quiz_answers"] = {}
    st.session_state["quiz_checked"] = {}
    st.session_state["quiz_view"] = "quiz"
    st.experimental_rerun()


def _render_quiz_play() -> None:
    """퀴즈 탭 - 뷰 3: 문제 풀기 (1문제씩)."""
    quizzes = st.session_state["quiz_data"]
    if not quizzes:
        st.error("퀴즈 데이터가 없습니다.")
        if st.button("선택 화면으로"):
            st.session_state["quiz_view"] = "selection"
            st.experimental_rerun()
        return

    idx = st.session_state["quiz_idx"]
    total = len(quizzes)

    # 진행 표시
    st.progress((idx + 1) / total)
    st.caption(f"{idx + 1} / {total}")
    st.markdown("---")

    q = quizzes[idx]
    st.markdown(f"### Q{idx + 1}. {q['question']}")
    st.markdown("")

    is_checked = st.session_state["quiz_checked"].get(idx, False)

    # 객관식 / 주관식
    if q["type"] == "multiple_choice":
        opts = q.get("options", {})
        options_list = [f"{k}. {v}" for k, v in opts.items()]
        current_answer = st.session_state["quiz_answers"].get(idx)
        default_idx = options_list.index(current_answer) if current_answer in options_list else 0
        chosen = st.radio(
            "선택지",
            options=options_list,
            index=default_idx,
            key=f"q_answer_{idx}",

            disabled=is_checked,
        )
        if chosen:
            st.session_state["quiz_answers"][idx] = chosen
        has_answer = bool(st.session_state["quiz_answers"].get(idx))
    else:
        typed = st.text_input(
            "답 입력",
            value=st.session_state["quiz_answers"].get(idx, ""),
            key=f"q_answer_{idx}",
            placeholder="답을 입력하세요",

            disabled=is_checked,
        )
        st.session_state["quiz_answers"][idx] = typed
        has_answer = bool(typed.strip())

    st.markdown("")

    # 확인 버튼 / 결과
    if not is_checked:
        if st.button("확인", disabled=not has_answer):
            st.session_state["quiz_checked"][idx] = True
            st.experimental_rerun()
    else:
        user_ans = st.session_state["quiz_answers"].get(idx, "")
        correct_ans = q["answer"]
        if q["type"] == "multiple_choice":
            is_correct = bool(user_ans and user_ans.startswith(correct_ans))
        else:
            is_correct = bool(user_ans.strip() and correct_ans.lower() in user_ans.lower())

        if is_correct:
            st.success(f"✅ 정답! | 해설: {q['explanation']}")
        else:
            st.error(f"❌ 오답 | 정답: {correct_ans} | 해설: {q['explanation']}")

    st.markdown("---")

    # 이전 / 다음
    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("◀ 이전", disabled=(idx == 0)):
            st.session_state["quiz_idx"] -= 1
            st.experimental_rerun()
    with col_next:
        if st.button("다음 ▶", disabled=(not is_checked or idx == total - 1)):
            st.session_state["quiz_idx"] += 1
            st.experimental_rerun()

    # 최종 점수 (모든 문제 확인 시)
    all_checked = all(st.session_state["quiz_checked"].get(i, False) for i in range(total))
    if all_checked:
        st.markdown("---")
        correct_count = sum(
            1 for i, qi in enumerate(quizzes)
            if (qi["type"] == "multiple_choice"
                and st.session_state["quiz_answers"].get(i, "").startswith(qi["answer"]))
            or (qi["type"] != "multiple_choice"
                and qi["answer"].lower() in st.session_state["quiz_answers"].get(i, "").lower())
        )
        score_pct = int(correct_count / total * 100)

        if score_pct >= 80:
            st.balloons()
            st.success(f"🎉 점수: {correct_count}/{total} ({score_pct}%) - 훌륭합니다!")
        elif score_pct >= 60:
            st.warning(f"📊 점수: {correct_count}/{total} ({score_pct}%) - 조금 더 복습해보세요.")
        else:
            st.error(f"📚 점수: {correct_count}/{total} ({score_pct}%) - 학습 가이드를 참고하세요.")

        # 오답 개념 추출 후 세션에 저장
        quiz_results = []
        for i, qi in enumerate(quizzes):
            user_ans = st.session_state["quiz_answers"].get(i, "")
            if qi["type"] == "multiple_choice":
                is_correct = bool(user_ans and user_ans.startswith(qi["answer"]))
            else:
                is_correct = bool(user_ans.strip() and qi["answer"].lower() in user_ans.lower())
            quiz_results.append({
                "question": qi["question"],
                "answer": qi["answer"],
                "user_answer": user_ans,
                "is_correct": is_correct,
                "explanation": qi.get("explanation", ""),
            })
        wrong_concepts = analyze_wrong_answers(quiz_results)
        st.session_state["quiz_wrong_concepts"] = wrong_concepts

        if wrong_concepts:
            st.info(f"오답 개념 {len(wrong_concepts)}개 추출됨: {', '.join(wrong_concepts[:5])}")

        st.markdown("")
        col_retry, col_new = st.columns(2)
        with col_retry:
            if st.button("🔄 다시 풀기"):
                st.session_state["quiz_idx"] = 0
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_checked"] = {}
                st.experimental_rerun()
        with col_new:
            if st.button("✏️ 새 문제 생성"):
                st.session_state["quiz_view"] = "selection"
                st.session_state["quiz_data"] = []
                st.session_state["quiz_idx"] = 0
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_checked"] = {}
                st.experimental_rerun()


def render_quiz_tab(indexed_dates: list[str]) -> None:
    """퀴즈 탭 진입점: quiz_view 상태에 따라 뷰 디스패치."""
    _quiz_session_init()
    view = st.session_state["quiz_view"]
    if view == "selection":
        _render_quiz_selection(indexed_dates)
    elif view == "loading":
        _render_quiz_loading()
    elif view == "quiz":
        _render_quiz_play()


# ══════════════════════════════════════════════════════════════════════════════
# 탭 2: 학습 가이드
# ══════════════════════════════════════════════════════════════════════════════

def _render_guide_result(guide_text: str, label: str = "") -> None:
    """생성된 학습 가이드 렌더링 + 다운로드 버튼."""
    st.markdown("---")
    st.markdown(guide_text)
    st.markdown("---")
    st.download_button(
        label="⬇ 학습 가이드 다운로드 (Markdown)",
        data=guide_text.encode("utf-8"),
        file_name=f"학습가이드_{label}.md" if label else "학습가이드.md",
        mime="text/markdown",
    )


def render_guide_tab() -> None:
    """탭 2: 강의 주제 입력 → RAG 학습 가이드 생성."""
    st.subheader("강의 주제로 학습 가이드 생성")
    st.caption("학습하고 싶은 강의 주제나 키워드를 입력하세요.")

    # 예시 버튼 클릭 시 다음 렌더에서 위젯 렌더 전에 적용
    if "general_query_pending" in st.session_state:
        st.session_state["general_query"] = st.session_state.pop("general_query_pending")

    query = st.text_input(
        label="강의 주제 또는 키워드",
        placeholder="예) FastAPI 라우터, ORM과 SQLAlchemy, 비동기 처리",
        key="general_query",
    )

    # 예시 버튼
    st.caption("예시:")
    col1, col2, col3 = st.columns(3)
    for col, example in zip(
        [col1, col2, col3],
        ["FastAPI 의존성 주입", "SQLAlchemy ORM 세션", "비동기 async await"],
    ):
        if col.button(example, key=f"ex_{example}"):
            st.session_state["general_query_pending"] = example
            st.experimental_rerun()

    st.markdown("---")

    if st.button("📝 학습 가이드 생성",
                 disabled=not bool(query and query.strip())):
        with st.spinner(f'"{query}" 관련 강의 섹션 검색 중...'):
            try:
                guide = generate_study_guide(query.strip())
                st.session_state["general_guide"] = guide
                st.session_state["general_query_used"] = query.strip()
            except Exception as e:
                st.error(f"학습 가이드 생성 실패: {e}")
                return

    if st.session_state.get("general_guide"):
        used = st.session_state.get("general_query_used", "")
        st.success(f'✅ "{used}" 학습 가이드 생성 완료!')
        _render_guide_result(st.session_state["general_guide"], label=used.replace(" ", "_")[:20])


# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 개인화 학습 가이드
# ══════════════════════════════════════════════════════════════════════════════

def render_personalized_tab() -> None:
    """탭 3: 퀴즈 오답 개념 입력 → 개인화 학습 가이드 생성."""
    st.subheader("퀴즈 오답 기반 개인화 학습 가이드")
    st.caption("퀴즈에서 틀린 개념들을 입력하면 해당 개념에 집중한 맞춤형 학습 가이드를 생성합니다.")

    # 퀴즈 오답 자동 채우기
    if "wrong_concepts_pending" in st.session_state:
        st.session_state["wrong_concepts_input"] = st.session_state.pop("wrong_concepts_pending")

    quiz_wrong = st.session_state.get("quiz_wrong_concepts", [])
    if quiz_wrong:
        st.success(f"퀴즈에서 오답 개념 {len(quiz_wrong)}개가 감지됐습니다: {', '.join(quiz_wrong[:5])}")
        if st.button("퀴즈 오답 개념 자동 채우기"):
            st.session_state["wrong_concepts_pending"] = ", ".join(quiz_wrong)
            st.experimental_rerun()

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

    st.markdown("---")

    if st.button("🎯 개인화 학습 가이드 생성",
                 disabled=not bool(wrong_input and wrong_input.strip())):
        concepts = parse_wrong_concepts_from_text(wrong_input)
        if not concepts:
            st.warning("유효한 개념이 입력되지 않았습니다.")
            return
        with st.spinner(f"{len(concepts)}개 오답 개념 분석 중..."):
            try:
                guide = generate_personalized_study_guide(concepts)
                st.session_state["personalized_guide"] = guide
                st.session_state["personalized_concepts"] = concepts
            except Exception as e:
                st.error(f"개인화 학습 가이드 생성 실패: {e}")
                return

    if st.session_state.get("personalized_guide"):
        used = st.session_state.get("personalized_concepts", [])
        label = ", ".join(used[:3]) + ("..." if len(used) > 3 else "")
        st.success(f"✅ [{label}] 개인화 학습 가이드 생성 완료!")
        _render_guide_result(
            st.session_state["personalized_guide"],
            label="개인화_" + "_".join(used[:2]),
        )


# ══════════════════════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar(indexed_dates: list[str]) -> None:
    """사이드바: 시스템 상태 및 사용 안내."""
    with st.sidebar:
        st.title("📚 LearnCraft")
        st.markdown("---")

        # 상태 표시
        if OPENAI_API_KEY:
            st.success("✅ OpenAI API 연결됨")
        else:
            st.error("❌ API 키 미설정")
        st.caption(f"🤖 모델: {LLM_MODEL}")
        st.caption(f"📂 인덱싱된 강의: {len(indexed_dates)}개")

        st.markdown("---")

        st.markdown("""
**사용 방법**

**📝 복습 퀴즈**
1. 강의 날짜 선택 + 난이도 설정
2. "문제 생성" 클릭
3. 1문제씩 풀고 점수 확인

**📖 학습 가이드**
1. 강의 주제 키워드 입력
2. "학습 가이드 생성" 클릭
3. 6개 섹션 가이드 확인

**🎯 개인화 가이드**
1. 퀴즈에서 틀린 개념 입력
2. "개인화 학습 가이드 생성" 클릭
        """)

        st.markdown("---")
        with st.expander("🔧 시스템 정보"):
            st.markdown("""
- **벡터 DB**: ChromaDB
- **임베딩**: text-embedding-3-small
- **검색 방식**: 코사인 유사도 (k=5)
- **LLM**: gpt-4o-mini (temp=0.3)
            """)


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Streamlit 앱 메인 진입점."""
    # 자동 인덱싱
    with st.spinner("강의 데이터 확인 중..."):
        _auto_index()

    indexed_dates = get_indexed_dates()

    # 사이드바
    render_sidebar(indexed_dates)

    # 헤더
    st.title("📚 LearnCraft")
    st.markdown("강의 스크립트를 RAG로 분석하여 **복습 퀴즈**와 **학습 가이드**를 자동 생성합니다.")

    # API 키 확인
    if not _check_api_key():
        st.stop()

    if not indexed_dates:
        st.warning("인덱싱된 강의가 없습니다. 잠시 후 새로고침 해주세요.")
        st.stop()

    st.markdown("---")

    # 세션 상태 초기화 (가이드 탭용)
    for key, default in [
        ("general_guide", None),
        ("general_query_used", ""),
        ("personalized_guide", None),
        ("personalized_concepts", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 탭 구성
    tab_quiz, tab_guide, tab_personalized = st.tabs([
        "📝 복습 퀴즈",
        "📖 학습 가이드",
        "🎯 개인화 학습 가이드",
    ])

    with tab_quiz:
        render_quiz_tab(indexed_dates)

    with tab_guide:
        render_guide_tab()

    with tab_personalized:
        render_personalized_tab()


if __name__ == "__main__":
    main()
