"""강의 스크립트 TXT 파일 및 커리큘럼 CSV 로드."""
from pathlib import Path
from typing import Optional
import re
import pandas as pd

from config.settings import SCRIPTS_DIR, CLEAN_DIR, CURRICULUM_PATH

# 파일명 날짜 패턴: 2026-02-27_kdt-backendj-21th.txt
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def get_available_dates() -> list[str]:
    """스크립트 디렉토리에서 사용 가능한 날짜 목록 반환 (정렬)."""
    dates = []
    for p in sorted(SCRIPTS_DIR.glob("*.txt")):
        m = _DATE_RE.search(p.name)
        if m:
            dates.append(m.group(1))
    return dates


def load_script(date: str) -> Optional[str]:
    """특정 날짜의 강의 스크립트 raw 텍스트 반환."""
    for p in SCRIPTS_DIR.glob("*.txt"):
        if date in p.name:
            return p.read_text(encoding="utf-8")
    return None


def load_clean_script(date: str) -> Optional[str]:
    """특정 날짜의 전처리된 clean 텍스트 반환. 파일이 없으면 None 반환."""
    clean_path = CLEAN_DIR / f"{date}_clean.txt"
    if clean_path.exists():
        return clean_path.read_text(encoding="utf-8")
    return None


def load_curriculum() -> dict[str, dict]:
    """
    커리큘럼 CSV 로드 → {date: {week, subject, content, learning_goal, sessions}} 형태로 반환.
    날짜 하나에 오전/오후 여러 row가 있으면 통합.
    """
    df = pd.read_csv(CURRICULUM_PATH, encoding="utf-8")
    df["date"] = df["date"].astype(str).str.strip()

    result: dict[str, dict] = {}
    for date, group in df.groupby("date"):
        row = group.iloc[0]
        contents = group["content"].dropna().unique().tolist()
        goals = group["learning_goal"].dropna().unique().tolist()
        result[date] = {
            "week": int(row["week"]),
            "subject": row["subject"],
            "content": " / ".join(contents),
            "learning_goal": " / ".join(goals),
            "sessions": group["session"].tolist(),
        }
    return result
