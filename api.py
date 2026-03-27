"""LearnCraft FastAPI 서버 — HTML 프론트엔드용 REST API."""
from __future__ import annotations

import asyncio
import sys

# Windows에서 uvicorn 이벤트 루프 호환성 문제 해결
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LearnCraft API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file serving ───────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "app"
DOCS_DIR = Path(__file__).parent / "docs"

# 품질 보고서 디렉토리 (없으면 생성)
from config.settings import QUIZ_REPORT_DIR
QUIZ_REPORT_DIR = Path(QUIZ_REPORT_DIR)
QUIZ_REPORT_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/docs", StaticFiles(directory=str(DOCS_DIR)), name="docs")
app.mount("/reports", StaticFiles(directory=str(QUIZ_REPORT_DIR)), name="reports")
app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/index.html")


# ── In-memory cache ──────────────────────────────────────────────────────────

_lecture_cache: list[dict] | None = None
_lecture_cache_time: float = 0.0
CACHE_TTL = 300  # 5분


# ── Request / Response models ─────────────────────────────────────────────────

class QuizGenerateRequest(BaseModel):
    date: Optional[str] = None          # 단일 날짜 (YYYY-MM-DD)
    dates: Optional[list[str]] = None   # 복수 날짜
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    query: Optional[str] = None         # 선택적 검색 쿼리


class EvaluateAnswersRequest(BaseModel):
    quizzes: list[dict]     # QuizItem 목록
    answers: dict           # {quiz_id: user_answer}


class PersonalizedGuideRequest(BaseModel):
    query: str              # 틀린 개념 / 검색 쿼리


# ── Lecture endpoints ─────────────────────────────────────────────────────────

@app.get("/api/lectures")
def list_lectures():
    """인덱싱된 모든 강의 날짜와 커리큘럼 정보를 반환합니다."""
    global _lecture_cache, _lecture_cache_time
    if _lecture_cache is not None and time.time() - _lecture_cache_time < CACHE_TTL:
        return _lecture_cache
    from src.vectorstore.store import get_indexed_dates, get_stt_curriculum
    dates = get_indexed_dates()
    result = []
    for date in sorted(dates, reverse=True):
        curriculum = get_stt_curriculum(date)
        result.append({
            "date": date,
            "subject": curriculum.get("subject", ""),
            "content": curriculum.get("content", ""),
            "learning_goal": curriculum.get("learning_goal", ""),
        })
    _lecture_cache = result
    _lecture_cache_time = time.time()
    return result


@app.get("/api/lectures/{date}")
def get_lecture(date: str):
    """특정 날짜의 강의 상세 정보를 반환합니다."""
    from src.vectorstore.store import get_stt_curriculum, is_date_indexed
    if not is_date_indexed(date):
        raise HTTPException(status_code=404, detail=f"{date} 날짜의 강의를 찾을 수 없습니다.")
    curriculum = get_stt_curriculum(date)
    return {
        "date": date,
        "subject": curriculum.get("subject", ""),
        "content": curriculum.get("content", ""),
        "learning_goal": curriculum.get("learning_goal", ""),
    }


# ── Quiz endpoints ────────────────────────────────────────────────────────────

@app.post("/api/quiz/generate")
def generate_quiz(req: QuizGenerateRequest):
    """퀴즈를 생성합니다. 단일 날짜 또는 복수 날짜/쿼리 모드를 지원합니다."""
    from src.rag.pipeline import build_context_by_date, build_context_by_query
    from src.quiz.generator import (
        generate_quiz_from_context,
        generate_quiz_multi_from_context,
    )

    try:
        # 단일 날짜 모드
        if req.date and not req.dates:
            ctx = build_context_by_date(req.date)
            result = generate_quiz_from_context(ctx, difficulty=req.difficulty)
        # 복수 날짜 또는 쿼리 모드
        else:
            dates = req.dates or ([] if not req.date else [req.date])
            ctx = build_context_by_query(dates, req.query)
            result = generate_quiz_multi_from_context(
                ctx, user_query=req.query, difficulty=req.difficulty
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("퀴즈 생성 중 오류")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/quiz/evaluate")
def evaluate_answers(req: EvaluateAnswersRequest):
    """사용자 답안을 채점합니다. 서술형은 LLM 평가, 객관식은 직접 비교."""
    from src.quiz.scoring import evaluate_short_answer
    from src.quiz.code_runner import fill_and_run

    results = {}
    for quiz in req.quizzes:
        qid = quiz.get("quiz_id", "")
        user_ans = req.answers.get(qid, "")
        qtype = quiz.get("type", "")

        if qtype == "multiple_choice":
            correct = user_ans.strip().upper() == quiz.get("answer", "").strip().upper()
            results[qid] = {"correct": correct, "answer": quiz.get("answer")}

        elif qtype == "short_answer":
            correct = evaluate_short_answer(
                question=quiz.get("question", ""),
                correct_answer=quiz.get("answer", ""),
                user_answer=user_ans,
                explanation=quiz.get("explanation", ""),
            )
            results[qid] = {"correct": correct, "answer": quiz.get("answer")}

        elif qtype == "code_completion":
            run_result = fill_and_run(
                template=quiz.get("code_template", ""),
                user_blanks=[user_ans] if isinstance(user_ans, str) else user_ans,
                expected_output=quiz.get("expected_output", ""),
                language=quiz.get("language", "python"),
            )
            results[qid] = {
                "correct": run_result.get("passed", False),
                "answer": quiz.get("blanks", []),
                "output": run_result.get("stdout", ""),
                "error": run_result.get("stderr", ""),
            }

    return results


# ── Guide endpoints ───────────────────────────────────────────────────────────

@app.get("/api/guide/{date}")
def get_guide(date: str):
    """특정 날짜 강의의 학습 가이드를 생성합니다."""
    from src.vectorstore.store import is_date_indexed
    from src.guide.summarizer import generate_guide
    if not is_date_indexed(date):
        raise HTTPException(status_code=404, detail=f"{date} 날짜의 강의를 찾을 수 없습니다.")
    try:
        return generate_guide(date)
    except Exception as e:
        logger.exception("학습 가이드 생성 중 오류")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/guide/personalized")
def get_personalized_guide(req: PersonalizedGuideRequest):
    """틀린 개념 쿼리를 기반으로 개인화 학습 가이드를 생성합니다."""
    from src.guide.summarizer import generate_guide_by_query
    try:
        return generate_guide_by_query(req.query)
    except Exception as e:
        logger.exception("개인화 가이드 생성 중 오류")
        raise HTTPException(status_code=500, detail=str(e))


# ── Report endpoints ──────────────────────────────────────────────────────────

@app.get("/api/reports")
def list_reports():
    """생성된 품질 보고서 목록을 반환합니다."""
    reports = []
    for f in sorted(QUIZ_REPORT_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        reports.append({
            "filename": f.name,
            "created_at": f.stat().st_mtime,
        })
    return reports
