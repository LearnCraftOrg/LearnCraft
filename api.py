"""LearnCraft FastAPI 서버 — HTML 프론트엔드용 REST API."""
from __future__ import annotations

import asyncio
import sys

# Windows에서 uvicorn 이벤트 루프 호환성 문제 해결
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_indexing():
    """미인덱싱 강의를 벡터스토어에 추가."""
    from src.ingestion.loader import get_available_dates, load_script, load_lecture_topics
    from src.ingestion.chunker import chunk_text
    from src.vectorstore.store import add_documents, get_indexed_dates

    available = get_available_dates()
    indexed = get_indexed_dates()
    unindexed = [d for d in available if d not in indexed]

    if not unindexed:
        logger.info("모든 강의가 이미 인덱싱되어 있습니다.")
        return

    logger.info("인덱싱 시작: %d개 강의", len(unindexed))
    for date in unindexed:
        text = load_script(date)
        if not text:
            continue
        headings = re.findall(r'^## (.+)', text, re.MULTILINE)
        meta = {
            "subject": "",
            "content": load_lecture_topics(date),
            "learning_goal": " / ".join(headings),
        }
        docs = chunk_text(text, {"date": date, **meta})
        add_documents(docs)
        logger.info("인덱싱 완료: %s (%d chunks)", date, len(docs))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.get_event_loop().run_in_executor(None, _run_indexing)
    yield


app = FastAPI(title="LearnCraft API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_ui(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/ui/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ── Static file serving ───────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "app"
DOCS_DIR = Path(__file__).parent / "docs"

# 품질 보고서 디렉토리 (없으면 생성)
from config.settings import QUIZ_REPORT_DIR, GENERATED_QUIZ_DIR, QUIZ_EVAL_DIR
QUIZ_REPORT_DIR = Path(QUIZ_REPORT_DIR)
QUIZ_REPORT_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_QUIZ_DIR = Path(GENERATED_QUIZ_DIR)

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
    """모든 강의 날짜와 메타데이터를 반환합니다."""
    global _lecture_cache, _lecture_cache_time
    if _lecture_cache is not None and time.time() - _lecture_cache_time < CACHE_TTL:
        return _lecture_cache
    from src.ingestion.loader import get_available_dates, get_lecture_metadata
    dates = get_available_dates()
    result = []
    for date in sorted(dates, reverse=True):
        meta = get_lecture_metadata(date)
        result.append({
            "date": date,
            "subject": meta.get("track", ""),
            "content": meta.get("topic", ""),
            "learning_goal": meta.get("learning_goal", ""),
            "category": meta.get("category", ""),
            "track": meta.get("track", ""),
        })
    _lecture_cache = result
    _lecture_cache_time = time.time()
    return result


@app.get("/api/lectures/{date}")
def get_lecture(date: str):
    """특정 날짜의 강의 상세 정보를 반환합니다."""
    from src.ingestion.loader import load_script, get_lecture_metadata
    if load_script(date) is None:
        raise HTTPException(status_code=404, detail=f"{date} 날짜의 강의를 찾을 수 없습니다.")
    meta = get_lecture_metadata(date)
    return {
        "date": date,
        "subject": meta.get("track", ""),
        "content": meta.get("topic", ""),
        "learning_goal": meta.get("learning_goal", ""),
        "category": meta.get("category", ""),
        "track": meta.get("track", ""),
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
                code_template=quiz.get("code_template", ""),
                user_inputs=[user_ans] if isinstance(user_ans, str) else user_ans,
                expected_output=quiz.get("expected_output", ""),
                language=quiz.get("language", "python"),
            )
            results[qid] = {
                "correct": run_result.get("is_correct", False),
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
    import json
    from src.ingestion.loader import load_lecture_topics

    reports = []
    for f in sorted(QUIZ_REPORT_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        # report_{uuid}.html → quiz_{uuid}.json
        uuid = f.stem.removeprefix("report_")
        quiz_file = GENERATED_QUIZ_DIR / f"quiz_{uuid}.json"

        lecture_date = ""
        difficulty = ""
        topic = ""
        overall_score = None
        grade = ""
        if quiz_file.exists():
            try:
                quiz_data = json.loads(quiz_file.read_text(encoding="utf-8"))
                lecture_date = quiz_data.get("lecture_date", "")
                difficulty = quiz_data.get("difficulty", "")
                if lecture_date:
                    topic = load_lecture_topics(lecture_date)
            except Exception:
                pass

        eval_file = Path(QUIZ_EVAL_DIR) / f"eval_{uuid}.json"
        if eval_file.exists():
            try:
                eval_data = json.loads(eval_file.read_text(encoding="utf-8"))
                overall_score = eval_data.get("overall_score")
                grade = eval_data.get("grade", "")
            except Exception:
                pass

        reports.append({
            "filename": f.name,
            "created_at": f.stat().st_mtime,
            "lecture_date": lecture_date,
            "difficulty": difficulty,
            "topic": topic,
            "overall_score": overall_score,
            "grade": grade,
        })
    return reports
