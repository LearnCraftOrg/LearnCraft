"""RAG 파이프라인 동작 확인 스크립트."""
import sys
sys.path.insert(0, "C:/Users/user/AI_NLP_Intern")

print("1. Retriever 테스트...")
from rag.retriever import get_retriever
r = get_retriever(k=3)
docs = r.invoke("FastAPI 라우터 의존성 주입")
print(f"   검색된 섹션: {len(docs)}개")
for d in docs:
    print(f"   - {d.metadata.get('date')} | {d.metadata.get('section_key','')[:50]}")

print("\n2. 학습 가이드 생성 테스트...")
from services.study_guide_service import generate_study_guide
guide = generate_study_guide("FastAPI 라우터 의존성 주입")
print(guide[:1500].encode('utf-8', errors='replace').decode('utf-8'))
print("\n... (이하 생략)")
print("\n✅ RAG 파이프라인 정상 동작!")
