# LearnCraft 관리자/강사 시작 가이드

LearnCraft를 처음 사용하는 관리자나 강사를 위한 설정 및 운영 가이드입니다.

---

## 1. 사전 준비

### Python 설치
Python 3.10 이상이 필요합니다.

```bash
python --version  # 3.10 이상 확인
```

### API 키 발급
아래 3가지 서비스의 API 키가 필요합니다.

| 서비스 | 용도 |
|--------|------|
| **OpenAI** | 퀴즈/가이드 생성 (gpt-4o-mini), 임베딩 (text-embedding-3-small) |
| **Google Gemini** | 퀴즈 품질 평가 (gemini-2.5-flash-lite) |
| **Google Cloud** | Vertex AI Grounding (사실 검증) |

---

## 2. 설치 및 환경 설정

### 의존성 설치

```bash
pip install -r requirements.txt
```

### .env 파일 생성

프로젝트 루트에 `.env` 파일을 생성하고 아래 내용을 입력합니다.

```
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GCP_PROJECT_ID=your-gcp-project-id
```

### Google Cloud 인증 설정

Vertex AI Grounding 기능을 사용하려면 서비스 계정 키 파일이 필요합니다.

1. Google Cloud Console에서 서비스 계정 키(JSON)를 발급합니다.
2. 파일을 `config/google_credentials.json` 경로에 저장합니다.

> Grounding 기능 없이 기본 퀴즈 생성 및 학습 가이드만 사용하는 경우 생략 가능합니다.

---

## 3. 강의 데이터 등록

새 강의를 추가할 때는 아래 4단계를 따릅니다.

### 3-1. 강의 스크립트 파일 추가

STT(음성→텍스트) 원본 스크립트를 아래 경로에 저장합니다.

```
data/강의 스크립트/YYYY-MM-DD_강의명.txt
```

예시: `data/강의 스크립트/2026-03-02_spring-boot-intro.txt`

### 3-2. 정제 스크립트 파일 추가

`src/ingestion/refine_scripts.py`를 실행하면 STT 원본 파일을 GPT-4o-mini로 자동 정제하여 `data/refined/`에 마크다운 파일을 생성합니다.

```bash
# 아직 정제되지 않은 파일만 처리 (권장)
python src/ingestion/refine_scripts.py

# 특정 날짜 파일만 처리
python src/ingestion/refine_scripts.py --file 2026-03-02

# 이미 존재하는 파일도 강제 재처리
python src/ingestion/refine_scripts.py --all
```

실행 결과로 `data/refined/YYYY-MM-DD_refined.md` 파일이 생성됩니다.

**정제 스크립트 동작 방식**

1. `data/강의 스크립트/`에서 `.txt` 파일을 읽습니다.
2. 300줄 단위 청크로 나누어 GPT-4o-mini에 전송합니다.
3. 타임스탬프·화자 ID 제거, 구어체 교정, 기술 용어 정정을 수행합니다.
4. `##`/`###` 마크다운 헤딩 구조로 재구성하여 저장합니다.

> 정제 결과가 마음에 들지 않으면 `data/refined/*.md` 파일을 직접 편집해도 됩니다. RAG는 이 파일을 기준으로 동작합니다.

### 3-3. topics.json 업데이트

`data/topics.json`에 날짜와 강의 주제를 추가합니다.

```json
{
  "2026-02-27": "MySQL 덤프와 데이터베이스 모델링",
  "2026-03-02": "Spring Boot 소개 및 프로젝트 구조"
}
```

### 3-4. 강의 커리큘럼 업데이트

`data/강의 커리큘럼.csv`에 강의 메타데이터를 추가합니다.

```
week,date,session,time,subject,content,learning_goal,instructor
8,2026-03-02,오전,09:00 ~ 12:00,Back-End Programming,Spring Boot 소개,Spring Boot 프로젝트 구조를 이해하고 기본 앱을 실행할 수 있다,홍길동
```

---

## 4. 앱 실행

프로젝트 루트에서 아래 명령어를 실행합니다.

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

이후 브라우저에서 `http://127.0.0.1:8000` 에 접속합니다.

> **첫 실행 시 자동 인덱싱**: 앱 시작 시 `data/refined/`에 있는 파일 중 아직 벡터 스토어에 등록되지 않은 강의를 자동으로 임베딩하고 인덱싱합니다. 강의 수에 따라 수 분이 소요될 수 있습니다.

---

## 5. 퀴즈 품질 관리 (선택)

퀴즈 자동 평가 파이프라인을 통해 생성된 퀴즈의 품질을 검토할 수 있습니다.

### 평가 실행

```bash
# 모든 퀴즈 일괄 평가
python src/quiz/evaluator/runner.py --all

# 특정 퀴즈 파일만 평가
python src/quiz/evaluator/runner.py data/logs/quizzes/quiz_xxx.json
```

### 보고서 생성

```bash
# 전체 HTML 보고서 재생성
python src/quiz/evaluator/report.py

# 특정 평가 파일만 보고서로 변환
python src/quiz/evaluator/report.py data/logs/evaluations/eval_xxx.json
```

생성된 보고서는 `data/logs/reports/`에서 확인하거나 앱의 **품질 보고서** 메뉴에서 볼 수 있습니다.

---

## 6. 데이터 디렉토리 구조 요약

```
data/
├── 강의 스크립트/     # 원본 STT 텍스트 (YYYY-MM-DD_*.txt)
├── clean/             # 전처리 텍스트
├── refined/           # 마크다운 정제 스크립트 (YYYY-MM-DD_refined.md)
├── .chroma/           # 벡터 스토어 (자동 생성, 수동 수정 불필요)
├── logs/
│   ├── quizzes/       # 생성된 퀴즈 JSON
│   ├── evaluations/   # 평가 결과 JSON
│   └── reports/       # HTML 품질 보고서
├── topics.json        # 날짜 → 강의 주제 매핑
└── 강의 커리큘럼.csv  # 커리큘럼 메타데이터
```
