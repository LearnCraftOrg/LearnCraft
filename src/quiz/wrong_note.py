"""오답 노트 모듈.

퀴즈에서 틀린 문제를 JSON 파일에 영구 저장하고,
다시 풀기 시 맞춘 문제를 오답 노트에서 자동 제거합니다.

파일 위치: ./data/wrong_note.json
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

WRONG_NOTE_PATH = Path("./data/wrong_note.json")


def _load() -> list[dict]:
    """JSON 파일에서 오답 목록 로드."""
    if not WRONG_NOTE_PATH.exists():
        return []
    try:
        return json.loads(WRONG_NOTE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    """오답 목록을 JSON 파일에 저장."""
    WRONG_NOTE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WRONG_NOTE_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _qid(question: str) -> str:
    """문제 텍스트의 SHA1 앞 12자리를 고유 ID로 사용."""
    return hashlib.sha1(question.strip().encode()).hexdigest()[:12]


def save_wrong_answers(quiz_results: list[dict], lecture_dates: list[str]) -> int:
    """
    퀴즈 오답을 오답 노트에 저장.

    같은 문제(question 해시 기준)가 이미 있으면 wrong_count를 증가시키고,
    새 문제면 새 항목으로 추가합니다.

    Args:
        quiz_results: 퀴즈 결과 리스트
                      (is_correct, question, type, options, answer, user_answer, explanation 포함)
        lecture_dates: 출처 강의 날짜 목록

    Returns:
        새로 추가된 오답 수
    """
    entries = _load()
    entry_map = {e["id"]: e for e in entries}
    now = datetime.now().isoformat(timespec="seconds")
    added = 0

    for r in quiz_results:
        if r.get("is_correct", True):
            continue

        qid = _qid(r["question"])
        if qid in entry_map:
            entry_map[qid]["wrong_count"] += 1
            entry_map[qid]["last_tried_at"] = now
            entry_map[qid]["user_answer"] = r.get("user_answer", "")
        else:
            entry_map[qid] = {
                "id": qid,
                "saved_at": now,
                "last_tried_at": now,
                "lecture_dates": lecture_dates,
                "question": r["question"],
                "type": r.get("type", "multiple_choice"),
                "options": r.get("options", {}),
                "answer": r["answer"],
                "user_answer": r.get("user_answer", ""),
                "explanation": r.get("explanation", ""),
                "wrong_count": 1,
            }
            added += 1

    _save(list(entry_map.values()))
    return added


def remove_mastered(question_ids: list[str]) -> None:
    """정답 맞춘 문제를 오답 노트에서 제거."""
    id_set = set(question_ids)
    entries = _load()
    entries = [e for e in entries if e["id"] not in id_set]
    _save(entries)


def load_wrong_note() -> list[dict]:
    """오답 노트 전체 로드 (마지막 시도 기준 최신순)."""
    entries = _load()
    return sorted(entries, key=lambda e: e["last_tried_at"], reverse=True)


def update_memo(entry_id: str, memo: str) -> bool:
    """오답 항목에 개인 메모를 저장/수정합니다.

    Args:
        entry_id: 오답 항목 ID
        memo: 저장할 메모 텍스트

    Returns:
        항목을 찾아 저장했으면 True, 없으면 False
    """
    entries = _load()
    for e in entries:
        if e["id"] == entry_id:
            e["memo"] = memo.strip()
            _save(entries)
            return True
    return False


def to_quiz_format(entries: list[dict]) -> list[dict]:
    """오답 노트 항목을 퀴즈 플레이어 형식으로 변환."""
    return [
        {
            "question": e["question"],
            "type": e["type"],
            "options": e.get("options", {}),
            "answer": e["answer"],
            "explanation": e["explanation"],
            "_wn_id": e["id"],  # 정답 시 오답 노트 제거를 위한 ID
        }
        for e in entries
    ]
