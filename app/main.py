"""LearnCraft - 복습 퀴즈 & AI 학습 가이드 통합 Streamlit UI.

UI 구성 (탭 4개):
- 탭 1: 복습 퀴즈      (강의 선택 → 문제 생성 → 풀기)
- 탭 2: 학습 가이드    (강의 주제 입력 → RAG 6섹션 가이드 생성)
- 탭 3: 개인화 가이드  (퀴즈 오답 개념 입력 → 맞춤 가이드 생성)
- 탭 4: 오답 노트      (틀린 문제 저장 → 다시 풀기)
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
import re as _re
from src.ingestion.loader import get_available_dates, load_script, load_lecture_topics
from src.ingestion.chunker import chunk_text
from src.rag.pipeline import build_context_by_date, build_context_by_query
from src.quiz.generator import generate_quiz_from_context, generate_quiz_multi_from_context
from src.quiz.analyzer import analyze_wrong_answers
from src.quiz.wrong_note import save_wrong_answers, remove_mastered, load_wrong_note, to_quiz_format
from src.services.study_guide_service import (
    generate_study_guide,
    generate_personalized_study_guide,
    stream_study_guide,
    stream_personalized_study_guide,
)

# ── 페이지 설정 ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LearnCraft",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── 체인 캐싱 (Streamlit 프로세스 전체에서 재사용) ────────────────────────────
@st.cache_resource
def _get_cached_study_guide_chain():
    """학습 가이드 RAG 체인을 한 번만 초기화하고 캐싱."""
    from src.rag.study_guide_chain import build_study_guide_chain
    return build_study_guide_chain(k=5)


# ── 자동 인덱싱 (앱 시작 시 미인덱싱 강의 처리) ──────────────────────────────
@st.cache_resource
def _auto_index():
    """미인덱싱 강의 자동 인덱싱 (최초 1회만 실행)."""
    available = get_available_dates()
    indexed = get_indexed_dates()
    unindexed = [d for d in available if d not in indexed]
    for date in unindexed:
        text = load_script(date)
        if text:
            headings = _re.findall(r'^## (.+)', text, _re.MULTILINE)
            meta = {
                "subject": "",
                "content": load_lecture_topics(date),
                "learning_goal": " / ".join(headings),
            }
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
        ("quiz_wrong_saved", False),
        ("personalized_guide", None),
        ("personalized_dates_used", []),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default


def _render_quiz_selection(indexed_dates: list[str]) -> None:
    """퀴즈 탭 - 뷰 1: 강의 선택."""
    st.subheader("강의 선택")

    # 강의 목록
    options = []
    for date in indexed_dates:
        topic = load_lecture_topics(date)[:40]
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
        st.session_state["quiz_wrong_saved"] = False
        st.rerun()


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
                st.rerun()
            return

    st.session_state["quiz_data"] = result.get("quizzes", [])
    st.session_state["quiz_idx"] = 0
    st.session_state["quiz_answers"] = {}
    st.session_state["quiz_checked"] = {}
    st.session_state["quiz_view"] = "quiz"
    st.rerun()


def _render_quiz_play() -> None:
    """퀴즈 탭 - 뷰 3: 문제 풀기 (1문제씩)."""
    quizzes = st.session_state["quiz_data"]
    if not quizzes:
        st.error("퀴즈 데이터가 없습니다.")
        if st.button("선택 화면으로"):
            st.session_state["quiz_view"] = "selection"
            st.rerun()
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
            st.rerun()
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
            st.rerun()
    with col_next:
        if st.button("다음 ▶", disabled=(not is_checked or idx == total - 1)):
            st.session_state["quiz_idx"] += 1
            st.rerun()

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
                "type": qi.get("type", "multiple_choice"),
                "options": qi.get("options", {}),
                "answer": qi["answer"],
                "user_answer": user_ans,
                "is_correct": is_correct,
                "explanation": qi.get("explanation", ""),
            })
        wrong_concepts = analyze_wrong_answers(quiz_results)
        st.session_state["quiz_wrong_concepts"] = wrong_concepts

        # 오답 노트 자동 저장 (퀴즈 세션당 1회)
        if not st.session_state.get("quiz_wrong_saved"):
            lecture_dates = st.session_state.get("quiz_selected_dates", [])
            added = save_wrong_answers(quiz_results, lecture_dates)
            st.session_state["quiz_wrong_saved"] = True
            if added > 0:
                st.info(f"📝 오답 {added}개가 오답 노트에 저장됐습니다.")

        if wrong_concepts:
            st.info(f"오답 개념 {len(wrong_concepts)}개 추출됨: {', '.join(wrong_concepts[:5])}")

        st.markdown("")
        col_retry, col_new = st.columns(2)
        with col_retry:
            if st.button("🔄 다시 풀기"):
                st.session_state["quiz_idx"] = 0
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_checked"] = {}
                st.session_state["quiz_wrong_saved"] = False
                st.rerun()
        with col_new:
            if st.button("✏️ 새 문제 생성"):
                st.session_state["quiz_view"] = "selection"
                st.session_state["quiz_data"] = []
                st.session_state["quiz_idx"] = 0
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_checked"] = {}
                st.rerun()


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


def render_guide_tab(indexed_dates: list[str]) -> None:
    """탭 2: 강의 선택 + 키워드 입력 → RAG 학습 가이드 생성."""
    st.subheader("강의 주제로 학습 가이드 생성")
    st.caption("강의를 선택하거나 키워드를 입력하여 학습 가이드를 생성하세요.")

    # STT 메타데이터 기반 날짜별 강의 제목 구성 (퀴즈 탭과 동일 방식)
    date_label_map = {}
    date_topic_map = {}
    for d in indexed_dates:
        topic = load_lecture_topics(d)[:40]
        date_label_map[d] = f"{d}  {topic}" if topic else d
        date_topic_map[d] = topic

    label_to_date = {v: k for k, v in date_label_map.items()}
    lecture_options = ["선택 안 함"] + list(date_label_map.values())

    # ── 강의 선택 ──────────────────────────────────────────────────────────────
    selected_label = st.selectbox(
        "강의 선택",
        options=lecture_options,
        key="guide_lecture_select",
    )
    selected_date = label_to_date.get(selected_label)
    base_query = ""
    if selected_date:
        base_query = date_topic_map.get(selected_date, selected_date)

    st.markdown("---")

    # ── 추가 키워드 입력 ────────────────────────────────────────────────────────
    st.caption("특정 주제나 키워드를 추가로 입력하세요 (선택사항).")

    if "guide_keyword_pending" in st.session_state:
        st.session_state["guide_keyword"] = st.session_state.pop("guide_keyword_pending")

    keyword = st.text_input(
        label="추가 키워드",
        placeholder="예) 의존성 주입, ORM 세션 관리, 비동기 처리",
        key="guide_keyword",
    )

    # 예시 버튼
    st.caption("예시:")
    col1, col2, col3 = st.columns(3)
    for col, example in zip(
        [col1, col2, col3],
        ["FastAPI 의존성 주입", "SQLAlchemy ORM 세션", "비동기 async await"],
    ):
        if col.button(example, key=f"ex_{example}"):
            st.session_state["guide_keyword_pending"] = example
            st.rerun()

    st.markdown("---")

    combined_query = " ".join(filter(None, [base_query, keyword.strip()]))

    if st.button("📝 학습 가이드 생성", disabled=not bool(combined_query)):
        st.session_state.pop("general_guide", None)
        st.session_state["general_query_used"] = combined_query
        try:
            with st.spinner("관련 강의 섹션 검색 중..."):
                stream = stream_study_guide(combined_query)
            guide = st.write_stream(stream)
            st.session_state["general_guide"] = guide
        except Exception as e:
            st.error(f"학습 가이드 생성 실패: {e}")
            return
        st.rerun()

    if st.session_state.get("general_guide"):
        used = st.session_state.get("general_query_used", "")
        st.success(f'✅ "{used}" 학습 가이드 생성 완료!')
        _render_guide_result(st.session_state["general_guide"], label=used.replace(" ", "_")[:20])


# ══════════════════════════════════════════════════════════════════════════════
# 탭 3: 개인화 학습 가이드
# ══════════════════════════════════════════════════════════════════════════════

def render_personalized_tab() -> None:
    """탭 3: 퀴즈 오답 기반 강의 선택 → 개인화 학습 가이드 생성."""
    st.subheader("퀴즈 오답 기반 개인화 학습 가이드")
    st.caption("퀴즈를 완료한 강의를 선택하면 오답 개념에 집중한 맞춤형 학습 가이드를 생성합니다.")

    quiz_wrong = st.session_state.get("quiz_wrong_concepts", [])
    quiz_dates = st.session_state.get("quiz_selected_dates", [])

    if not quiz_wrong or not quiz_dates:
        st.info("복습 퀴즈를 완료하면 여기에 강의 목록이 표시됩니다.")
        return

    # 날짜별 라벨 구성
    date_label_map = {}
    for d in quiz_dates:
        topic = load_lecture_topics(d)[:40]
        date_label_map[d] = f"{d}  {topic}" if topic else d

    # 강의 선택 (기본: 전체 선택)
    if "personalized_date_pending" in st.session_state:
        st.session_state["personalized_dates_selected"] = st.session_state.pop("personalized_date_pending")

    all_labels = list(date_label_map.values())
    selected_labels = st.multiselect(
        label="강의 날짜 선택",
        options=all_labels,
        default=st.session_state.get("personalized_dates_selected", all_labels),
        key="personalized_dates_selected",
    )

    # 선택된 라벨 → 날짜 역변환
    label_to_date = {v: k for k, v in date_label_map.items()}
    selected_dates = [label_to_date[l] for l in selected_labels if l in label_to_date]

    st.markdown("---")

    if st.button("🎯 개인화 학습 가이드 생성", disabled=not selected_dates):
        st.session_state.pop("personalized_guide", None)
        st.session_state["personalized_dates_used"] = selected_dates
        try:
            with st.spinner(f"오답 개념 {len(quiz_wrong)}개 관련 강의 섹션 검색 중..."):
                stream = stream_personalized_study_guide(quiz_wrong)
            guide = st.write_stream(stream)
            st.session_state["personalized_guide"] = guide
        except Exception as e:
            st.error(f"개인화 학습 가이드 생성 실패: {e}")
            return
        st.rerun()

    if st.session_state.get("personalized_guide"):
        used_dates = st.session_state.get("personalized_dates_used", [])
        label = ", ".join(used_dates[:3]) + ("..." if len(used_dates) > 3 else "")
        st.success(f"✅ [{label}] 개인화 학습 가이드 생성 완료!")
        _render_guide_result(
            st.session_state["personalized_guide"],
            label="개인화_" + "_".join(used_dates[:2]),
        )


# ══════════════════════════════════════════════════════════════════════════════
# 탭 4: 오답 노트
# ══════════════════════════════════════════════════════════════════════════════

def _render_wn_list() -> None:
    """오답 노트 목록 뷰."""
    entries = load_wrong_note()

    if not entries:
        st.info("저장된 오답이 없습니다. 복습 퀴즈를 완료하면 자동으로 저장됩니다.")
        return

    st.caption(f"총 {len(entries)}개 오답 문제 저장됨")

    # 날짜 필터
    all_dates = sorted({d for e in entries for d in e.get("lecture_dates", [])})
    if all_dates:
        filter_dates = st.multiselect(
            "강의 날짜 필터",
            options=all_dates,
            default=[],
            placeholder="전체 표시 (날짜 선택 시 해당 강의 오답만 표시)",
            key="wn_date_filter",
        )
        if filter_dates:
            entries = [e for e in entries if any(d in filter_dates for d in e.get("lecture_dates", []))]

    st.markdown("---")

    # 문제 목록 + 체크박스
    selected_ids = []
    for i, e in enumerate(entries):
        col_check, col_info = st.columns([0.5, 9.5])
        with col_check:
            checked = st.checkbox("선택", key=f"wn_check_{e['id']}", label_visibility="collapsed")
        with col_info:
            dates_label = ", ".join(e.get("lecture_dates", [])[:2])
            preview = e["question"][:70] + ("..." if len(e["question"]) > 70 else "")
            st.markdown(
                f"**Q{i+1}.** {preview}  \n"
                f"<span style='color:gray;font-size:0.85em'>"
                f"틀린 횟수: {e['wrong_count']}회 &nbsp;|&nbsp; "
                f"강의: {dates_label} &nbsp;|&nbsp; "
                f"마지막 시도: {e['last_tried_at'][:10]}"
                f"</span>",
                unsafe_allow_html=True,
            )
        if checked:
            selected_ids.append(e["id"])

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📚 선택 문제 다시 풀기", disabled=not selected_ids):
            selected = [e for e in entries if e["id"] in selected_ids]
            st.session_state["wn_data"] = to_quiz_format(selected)
            st.session_state["wn_idx"] = 0
            st.session_state["wn_answers"] = {}
            st.session_state["wn_checked"] = {}
            st.session_state.pop("wn_mastered_removed", None)
            st.session_state["wn_view"] = "quiz"
            st.rerun()
    with col2:
        if st.button("📚 전체 다시 풀기", disabled=not entries):
            st.session_state["wn_data"] = to_quiz_format(entries)
            st.session_state["wn_idx"] = 0
            st.session_state["wn_answers"] = {}
            st.session_state["wn_checked"] = {}
            st.session_state.pop("wn_mastered_removed", None)
            st.session_state["wn_view"] = "quiz"
            st.rerun()
    with col3:
        if st.button("🗑 선택 문제 삭제", disabled=not selected_ids):
            remove_mastered(selected_ids)
            st.success(f"{len(selected_ids)}개 삭제됐습니다.")
            st.rerun()


def _render_wn_quiz() -> None:
    """오답 노트 퀴즈 풀기 뷰."""
    quizzes = st.session_state.get("wn_data", [])
    if not quizzes:
        st.session_state["wn_view"] = "list"
        st.rerun()
        return

    if st.button("← 오답 목록으로"):
        st.session_state["wn_view"] = "list"
        st.rerun()
        return

    idx = st.session_state["wn_idx"]
    total = len(quizzes)

    st.progress((idx + 1) / total)
    st.caption(f"{idx + 1} / {total}")
    st.markdown("---")

    q = quizzes[idx]
    st.markdown(f"### Q{idx + 1}. {q['question']}")
    st.markdown("")

    is_checked = st.session_state["wn_checked"].get(idx, False)

    if q["type"] == "multiple_choice":
        opts = q.get("options", {})
        options_list = [f"{k}. {v}" for k, v in opts.items()]
        current_answer = st.session_state["wn_answers"].get(idx)
        default_idx = options_list.index(current_answer) if current_answer in options_list else 0
        chosen = st.radio(
            "선택지",
            options=options_list,
            index=default_idx,
            key=f"wn_answer_{idx}",
            disabled=is_checked,
        )
        if chosen:
            st.session_state["wn_answers"][idx] = chosen
        has_answer = bool(st.session_state["wn_answers"].get(idx))
    else:
        typed = st.text_input(
            "답 입력",
            value=st.session_state["wn_answers"].get(idx, ""),
            key=f"wn_answer_{idx}",
            placeholder="답을 입력하세요",
            disabled=is_checked,
        )
        st.session_state["wn_answers"][idx] = typed
        has_answer = bool(typed.strip())

    st.markdown("")

    if not is_checked:
        if st.button("확인", key="wn_confirm", disabled=not has_answer):
            st.session_state["wn_checked"][idx] = True
            st.rerun()
    else:
        user_ans = st.session_state["wn_answers"].get(idx, "")
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

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("◀ 이전", key="wn_prev", disabled=(idx == 0)):
            st.session_state["wn_idx"] -= 1
            st.rerun()
    with col_next:
        if st.button("다음 ▶", key="wn_next", disabled=(not is_checked or idx == total - 1)):
            st.session_state["wn_idx"] += 1
            st.rerun()

    # 최종 결과
    all_checked = all(st.session_state["wn_checked"].get(i, False) for i in range(total))
    if all_checked:
        st.markdown("---")
        mastered_ids = []
        correct_count = 0
        for i, qi in enumerate(quizzes):
            user_ans = st.session_state["wn_answers"].get(i, "")
            if qi["type"] == "multiple_choice":
                is_correct = bool(user_ans and user_ans.startswith(qi["answer"]))
            else:
                is_correct = bool(user_ans.strip() and qi["answer"].lower() in user_ans.lower())
            if is_correct:
                correct_count += 1
                if "_wn_id" in qi:
                    mastered_ids.append(qi["_wn_id"])

        score_pct = int(correct_count / total * 100)
        if score_pct >= 80:
            st.balloons()
            st.success(f"🎉 점수: {correct_count}/{total} ({score_pct}%) - 훌륭합니다!")
        elif score_pct >= 60:
            st.warning(f"📊 점수: {correct_count}/{total} ({score_pct}%) - 조금 더 복습해보세요.")
        else:
            st.error(f"📚 점수: {correct_count}/{total} ({score_pct}%) - 다시 한번 복습해보세요.")

        # 맞춘 문제 오답 노트에서 제거 (1회)
        if mastered_ids and not st.session_state.get("wn_mastered_removed"):
            remove_mastered(mastered_ids)
            st.session_state["wn_mastered_removed"] = True
            st.success(f"✅ 정답 맞춘 문제 {len(mastered_ids)}개를 오답 노트에서 제거했습니다.")

        st.markdown("")
        col_retry, col_back = st.columns(2)
        with col_retry:
            if st.button("🔄 다시 풀기", key="wn_retry"):
                st.session_state["wn_idx"] = 0
                st.session_state["wn_answers"] = {}
                st.session_state["wn_checked"] = {}
                st.session_state.pop("wn_mastered_removed", None)
                st.rerun()
        with col_back:
            if st.button("← 오답 목록으로", key="wn_back"):
                st.session_state["wn_view"] = "list"
                st.session_state.pop("wn_mastered_removed", None)
                st.rerun()


def render_wrong_note_tab() -> None:
    """탭 4: 오답 노트 진입점."""
    st.subheader("오답 노트")
    st.caption("퀴즈에서 틀린 문제가 자동 저장됩니다. 선택해서 다시 풀고, 맞추면 자동으로 제거됩니다.")

    for key, default in [
        ("wn_view", "list"),
        ("wn_data", []),
        ("wn_idx", 0),
        ("wn_answers", {}),
        ("wn_checked", {}),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    if st.session_state["wn_view"] == "list":
        _render_wn_list()
    elif st.session_state["wn_view"] == "quiz":
        _render_wn_quiz()


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
    # 체인 미리 초기화 (첫 가이드 요청 시 지연 제거)
    _get_cached_study_guide_chain()

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
    tab_quiz, tab_guide, tab_personalized, tab_wrong_note = st.tabs([
        "📝 복습 퀴즈",
        "📖 학습 가이드",
        "🎯 개인화 학습 가이드",
        "📒 오답 노트",
    ])

    with tab_quiz:
        render_quiz_tab(indexed_dates)

    with tab_guide:
        render_guide_tab(indexed_dates)

    with tab_personalized:
        render_personalized_tab()

    with tab_wrong_note:
        render_wrong_note_tab()


if __name__ == "__main__":
    main()
