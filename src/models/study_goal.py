from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text

from src.database import Base


class StudyGoal(Base):
    __tablename__ = "study_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_name = Column(String, nullable=False)
    exam_date = Column(Date, nullable=False)
    lecture_dates = Column(Text, nullable=False)   # JSON string: ["2024-11-18", ...]
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
