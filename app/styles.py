"""LearnCraft 공통 CSS 스타일 — 멋쟁이사자처럼 브랜드 테마."""
import streamlit as st

BRAND_PRIMARY = "#FF6B00"
BRAND_PRIMARY_HOVER = "#E55F00"


def inject_global_css() -> None:
    """모든 페이지 공통 글로벌 CSS를 주입한다."""
    st.markdown(
        f"""
        <style>
        :root {{
            --brand-primary: {BRAND_PRIMARY};
            --brand-primary-hover: {BRAND_PRIMARY_HOVER};
        }}

        /* Primary 버튼 — 멋사 주황 */
        button[kind="primary"],
        [data-testid="stBaseButton-primary"] {{
            background-color: var(--brand-primary) !important;
            border-color: var(--brand-primary) !important;
            color: #fff !important;
        }}
        button[kind="primary"]:hover,
        [data-testid="stBaseButton-primary"]:hover {{
            background-color: var(--brand-primary-hover) !important;
            border-color: var(--brand-primary-hover) !important;
        }}

        /* 인풋/셀렉트박스 포커스 테두리 */
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {{
            border-color: var(--brand-primary) !important;
            box-shadow: 0 0 0 1px var(--brand-primary) !important;
        }}

        /* 라디오 버튼 선택 색상 */
        [data-testid="stRadio"] label[data-selected="true"] {{
            color: var(--brand-primary) !important;
        }}

        /* 폼 label 크기 개선 */
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] label {{
            font-size: 0.95rem !important;
            font-weight: 500 !important;
            color: #374151 !important;
        }}

        /* data_editor 테이블 글씨 크기 */
        [data-testid="stDataEditor"] .dvn-scroller {{
            font-size: 0.9rem !important;
        }}
        [data-testid="stDataEditor"] .glideDataEditor {{
            font-size: 0.9rem !important;
        }}

        /* 기능 카드 (홈 화면용) */
        .lc-feature-card {{
            background: #fff;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 24px 20px;
            height: 100%;
            transition: box-shadow 0.15s ease;
        }}
        .lc-feature-card:hover {{
            box-shadow: 0 4px 12px rgba(255, 107, 0, 0.12);
            border-color: var(--brand-primary);
        }}
        .lc-feature-card .icon {{
            font-size: 1.6rem;
            margin-bottom: 8px;
        }}
        .lc-feature-card h3 {{
            font-size: 1rem;
            font-weight: 700;
            color: #111827;
            margin: 0 0 6px 0;
        }}
        .lc-feature-card p {{
            font-size: 0.875rem;
            color: #6b7280;
            margin: 0;
            line-height: 1.55;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_step_indicator(active_step: int) -> None:
    """퀴즈 진행 3단계 표시기를 렌더링한다.

    Args:
        active_step: 현재 활성 단계 (1=강의 선택, 2=문제 생성, 3=퀴즈 풀기)
    """
    steps = ["강의 선택", "문제 생성", "퀴즈 풀기"]

    def _step_html(label: str, step_num: int) -> str:
        is_active = step_num == active_step
        is_done = step_num < active_step
        if is_active:
            circle_style = f"background:{BRAND_PRIMARY};color:#fff;border:2px solid {BRAND_PRIMARY};"
            label_style = f"color:{BRAND_PRIMARY};font-weight:700;"
        elif is_done:
            circle_style = f"background:{BRAND_PRIMARY};color:#fff;border:2px solid {BRAND_PRIMARY};opacity:0.5;"
            label_style = "color:#9ca3af;font-weight:500;"
        else:
            circle_style = "background:#fff;color:#9ca3af;border:2px solid #e5e7eb;"
            label_style = "color:#9ca3af;font-weight:400;"

        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px;">'
            f'  <div style="{circle_style}width:32px;height:32px;border-radius:50%;'
            f'display:flex;align-items:center;justify-content:center;font-size:0.8rem;font-weight:700;">'
            f'    {step_num}'
            f'  </div>'
            f'  <span style="{label_style}font-size:0.8rem;">{label}</span>'
            f'</div>'
        )

    connector = (
        '<div style="flex:1;height:2px;background:#e5e7eb;margin-top:16px;max-width:80px;"></div>'
    )

    items = []
    for i, step_label in enumerate(steps, start=1):
        items.append(_step_html(step_label, i))
        if i < len(steps):
            items.append(connector)

    html = (
        '<div style="display:flex;align-items:flex-start;justify-content:center;'
        'gap:0;padding:16px 0 24px 0;">'
        + "".join(items)
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)
