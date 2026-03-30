from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from src.database import Base


class WrongNote(Base):
    __tablename__ = "wrong_notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 문제 식별 / 중복 방지
    question = Column(Text, nullable=False)
    question_hash = Column(String(12), nullable=True, index=True)   # SHA1[:12] dedup key

    # 퀴즈 데이터
    question_type = Column(String, nullable=False)
    options = Column(Text, nullable=True)           # JSON: {"A": "...", "B": "..."}
    user_answer = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)

    # 분류
    concept_tag = Column(String, nullable=True, index=True)
    lecture_date = Column(String, nullable=True)    # 단일 날짜 (하위 호환)
    lecture_dates = Column(Text, nullable=True)     # JSON: ["YYYY-MM-DD", ...]

    # 학습 추적
    wrong_count = Column(Integer, default=1, nullable=False)
    last_tried_at = Column(DateTime, nullable=True)
    memo = Column(Text, nullable=True)              # 개인 메모

    created_at = Column(DateTime, default=datetime.utcnow)
