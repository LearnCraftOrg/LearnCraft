import sys
import json
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import QUIZ_EVAL_DIR, QUIZ_REPORT_DIR, GENERATED_QUIZ_DIR
from src.quiz.evaluator.duplicate import THRESHOLD_DUPLICATE


def _badge(text: str, color: str) -> str:
    colors = {
        "green":  "#22c55e",
        "red":    "#ef4444",
        "yellow": "#f59e0b",
        "gray":   "#6b7280",
    }
    bg = colors.get(color, "#6b7280")
    return (
        f'<span style="background:{bg};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;font-weight:bold;">{text}</span>'
    )


def _pass_badge(passed: bool) -> str:
    return _badge("PASS", "green") if passed else _badge("FAIL", "red")


def _render_structural(result: dict) -> str:
    if result is None:
        return "<p>평가 스킵</p>"

    rows = ""
    for i, item in enumerate(result.get("item_results", []), 1):
        status = _pass_badge(item["pass"])
        errors = "".join(f"<li>❌ {e}</li>" for e in item["errors"])
        warnings = "".join(f"<li>⚠️ {w}</li>" for w in item["warnings"])
        detail = f"<ul>{errors}{warnings}</ul>" if errors or warnings else "<p>이상 없음</p>"
        rows += f"""
        <tr>
            <td style="text-align:center;font-weight:bold;">Q{i}</td>
            <td>{status}</td>
            <td>{detail} <br><small style="color:#666;font-size:0.8em;">ID: {item['quiz_id'][:8]}...</small></td>
        </tr>"""

    set_errors = "".join(
        f'<li style="color:#ef4444;">❌ {e}</li>'
        for e in result.get("set_errors", [])
    )
    set_warnings = "".join(
        f'<li style="color:#f59e0b;">⚠️ {w}</li>'
        for w in result.get("set_warnings", [])
    )

    return f"""
    <div class="section">
        <h3>1. 구조적 유효성 {_pass_badge(result['pass'])}</h3>
        {'<ul>' + set_errors + set_warnings + '</ul>' if set_errors or set_warnings else ''}
        <table>
            <thead><tr><th style="width:40px;">번호</th><th style="width:60px;">결과</th><th>상세</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def _render_grounding(result: dict, quizzes: list[dict], sources: list[dict]) -> str:
    if result is None:
        return """<div class="section"><h3>2. Grounding <span style="color:#6b7280;">스킵</span></h3></div>"""

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

        if quiz_type == "multiple_choice":
            answer_text = options.get(answer, answer)
        else:
            answer_text = answer
        grounding_qa_target = f"{question}에 대한 정답은 {answer_text}이다."

        # BM25 매칭 결과 (신규) 또는 fallback (구버전 호환)
        source_chunks_bm25 = quiz_obj.get("source_chunks_bm25")
        if source_chunks_bm25 is None:
            raw_ids = quiz_obj.get("source_chunk_ids") or []
            if not raw_ids:
                legacy_id = quiz_obj.get("source_chunk_id")
                raw_ids = [legacy_id] if legacy_id else []
            source_chunks_bm25 = [{"chunk_id": sid, "bm25_score": None} for sid in raw_ids]
        # BM25 점수 내림차순 정렬 (None은 뒤로)
        source_chunks_bm25 = sorted(
            source_chunks_bm25,
            key=lambda m: m.get("bm25_score") or 0,
            reverse=True,
        )
        source_chunk_ids = [m["chunk_id"] for m in source_chunks_bm25]

        sources_html = ""
        for idx, chunk_info in enumerate(source_chunks_bm25):
            sid = chunk_info["chunk_id"]
            bm25_score = chunk_info.get("bm25_score")
            score_str = f" | BM25: {bm25_score:.4f}" if bm25_score is not None else ""
            s_content = source_map.get(sid, "(근거 청크 없음)")
            sources_html += f"""
                <details style="font-size:0.85em;margin-bottom:8px;border:1px solid #eee;padding:4px;border-radius:4px;">
                    <summary style="cursor:pointer;color:#2563eb;">📖 참조 청크 {idx+1} 보기 ({sid[:8]}...{score_str})</summary>
                    <pre style="white-space:pre-wrap;margin-top:8px;background:#f8fafc;padding:8px;font-family:inherit;">{s_content}</pre>
                </details>
            """

        grounding_pass = item.get("grounding_pass")
        grounding_reason = item.get("grounding_reason") or ""
        explanation_pass = item.get("explanation_pass")
        explanation_reason = item.get("explanation_reason") or ""

        def _eval_cell(passed, reason):
            if passed is None:
                return "<span style='color:#6b7280;'>N/A</span>"
            icon = "✅" if passed else "❌"
            color = "green" if passed else "#ef4444"
            return f"<span style='color:{color};'>{icon} {reason}</span>"

        errors_html = "".join(f"<li style='color:#ef4444;'>❌ {e}</li>" for e in errors_list)
        warnings_html = "".join(f"<li style='color:#f59e0b;'>⚠️ {w}</li>" for w in warnings_list)
        detail = f"<ul>{errors_html}{warnings_html}</ul>" if errors_html or warnings_html else "<p style='color:green;'>✅ 통과</p>"

        rows += f"""
        <tr>
            <td style="text-align:center;vertical-align:middle;font-weight:bold;">Q{i}</td>
            <td style="width:260px;">
                <div style="font-size:0.85em;">
                    <div style="background:#fefce8;padding:6px;border-radius:4px;border:1px solid #fef08a;">{grounding_qa_target}</div>
                </div>
                <div style="font-size:0.75em;color:#666;margin-top:6px;">ID: {quiz_id[:8]}... | Sources: {', '.join([sid[:8] for sid in source_chunk_ids])}</div>
            </td>
            <td style="text-align:center;">{status}</td>
            <td style="font-size:0.85em;">{_eval_cell(grounding_pass, grounding_reason)}</td>
            <td style="font-size:0.85em;">{_eval_cell(explanation_pass, explanation_reason)}</td>
            <td>
                {sources_html}
                {detail}
            </td>
        </tr>"""

    section_pass_badge = _pass_badge(result.get("pass", False))

    return f"""
    <div class="section">
        <h3>2. Grounding + 해설 품질 {section_pass_badge}</h3>
        <table>
            <thead><tr><th style="width:40px;">번호</th><th>문항 및 근거</th><th style="width:60px;">결과</th><th style="width:180px;">Grounding</th><th style="width:180px;">해설 품질</th><th>근거 원문</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def _render_distractor(result: dict, quizzes: list[dict], sources: list[dict]) -> str:
    if result is None:
        return """<div class="section"><h3>3. Distractor 품질 <span style="color:#6b7280;">스킵</span></h3></div>"""

    quiz_map = {q["quiz_id"]: q for q in quizzes}
    source_map = {s["chunk_id"]: s["content"] for s in sources}

    rows = ""
    for i, item in enumerate(result.get("item_results", []), 1):
        if item.get("skipped"):
            continue

        status = _badge("PASS", "green") if item["pass"] else _badge("FAIL", "red")
        errors = "".join(f"<li>❌ {e}</li>" for e in item.get("errors", []))

        quiz_obj = quiz_map.get(item['quiz_id'], {})
        options = quiz_obj.get("options", {})

        distractor_detail = ""
        for key, dr in item.get("distractor_results", {}).items():
            score = dr.get("max_score", "N/A")
            cov = dr.get("coverage_ratio", 0.0)
            uncovered = dr.get("uncovered_words", [])
            pass_status = dr.get("pass")
            matched_chunk = dr.get("matched_chunk_id")

            icon = "✅" if pass_status else "❌"
            color = "green" if pass_status else "red"
            text = options.get(key, "(텍스트 없음)")

            cov_str = f"{cov*100:.0f}%"
            uncovered_str = f" | 미매칭 단어: <span style='color:#ef4444;'>{', '.join(uncovered)}</span>" if uncovered else ""

            if matched_chunk and matched_chunk in source_map:
                s_content = source_map[matched_chunk]
                match_html = f"""
                <details style="font-size:0.85em;margin-top:4px;border:1px solid #e2e8f0;padding:4px;border-radius:4px;background:#f8fafc;color:#334155;">
                    <summary style="cursor:pointer;color:#2563eb;">📖 매칭된 강의 원문 보기 (BM25: {score}, 커버리지: {cov_str}{uncovered_str})</summary>
                    <div style="margin-top:6px;white-space:pre-wrap;">{s_content}</div>
                </details>
                """
            else:
                match_html = f" <br><small>(BM25: {score}, 커버리지: {cov_str}{uncovered_str})</small>"

            distractor_detail += f"<li style='color:{color};margin-bottom:8px;'>{icon} <b>오답 {key}</b>: {text}{match_html}</li>"

        detail = f"<ul>{errors}{distractor_detail}</ul>" if errors or distractor_detail else "<p>이상 없음</p>"
        rows += f"""
        <tr>
            <td style="text-align:center;font-weight:bold;">Q{i}</td>
            <td>{status}</td>
            <td>{detail} <br><small style="color:#666;font-size:0.8em;">ID: {item['quiz_id'][:8]}...</small></td>
        </tr>"""

    return f"""
    <div class="section">
        <h3>3. Distractor 품질 {_pass_badge(result['pass'])}</h3>
        <table>
            <thead><tr><th style="width:40px;">번호</th><th style="width:60px;">결과</th><th>상세</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def _render_duplicate(result: dict, quiz_id_to_num: dict) -> str:
    if result is None:
        return """<div class="section"><h3>4. 의미적 중복 <span style="color:#6b7280;">스킵</span></h3></div>"""

    embed_map = result.get("embed_map", {})
    errors_html = ""

    for pair in result.get("errors", []):
        num_a = quiz_id_to_num.get(pair['quiz_id_a'], "?")
        num_b = quiz_id_to_num.get(pair['quiz_id_b'], "?")
        text_a = embed_map.get(pair['quiz_id_a'], "")
        text_b = embed_map.get(pair['quiz_id_b'], "")
        errors_html += f"""
        <div class="pair-card fail">
            ❌ <b>위험 (유사도 {pair['similarity']})</b> - (Q{num_a} & Q{num_b})<br>
            <div style="margin-top:5px;background:white;padding:5px;border-radius:4px;">
                <small><b>Q{num_a}:</b> {pair['question_a']}</small><br>
                <small style="color:#6b7280;">임베딩: {text_a}</small>
                <small style="border-top:1px solid #eee;display:block;margin-top:3px;padding-top:3px;">
                    <b>Q{num_b}:</b> {pair['question_b']}</small><br>
                <small style="color:#6b7280;">임베딩: {text_b}</small>
            </div>
        </div>"""

    content = errors_html if errors_html else f"<p>중복 없음 (모든 문항 간 유사도 {THRESHOLD_DUPLICATE} 미만)</p>"

    return f"""
    <div class="section">
        <h3>4. 의미적 중복 {_pass_badge(result['pass'])}</h3>
        {content}
    </div>"""


def generate_report(eval_result: dict, quiz_set: dict | None = None) -> str:
    quiz_set_id = eval_result.get("quiz_set_id", "unknown")
    evaluated_at = eval_result.get("evaluated_at", "")
    overall_pass = eval_result.get("overall_pass", False)
    fail_reasons = eval_result.get("fail_reasons", [])

    quizzes = quiz_set.get("quizzes", []) if quiz_set else []
    sources = quiz_set.get("retrieval_sources", []) if quiz_set else []

    fail_reason_str = ", ".join(fail_reasons) if fail_reasons else "없음"
    overall_badge = _pass_badge(overall_pass)

    quiz_id_to_num = {q["quiz_id"]: i+1 for i, q in enumerate(quizzes)}

    structural_html = _render_structural(eval_result.get("structural"))
    grounding_html = _render_grounding(eval_result.get("grounding"), quizzes, sources)
    distractor_html = _render_distractor(eval_result.get("distractor"), quizzes, sources)
    duplicate_html = _render_duplicate(eval_result.get("duplicate"), quiz_id_to_num)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>퀴즈 품질 평가 리포트</title>
  <style>
    body {{ font-family: sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #1f2937; }}
    h1 {{ border-bottom: 2px solid #e5e7eb; padding-bottom: 12px; }}
    h3 {{ margin-top: 0; }}
    .summary {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 24px; margin-bottom: 24px; }}
    .summary p {{ margin: 4px 0; }}
    .section {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 24px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
    th {{ background: #f3f4f6; text-align: left; padding: 8px 12px; border-bottom: 1px solid #e5e7eb; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }}
    ul {{ margin: 0; padding-left: 16px; }}
    li {{ margin: 2px 0; }}
    .pair-card {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 14px; margin: 6px 0; }}
    .pair-card.fail {{ border-color: #fca5a5; background: #fff5f5; }}
    .pair-card.warn {{ border-color: #fcd34d; background: #fffbeb; }}
  </style>
</head>
<body>
  <h1>퀴즈 품질 평가 리포트</h1>

  <div class="summary">
    <p><strong>세트 ID:</strong> {quiz_set_id}</p>
    <p><strong>평가 시각:</strong> {evaluated_at}</p>
    <p><strong>최종 결과:</strong> {overall_badge}</p>
    <p><strong>실패 원인:</strong> {fail_reason_str}</p>
  </div>

  {structural_html}
  {grounding_html}
  {distractor_html}
  {duplicate_html}

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