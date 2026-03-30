from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from src.database import Base


class QuizRecord(Base):
    __tablename__ = "quiz_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quiz_set_id = Column(String, nullable=False)
    lecture_date = Column(String, nullable=True)
    difficulty = Column(String, nullable=False)
    total_questions = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    score_pct = Column(Integer, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
