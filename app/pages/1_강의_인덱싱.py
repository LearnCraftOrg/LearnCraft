"""강의 스크립트 선택 및 ChromaDB 인덱싱."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.ingestion.loader import get_available_dates, load_curriculum, load_clean_script
from src.ingestion.chunker import chunk_text
from src.vectorstore.store import is_date_indexed, add_documents, delete_date, get_indexed_dates

st.set_page_config(page_title="강의 인덱싱", page_icon="📥", layout="wide")
st.title("📥 강의 인덱싱")
st.caption("강의 스크립트를 벡터DB에 저장합니다.")

# 데이터 로드
available_dates = get_available_dates()
curriculum_map = load_curriculum()
indexed_dates = get_indexed_dates()

if not available_dates:
    st.error("강의 스크립트 파일이 없습니다. `data/강의 스크립트/` 폴더를 확인하세요.")
    st.stop()

# 강의 목록 테이블
st.subheader("강의 목록")

col_header = st.columns([1, 1.5, 2.5, 2, 1.5])
col_header[0].markdown("**날짜**")
col_header[1].markdown("**주차**")
col_header[2].markdown("**과목/내용**")
col_header[3].markdown("**학습 목표**")
col_header[4].markdown("**상태**")

st.divider()

selected_dates = []
for date in available_dates:
    info = curriculum_map.get(date, {})
    is_indexed = date in indexed_dates

    cols = st.columns([1, 1.5, 2.5, 2, 1.5])
    checked = cols[0].checkbox(date, key=f"chk_{date}", value=False)
    cols[1].write(f"{info.get('week', '-')}주차")
    cols[2].write(f"{info.get('subject', '-')} / {info.get('content', '-')[:30]}...")
    cols[3].write(info.get("learning_goal", "-")[:40] + "...")
    if is_indexed:
        cols[4].success("✅ 인덱싱됨")
    else:
        cols[4].warning("⬜ 미인덱싱")

    if checked:
        selected_dates.append(date)

st.divider()

# 인덱싱 버튼
col_btn1, col_btn2, _ = st.columns([1.5, 1.5, 5])
run_index = col_btn1.button(
    "▶ 인덱싱 시작",
    disabled=len(selected_dates) == 0,
    type="primary",
)
run_reindex = col_btn2.button(
    "🔄 재인덱싱",
    disabled=len(selected_dates) == 0,
    help="선택한 날짜의 기존 데이터를 삭제하고 다시 인덱싱합니다.",
)

if run_index or run_reindex:
    if not selected_dates:
        st.warning("인덱싱할 강의를 선택하세요.")
    else:
        progress_bar = st.progress(0)
        status_box = st.empty()

        for i, date in enumerate(selected_dates):
            status_box.info(f"처리 중: {date} ({i + 1}/{len(selected_dates)})")

            # 재인덱싱이면 기존 데이터 삭제
            if run_reindex and date in indexed_dates:
                delete_date(date)

            # 이미 인덱싱됨 + 일반 인덱싱이면 스킵
            if not run_reindex and date in indexed_dates:
                status_box.success(f"{date} 이미 인덱싱됨, 스킵")
                progress_bar.progress((i + 1) / len(selected_dates))
                continue

            # clean 스크립트 로드
            text = load_clean_script(date)
            if not text:
                status_box.error(f"{date} clean 파일을 찾을 수 없습니다. (data/clean/{date}_clean.txt)")
                continue

            info = curriculum_map.get(date, {})

            # 청크 생성
            metadata = {
                "date": date,
                "week": str(info.get("week", "")),
                "subject": info.get("subject", ""),
                "content": info.get("content", ""),
                "learning_goal": info.get("learning_goal", ""),
            }
            docs = chunk_text(text, metadata)

            # 벡터스토어에 추가
            count = add_documents(docs)
            status_box.success(f"✅ {date}: {count}개 청크 인덱싱 완료")
            progress_bar.progress((i + 1) / len(selected_dates))

        st.success(f"🎉 총 {len(selected_dates)}개 강의 인덱싱 완료!")
        st.rerun()
