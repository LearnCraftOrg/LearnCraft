"""퀴즈 생성 및 풀기 인터페이스."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time

import pandas as pd
import streamlit as st

from src.vectorstore.store import get_indexed_dates
from src.ingestion.loader import load_lecture_topics
from src.rag.pipeline import build_context_by_date, build_context_by_query
from src.quiz.generator import generate_quiz_from_context, generate_quiz_multi_from_context
from src.quiz.scoring import evaluate_short_answer
from src.quiz.code_runner import fill_and_run
from app.styles import inject_global_css, render_step_indicator

st.set_page_config(page_title="퀴즈 풀기", page_icon="📝", layout="wide")
inject_global_css()
st.title("복습 퀴즈")

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
    ("quiz_difficulty", "medium"),
    ("quiz_idx", 0),
    ("quiz_answers", {}),
    ("quiz_checked", {}),
    ("quiz_eval_results", {}),
    ("quiz_code_run_details", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── 뷰 1: 강의 선택 ──────────────────────────────────────────
def render_selection_view():
    render_step_indicator(1)
    st.subheader("강의 선택")

    rows = []
    for date in indexed_dates:
        topic = load_lecture_topics(date) or date
        rows.append({"선택": False, "날짜": date, "주제": topic})

    df = pd.DataFrame(rows)

    row_height = 35
    header_height = 38
    dynamic_height = max(150, header_height + row_height * len(df))

    edited = st.data_editor(
        df,
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", default=False, width=60),
            "날짜": st.column_config.TextColumn("날짜", disabled=True, width=130),
            "주제": st.column_config.TextColumn("주제", disabled=True),
        },
        use_container_width=True,
        hide_index=True,
        height=dynamic_height,
        key="lecture_table",
    )
    selected_dates = edited.loc[edited["선택"] == True, "날짜"].tolist()

    st.divider()

    difficulty = st.radio(
        "난이도",
        options=["easy", "medium", "hard"],
        format_func=lambda x: {"easy": "쉬움", "medium": "보통", "hard": "어려움"}[x],
        index=1,
        horizontal=True,
        key="difficulty_radio",
    )

    user_query = st.text_area(
        label="문제 생성 범위 (선택사항)",
        placeholder="문제 생성 주제를 입력하세요\n예) 특정 기간 내 범위에 대한 문제를 생성해줘",
        height=100,
        key="user_query_input",
    )

    can_submit = len(selected_dates) > 0 or bool(user_query.strip())

    if st.button("문제 생성", type="primary", disabled=not can_submit):
        st.session_state["quiz_selected_dates"] = selected_dates
        st.session_state["quiz_user_query"] = user_query.strip()
        st.session_state["quiz_difficulty"] = difficulty
        st.session_state["view"] = "loading"
        st.rerun()


# ── 뷰 2: 로딩 ───────────────────────────────────────────────
def render_loading_view():
    render_step_indicator(2)

    st.markdown(
        '<p style="text-align:center;font-size:1.1rem;color:#6b7280;margin:2rem 0 1rem;">퀴즈를 생성하고 있습니다...</p>',
        unsafe_allow_html=True,
    )

    # 이미 생성된 결과가 있으면 스킵
    if st.session_state.get("quiz_result_cache"):
        result = st.session_state["quiz_result_cache"]
        st.session_state["quiz_data"] = result.get("quizzes", [])
        st.session_state["quiz_idx"] = 0
        st.session_state["quiz_answers"] = {}
        st.session_state["quiz_checked"] = {}
        st.session_state["quiz_eval_results"] = {}
        st.session_state["quiz_code_run_details"] = {}
        st.session_state["quiz_result_cache"] = None
        st.session_state["view"] = "quiz"
        st.rerun()
        return

    dates = st.session_state["quiz_selected_dates"]
    query = st.session_state["quiz_user_query"]
    difficulty = st.session_state["quiz_difficulty"]
    has_text = bool(query)
    is_single = len(dates) == 1 and not has_text

    with st.status("퀴즈 준비 중...", expanded=True) as status:
        msg = st.empty()
        try:
            msg.write("문서 불러오는 중...")
            t0 = time.perf_counter()
            if is_single:
                ctx = build_context_by_date(dates[0])
            else:
                ctx = build_context_by_query(dates, query if has_text else None)
            print(f"[TIMING] build_context: {time.perf_counter()-t0:.2f}s")

            msg.write("GPT-4o mini로 문제 생성 중...")
            t1 = time.perf_counter()
            if is_single:
                result = generate_quiz_from_context(ctx, difficulty=difficulty)
                st.session_state["quiz_result_cache"] = result
                status.update(label="퀴즈 준비 완료!", state="complete")
            else:
                result = generate_quiz_multi_from_context(ctx, query if has_text else None, difficulty=difficulty)
            print(f"[TIMING] generate_quiz: {time.perf_counter()-t1:.2f}s")

            msg.empty()
            status.update(label="퀴즈 준비 완료!", state="complete")
        except Exception as e:
            status.update(label="생성 실패", state="error")
            st.error(f"퀴즈 생성 실패: {e}")
            if st.button("선택 화면으로 돌아가기"):
                st.session_state["view"] = "selection"
                st.rerun()
            return

    st.session_state["quiz_data"] = result.get("quizzes", [])
    st.session_state["quiz_idx"] = 0
    st.session_state["quiz_answers"] = {}
    st.session_state["quiz_checked"] = {}
    st.session_state["quiz_eval_results"] = {}
    st.session_state["quiz_code_run_details"] = {}
    st.session_state["view"] = "quiz"
    st.rerun()


# ── code_completion 빈칸 입력 렌더링 ─────────────────────────
def _render_code_completion_inputs(q: dict, idx: int, is_checked: bool) -> bool:
    """code_completion 퀴즈의 코드 표시 및 빈칸 입력 위젯 렌더링.

    Returns:
        has_answer: 모든 빈칸이 채워졌는지 여부
    """
    code_template = q.get("code_template", "")
    n_blanks = code_template.count("___")

    lang = q.get("language", "python")
    st.code(code_template, language=lang)

    if n_blanks == 0:
        st.warning("코드 템플릿에 빈칸(___)이 없습니다.")
        return False

    cols = st.columns(n_blanks) if n_blanks > 1 else [st]
    for i, col in enumerate(cols):
        col.text_input(
            f"빈칸 {i + 1}",
            key=f"code_blank_{idx}_{i}",
            placeholder=f"빈칸 {i + 1}",
            disabled=is_checked,
        )

    return all(
        bool(st.session_state.get(f"code_blank_{idx}_{i}", "").strip())
        for i in range(n_blanks)
    )


def _show_explanation(explanation: str):
    """해설을 이모지 파트별 색상 카드로 렌더링."""
    import re
    parts = [p.strip() for p in explanation.split("|") if p.strip()]
    for part in parts:
        if part.startswith("✅"):
            bg, border, color = "#f0fdf4", "#86efac", "#166534"
            st.markdown(
                f'<div style="background:{bg};border:1px solid {border};border-radius:10px;'
                f'padding:14px 18px;margin-top:8px;font-size:0.88rem;color:{color};line-height:1.75;">'
                f'{part}</div>',
                unsafe_allow_html=True,
            )
        elif part.startswith("❌"):
            bg, border = "#fff7f7", "#fca5a5"
            prefix_end = part.find(":") + 1
            prefix = part[:prefix_end]
            body = part[prefix_end:].strip()
            items = re.split(r",\s*(?=[A-D]-)", body)
            rows_html = "".join(
                f'<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid #fee2e2;">'
                f'<span style="font-weight:700;min-width:20px;">{item.split("-")[0].strip()}</span>'
                f'<span>{"−".join(item.split("-")[1:]).strip()}</span></div>'
                if "-" in item else
                f'<div style="padding:5px 0;border-bottom:1px solid #fee2e2;">{item.strip()}</div>'
                for item in items if item.strip()
            )
            st.markdown(
                f'<div style="background:{bg};border:1px solid {border};border-radius:10px;'
                f'padding:14px 18px;margin-top:8px;font-size:0.88rem;color:#7f1d1d;">'
                f'<div style="font-weight:600;margin-bottom:8px;">{prefix}</div>'
                f'{rows_html}</div>',
                unsafe_allow_html=True,
            )
        elif part.startswith("📌"):
            bg, border, color = "#eff6ff", "#93c5fd", "#1e40af"
            st.markdown(
                f'<div style="background:{bg};border:1px solid {border};border-radius:10px;'
                f'padding:14px 18px;margin-top:8px;font-size:0.88rem;color:{color};line-height:1.75;">'
                f'{part}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;'
                f'padding:14px 18px;margin-top:8px;font-size:0.88rem;color:#374151;line-height:1.75;">'
                f'{part}</div>',
                unsafe_allow_html=True,
            )


# ── 뷰 3: 문제 풀기 (1문제씩) ────────────────────────────────
def render_quiz_view():
    quizzes = st.session_state["quiz_data"]
    if not quizzes:
        st.error("퀴즈 데이터가 없습니다.")
        if st.button("선택 화면으로"):
            st.session_state["view"] = "selection"
            st.rerun()
        return

    render_step_indicator(3)

    # 강의 출처 표시
    selected_dates = st.session_state.get("quiz_selected_dates", [])
    if selected_dates:
        dates_str = ", ".join(selected_dates)
        st.caption(f"강의: {dates_str}")

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
    elif q["type"] == "short_answer":
        current_text = st.session_state["quiz_answers"].get(idx, "")
        typed: str = st.text_input(
            "답 입력",
            value=current_text,
            key=f"answer_{idx}",
            placeholder="답을 입력하세요",
            label_visibility="collapsed",
            disabled=is_checked,
        )
        st.session_state["quiz_answers"][idx] = typed
        has_answer = bool(typed.strip())
    else:  # code_completion
        typed = ""
        has_answer = _render_code_completion_inputs(q, idx, is_checked)

    st.markdown("")

    # 확인 버튼 / 결과 표시
    if not is_checked:
        if q["type"] == "code_completion":
            if st.button("실행 및 채점", disabled=not has_answer, key=f"run_{idx}"):
                n_blanks = q["code_template"].count("___")
                user_inputs = [
                    st.session_state.get(f"code_blank_{idx}_{i}", "")
                    for i in range(n_blanks)
                ]
                with st.spinner("코드 실행 중..."):
                    run_result = fill_and_run(
                        q["code_template"], user_inputs, q.get("expected_output") or "",
                        language=q.get("language", "python"),
                    )
                st.session_state["quiz_eval_results"][idx] = run_result["is_correct"]
                st.session_state["quiz_code_run_details"][idx] = run_result
                st.session_state["quiz_checked"][idx] = True
                st.rerun()
        else:
            if st.button("확인", disabled=not has_answer):
                st.session_state["quiz_checked"][idx] = True
                if q["type"] == "short_answer":
                    with st.spinner("답안 평가 중..."):
                        result = evaluate_short_answer(
                            question=q["question"],
                            correct_answer=q["answer"],
                            user_answer=typed,
                            explanation=q["explanation"],
                        )
                    st.session_state["quiz_eval_results"][idx] = result
                st.rerun()
    else:
        user_ans = st.session_state["quiz_answers"].get(idx, "")
        correct_ans = q["answer"]

        if q["type"] == "multiple_choice":
            is_correct = bool(user_ans and user_ans.startswith(correct_ans))
            if is_correct:
                st.success("정답!")
            else:
                st.error(f"오답  |  정답: **{correct_ans}**")
            _show_explanation(q["explanation"])
        elif q["type"] == "code_completion":
            run_details = st.session_state["quiz_code_run_details"].get(idx, {})
            is_correct = st.session_state["quiz_eval_results"].get(idx, False)
            if run_details.get("stdout"):
                st.code(run_details["stdout"], language="text")
            if is_correct:
                st.success("정답! 실행 결과가 일치합니다")
            else:
                stderr = run_details.get("stderr", "")
                if stderr:
                    st.error(f"실행 오류: {stderr}")
                else:
                    st.error(
                        f"출력 불일치\n\n"
                        f"기대값: `{q['expected_output']}`\n\n"
                        f"실행 결과: `{run_details.get('stdout', '')}`"
                    )
            _show_explanation(q["explanation"])
            st.caption(
                f"실행 시간: {run_details.get('exec_time', 'N/A')} "
                f"| 상태: {run_details.get('status', '')}"
            )
        else:  # short_answer
            is_correct = st.session_state["quiz_eval_results"].get(idx, False)
            if is_correct:
                st.success("정답!")
            else:
                st.error(f"오답  |  정답: **{correct_ans}**")
            _show_explanation(q["explanation"])

    st.divider()

    # 이전 / 다음 버튼
    is_last = idx == total - 1
    all_checked = all(st.session_state["quiz_checked"].get(i, False) for i in range(total))

    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("이전", disabled=(idx == 0), use_container_width=True):
            st.session_state["quiz_idx"] -= 1
            st.rerun()
    with col_next:
        if is_last and is_checked and all_checked:
            if st.button("결과 보기", type="primary", use_container_width=True):
                st.session_state["view"] = "score"
                st.rerun()
        else:
            next_disabled = not is_checked or is_last
            if st.button("다음", disabled=next_disabled, use_container_width=True):
                st.session_state["quiz_idx"] += 1
                st.rerun()


# ── 뷰 4: 점수 화면 ──────────────────────────────────────────
def render_score_view():
    quizzes = st.session_state["quiz_data"]
    total = len(quizzes)

    correct_count = 0
    results = []
    type_labels = {"multiple_choice": "객관식", "short_answer": "단답형", "code_completion": "코드완성"}

    for i, q_item in enumerate(quizzes):
        ans = st.session_state["quiz_answers"].get(i, "")
        if q_item["type"] == "multiple_choice":
            is_correct = bool(ans and ans.startswith(q_item["answer"]))
        else:
            is_correct = st.session_state["quiz_eval_results"].get(i, False)
        if is_correct:
            correct_count += 1
        results.append({
            "번호": i + 1,
            "유형": type_labels.get(q_item["type"], q_item["type"]),
            "정오": "O" if is_correct else "X",
        })

    score_pct = int(correct_count / total * 100)

    # 점수 헤더
    if score_pct >= 80:
        color = "#16a34a"
        msg = "훌륭합니다!"
    elif score_pct >= 60:
        color = "#d97706"
        msg = "조금 더 복습해보세요."
    else:
        color = "#dc2626"
        msg = "학습 가이드를 참고하세요."

    st.markdown(
        f'<div style="text-align:center;padding:32px 0 16px;">'
        f'  <div style="font-size:3.5rem;font-weight:800;color:{color};">{score_pct}%</div>'
        f'  <div style="font-size:1.2rem;color:#374151;margin-top:4px;">{correct_count} / {total} 정답  —  {msg}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # 문항별 결과 테이블
    st.subheader("문항별 결과")
    result_df = pd.DataFrame(results)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    st.markdown("")

    col_retry, col_new = st.columns(2)
    with col_retry:
        if st.button("다시 풀기", use_container_width=True):
            st.session_state["quiz_idx"] = 0
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_checked"] = {}
            st.session_state["quiz_eval_results"] = {}
            st.session_state["quiz_code_run_details"] = {}
            st.session_state["view"] = "quiz"
            st.rerun()
    with col_new:
        if st.button("새 문제 생성", type="primary", use_container_width=True):
            st.session_state["view"] = "selection"
            st.session_state["quiz_data"] = []
            st.session_state["quiz_idx"] = 0
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_checked"] = {}
            st.session_state["quiz_eval_results"] = {}
            st.session_state["quiz_code_run_details"] = {}
            st.rerun()


# ── 뷰 디스패치 ──────────────────────────────────────────────
view = st.session_state["view"]

if view == "selection":
    render_selection_view()
elif view == "loading":
    render_loading_view()
elif view == "quiz":
    render_quiz_view()
elif view == "score":
    render_score_view()
