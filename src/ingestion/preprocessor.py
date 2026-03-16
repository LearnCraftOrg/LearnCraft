"""STT 강의 스크립트 텍스트 정제.

입력 형식: <09:10:18> 767644ba: 텍스트
출력: 타임스탬프/화자ID 제거된 연속 텍스트
"""
import re

_TIMESTAMP_PATTERN = re.compile(r"^<\d{2}:\d{2}:\d{2}>\s+[a-f0-9]+:\s*", re.MULTILINE)
_MULTI_SPACE = re.compile(r"\s{2,}")


def preprocess(raw_text: str) -> str:
    """
    1. 타임스탬프 + 화자ID 접두사 제거
    2. 빈 줄 제거
    3. 줄을 공백으로 이어 붙여 연속 텍스트 생성
    """
    lines = raw_text.splitlines()
    cleaned = []
    for line in lines:
        line = _TIMESTAMP_PATTERN.sub("", line).strip()
        if line:
            cleaned.append(line)

    text = " ".join(cleaned)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()
