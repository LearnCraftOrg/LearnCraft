"""퀴즈 생성 및 풀기 인터페이스."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.vectorstore.store import get_indexed_dates
from src.ingestion.loader import load_curriculum
from src.quiz.generator import generate_quiz

st.set_page_config(page_title="퀴즈 풀기", page_icon="📝", layout="wide")
st.title("📝 복습 퀴즈")

indexed_dates = get_indexed_dates()
curriculum_map = load_curriculum()

if not indexed_dates:
    st.warning("인덱싱된 강의가 없습니다. **강의 인덱싱** 페이지에서 먼저 인덱싱하세요.")
    st.stop()

# 날짜 선택
date_labels = {
    d: f"{d} | {curriculum_map.get(d, {}).get('subject', '')} - {curriculum_map.get(d, {}).get('content', '')[:30]}"
    for d in indexed_dates
}
selected_label = st.selectbox("강의 날짜 선택", options=list(date_labels.values()))
selected_date = [d for d, l in date_labels.items() if l == selected_label][0]

info = curriculum_map.get(selected_date, {})
st.caption(f"📌 학습 목표: {info.get('learning_goal', '-')}")

# 퀴즈 생성 버튼
if st.button("🎲 퀴즈 생성", type="primary"):
    with st.spinner("GPT-4o가 퀴즈를 생성 중입니다..."):
        try:
            result = generate_quiz(selected_date)
            st.session_state["quiz_data"] = result.get("quizzes", [])
            st.session_state["quiz_date"] = selected_date
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_submitted"] = False
        except Exception as e:
            st.error(f"퀴즈 생성 실패: {e}")

# 퀴즈 표시
if st.session_state.get("quiz_data") and st.session_state.get("quiz_date") == selected_date:
    quizzes = st.session_state["quiz_data"]
    submitted = st.session_state.get("quiz_submitted", False)
    answers = st.session_state.get("quiz_answers", {})

    st.divider()
    st.subheader(f"총 {len(quizzes)}문항")

    with st.form("quiz_form"):
        for i, q in enumerate(quizzes):
            q_num = i + 1
            st.markdown(f"**Q{q_num}. {q['question']}**")

            if q["type"] == "multiple_choice":
                opts = q.get("options", {})
                options_list = [f"{k}. {v}" for k, v in opts.items()]
                choice = st.radio(
                    label=f"q{q_num}_radio",
                    options=options_list,
                    index=None,
                    key=f"q{q_num}",
                    label_visibility="collapsed",
                    disabled=submitted,
                )
                answers[q_num] = choice
            else:
                user_ans = st.text_input(
                    label=f"q{q_num}_input",
                    placeholder="답을 입력하세요",
                    key=f"q{q_num}",
                    label_visibility="collapsed",
                    disabled=submitted,
                )
                answers[q_num] = user_ans

            # 제출 후 정답/해설 표시
            if submitted:
                correct_ans = q["answer"]
                user_ans = answers.get(q_num, "")

                if q["type"] == "multiple_choice":
                    is_correct = user_ans and user_ans.startswith(correct_ans)
                else:
                    is_correct = user_ans.strip() != "" and correct_ans.lower() in user_ans.lower()

                if is_correct:
                    st.success(f"✅ 정답! | 해설: {q['explanation']}")
                else:
                    st.error(f"❌ 오답 | 정답: {correct_ans} | 해설: {q['explanation']}")

            st.markdown("")

        if not submitted:
            if st.form_submit_button("✔ 제출", type="primary"):
                st.session_state["quiz_answers"] = answers
                st.session_state["quiz_submitted"] = True
                st.rerun()

    if submitted:
        # 점수 계산
        correct = 0
        for i, q in enumerate(quizzes):
            q_num = i + 1
            user_ans = answers.get(q_num, "")
            if q["type"] == "multiple_choice":
                if user_ans and user_ans.startswith(q["answer"]):
                    correct += 1
            else:
                if user_ans.strip() and q["answer"].lower() in user_ans.lower():
                    correct += 1

        st.divider()
        score_pct = int(correct / len(quizzes) * 100)
        if score_pct >= 80:
            st.balloons()
            st.success(f"🎉 점수: {correct}/{len(quizzes)} ({score_pct}%) - 훌륭합니다!")
        elif score_pct >= 60:
            st.warning(f"📊 점수: {correct}/{len(quizzes)} ({score_pct}%) - 조금 더 복습해보세요.")
        else:
            st.error(f"📚 점수: {correct}/{len(quizzes)} ({score_pct}%) - 학습 가이드를 참고하세요.")

        if st.button("🔄 다시 풀기"):
            st.session_state["quiz_submitted"] = False
            st.session_state["quiz_answers"] = {}
            st.rerun()
