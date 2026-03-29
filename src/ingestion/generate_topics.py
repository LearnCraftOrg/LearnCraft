"""
기존 refined.md 파일에서 날짜별 강의 주제를 추출하고 7개 트랙으로 분류해 topics.json으로 저장한다.

새 구조: {date: {topic, category, track, learning_goal}}

사용법: python src/ingestion/generate_topics.py
"""

import json
import re

from openai import OpenAI

from config.settings import REFINED_DIR, TOPICS_PATH, OPENAI_API_KEY

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

TRACKS = [
    "Python",
    "백엔드 : JAVA",
    "클라우드 엔지니어링",
    "데이터 분석",
    "UX/UI 디자인",
    "그로스 마케팅",
    "AI 심화 : 자연어 처리",
]

TRACK_TO_CATEGORY = {
    "Python": "소프트웨어 개발",
    "백엔드 : JAVA": "소프트웨어 개발",
    "클라우드 엔지니어링": "소프트웨어 개발",
    "데이터 분석": "데이터, AI 및 사용자 경험",
    "UX/UI 디자인": "데이터, AI 및 사용자 경험",
    "그로스 마케팅": "데이터, AI 및 사용자 경험",
    "AI 심화 : 자연어 처리": "단기심화",
}


def extract_topic(text: str) -> str:
    """refined.md 텍스트에서 대표 강의 주제를 추출한다."""
    first_line = text.splitlines()[0] if text else ""
    if first_line.startswith("# 강의 주제:"):
        return first_line[len("# 강의 주제:"):].strip()
    headings = re.findall(r"^## (.+)", text, re.MULTILINE)
    return headings[0] if headings else ""


def extract_learning_goals(text: str) -> str:
    """refined.md에서 ## 헤딩 최대 3개를 줄바꿈으로 연결해 반환한다."""
    headings = re.findall(r"^## (.+)", text, re.MULTILINE)
    return "\n".join(headings[:3])


def classify_track(topic: str, learning_goals: str, client: OpenAI) -> str:
    """GPT-4o-mini를 사용해 강의를 7개 트랙 중 하나로 분류한다."""
    track_list = ", ".join(TRACKS)
    user_msg = f"강의 주제: {topic}\n소목차:\n{learning_goals}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    f"다음 강의 주제와 소목차를 보고 아래 7개 트랙 중 정확히 하나를 골라라.\n"
                    f"트랙 목록: {track_list}\n"
                    "트랙 이름만 출력하고 다른 내용은 절대 쓰지 마라."
                ),
            },
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        max_tokens=30,
    )
    raw = resp.choices[0].message.content.strip()
    if raw in TRACKS:
        return raw
    for t in TRACKS:
        if t in raw or raw in t:
            return t
    return TRACKS[0]


def main() -> None:
    client = OpenAI(api_key=OPENAI_API_KEY)
    topics: dict[str, dict] = {}

    md_files = sorted(REFINED_DIR.glob("*_refined.md"))
    if not md_files:
        print(f"refined.md 파일을 찾을 수 없습니다: {REFINED_DIR}")
        return

    for md_file in md_files:
        m = _DATE_RE.search(md_file.name)
        if not m:
            continue
        date = m.group(1)
        text = md_file.read_text(encoding="utf-8")
        topic = extract_topic(text)
        learning_goals = extract_learning_goals(text)
        track = classify_track(topic, learning_goals, client)
        category = TRACK_TO_CATEGORY.get(track, "소프트웨어 개발")
        topics[date] = {
            "topic": topic,
            "category": category,
            "track": track,
            "learning_goal": learning_goals,
        }
        print(f"  {date}: [{category} | {track}] {topic}")

    with open(TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

    print(f"\n저장 완료: {TOPICS_PATH} ({len(topics)}개 날짜)")


if __name__ == "__main__":
    main()
