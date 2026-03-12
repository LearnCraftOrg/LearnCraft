"""퀴즈 생성 및 풀기 인터페이스."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src.vectorstore.store import get_indexed_dates
from src.ingestion.loader import extract_stt_metadata
from src.quiz.generator import generate_quiz, generate_quiz_multi

st.set_page_config(page_title="퀴즈 풀기", page_icon="📝", layout="wide")
st.title("📝 복습 퀴즈")

indexed_dates = get_indexed_dates()

if not indexed_dates:
    st.warning("인덱싱된 강의가 없습니다. 홈 화면을 새로고침하세요.")
    st.stop()

# ── Session State 초기화 ─────────────────────────────────────
for key, default in [
    ("view", "selection"),
    ("quiz_data", []),
    ("quiz_selected_dates", []),
    ("quiz_user_query", ""),
    ("quiz_idx", 0),
    ("quiz_answers", {}),
    ("quiz_checked", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── 뷰 1: 강의 선택 ──────────────────────────────────────────
def render_selection_view():
    st.subheader("강의 선택")

    rows = []
    for date in indexed_dates:
        meta = extract_stt_metadata(date)
        topic = meta["content"][:60] if meta.get("content") else date
        rows.append({"선택": False, "날짜": date, "주제": topic})

    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", default=False),
            "날짜": st.column_config.TextColumn("날짜", disabled=True),
            "주제": st.column_config.TextColumn("주제", disabled=True),
        },
        use_container_width=True,
        hide_index=True,
        height=370,
        key="lecture_table",
    )
    selected_dates = edited.loc[edited["선택"] == True, "날짜"].tolist()

    st.divider()

    user_query = st.text_area(
        label="문제 생성 범위 (선택사항)",
        placeholder="문제 생성 주제를 입력하세요\n예) 특정 기간 내 범위에 대한 문제를 생성해줘",
        height=100,
        key="user_query_input",
    )

    can_submit = len(selected_dates) > 0 or bool(user_query.strip())

    if st.button("🎲 문제 생성", type="primary", disabled=not can_submit):
        st.session_state["quiz_selected_dates"] = selected_dates
        st.session_state["quiz_user_query"] = user_query.strip()
        st.session_state["view"] = "loading"
        st.rerun()


# ── 뷰 2: 로딩 ───────────────────────────────────────────────
def render_loading_view():
    st.markdown("## 퀴즈를 생성하고 있습니다...")

    dates = st.session_state["quiz_selected_dates"]
    query = st.session_state["quiz_user_query"]
    has_text = bool(query)

    with st.spinner("GPT-4o가 퀴즈를 생성 중입니다. 잠시만 기다려주세요..."):
        try:
            if len(dates) == 1 and not has_text:
                result = generate_quiz(dates[0])
            else:
                result = generate_quiz_multi(
                    dates=dates,
                    user_query=query if has_text else None,
                )
            st.session_state["quiz_data"] = result.get("quizzes", [])
        except Exception as e:
            st.error(f"퀴즈 생성 실패: {e}")
            if st.button("선택 화면으로 돌아가기"):
                st.session_state["view"] = "selection"
                st.rerun()
            return

    st.session_state["quiz_idx"] = 0
    st.session_state["quiz_answers"] = {}
    st.session_state["quiz_checked"] = {}
    st.session_state["view"] = "quiz"
    st.rerun()


# ── 뷰 3: 문제 풀기 (1문제씩) ────────────────────────────────
def render_quiz_view():
    quizzes = st.session_state["quiz_data"]
    if not quizzes:
        st.error("퀴즈 데이터가 없습니다.")
        if st.button("선택 화면으로"):
            st.session_state["view"] = "selection"
            st.rerun()
        return

    idx = st.session_state["quiz_idx"]
    total = len(quizzes)

    # 진행 표시
    st.progress((idx + 1) / total)
    st.caption(f"{idx + 1} / {total}")
    st.divider()

    q = quizzes[idx]
    st.markdown(f"### Q{idx + 1}. {q['question']}")
    st.markdown("")

    is_checked = st.session_state["quiz_checked"].get(idx, False)

    if q["type"] == "multiple_choice":
        opts = q.get("options", {})
        options_list = [f"{k}. {v}" for k, v in opts.items()]
        current_answer = st.session_state["quiz_answers"].get(idx)
        default_idx = None
        if current_answer and current_answer in options_list:
            default_idx = options_list.index(current_answer)
        chosen = st.radio(
            "선택지",
            options=options_list,
            index=default_idx,
            key=f"answer_{idx}",
            label_visibility="collapsed",
            disabled=is_checked,
        )
        if chosen:
            st.session_state["quiz_answers"][idx] = chosen
        has_answer = bool(st.session_state["quiz_answers"].get(idx))
    else:
        current_text = st.session_state["quiz_answers"].get(idx, "")
        typed = st.text_input(
            "답 입력",
            value=current_text,
            key=f"answer_{idx}",
            placeholder="답을 입력하세요",
            label_visibility="collapsed",
            disabled=is_checked,
        )
        st.session_state["quiz_answers"][idx] = typed
        has_answer = bool(typed.strip())

    st.markdown("")

    # 확인 버튼 / 결과 표시
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

    st.divider()

    # 이전 / 다음 버튼
    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("◀ 이전", disabled=(idx == 0), use_container_width=True):
            st.session_state["quiz_idx"] -= 1
            st.rerun()
    with col_next:
        next_disabled = not is_checked or idx == total - 1
        if st.button("다음 ▶", disabled=next_disabled, use_container_width=True):
            st.session_state["quiz_idx"] += 1
            st.rerun()

    # 최종 점수 (모든 문제 확인 완료 시)
    all_checked = all(st.session_state["quiz_checked"].get(i, False) for i in range(total))
    if all_checked:
        st.divider()
        correct_count = 0
        for i, q_item in enumerate(quizzes):
            ans = st.session_state["quiz_answers"].get(i, "")
            if q_item["type"] == "multiple_choice":
                if ans and ans.startswith(q_item["answer"]):
                    correct_count += 1
            else:
                if ans.strip() and q_item["answer"].lower() in ans.lower():
                    correct_count += 1

        score_pct = int(correct_count / total * 100)
        if score_pct >= 80:
            st.balloons()
            st.success(f"🎉 점수: {correct_count}/{total} ({score_pct}%) - 훌륭합니다!")
        elif score_pct >= 60:
            st.warning(f"📊 점수: {correct_count}/{total} ({score_pct}%) - 조금 더 복습해보세요.")
        else:
            st.error(f"📚 점수: {correct_count}/{total} ({score_pct}%) - 학습 가이드를 참고하세요.")

        st.markdown("")
        col_retry, col_new = st.columns(2)
        with col_retry:
            if st.button("🔄 다시 풀기", use_container_width=True):
                st.session_state["quiz_idx"] = 0
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_checked"] = {}
                st.rerun()
        with col_new:
            if st.button("✏️ 새 문제 생성", use_container_width=True):
                st.session_state["view"] = "selection"
                st.session_state["quiz_data"] = []
                st.session_state["quiz_idx"] = 0
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_checked"] = {}
                st.rerun()


# ── 뷰 디스패치 ──────────────────────────────────────────────
view = st.session_state["view"]

if view == "selection":
    render_selection_view()
elif view == "loading":
    render_loading_view()
elif view == "quiz":
    render_quiz_view()
