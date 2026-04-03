# LearnCraft

> KDT 부트캠프 수강생을 위한 AI 학습 보조 시스템

강의 녹음 텍스트를 입력하면 **퀴즈 생성 → 채점 → 오답 분석 → 개인화 복습 가이드 → 학습 플랜**까지 end-to-end로 제공합니다.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| **퀴즈 생성** | 강의 내용 기반 객관식·단답형·코드 완성형 문항 자동 생성 |
| **자동 채점** | 단답형은 GPT 의미 채점, 코드 완성형은 Judge0 샌드박스 실행 |
| **학습 가이드** | 핵심 개념·개념 설명(코드 예시)·핵심 요약·흔한 오해·실용적 응용 5섹션 |
| **개인화 가이드** | 오답 키워드 기반 벡터 검색으로 취약 개념 맞춤 가이드 생성 |
| **오답 노트** | 틀린 문항 자동 저장, 메모 및 완료 처리 |
| **학습 플랜** | 시험일 기준 일별 복습 일정 + 취약 개념 태그 자동 생성 |
| **퀴즈 품질 보고서** | 구조·근거·오답지·중복 4단계 자동 품질 평가 |

---

## 기술 스택

| 역할 | 기술 |
|---|---|
| 퀴즈/가이드/채점 LLM | GPT-4o-mini |
| 품질 평가 LLM | Gemini 2.5 Flash Lite |
| 임베딩 | text-embedding-3-small |
| 벡터 DB | ChromaDB |
| 코드 실행 | Judge0 API |
| 한국어 형태소 분석 | Kiwipiepy |
| 키워드 검색 | BM25 (rank_bm25) |
| 백엔드 | FastAPI |
| 프론트엔드 | Static HTML / CSS / JS |
| DB | SQLite + SQLAlchemy |
| 인증 | JWT |

---

## 프로젝트 구조

```
LearnCraft/
├── api.py                  # FastAPI 진입점
├── app/                    # 프론트엔드 (Static HTML)
│   ├── config.js           # API base URL 설정
│   ├── index.html          # 대시보드
│   ├── lectures.html       # 강의 목록
│   ├── lecture-detail.html # 강의 상세 + 학습 가이드
│   ├── quiz-setup.html     # 퀴즈 생성
│   ├── quiz-review.html    # 퀴즈 풀기
│   ├── quiz-feedback.html  # 퀴즈 결과
│   ├── wrong-note.html     # 오답 노트
│   ├── personalized-guide.html  # 개인화 가이드
│   ├── study-plan.html     # 학습 플랜
│   └── quality-report.html # 퀴즈 품질 보고서
├── src/
│   ├── rag/                # RAG 파이프라인 (retriever, chain)
│   ├── quiz/               # 퀴즈 생성·분석·오답 처리
│   ├── guide/              # 학습 가이드 생성
│   ├── ingestion/          # 강의 데이터 로딩·정제·청킹
│   ├── vectorstore/        # ChromaDB 벡터스토어
│   ├── services/           # 학습 가이드 서비스 (LCEL)
│   └── auth.py             # 인증
├── config/
│   └── settings.py         # 환경 변수 설정
├── refined/                # 정제된 강의 마크다운 (YYYY-MM-DD_refined.md)
├── data              # 강의 데이터 및 ChromaDB 로컬 저장소
└── requirements.txt
```

---

## 시작하기

### 1. 환경 설정

```bash
git clone https://github.com/LearnCraftOrg/LearnCraft.git
cd LearnCraft
pip install -r requirements.txt
```

`.env` 파일 생성:

```env
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key        # 품질 보고서용 (선택)
JUDGE0_API_KEY=your_judge0_api_key        # 코드 실행용 (선택)
SECRET_KEY=your_jwt_secret_key
```

### 2. 서버 실행

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://localhost:8000` 접속

---

## 데이터 파이프라인

```
STT 원본 텍스트
    ↓ 잡음 제거 (타임스탬프, 화자 ID)
    ↓ GPT-4o-mini → 구조화된 마크다운 (정제)
    ↓ ## 섹션 단위 청킹
    ↓ 헤딩 텍스트 임베딩 + 섹션 전체 내용은 메타데이터로 저장
ChromaDB (벡터 DB)
```

> **설계 포인트**: 헤딩만 임베딩하고 본문은 메타데이터로 저장해 검색 정확도와 토큰 효율을 동시에 확보합니다.

---

## 퀴즈 생성 방식

- **Chain-of-Thought 4단계 프롬프트**: 핵심 개념 추출 → 문항 설계 → 오답 보기 설계 → 자기 검토
- **BM25 소스 역추적**: 각 문항이 어느 강의 청크에서 유래했는지 자동 태깅
- **코드 실행 채점**: Judge0 API (Python·SQLite) + 로컬 `exec()` 폴백

## 퀴즈 품질 평가 (4단계 자동화)

| 단계 | 방법 |
|---|---|
| 구조 검증 | 문항 수·유형 배분·필수 필드 규칙 기반 검사 |
| 근거 검증 | Gemini 2.5 Flash Lite + BM25 소스 청크로 환각 탐지 |
| 오답지 검증 | Kiwipiepy 형태소 분석 + BM25 강의 출처 확인 |
| 중복 탐지 | 임베딩 코사인 유사도 ≥ 0.85 중복 판정 |

> 퀴즈 응답과 평가는 **비동기 병렬 처리**로 응답 속도에 영향을 주지 않습니다.
