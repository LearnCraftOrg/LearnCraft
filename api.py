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

from config.settings import CORS_ORIGINS, GUEST_EMAIL

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


def _migrate_wrong_notes_table(engine) -> None:
    """wrong_notes 테이블에 신규 컬럼이 없으면 추가합니다 (SQLite ALTER TABLE)."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "wrong_notes" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("wrong_notes")}
    additions = [
        ("question_hash", "VARCHAR(12)"),
        ("options",       "TEXT"),
        ("lecture_dates", "TEXT"),
        ("wrong_count",   "INTEGER DEFAULT 1 NOT NULL"),
        ("last_tried_at", "DATETIME"),
        ("memo",          "TEXT"),
    ]
    with engine.begin() as conn:
        for col, col_type in additions:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE wrong_notes ADD COLUMN {col} {col_type}"))
    logger.info("wrong_notes 마이그레이션 완료")


def _ensure_guest_user(engine) -> None:
    """비로그인 오답 노트용 게스트 사용자를 DB에 보장합니다."""
    from src.database import SessionLocal
    from src.models.user import User
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == GUEST_EMAIL).first():
            import hashlib
            # bcrypt 없이도 동작하도록 sha256 기반 더미 해시 사용
            dummy_hash = "$2b$12$" + hashlib.sha256(b"learncraft_guest").hexdigest()[:53]
            guest = User(
                email=GUEST_EMAIL,
                password_hash=dummy_hash,
                name="게스트",
            )
            db.add(guest)
            db.commit()
            logger.info("게스트 사용자 생성 완료")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.database import Base, engine
    import src.models.user  # noqa — 모델 등록
    import src.models.wrong_note  # noqa — 모델 등록
    import src.models.study_goal  # noqa — 모델 등록
    import src.models.quiz_record  # noqa — 모델 등록
    Base.metadata.create_all(bind=engine)
    _migrate_wrong_notes_table(engine)
    _ensure_guest_user(engine)
    await asyncio.get_event_loop().run_in_executor(None, _run_indexing)
    yield


app = FastAPI(title="LearnCraft API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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


# ── 오답 노트 요청 모델 (비로그인/JSON → DB 통합) ────────────────────────────

class SaveWrongNoteRequest(BaseModel):
    quiz_results: list[dict]
    lecture_dates: list[str]


class RemoveMasteredRequest(BaseModel):
    ids: list[int]      # DB primary key (integer)


# ── 오답 노트 DB 헬퍼 ─────────────────────────────────────────────────────────

def _get_guest_user_id(db: Session) -> int:
    """게스트 사용자 ID를 반환합니다 (없으면 생성)."""
    from src.models.user import User
    guest = db.query(User).filter(User.email == GUEST_EMAIL).first()
    if not guest:
        import hashlib
        dummy_hash = "$2b$12$" + hashlib.sha256(b"learncraft_guest").hexdigest()[:53]
        guest = User(email=GUEST_EMAIL, password_hash=dummy_hash, name="게스트")
        db.add(guest)
        db.commit()
        db.refresh(guest)
    return guest.id


def _wrong_note_dict(note) -> dict:
    """WrongNote DB 레코드를 프론트엔드 호환 딕셔너리로 변환합니다."""
    import json
    options: dict = {}
    if note.options:
        try:
            options = json.loads(note.options)
        except (json.JSONDecodeError, TypeError):
            pass

    lecture_dates: list = []
    if note.lecture_dates:
        try:
            lecture_dates = json.loads(note.lecture_dates)
        except (json.JSONDecodeError, TypeError):
            pass
    elif note.lecture_date:
        lecture_dates = [note.lecture_date]

    last_tried = note.last_tried_at or note.created_at
    return {
        "id": note.id,
        "question": note.question,
        "type": note.question_type,
        "options": options,
        "answer": note.correct_answer,
        "user_answer": note.user_answer or "",
        "explanation": note.explanation or "",
        "wrong_count": note.wrong_count if note.wrong_count is not None else 1,
        "lecture_dates": lecture_dates,
        "last_tried_at": last_tried.isoformat() if last_tried else "",
        "memo": note.memo or "",
    }


# ── Study Goal request models ─────────────────────────────────────────────────

class StudyGoalCreate(BaseModel):
    exam_name: str
    exam_date: str          # YYYY-MM-DD
    lecture_dates: list[str]  # ["YYYY-MM-DD", ...]


# ── Quiz Record request models ────────────────────────────────────────────────

class QuizRecordCreate(BaseModel):
    quiz_set_id: str
    lecture_date: Optional[str] = None
    difficulty: str
    total_questions: int
    correct_count: int
    score_pct: int
    submitted_at: Optional[str] = None


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


# ── DB 기반 Wrong Note endpoints (로그인 필요) ────────────────────────────────

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


@app.get("/api/quiz/status/{quiz_set_id}")
def quiz_explanation_status(quiz_set_id: str):
    """해설 생성 완료 여부를 반환합니다. complete 시 explanations 맵 포함."""
    import json as _json
    from pathlib import Path
    from config.settings import GENERATED_QUIZ_DIR

    file_path = Path(GENERATED_QUIZ_DIR) / f"quiz_{quiz_set_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="퀴즈를 찾을 수 없습니다.")
    with open(file_path, encoding="utf-8") as f:
        record = _json.load(f)
    status = record.get("explanations_status", "pending")
    response: dict = {"quiz_set_id": quiz_set_id, "explanations_status": status}
    if status == "complete":
        response["explanations"] = {
            q["quiz_id"]: q.get("explanation", "")
            for q in record.get("quizzes", [])
        }
    return response


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
            # 빈 답안은 LLM 호출 없이 즉시 오답 처리
            if not user_ans or not user_ans.strip():
                results[qid] = {"correct": False, "answer": quiz.get("answer")}
                continue
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


# ── Quiz record endpoints ─────────────────────────────────────────────────────

@app.post("/api/quiz/records", status_code=201)
def save_quiz_record(req: QuizRecordCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """로그인된 사용자의 퀴즈 결과를 DB에 저장합니다."""
    from datetime import datetime as dt
    from src.models.quiz_record import QuizRecord
    submitted_at = dt.fromisoformat(req.submitted_at) if req.submitted_at else dt.utcnow()
    record = (
        db.query(QuizRecord)
        .filter(QuizRecord.user_id == current_user.id, QuizRecord.quiz_set_id == req.quiz_set_id)
        .first()
    )
    if record:
        record.lecture_date = req.lecture_date
        record.difficulty = req.difficulty
        record.total_questions = req.total_questions
        record.correct_count = req.correct_count
        record.score_pct = req.score_pct
        record.submitted_at = submitted_at
    else:
        record = QuizRecord(
            user_id=current_user.id,
            quiz_set_id=req.quiz_set_id,
            lecture_date=req.lecture_date,
            difficulty=req.difficulty,
            total_questions=req.total_questions,
            correct_count=req.correct_count,
            score_pct=req.score_pct,
            submitted_at=submitted_at,
        )
        db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "quiz_set_id": record.quiz_set_id, "score_pct": record.score_pct}


@app.get("/api/quiz/records")
def list_quiz_records(limit: int = 20, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """로그인된 사용자의 퀴즈 기록 목록을 반환합니다."""
    from src.models.quiz_record import QuizRecord
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.user_id == current_user.id)
        .order_by(QuizRecord.submitted_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "quiz_set_id": r.quiz_set_id,
            "lecture_date": r.lecture_date,
            "difficulty": r.difficulty,
            "total_questions": r.total_questions,
            "correct_count": r.correct_count,
            "score_pct": r.score_pct,
            "submitted_at": r.submitted_at,
        }
        for r in records
    ]


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


# ── Wrong note endpoints (DB 기반, 비로그인 지원) ─────────────────────────────

@app.get("/api/wrong-note")
def get_wrong_note(db: Session = Depends(get_db)):
    """오답 노트 전체 목록을 반환합니다."""
    from src.models.wrong_note import WrongNote
    guest_id = _get_guest_user_id(db)
    notes = (
        db.query(WrongNote)
        .filter(WrongNote.user_id == guest_id)
        .order_by(WrongNote.last_tried_at.desc(), WrongNote.created_at.desc())
        .all()
    )
    return [_wrong_note_dict(n) for n in notes]


@app.post("/api/wrong-note/save")
def save_wrong_note(req: SaveWrongNoteRequest, db: Session = Depends(get_db)):
    """퀴즈 오답을 오답 노트에 저장합니다. 같은 문제는 wrong_count를 누적합니다."""
    import hashlib, json
    from datetime import datetime as dt
    from src.models.wrong_note import WrongNote

    guest_id = _get_guest_user_id(db)
    now = dt.utcnow()
    added = 0

    for r in req.quiz_results:
        if r.get("is_correct", True):
            continue

        question = r.get("question", "").strip()
        if not question:
            continue
        qhash = hashlib.sha1(question.encode()).hexdigest()[:12]

        existing = (
            db.query(WrongNote)
            .filter(WrongNote.user_id == guest_id, WrongNote.question_hash == qhash)
            .first()
        )
        if existing:
            existing.wrong_count = (existing.wrong_count or 1) + 1
            existing.last_tried_at = now
            existing.user_answer = r.get("user_answer", "")
        else:
            lecture_date = req.lecture_dates[0] if req.lecture_dates else None
            note = WrongNote(
                user_id=guest_id,
                question=question,
                question_hash=qhash,
                question_type=r.get("type", r.get("question_type", "multiple_choice")),
                options=json.dumps(r.get("options", {}), ensure_ascii=False),
                user_answer=r.get("user_answer", ""),
                correct_answer=r.get("answer", r.get("correct_answer", "")),
                explanation=r.get("explanation", ""),
                lecture_date=lecture_date,
                lecture_dates=json.dumps(req.lecture_dates, ensure_ascii=False),
                wrong_count=1,
                last_tried_at=now,
            )
            db.add(note)
            added += 1

    db.commit()
    return {"added": added}


@app.delete("/api/wrong-note")
def remove_from_wrong_note(req: RemoveMasteredRequest, db: Session = Depends(get_db)):
    """오답 노트에서 선택한 항목을 제거합니다."""
    from src.models.wrong_note import WrongNote
    guest_id = _get_guest_user_id(db)
    db.query(WrongNote).filter(
        WrongNote.id.in_(req.ids),
        WrongNote.user_id == guest_id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"removed": len(req.ids)}


class UpdateMemoRequest(BaseModel):
    memo: str


@app.patch("/api/wrong-note/{entry_id}/memo")
def update_wrong_note_memo(entry_id: int, req: UpdateMemoRequest, db: Session = Depends(get_db)):
    """오답 항목에 개인 메모를 저장합니다."""
    from src.models.wrong_note import WrongNote
    guest_id = _get_guest_user_id(db)
    note = db.query(WrongNote).filter(
        WrongNote.id == entry_id,
        WrongNote.user_id == guest_id,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    note.memo = req.memo.strip()
    db.commit()
    return {"ok": True}
