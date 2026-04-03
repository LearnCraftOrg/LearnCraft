# LearnCraft

강의 스크립트를 기반으로 퀴즈, 해설, 학습 가이드를 자동 생성하는 RAG 기반 AI 학습 플랫폼입니다.

## 주요 기능

- **퀴즈 자동 생성**: 강의 내용을 분석하여 다양한 유형의 퀴즈 생성
- **학습 가이드**: 개인화된 학습 가이드 및 학습 계획 제공
- **오답 노트**: 틀린 문제를 자동으로 기록하고 취약점 분석
- **RAG 파이프라인**: 벡터 검색(ChromaDB) + BM25 하이브리드 검색
- **사용자 인증**: JWT 기반 회원가입/로그인

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | Python, FastAPI |
| Frontend | HTML, CSS, JavaScript |
| AI/LLM | OpenAI GPT, LangChain |
| Vector DB | ChromaDB |
| Search | BM25 (rank-bm25), 하이브리드 검색 |
| Auth | JWT (python-jose), bcrypt |
| DB | SQLAlchemy |

## 프로젝트 구조

```
LearnCraft/
├── api.py                  # FastAPI 엔트리포인트
├── app/                    # 프론트엔드 (HTML/JS)
│   ├── index.html
│   ├── quiz-setup.html
│   ├── quiz-review.html
│   ├── quiz-feedback.html
│   ├── wrong-notes.html
│   ├── study-plan.html
│   ├── personalized-guide.html
│   ├── lectures.html
│   ├── lecture-detail.html
│   └── styles/
├── src/                    # 백엔드 핵심 모듈
│   ├── ingestion/          # 강의 데이터 로드 및 전처리
│   ├── vectorstore/        # 임베딩 및 벡터 저장소
│   ├── rag/                # RAG 파이프라인 및 검색
│   ├── quiz/               # 퀴즈 생성, 채점, 오답 분석
│   ├── guide/              # 학습 가이드 생성
│   ├── evaluation/         # 평가 및 품질 검증
│   ├── models/             # DB 모델 (User, QuizRecord 등)
│   ├── auth.py             # 인증 로직
│   └── database.py         # DB 연결
├── config/
│   └── settings.py         # 환경 설정
├── data/                   # 강의 데이터 및 chroma db
├── tests/                  # 테스트
└── requirements.txt
```

## 시작하기

### 1. 환경 설정

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성:

```env
OPENAI_API_KEY=your_openai_api_key
SECRET_KEY=your_jwt_secret_key
DATABASE_URL=sqlite:///./learncraft.db
```

### 3. 서버 실행

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://localhost:8000`으로 접속하세요.

## 데이터 파이프라인

1. **강의 로드** (`src/ingestion/loader.py`): 강의 스크립트 파일 로드
2. **전처리** (`src/ingestion/preprocessor.py`): 텍스트 정제 및 정규화
3. **청킹** (`src/ingestion/chunker.py`): 의미 단위로 분할
4. **임베딩** (`src/vectorstore/embedder.py`): OpenAI 임베딩 생성
5. **벡터 저장** (`src/vectorstore/store.py`): ChromaDB에 저장
6. **검색** (`src/rag/retriever.py`): 하이브리드 검색으로 관련 청크 추출
7. **생성** (`src/quiz/generator.py`, `src/guide/summarizer.py`): LLM으로 콘텐츠 생성
