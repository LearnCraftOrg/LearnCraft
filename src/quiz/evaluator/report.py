import re
import sys
import json
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import QUIZ_EVAL_DIR, QUIZ_REPORT_DIR, GENERATED_QUIZ_DIR
from src.quiz.evaluator.duplicate import THRESHOLD_DUPLICATE_WARN, THRESHOLD_DUPLICATE_FAIL


def _badge(text: str, color: str) -> str:
    colors = {
        "green":  ("#dcfce7", "#166534"),
        "red":    ("#fee2e2", "#991b1b"),
        "yellow": ("#fef9c3", "#854d0e"),
        "gray":   ("#f3f4f6", "#4b5563"),
    }
    bg, fg = colors.get(color, ("#f3f4f6", "#4b5563"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:20px;font-size:0.75em;font-weight:700;letter-spacing:0.04em;">{text}</span>'
    )


def _pass_badge(passed: bool) -> str:
    return _badge("PASS", "green") if passed else _badge("FAIL", "red")


def _eval_cell(passed, reason: str) -> str:
    if passed is None:
        return "<span style='color:#9ca3af;font-size:0.85em;'>N/A</span>"
    if passed:
        return f"<span style='color:#16a34a;font-size:0.85em;'>✓ {reason}</span>"
    return f"<span style='color:#dc2626;font-size:0.85em;'>✗ {reason}</span>"


def _source_chunks_html(quiz_obj: dict, source_map: dict) -> str:
    source_chunks_bm25 = quiz_obj.get("source_chunks_bm25")
    if source_chunks_bm25 is None:
        raw_ids = quiz_obj.get("source_chunk_ids") or []
        if not raw_ids:
            legacy_id = quiz_obj.get("source_chunk_id")
            raw_ids = [legacy_id] if legacy_id else []
        source_chunks_bm25 = [{"chunk_id": sid, "bm25_score": None} for sid in raw_ids]
    source_chunks_bm25 = sorted(
        source_chunks_bm25,
        key=lambda m: m.get("bm25_score") or 0,
        reverse=True,
    )
    html = ""
    for idx, chunk_info in enumerate(source_chunks_bm25):
        sid = chunk_info["chunk_id"]
        bm25_score = chunk_info.get("bm25_score")
        score_str = f" · BM25 {bm25_score:.4f}" if bm25_score is not None else ""
        content = source_map.get(sid, "(근거 청크 없음)")
        html += f"""
            <details style="font-size:0.83em;margin-bottom:6px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
                <summary style="cursor:pointer;color:#3b82f6;padding:6px 10px;background:#f8fafc;user-select:none;">참조 청크 {idx+1} <span style="color:#94a3b8;font-size:0.9em;">{sid[:8]}…{score_str}</span></summary>
                <pre style="white-space:pre-wrap;margin:0;padding:10px 12px;background:#fff;font-family:inherit;font-size:0.95em;color:#374151;border-top:1px solid #e2e8f0;">{content}</pre>
            </details>
        """
    return html


def _parse_explanation(explanation: str) -> tuple[str, dict, str]:
    """
    해설에서 정답 근거, 오답별 이유, 핵심 포인트 파싱.

    Returns:
        (correct_reason, {"A": "이유", ...}, key_point)
    """
    correct_reason = ""
    distractor_reasons = {}
    key_point = ""

    # ✅ 정답 근거 파싱
    m = re.search(r"✅ 정답 근거:\s*(.*?)(?=\||📌|❌|$)", explanation, re.DOTALL)
    if m:
        correct_reason = m.group(1).strip()

    # 📌 핵심 포인트 파싱
    m = re.search(r"📌 핵심 포인트:\s*(.*?)(?=\||✅|❌|$)", explanation, re.DOTALL)
    if m:
        key_point = m.group(1).strip()

    # ❌ 오답 함정 파싱
    m = re.search(r"❌ 오답 함정:\s*(.*?)(?=\||✅|📌|$)", explanation, re.DOTALL)
    if m:
        distractor_text = m.group(1).strip()
        # A-이유 또는 A는 이유 패턴 모두 처리
        for dm in re.finditer(r"\b([A-D])(?:[–\-]|는|:)\s*(.+?)(?=(?:,\s*)?[A-D](?:[–\-]|는|:)|$)", distractor_text, re.DOTALL):
            distractor_reasons[dm.group(1)] = dm.group(2).strip().rstrip(",").strip()

    return correct_reason, distractor_reasons, key_point


def _options_html(quiz_obj: dict, show_explanation: bool = False) -> str:
    options = quiz_obj.get("options", {})
    answer = quiz_obj.get("answer", "")
    explanation = quiz_obj.get("explanation", "")
    if not options:
        return ""

    correct_reason, distractor_reasons, _ = _parse_explanation(explanation) if show_explanation else ("", {}, "")

    html = "<div style='margin-top:8px;display:flex;flex-direction:column;gap:4px;'>"
    for k, v in options.items():
        is_ans = k == answer
        bg = "#f0fdf4" if is_ans else "#f9fafb"
        border = "#86efac" if is_ans else "#e5e7eb"
        color = "#15803d" if is_ans else "#374151"
        weight = "600" if is_ans else "normal"

        if show_explanation:
            reason = correct_reason if is_ans else distractor_reasons.get(k, "")
            reason_html = (
                f"<div style='font-size:0.8em;color:{'#16a34a' if is_ans else '#6b7280'};margin-top:3px;padding-left:6px;border-left:2px solid {'#86efac' if is_ans else '#d1d5db'};'>{reason}</div>"
                if reason else ""
            )
        else:
            reason_html = ""

        html += f"<div style='padding:5px 8px;background:{bg};color:{color};font-weight:{weight};border-radius:5px;border:1px solid {border};font-size:0.84em;'><b>{k}.</b> {v}{reason_html}</div>"
    html += "</div>"
    return html


def _short_answer_html(quiz_obj: dict) -> str:
    answer = quiz_obj.get("answer", "")
    explanation = quiz_obj.get("explanation", "")
    correct_reason, _, key_point = _parse_explanation(explanation)

    ans_box = f"""
    <div style='padding:5px 8px;background:#f0fdf4;color:#15803d;font-weight:600;border-radius:5px;border:1px solid #86efac;font-size:0.84em;'>
        <b>정답:</b> {answer}
        {f"<div style='font-size:0.95em;color:#16a34a;margin-top:3px;padding-left:6px;border-left:2px solid #86efac;font-weight:normal;'>{correct_reason}</div>" if correct_reason else ""}
    </div>"""
    
    kp_box = ""
    if key_point:
        kp_box = f"""
        <div style='margin-top:4px;padding:5px 8px;background:#f9fafb;color:#475569;border-radius:5px;border:1px solid #e5e7eb;font-size:0.84em;'>
            <b>📌 핵심 포인트:</b> {key_point}
        </div>"""

    return f"<div style='margin-top:8px;'>{ans_box}{kp_box}</div>"


# ── 섹션별 렌더링 ─────────────────────────────────────────────────────────────

def _render_structural(result: dict) -> str:
    if result is None:
        return "<p>평가 스킵</p>"

    item_results = result.get("item_results", [])
    failed_items = [(i+1, item) for i, item in enumerate(item_results) if not item["pass"]]
    pass_nums = [i+1 for i, item in enumerate(item_results) if item["pass"]]

    set_errors_html = "".join(f'<li style="color:#dc2626;">✗ {e}</li>' for e in result.get("set_errors", []))
    set_warnings_html = "".join(f'<li style="color:#d97706;">⚠ {w}</li>' for w in result.get("set_warnings", []))
    set_issues = f'<ul style="margin:6px 0 0 0;padding-left:16px;">{set_errors_html}{set_warnings_html}</ul>' if set_errors_html or set_warnings_html else '<span class="ok-text">이상 없음</span>'

    if pass_nums:
        pass_str = ", ".join(f"Q{n}" for n in pass_nums)
        item_pass_summary = f'<span class="ok-text">{pass_str} — 이상 없음</span>'
    else:
        item_pass_summary = ""

    rows = ""
    for i, item in failed_items:
        errors = "".join(f"<li style='color:#dc2626;'>✗ {e}</li>" for e in item["errors"])
        warnings = "".join(f"<li style='color:#d97706;'>⚠ {w}</li>" for w in item["warnings"])
        rows += f"""
        <tr>
            <td class="num-cell">Q{i}</td>
            <td>{_pass_badge(False)}</td>
            <td><ul style="margin:0;padding-left:16px;">{errors}{warnings}</ul>
                <span class="id-text">ID: {item['quiz_id'][:8]}…</span></td>
        </tr>"""

    fail_table = f"""
        <table style="margin-top:8px;">
            <thead><tr><th style="width:48px;">번호</th><th style="width:70px;">결과</th><th>상세</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>""" if failed_items else ""

    return f"""
    <div class="card">
        <div class="card-header">
            <span class="section-num">1</span>
            <span class="section-title">구조적 유효성</span>
            {_pass_badge(result['pass'])}
        </div>
        <div class="card-body">
            <div class="check-group">
                <div class="check-label">세트</div>
                <div class="check-desc">총 문항 수(10개) · MCQ 7 / 단답형 3 · 난이도별 유형 분포 · 정답 분포(A/B/C/D) 균형</div>
                <div class="check-result">{set_issues}</div>
            </div>
            <div class="check-group">
                <div class="check-label">개별 문항</div>
                <div class="check-desc">필수 필드 존재 여부 · MCQ 선택지 A~D · 근거 청크 유효성</div>
                <div class="check-result">{item_pass_summary}{fail_table}</div>
            </div>
        </div>
    </div>"""


def _render_grounding(result: dict, quizzes: list[dict], sources: list[dict]) -> str:
    if result is None:
        return """<div class="card"><div class="card-header"><span class="section-num">2</span><span class="section-title">Grounding + 해설 품질</span><span class="skip-badge">스킵</span></div></div>"""

    quiz_map = {q["quiz_id"]: q for q in quizzes}
    source_map = {s["chunk_id"]: s["content"] for s in sources}

    rows = ""
    for i, item in enumerate(result.get("item_results", []), 1):
        quiz_id = item["quiz_id"]
        errors_list = item.get("errors", [])
        warnings_list = item.get("warnings", [])

        if errors_list:
            status = _badge("FAIL", "red")
        elif warnings_list:
            status = _badge("WARN", "yellow")
        else:
            status = _badge("PASS", "green")

        quiz_obj = quiz_map.get(quiz_id, {})
        question = quiz_obj.get("question", "(질문 없음)")
        answer = quiz_obj.get("answer", "")
        options = quiz_obj.get("options", {})
        quiz_type = quiz_obj.get("type", "")
        explanation = quiz_obj.get("explanation", "")

        answer_text = options.get(answer, answer) if quiz_type == "multiple_choice" else answer

        source_chunks_bm25 = quiz_obj.get("source_chunks_bm25")
        if source_chunks_bm25 is None:
            raw_ids = quiz_obj.get("source_chunk_ids") or []
            if not raw_ids:
                legacy_id = quiz_obj.get("source_chunk_id")
                raw_ids = [legacy_id] if legacy_id else []
            source_chunks_bm25 = [{"chunk_id": sid, "bm25_score": None} for sid in raw_ids]
        source_chunks_bm25 = sorted(source_chunks_bm25, key=lambda m: m.get("bm25_score") or 0, reverse=True)
        source_chunk_ids = [m["chunk_id"] for m in source_chunks_bm25]

        sources_html = _source_chunks_html(quiz_obj, source_map)
        opts_html = _options_html(quiz_obj, show_explanation=True)

        grounding_pass = item.get("grounding_pass")
        grounding_reason = item.get("grounding_reason") or ""
        explanation_pass = item.get("explanation_pass")
        explanation_reason = item.get("explanation_reason") or ""

        errors_html = "".join(f"<li style='color:#dc2626;'>✗ {e}</li>" for e in errors_list)
        warnings_html = "".join(f"<li style='color:#d97706;'>⚠ {w}</li>" for w in warnings_list)
        detail = f"<ul style='margin:6px 0 0 0;padding-left:16px;'>{errors_html}{warnings_html}</ul>" if errors_html or warnings_html else ""

        rows += f"""
        <div class="g-item">
            <div class="g-item-header">
                <span class="num-cell" style="width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:#f1f5f9;font-size:0.8em;">Q{i}</span>
                {status}
                <span class="id-text">ID: {quiz_id[:8]}…</span>
            </div>
            <div class="g-question-box">
                <div style="font-size:0.88em;font-weight:600;color:#1e293b;margin-bottom:8px;">{question}</div>
                {opts_html}
                {_short_answer_html(quiz_obj) if quiz_type == "short_answer" else ""}
            </div>
            <div class="g-eval-row">
                <div class="g-eval-cell">
                    <div class="g-eval-label">Grounding</div>
                    <div>{_eval_cell(grounding_pass, grounding_reason)}</div>
                </div>
                <div class="g-eval-cell">
                    <div class="g-eval-label">해설 품질</div>
                    <div>{_eval_cell(explanation_pass, explanation_reason)}</div>
                </div>
                <div class="g-eval-cell g-eval-cell--wide">
                    <div class="g-eval-label">근거 원문</div>
                    {sources_html if sources_html else '<span class="id-text">청크 없음</span>'}
                </div>
            </div>
        </div>"""

    return f"""
    <div class="card">
        <div class="card-header">
            <span class="section-num">2</span>
            <span class="section-title">Grounding + 해설 품질</span>
            {_pass_badge(result.get('pass', False))}
        </div>
        <div class="g-list">{rows}</div>
    </div>"""


def _render_distractor(result: dict, quizzes: list[dict], sources: list[dict]) -> str:
    if result is None:
        return """<div class="card"><div class="card-header"><span class="section-num">3</span><span class="section-title">Distractor 품질</span><span class="skip-badge">스킵</span></div></div>"""

    quiz_map = {q["quiz_id"]: q for q in quizzes}
    source_map = {s["chunk_id"]: s["content"] for s in sources}

    rows = ""
    for i, item in enumerate(result.get("item_results", []), 1):
        if item.get("skipped"):
            continue

        status = _badge("PASS", "green") if item["pass"] else _badge("FAIL", "red")
        errors = "".join(f"<li style='color:#dc2626;'>✗ {e}</li>" for e in item.get("errors", []))

        quiz_obj = quiz_map.get(item['quiz_id'], {})
        options = quiz_obj.get("options", {})

        distractor_detail = ""
        for key, dr in item.get("distractor_results", {}).items():
            score = dr.get("max_score", "N/A")
            cov = dr.get("coverage_ratio", 0.0)
            uncovered = dr.get("uncovered_words", [])
            pass_status = dr.get("pass")
            matched_chunk = dr.get("matched_chunk_id")

            color = "#16a34a" if pass_status else "#dc2626"
            icon = "✓" if pass_status else "✗"
            text = options.get(key, "(텍스트 없음)")
            cov_str = f"{cov*100:.0f}%"
            uncovered_str = f" · 미매칭: <span style='color:#dc2626;'>{', '.join(uncovered)}</span>" if uncovered else ""

            if matched_chunk and matched_chunk in source_map:
                s_content = source_map[matched_chunk]
                match_html = f"""
                <details style="font-size:0.83em;margin-top:4px;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden;">
                    <summary style="cursor:pointer;color:#3b82f6;padding:5px 8px;background:#f8fafc;user-select:none;">매칭 원문 <span style="color:#94a3b8;font-size:0.9em;">BM25: {score} · 커버리지: {cov_str}{uncovered_str}</span></summary>
                    <pre style="white-space:pre-wrap;margin:0;padding:10px 12px;font-family:inherit;font-size:0.95em;color:#374151;border-top:1px solid #e2e8f0;">{s_content}</pre>
                </details>"""
            else:
                match_html = f"<span style='font-size:0.82em;color:#94a3b8;'>(BM25: {score} · {cov_str}{uncovered_str})</span>"

            distractor_detail += f"<li style='color:{color};margin-bottom:8px;'><b>{icon} 오답 {key}.</b> {text}{match_html}</li>"

        detail = f"<ul style='margin:0;padding-left:16px;'>{errors}{distractor_detail}</ul>" if errors or distractor_detail else "<span class='ok-text'>이상 없음</span>"
        rows += f"""
        <tr>
            <td class="num-cell">{i}</td>
            <td style="text-align:center;white-space:nowrap;">{status}</td>
            <td>{detail}<div class="id-text" style="margin-top:4px;">ID: {item['quiz_id'][:8]}…</div></td>
        </tr>"""

    return f"""
    <div class="card">
        <div class="card-header">
            <span class="section-num">3</span>
            <span class="section-title">Distractor 품질</span>
            {_pass_badge(result['pass'])}
        </div>
        <div class="card-body" style="padding:0;">
        <table>
            <thead><tr><th style="width:36px;">#</th><th style="width:70px;">결과</th><th>상세</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        </div>
    </div>"""


def _render_duplicate(result: dict, quiz_id_to_num: dict, quizzes: list[dict] = None) -> str:
    if result is None:
        return """<div class="card"><div class="card-header"><span class="section-num">4</span><span class="section-title">의미적 중복</span><span class="skip-badge">스킵</span></div></div>"""

    quiz_map = {q["quiz_id"]: q for q in (quizzes or [])}
    
    def _answer_text(qid):
        q = quiz_map.get(qid, {})
        ans = q.get("answer", "")
        opts = q.get("options", {})
        if opts:
            return f"{ans}. {opts.get(ans, '')}"
        return ans

    def _pair_html(pair, status, color):
        num_a = quiz_id_to_num.get(pair['quiz_id_a'], "?")
        num_b = quiz_id_to_num.get(pair['quiz_id_b'], "?")
        ans_a = _answer_text(pair['quiz_id_a'])
        ans_b = _answer_text(pair['quiz_id_b'])
        
        # WARN 상태일 때만 연한 노란색 배경 적용
        bg = "#fffbeb" if status == "WARN" else "#ffffff"
        border_inner = "#fef3c7" if status == "WARN" else "#f3f4f6"

        return f"""
        <div class="pair-card" style="border-left:4px solid {color}; background: {bg};">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                {_badge(status, color)}
                <span style="font-size:0.85em;font-weight:600;color:#374151;">Q{num_a} · Q{num_b}</span>
                <span style="font-size:0.82em;color:#9ca3af;">유사도 {pair['similarity']}</span>
            </div>
            <div style="font-size:0.84em;color:#374151;padding:6px 0 4px 0;border-top:1px solid {border_inner};display:flex;flex-direction:column;gap:6px;">
                <div>
                    <div><b>Q{num_a}.</b> {pair['question_a']}</div>
                    <div style="padding-left:6px;border-left:2px solid #86efac;color:#15803d;font-size:0.9em;margin-top:2px;">정답: {ans_a}</div>
                </div>
                <div>
                    <div><b>Q{num_b}.</b> {pair['question_b']}</div>
                    <div style="padding-left:6px;border-left:2px solid #86efac;color:#15803d;font-size:0.9em;margin-top:2px;">정답: {ans_b}</div>
                </div>
            </div>
        </div>"""

    pairs_html = ""
    for pair in result.get("errors", []):
        pairs_html += _pair_html(pair, "FAIL", "#ef4444")
    for pair in result.get("warnings", []):
        pairs_html += _pair_html(pair, "WARN", "#f59e0b")

    if not pairs_html:
        pairs_html = "<div style='padding:20px;text-align:center;color:#6b7280;font-size:0.9em;'>중복된 문항이 없습니다.</div>"

    legend_html = f"""
    <div style="margin-bottom:12px;display:flex;gap:12px;font-size:0.82em;color:#6b7280;background:#f8fafc;padding:8px 12px;border-radius:6px;border:1px solid #f1f5f9;">
        <span><b>판정 기준:</b></span>
        <span><span style="color:#16a34a;font-weight:600;">PASS</span> &lt; {THRESHOLD_DUPLICATE_WARN}</span>
        <span><span style="color:#f59e0b;font-weight:600;">WARN</span> &ge; {THRESHOLD_DUPLICATE_WARN}</span>
        <span><span style="color:#ef4444;font-weight:600;">FAIL</span> &ge; {THRESHOLD_DUPLICATE_FAIL}</span>
    </div>"""

    return f"""
    <div class="card">
        <div class="card-header">
            <span class="section-num">4</span>
            <span class="section-title">의미적 중복</span>
            {_pass_badge(result['pass'])}
        </div>
        <div class="card-body">
            {legend_html}
            <div style="display:flex;flex-direction:column;gap:12px;">
                {pairs_html}
            </div>
        </div>
    </div>"""


# ── 문제별 보기 ───────────────────────────────────────────────────────────────

def _render_by_question(
    quizzes: list[dict],
    structural_result: dict,
    grounding_result: dict,
    distractor_result: dict,
    duplicate_result: dict,
    sources: list[dict],
) -> str:
    source_map = {s["chunk_id"]: s["content"] for s in sources}

    structural_map = {item["quiz_id"]: item for item in (structural_result or {}).get("item_results", [])}
    grounding_map = {item["quiz_id"]: item for item in (grounding_result or {}).get("item_results", [])}
    distractor_map = {item["quiz_id"]: item for item in (distractor_result or {}).get("item_results", [])}

    # 중복 여부 확인
    in_dup_error = False
    in_dup_warn = False
    cards = ""
    for i, quiz in enumerate(quizzes, 1):
        quiz_id = quiz.get("quiz_id", "")
        quiz_type = quiz.get("type", "")
        style = quiz.get("style", "")
        question = quiz.get("question", "")
        answer = quiz.get("answer", "")
        options = quiz.get("options", {})
        explanation = quiz.get("explanation", "")
        answer_text = options.get(answer, answer) if quiz_type == "multiple_choice" else answer

        s_item = structural_map.get(quiz_id, {})
        g_item = grounding_map.get(quiz_id, {})
        d_item = distractor_map.get(quiz_id, {})
        
        in_dup_error = False
        in_dup_warn = False
        if duplicate_result:
            for pair in duplicate_result.get("errors", []):
                if quiz_id in [pair['quiz_id_a'], pair['quiz_id_b']]:
                    in_dup_error = True
                    break
            if not in_dup_error:
                for pair in duplicate_result.get("warnings", []):
                    if quiz_id in [pair['quiz_id_a'], pair['quiz_id_b']]:
                        in_dup_warn = True
                        break

        s_pass = s_item.get("pass", True)
        g_pass = g_item.get("pass", True)
        d_pass = d_item.get("pass", True)
        # Q-Overall 판단
        q_overall = s_pass and g_pass and d_pass and not in_dup_error

        # 문항 내용
        if quiz_type == "multiple_choice":
            content_html = _options_html(quiz, show_explanation=True)
        else:
            content_html = _short_answer_html(quiz)
            
        chunks_html = _source_chunks_html(quiz, source_map)

        # 구조적 유효성
        s_errors = s_item.get("errors", [])
        s_warnings = s_item.get("warnings", [])
        s_detail = (
            "<ul>" + "".join(f"<li style='color:#ef4444;'>❌ {e}</li>" for e in s_errors)
            + "".join(f"<li style='color:#f59e0b;'>⚠️ {w}</li>" for w in s_warnings) + "</ul>"
            if s_errors or s_warnings else "<span style='color:green;'>✅ 이상 없음</span>"
        )

        # Grounding + 해설
        g_grounding_pass = g_item.get("grounding_pass")
        g_grounding_reason = g_item.get("grounding_reason") or ""
        g_exp_pass = g_item.get("explanation_pass")
        g_exp_reason = g_item.get("explanation_reason") or ""
        g_errors = g_item.get("errors", [])
        g_detail = (
            f"<div style='margin-bottom:4px;'><b>Grounding:</b> {_eval_cell(g_grounding_pass, g_grounding_reason)}</div>"
            f"<div><b>해설:</b> {_eval_cell(g_exp_pass, g_exp_reason)}</div>"
            if g_item else "<span style='color:#6b7280;'>N/A</span>"
        )

        # Distractor
        d_skipped = d_item.get("skipped", False)
        d_errors = d_item.get("errors", [])
        d_results = d_item.get("distractor_results", {})
        if d_skipped:
            d_detail = "<span style='color:#6b7280;'>단답형 - 스킵</span>"
        else:
            d_lines = ""
            for key, dr in d_results.items():
                pass_status = dr.get("pass")
                icon = "✅" if pass_status else "❌"
                color = "green" if pass_status else "#ef4444"
                text = options.get(key, "")
                score = dr.get("max_score", "N/A")
                d_lines += f"<div style='color:{color};font-size:0.85em;'>{icon} <b>{key}.</b> {text} <small>(BM25:{score})</small></div>"
            d_detail = d_lines if d_lines else "<span style='color:green;'>✅ 이상 없음</span>"

        # 중복
        if in_dup_error:
            dup_detail = "<span style='color:#ef4444;'>❌ 중복 감지됨 (FAIL)</span>"
        elif in_dup_warn:
            dup_detail = "<span style='color:#f59e0b;'>⚠️ 유사도 높음 (WARN)</span>"
        else:
            dup_detail = "<span style='color:green;'>✅ 이상 없음</span>"

        cards += f"""
        <div class="card">
            <div class="card-header">
                <span class="section-num">{i}</span>
                <span class="section-title" style="font-size:0.95em;">{question[:60]}{"…" if len(question) > 60 else ""}</span>
                {_pass_badge(q_overall)}
                <span class="id-text" style="margin-left:auto;">[{quiz_type}] [{style}]</span>
            </div>
            <div class="card-body">
                <div class="quiz-content-box">
                    <div style="font-weight:600;color:#111827;margin-bottom:8px;font-size:0.95em;">{question}</div>
                    {content_html}
                    <div style="margin-top:10px;padding:8px 12px;background:#f1f5f9;border-radius:5px;border-left:3px solid #94a3b8;font-size:0.83em;color:#475569;">
                        <b style="color:#334155;">해설</b> {explanation}
                    </div>
                </div>

                <div class="eval-grid">
                    <div class="eval-tile">
                        <div class="eval-tile-title">구조적 유효성 {_pass_badge(s_pass)}</div>
                        <div class="eval-tile-body">{s_detail}</div>
                    </div>
                    <div class="eval-tile">
                        <div class="eval-tile-title">Grounding + 해설 {_pass_badge(g_pass)}</div>
                        <div class="eval-tile-body">{g_detail}</div>
                    </div>
                    <div class="eval-tile">
                        <div class="eval-tile-title">Distractor {_pass_badge(d_pass)}</div>
                        <div class="eval-tile-body">{d_detail}</div>
                    </div>
                    <div class="eval-tile">
                        <div class="eval-tile-title">의미적 중복 {_pass_badge(not in_dup_error)}</div>
                        <div class="eval-tile-body">{dup_detail}</div>
                    </div>
                </div>

                {chunks_html}
            </div>
        </div>"""

    return cards


# ── 리포트 생성 ───────────────────────────────────────────────────────────────

def generate_report(eval_result: dict, quiz_set: dict | None = None) -> str:
    quiz_set_id = eval_result.get("quiz_set_id", "unknown")
    evaluated_at_raw = eval_result.get("evaluated_at", "")
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(evaluated_at_raw)
        evaluated_at = dt.astimezone().strftime("%Y년 %m월 %d일 %H:%M:%S")
    except Exception:
        evaluated_at = evaluated_at_raw
    fail_reasons = eval_result.get("fail_reasons", [])
    overall_score = eval_result.get("overall_score")
    grade = eval_result.get("grade", "")

    quizzes = quiz_set.get("quizzes", []) if quiz_set else []
    sources = quiz_set.get("retrieval_sources", []) if quiz_set else []

    fail_reason_str = ", ".join(fail_reasons) if fail_reasons else "없음"

    # 점수 배지
    _grade_styles = {
        "A": "background:#dcfce7;color:#166534",
        "B": "background:#dbeafe;color:#1d4ed8",
        "C": "background:#fef9c3;color:#854d0e",
        "D": "background:#fee2e2;color:#991b1b",
    }
    _grade_labels = {"A": "우수", "B": "양호", "C": "보통", "D": "미흡"}
    if overall_score is not None:
        _gs = _grade_styles.get(grade, "background:#f1f5f9;color:#475569")
        _gl = _grade_labels.get(grade, grade)
        score_badge = (
            f'<span style="{_gs};padding:3px 10px;border-radius:6px;'
            f'font-weight:700;font-size:1.1em;">{overall_score}점</span>'
            f'&nbsp;<span style="font-size:0.85em;color:#64748b;">{grade}등급 · {_gl}</span>'
        )
    else:
        score_badge = "<span>점수 없음</span>"
    quiz_id_to_num = {q["quiz_id"]: i+1 for i, q in enumerate(quizzes)}

    structural_result = eval_result.get("structural")
    grounding_result = eval_result.get("grounding")
    distractor_result = eval_result.get("distractor")
    duplicate_result = eval_result.get("duplicate")

    structural_html = _render_structural(structural_result)
    grounding_html = _render_grounding(grounding_result, quizzes, sources)
    distractor_html = _render_distractor(distractor_result, quizzes, sources)
    duplicate_html = _render_duplicate(duplicate_result, quiz_id_to_num, quizzes)
    by_question_html = _render_by_question(quizzes, structural_result, grounding_result, distractor_result, duplicate_result, sources)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>퀴즈 품질 평가 리포트</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      max-width: 1160px; margin: 0 auto; padding: 32px 24px 64px;
      color: #111827; background: #f8fafc; line-height: 1.5;
    }}

    /* ── Header ── */
    .page-header {{
      margin-bottom: 28px;
    }}
    .page-header h1 {{
      font-size: 1.5rem; font-weight: 700; color: #0f172a; margin: 0 0 4px 0;
    }}
    .page-header .subtitle {{ font-size: 0.85em; color: #64748b; }}

    /* ── Summary card ── */
    .summary {{
      background: white; border: 1px solid #e2e8f0;
      border-radius: 12px; padding: 20px 28px; margin-bottom: 24px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.04);
      display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px 24px;
    }}
    .summary-item {{ display: flex; flex-direction: column; gap: 2px; }}
    .summary-label {{ font-size: 0.75em; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em; }}
    .summary-value {{ font-size: 0.92em; color: #1e293b; font-weight: 500; }}

    /* ── Toggle ── */
    .view-toggle {{
      display: inline-flex; gap: 0; margin-bottom: 20px;
      border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;
      background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .view-toggle button {{
      padding: 8px 22px; border: none; background: transparent;
      cursor: pointer; font-size: 0.875em; font-weight: 500;
      color: #64748b; transition: background 0.15s, color 0.15s;
    }}
    .view-toggle button:not(:last-child) {{ border-right: 1px solid #e2e8f0; }}
    .view-toggle button.active {{ background: #1e40af; color: white; }}
    .view-toggle button:not(.active):hover {{ background: #f1f5f9; color: #1e293b; }}

    /* ── Card ── */
    .card {{
      background: white; border: 1px solid #e2e8f0; border-radius: 12px;
      margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); overflow: hidden;
    }}
    .card-header {{
      display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
      padding: 14px 20px; border-bottom: 1px solid #f1f5f9; background: #fafafa;
    }}
    .section-num {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 26px; height: 26px; border-radius: 50%;
      background: #e0e7ff; color: #3730a3; font-size: 0.8em; font-weight: 700; flex-shrink: 0;
    }}
    .section-title {{ font-size: 1.05em; font-weight: 700; color: #0f172a; }}
    .card-body {{ padding: 16px 20px; }}
    .skip-badge {{
      font-size: 0.75em; font-weight: 600; color: #94a3b8;
      background: #f1f5f9; border-radius: 20px; padding: 2px 10px;
    }}

    /* ── Check groups (structural) ── */
    .check-group {{ margin-bottom: 14px; }}
    .check-group:last-child {{ margin-bottom: 0; }}
    .check-label {{ font-size: 0.82em; font-weight: 700; color: #374151; margin-bottom: 2px; }}
    .check-desc {{ font-size: 0.78em; color: #94a3b8; margin-bottom: 6px; }}
    .check-result {{ font-size: 0.85em; }}

    /* ── Table ── */
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875em; }}
    th {{
      background: #f8fafc; text-align: left; padding: 9px 14px;
      border-bottom: 1px solid #e2e8f0; font-size: 0.8em; font-weight: 600;
      color: #64748b; text-transform: uppercase; letter-spacing: 0.04em;
    }}
    td {{ padding: 10px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    tbody tr:hover td {{ background: #fafafa; }}
    .num-cell {{ text-align: center; font-weight: 700; color: #64748b; font-size: 0.85em; }}

    /* ── Pair card (duplicates) ── */
    .pair-card {{
      border: 1px solid #fca5a5; background: #fff5f5;
      border-radius: 8px; padding: 12px 16px; margin: 6px 0;
    }}

    /* ── Quiz content box ── */
    .quiz-content-box {{
      background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
      padding: 14px 16px; margin-bottom: 14px;
    }}

    /* ── Eval grid (per-question view) ── */
    .eval-grid {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px;
    }}
    @media (max-width: 900px) {{
      .eval-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    .eval-tile {{
      border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; background: #fafafa;
    }}
    .eval-tile-title {{
      font-size: 0.78em; font-weight: 700; color: #374151;
      margin-bottom: 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    }}
    .eval-tile-body {{ font-size: 0.82em; color: #475569; }}

    /* ── Grounding list ── */
    .g-list {{ display: flex; flex-direction: column; }}
    .g-item {{ border-bottom: 1px solid #f1f5f9; padding: 16px 20px; }}
    .g-item:last-child {{ border-bottom: none; }}
    .g-item-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }}
    .g-question-box {{
      background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
      padding: 12px 14px; margin-bottom: 12px;
    }}
    .g-eval-row {{
      display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 12px;
    }}
    .g-eval-cell {{
      background: #fafafa; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px;
    }}
    .g-eval-label {{
      font-size: 0.72em; font-weight: 700; color: #94a3b8;
      text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;
    }}

    /* ── Misc ── */
    ul {{ margin: 0; padding-left: 16px; }}
    li {{ margin: 3px 0; }}
    .ok-text {{ color: #16a34a; font-size: 0.85em; font-weight: 500; }}
    .id-text {{ font-size: 0.75em; color: #94a3b8; }}
  </style>
</head>
<body>
  <div class="page-header">
    <h1>퀴즈 품질 평가 리포트</h1>
    <span class="subtitle">LearnCraft · 자동 생성 평가 보고서</span>
  </div>

  <div class="summary">
    <div class="summary-item">
      <span class="summary-label">세트 ID</span>
      <span class="summary-value" style="font-size:0.8em;color:#64748b;">{quiz_set_id}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">평가 시각</span>
      <span class="summary-value">{evaluated_at}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">품질 점수</span>
      <span class="summary-value">{score_badge}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">문제 원인</span>
      <span class="summary-value" style="color:#dc2626;">{fail_reason_str}</span>
    </div>
  </div>

  <div class="view-toggle">
    <button id="btn-section" class="active" onclick="showView('section')">섹션별 보기</button>
    <button id="btn-question" onclick="showView('question')">문제별 보기</button>
  </div>

  <div id="view-section">
    {structural_html}
    {grounding_html}
    {distractor_html}
    {duplicate_html}
  </div>

  <div id="view-question" style="display:none;">
    {by_question_html}
  </div>

  <script>
    function showView(type) {{
      document.getElementById('view-section').style.display = type === 'section' ? 'block' : 'none';
      document.getElementById('view-question').style.display = type === 'question' ? 'block' : 'none';
      document.getElementById('btn-section').className = type === 'section' ? 'active' : '';
      document.getElementById('btn-question').className = type === 'question' ? 'active' : '';
    }}
  </script>
</body>
</html>"""


def save_report(eval_result: dict, quiz_set: dict | None = None) -> Path:
    os.makedirs(QUIZ_REPORT_DIR, exist_ok=True)
    quiz_set_id = eval_result["quiz_set_id"]
    file_path = Path(QUIZ_REPORT_DIR) / f"report_{quiz_set_id}.html"
    html = generate_report(eval_result, quiz_set)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)
    return file_path


def save_report_from_eval_file(eval_json_path: str) -> Path:
    with open(eval_json_path, encoding="utf-8") as f:
        eval_result = json.load(f)

    quiz_set_id = eval_result["quiz_set_id"]
    quiz_json_path = Path(GENERATED_QUIZ_DIR) / f"quiz_{quiz_set_id}.json"
    quiz_set = None
    if quiz_json_path.exists():
        with open(quiz_json_path, encoding="utf-8") as f:
            quiz_set = json.load(f)

    return save_report(eval_result, quiz_set)


def save_reports_all() -> None:
    eval_dir = Path(QUIZ_EVAL_DIR)
    eval_files = sorted(eval_dir.glob("eval_*.json"))

    if not eval_files:
        print(f"리포트 생성할 평가 파일이 없습니다: {eval_dir}")
        return

    for eval_file in eval_files:
        path = save_report_from_eval_file(str(eval_file))
        print(f"리포트 생성: {path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2:
        path = save_report_from_eval_file(sys.argv[1])
        print(f"리포트 저장: {path}")
    else:
        save_reports_all()
