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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    from src.database import Base, engine
    import src.models.user  # noqa — 모델 등록
    import src.models.wrong_note  # noqa — 모델 등록
    import src.models.study_goal  # noqa — 모델 등록
    Base.metadata.create_all(bind=engine)
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


# ── Auth request / response models ───────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


# ── Wrong Note request models ─────────────────────────────────────────────────

class WrongNoteCreate(BaseModel):
    question: str
    question_type: str
    user_answer: str
    correct_answer: str
    explanation: Optional[str] = None
    concept_tag: Optional[str] = None
    lecture_date: Optional[str] = None


class WrongNotesBulkCreate(BaseModel):
    notes: list[WrongNoteCreate]


# ── Study Goal request models ─────────────────────────────────────────────────

class StudyGoalCreate(BaseModel):
    exam_name: str
    exam_date: str          # YYYY-MM-DD
    lecture_dates: list[str]  # ["YYYY-MM-DD", ...]


# ── Auth endpoints ────────────────────────────────────────────────────────────

from src.database import get_db
from src.auth import get_current_user


@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    from src.models.user import User
    from src.auth import hash_password
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다.")
    user = User(email=req.email, password_hash=hash_password(req.password), name=req.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "created_at": user.created_at}


@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    from src.models.user import User
    from src.auth import verify_password, create_access_token
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "name": user.name, "created_at": user.created_at},
    }


@app.get("/api/auth/me")
def me(current_user=Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email, "name": current_user.name, "created_at": current_user.created_at}


# ── Wrong Note endpoints ──────────────────────────────────────────────────────

@app.post("/api/notes")
def save_notes(req: WrongNotesBulkCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from src.models.wrong_note import WrongNote
    saved = []
    for item in req.notes:
        note = WrongNote(user_id=current_user.id, **item.dict())
        db.add(note)
        saved.append(note)
    db.commit()
    for note in saved:
        db.refresh(note)
    return [{"id": n.id, "question": n.question, "concept_tag": n.concept_tag} for n in saved]


@app.get("/api/notes")
def get_notes(concept_tag: Optional[str] = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from src.models.wrong_note import WrongNote
    query = db.query(WrongNote).filter(WrongNote.user_id == current_user.id)
    if concept_tag:
        query = query.filter(WrongNote.concept_tag == concept_tag)
    notes = query.order_by(WrongNote.created_at.desc()).all()
    return [
        {
            "id": n.id,
            "question": n.question,
            "question_type": n.question_type,
            "user_answer": n.user_answer,
            "correct_answer": n.correct_answer,
            "explanation": n.explanation,
            "concept_tag": n.concept_tag,
            "lecture_date": n.lecture_date,
            "created_at": n.created_at,
        }
        for n in notes
    ]


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from src.models.wrong_note import WrongNote
    note = db.query(WrongNote).filter(WrongNote.id == note_id, WrongNote.user_id == current_user.id).first()
    if not note:
        raise HTTPException(status_code=404, detail="오답 노트를 찾을 수 없습니다.")
    db.delete(note)
    db.commit()
    return {"success": True}


# ── Study Goal endpoints ──────────────────────────────────────────────────────

@app.post("/api/goals", status_code=201)
def create_goal(req: StudyGoalCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    import json
    from datetime import date as date_type
    from src.models.study_goal import StudyGoal
    exam_date = date_type.fromisoformat(req.exam_date)
    goal = StudyGoal(
        user_id=current_user.id,
        exam_name=req.exam_name,
        exam_date=exam_date,
        lecture_dates=json.dumps(req.lecture_dates, ensure_ascii=False),
        is_active=True,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_dict(goal)


@app.get("/api/goals")
def list_goals(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from src.models.study_goal import StudyGoal
    goals = db.query(StudyGoal).filter(StudyGoal.user_id == current_user.id).order_by(StudyGoal.created_at.desc()).all()
    return [_goal_dict(g) for g in goals]


@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from src.models.study_goal import StudyGoal
    goal = db.query(StudyGoal).filter(StudyGoal.id == goal_id, StudyGoal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="학습 목표를 찾을 수 없습니다.")
    db.delete(goal)
    db.commit()
    return {"success": True}


@app.get("/api/goals/{goal_id}/plan")
def get_goal_plan(goal_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from src.models.study_goal import StudyGoal
    goal = db.query(StudyGoal).filter(StudyGoal.id == goal_id, StudyGoal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="학습 목표를 찾을 수 없습니다.")
    from src.services.study_plan_service import generate_study_plan
    from src.models.wrong_note import WrongNote
    wrong_notes = db.query(WrongNote).filter(WrongNote.user_id == current_user.id).all()
    plan = generate_study_plan(goal, wrong_notes)
    return plan


def _goal_dict(goal):
    import json
    return {
        "id": goal.id,
        "exam_name": goal.exam_name,
        "exam_date": goal.exam_date.isoformat() if goal.exam_date else None,
        "lecture_dates": json.loads(goal.lecture_dates) if goal.lecture_dates else [],
        "is_active": goal.is_active,
        "created_at": goal.created_at,
    }


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


# ── Quiz history endpoint ─────────────────────────────────────────────────────

@app.get("/api/quiz/history")
def list_quiz_history(limit: int = 6):
    """최근 생성된 퀴즈 목록을 반환합니다."""
    import json
    from config.settings import GENERATED_QUIZ_DIR
    quiz_dir = Path(GENERATED_QUIZ_DIR)
    if not quiz_dir.exists():
        return []
    files = sorted(quiz_dir.glob("quiz_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    result = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            result.append({
                "quiz_set_id": data.get("quiz_set_id", ""),
                "generated_at": data.get("generated_at", ""),
                "lecture_date": data.get("lecture_date"),
                "difficulty": data.get("difficulty", "medium"),
                "question_count": len(data.get("quizzes", [])),
            })
        except Exception:
            continue
    return result


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
