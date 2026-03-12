"""퀴즈 생성 파이프라인 디버그 테스트.

실행 방법:
    cd c:\\Users\\amate\\GIT\\LearnCraft
    python tests/test_quiz_generation.py
    python tests/test_quiz_generation.py 2026-02-03   # 날짜 지정
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-02-02"

print(f"\n{'='*60}")
print(f"  퀴즈 생성 디버그: {DATE}")
print(f"{'='*60}\n")

# ── Step 1. clean 파일 로드 ──────────────────────────────────
print("[1/4] clean 파일 로드")
from src.ingestion.loader import load_clean_script, load_curriculum

text = load_clean_script(DATE)
if not text:
    print(f"  ❌ data/clean/{DATE}_clean.txt 없음")
    sys.exit(1)
print(f"  ✅ {len(text):,}자 로드")
print(f"  미리보기: {text[:100]}...\n")

# ── Step 2. 인덱싱 여부 확인 & 인덱싱 ──────────────────────────
print("[2/4] 인덱싱 확인 및 청킹")
from src.ingestion.chunker import chunk_text
from src.vectorstore.store import is_date_indexed, add_documents

curriculum_map = load_curriculum()
info = curriculum_map.get(DATE, {})
print(f"  커리큘럼: {info.get('subject', '-')} / {info.get('content', '-')[:40]}")
print(f"  학습목표: {info.get('learning_goal', '-')[:60]}")

if is_date_indexed(DATE):
    print(f"  ✅ 이미 인덱싱됨, 스킵\n")
else:
    metadata = {
        "date": DATE,
        "week": str(info.get("week", "")),
        "subject": info.get("subject", ""),
        "content": info.get("content", ""),
        "learning_goal": info.get("learning_goal", ""),
    }

    print("  청킹 중...", end=" ", flush=True)
    t0 = time.time()
    docs = chunk_text(text, metadata)
    chunk_elapsed = time.time() - t0
    print(f"{len(docs)}개 청크 생성 ({chunk_elapsed:.2f}s)")

    print(f"  임베딩 & 저장 중 ", end="", flush=True)
    t1 = time.time()
    for i, doc in enumerate(docs, 1):
        if i % max(1, len(docs) // 10) == 0 or i == len(docs):
            pct = int(i / len(docs) * 100)
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            print(f"\r  임베딩 & 저장 중 [{bar}] {pct}% ({i}/{len(docs)})", end="", flush=True)
    count = add_documents(docs)
    embed_elapsed = time.time() - t1
    print(f"\n  ✅ {count}개 청크 인덱싱 완료 (임베딩+저장: {embed_elapsed:.2f}s)\n")

# ── Step 3. RAG 컨텍스트 확인 ────────────────────────────────
print("[3/4] RAG 컨텍스트 검색")
from src.rag.pipeline import build_context
from src.rag.retriever import get_retriever

ctx = build_context(DATE)
print(f"  검색 쿼리: {ctx['query'][:80]}")

retriever = get_retriever(DATE)
retrieved_docs = retriever.invoke(ctx["query"])
print(f"  검색된 청크: {len(retrieved_docs)}개 (총 {len(ctx['lecture_context']):,}자)\n")

for i, doc in enumerate(retrieved_docs, 1):
    chunk_idx = doc.metadata.get("chunk_index", "?")
    print(f"  ┌─ [청크 {i}] chunk_index={chunk_idx}")
    print(f"  │  {doc.page_content[:120].replace(chr(10), ' ')}...")
    print(f"  └─ ({len(doc.page_content)}자)\n")

# ── Step 4. 퀴즈 생성 ────────────────────────────────────────
print("[4/4] GPT-4o 퀴즈 생성 중...", end=" ", flush=True)
from src.quiz.generator import generate_quiz

t2 = time.time()
result = generate_quiz(DATE)
gen_elapsed = time.time() - t2
quizzes = result.get("quizzes", [])
print(f"✅ {len(quizzes)}문항 생성 완료 ({gen_elapsed:.2f}s)\n")

# ── 결과 출력 ────────────────────────────────────────────────
print(f"{'='*60}")
print("  생성된 문제 목록")
print(f"{'='*60}\n")

for i, q in enumerate(quizzes, 1):
    qtype = "객관식" if q["type"] == "multiple_choice" else "주관식"
    print(f"[Q{i}] ({qtype}) {q['question']}")
    if q["type"] == "multiple_choice":
        for key, val in q.get("options", {}).items():
            print(f"      {key}. {val}")
    print(f"  → 정답: {q['answer']}")
    print(f"  → 해설: {q['explanation']}\n")

# JSON 전체 저장
out_path = ROOT / "tests" / f"output_{DATE}.json"
out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"JSON 전체 결과 저장: {out_path}")
