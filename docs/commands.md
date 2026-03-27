# 자주 쓰는 명령어

## 앱 실행

터미널에서 프로젝트 루트에서 실행:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

## 환경 변수

```
프로젝트 루트에 `.env` 파일을 만들고 아래 키를 설정합니다:
```

## 평가 실행 (퀴즈 JSON -> 결과 JSON)

```bash
# 모든 퀴즈 JSON 파일을 바탕으로 평가 데이터 일괄 재생성
python src/quiz/evaluator/runner.py --all

# 특정 퀴즈 JSON 파일 하나만 평가 실행
python src/quiz/evaluator/runner.py [quiz_json_파일_경로]
```

## 리포트 관리

```bash
# 모든 평가 JSON 파일을 바탕으로 HTML 리포트 일괄 재생성
python src/quiz/evaluator/report.py

# 특정 평가 JSON 파일 하나만 리포트로 변환
python src/quiz/evaluator/report.py data/logs/evaluations/eval_xxx.json
```

