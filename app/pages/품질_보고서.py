import streamlit as st
import os
from pathlib import Path
import sys

# 프로젝트 루트를 sys.path에 추가 (config, src 접근용)
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import QUIZ_REPORT_DIR

st.set_page_config(page_title="LearnCraft - 품질 보고서", page_icon="📊", layout="wide")

st.title("📊 퀴즈 품질 평가 보고서")
st.markdown("생성된 퀴즈의 구조, Grounding, 오답 품질, 중복 여부 평가 결과를 확인합니다.")

# 보고서 디렉토리 확인
report_dir = Path(QUIZ_REPORT_DIR)
if not report_dir.exists():
    st.info("아직 생성된 보고서가 없습니다. 퀴즈를 먼저 생성해 주세요.")
    st.stop()

# 보고서 파일 목록 (최신순)
report_files = sorted(report_dir.glob("report_*.html"), key=os.path.getmtime, reverse=True)

if not report_files:
    st.info("확인 가능한 보고서가 없습니다.")
    st.stop()

# 보고서 선택
report_options = {f.name: f for f in report_files}
selected_report_name = st.selectbox("보고서 선택", list(report_options.keys()))

if selected_report_name:
    report_path = report_options[selected_report_name]
    
    with open(report_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 상단 정보 및 액션
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"파일 경로: `{report_path}`")
    with col2:
        st.download_button(
            label="HTML 다운로드",
            data=html_content,
            file_name=selected_report_name,
            mime="text/html"
        )

    st.divider()

    # HTML 렌더링 (IFrame 사용)
    # 보고서의 높이가 가변적이므로 충분한 높이 설정 또는 스크롤 허용
    import streamlit.components.v1 as components
    components.html(html_content, height=1200, scrolling=True)
