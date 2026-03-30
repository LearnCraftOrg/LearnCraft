from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from src.database import Base


class WrongNote(Base):
    __tablename__ = "wrong_notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    question_type = Column(String, nullable=False)
    user_answer = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    concept_tag = Column(String, nullable=True)
    lecture_date = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
