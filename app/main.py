"""LearnCraft - 강의 기반 복습 퀴즈 & 학습 가이드 자동 생성 데모."""
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (Streamlit 실행 시 필요)
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="LearnCraft",
    page_icon="📚",
    layout="wide",
)

st.title("📚 LearnCraft")
st.subheader("강의 내용 기반 복습 퀴즈 & 학습 가이드 자동 생성")

st.markdown("""
LearnCraft는 강의 스크립트(STT)를 RAG 파이프라인으로 분석하여
**복습 퀴즈**와 **학습 가이드**를 자동으로 생성합니다.

---

### 사용 방법

| 단계 | 페이지 | 설명 |
|------|--------|------|
| 1️⃣ | **강의 인덱싱** | 강의 스크립트를 선택하고 벡터DB에 인덱싱 |
| 2️⃣ | **퀴즈 풀기** | 인덱싱된 강의로 퀴즈 생성 후 학습 |
| 3️⃣ | **학습 가이드** | 핵심 개념 요약 및 복습 포인트 확인 |

---

왼쪽 사이드바에서 페이지를 선택하세요.
""")

# API 키 설정 상태 표시
from config.settings import OPENAI_API_KEY
if not OPENAI_API_KEY:
    st.error("⚠️ OPENAI_API_KEY가 설정되지 않았습니다. 프로젝트 루트에 `.env` 파일을 생성하세요.")
    st.code("OPENAI_API_KEY=sk-...")
else:
    st.success("✅ OpenAI API 키 확인됨")
