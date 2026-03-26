"""RAG 파이프라인 동작 확인 스크립트."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("1. Retriever 테스트...")
from src.rag.retriever import retrieve_by_query
docs = retrieve_by_query("FastAPI 라우터 의존성 주입")
print(f"   검색된 섹션: {len(docs)}개")
for d in docs:
    print(f"   - {d['metadata'].get('date')} | {d['metadata'].get('section_key', '')[:50]}")

print("\n2. 학습 가이드 생성 테스트...")
from src.guide.summarizer import generate_guide_by_query
guide = generate_guide_by_query("FastAPI 라우터 의존성 주입")
print(f"   핵심 개념: {len(guide.get('key_concepts', []))}개")
print(f"   요약: {guide.get('summary', '')[:100]}...")

print("\n✅ RAG 파이프라인 정상 동작!")
