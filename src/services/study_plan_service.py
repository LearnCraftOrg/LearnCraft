"""학습 플랜 생성 서비스.

StudyGoal + 오답노트를 기반으로 시험까지의 일별 학습 계획을 생성합니다.
오답이 많은 강의를 초반에 집중 배치하는 가중치 분배 로직을 사용합니다.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, timedelta

from openai import OpenAI

from config.settings import LLM_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def generate_study_plan(goal, wrong_notes: list) -> dict:
    """StudyGoal + 오답노트를 받아 학습 플랜 dict를 반환."""
    today = date.today()
    exam_date: date = goal.exam_date if isinstance(goal.exam_date, date) else date.fromisoformat(str(goal.exam_date))
    lecture_dates: list[str] = json.loads(goal.lecture_dates) if isinstance(goal.lecture_dates, str) else goal.lecture_dates

    dday = max((exam_date - today).days, 0)

    # ── 오답 집계: 개념 태그 빈도 + 강의 날짜별 오답 수/개념 ────────────────────
    tag_counts: Counter = Counter()
    date_wrong_map: dict[str, dict] = {}   # {lecture_date: {"count": int, "concepts": [str]}}

    for note in wrong_notes:
        if note.concept_tag:
            tag_counts[note.concept_tag] += 1
        ldate = note.lecture_date
        if ldate:
            entry = date_wrong_map.setdefault(ldate, {"count": 0, "concepts": []})
            entry["count"] += 1
            if note.concept_tag and note.concept_tag not in entry["concepts"]:
                entry["concepts"].append(note.concept_tag)

    weak_concepts = [tag for tag, _ in tag_counts.most_common(5)]

    # ── 강의를 오답 수 기준 내림차순 정렬 → 취약 강의 분류 ─────────────────────
    sorted_lectures = sorted(
        lecture_dates,
        key=lambda d: date_wrong_map.get(d, {}).get("count", 0),
        reverse=True,
    )
    weak_cutoff = max(1, round(len(sorted_lectures) * 0.3)) if sorted_lectures else 0
    weak_lectures = sorted_lectures[:weak_cutoff]
    normal_lectures = sorted_lectures[weak_cutoff:]

    # ── 가중치 분배 ──────────────────────────────────────────────────────────
    days_available = max(dday, 1)
    daily_plan = _distribute_lectures(
        weak_lectures, normal_lectures, days_available, today, date_wrong_map
    )

    # ── LLM 팁 생성 ──────────────────────────────────────────────────────────
    tips = _generate_tips(goal.exam_name, weak_concepts, daily_plan)
    for i, day_item in enumerate(daily_plan):
        day_item["tip"] = tips[i] if i < len(tips) else ""

    return {
        "goal": {
            "id": goal.id,
            "exam_name": goal.exam_name,
            "exam_date": exam_date.isoformat(),
        },
        "dday": dday,
        "weak_concepts": weak_concepts,
        "daily_plan": daily_plan,
    }


def _distribute_lectures(
    weak_lectures: list[str],
    normal_lectures: list[str],
    days: int,
    start: date,
    date_wrong_map: dict,
) -> list[dict]:
    """오답 가중치 기반 강의 분배.

    - 취약 강의(상위 30%): 초반 일정에 1개/일씩 집중 배치
    - 나머지 강의: 남은 날짜에 균등 분배
    - 각 일별 항목에 focus_concepts(해당 강의의 오답 개념 태그) 포함
    """
    display_days = min(days, 14)
    plan = [
        {"day": i + 1, "date": (start + timedelta(days=i)).isoformat(), "lectures": [], "focus_concepts": []}
        for i in range(display_days)
    ]

    # ── 취약 강의: 초반에 1개/일 배치 (최대 display_days의 절반까지) ──────────
    weak_days = min(len(weak_lectures), max(1, display_days // 2))
    for j, lec in enumerate(weak_lectures[:weak_days]):
        plan[j]["lectures"].append(lec)

    # ── 나머지 강의: 남은 날짜에 균등 분배 ──────────────────────────────────
    remaining_plan = plan[weak_days:]
    if normal_lectures and remaining_plan:
        total = len(normal_lectures)
        r_days = len(remaining_plan)
        if total <= r_days:
            # linspace 방식
            for j, lec in enumerate(normal_lectures):
                idx = round(j * (r_days - 1) / max(total - 1, 1)) if total > 1 else 0
                remaining_plan[min(idx, r_days - 1)]["lectures"].append(lec)
        else:
            assigned = 0
            for i in range(r_days):
                rem_d = r_days - i
                rem_l = total - assigned
                count = max(1, round(rem_l / rem_d))
                remaining_plan[i]["lectures"] = normal_lectures[assigned: assigned + count]
                assigned += count
                if assigned >= total:
                    break

    # ── focus_concepts 설정 ──────────────────────────────────────────────────
    for day_item in plan:
        concepts: list[str] = []
        for lec in day_item["lectures"]:
            concepts.extend(date_wrong_map.get(lec, {}).get("concepts", []))
        # 중복 제거, 순서 유지
        seen: set[str] = set()
        unique: list[str] = []
        for c in concepts:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        day_item["focus_concepts"] = unique

    return plan


def _generate_tips(exam_name: str, weak_concepts: list[str], daily_plan: list[dict]) -> list[str]:
    """LLM으로 일별 학습 팁을 생성. 실패 시 빈 문자열 목록 반환."""
    if not daily_plan:
        return []

    plan_summary = "\n".join(
        f"Day {d['day']} ({d['date']}): 강의 {len(d['lectures'])}개"
        + (f", 취약개념: {', '.join(d['focus_concepts'][:2])}" if d.get("focus_concepts") else "")
        for d in daily_plan
    )
    weak_str = ", ".join(weak_concepts) if weak_concepts else "없음"

    prompt = f"""시험명: {exam_name}
취약 개념: {weak_str}
학습 일정:
{plan_summary}

위 정보를 바탕으로 각 Day별 한 줄 학습 팁을 JSON 배열로 작성하세요.
- 배열 길이는 반드시 {len(daily_plan)}개
- 각 팁은 30자 이내 한국어 문장
- 취약 개념이 있다면 자연스럽게 반영
- 형식: ["팁1", "팁2", ...]"""

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "당신은 학습 플래너입니다. 지시에 따라 JSON만 반환하세요."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("[")
        end = raw.rfind("]") + 1
        tips = json.loads(raw[start:end])
        if isinstance(tips, list) and len(tips) == len(daily_plan):
            return [str(t) for t in tips]
    except Exception as e:
        logger.warning("학습 팁 LLM 생성 실패: %s", e)

    return ["" for _ in daily_plan]
