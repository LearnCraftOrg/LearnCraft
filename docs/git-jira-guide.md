# Git & Jira 워크플로우 가이드

**이슈를 만든다 → 브랜치를 낸다 → 작업한다 → 커밋한다 → 푸시한다 → PR을 만든다 → 리뷰받고 develop에 머지한다**

---

## 브랜치 구조


| 브랜치          | 용도              |
| ------------ | --------------- |
| `main`       | 배포용             |
| `develop`    | 개발본이 모이는 통합 브랜치 |
| `feat/`*     | 기능 개발           |
| `fix/*`      | 버그 수정           |
| `refactor/*` | 리팩토링            |


모든 작업은 `develop` 기준으로 시작하고, 완료되면 PR을 통해 `develop`으로 합칩니다.
`develop`에 직접 push하지 않습니다.

---

## 단계별 가이드

### 1. 이슈를 먼저 만든다

Jira 또는 GitHub Issue에 할 일을 하나 만듭니다.

```text
SCRUM-12: 퀴즈 생성기 개선
```

이슈를 먼저 만드는 이유:

- 작업 단위를 분리하기 쉽고
- 브랜치, 커밋, PR을 이슈와 연결할 수 있고
- 누가 무슨 작업을 하는지 명확해지기 때문입니다.

---

### 2. develop을 최신화하고 브랜치를 만든다

```bash
git checkout develop
git pull origin develop
git checkout -b feat/SCRUM-12-quiz-generator
```

브랜치 이름 형식: `타입/이슈번호-설명`


| 예시                                |
| --------------------------------- |
| `feat/SCRUM-12-quiz-generator`    |
| `fix/SCRUM-15-login-error`        |
| `refactor/SCRUM-20-search-module` |


---

### 3. 해당 브랜치에서만 작업한다

**한 기능 = 한 브랜치 = 한 PR** 원칙을 지킵니다.

한 브랜치에 여러 기능을 작업하면:

- 리뷰가 어려워지고
- 충돌이 늘고
- 문제 발생 시 되돌리기 어려워집니다.

---

### 4. 작업이 끝나면 커밋한다

```bash
git add .
git commit -m "feat #SCRUM-12: improve quiz generation pipeline"
```

커밋 메시지 형식: `타입 #이슈번호: 요약`

---

### 5. 원격 저장소로 push한다

```bash
git push origin feat/SCRUM-12-quiz-generator
```

---

### 6. Pull Request를 만든다

- **base**: `develop`
- **compare**: `feat/SCRUM-12-quiz-generator`

PR 제목 예시:

```text
[#SCRUM-12] improve quiz generation pipeline
```

PR 본문 예시:

```text
Closes #SCRUM-12

- 퀴즈 생성 파이프라인 추가
- schema validation 추가
- parsing 안정성 개선
```

`Closes #이슈번호`를 넣으면 머지 시 이슈가 자동으로 닫힙니다.

---

### 7. 리뷰를 받고 수정한다

리뷰 중 수정 요청이 오면, **같은 브랜치에서 수정 후 commit/push**합니다.
그러면 PR에 자동으로 반영됩니다.

---

### 8. 머지 전 develop 최신화

내가 작업하는 동안 다른 팀원이 develop에 머지했을 수 있습니다.
충돌을 미리 해결한 뒤 머지합니다.

```bash
git checkout develop
git pull origin develop

git checkout feat/SCRUM-12-quiz-generator
git merge develop
# 충돌이 있으면 해결 후 commit
```

---

### 9. 최종 머지

리뷰 완료 및 충돌 해결 후 GitHub에서 `develop`으로 머지합니다.

> **Squash Merge** 권장 — 작업 브랜치의 여러 커밋을 하나로 정리해 히스토리를 깔끔하게 유지합니다.

---

### 10. 머지 후 정리

```bash
git checkout develop
git pull origin develop
git branch -d feat/SCRUM-12-quiz-generator
```

---

## 요약

```text
1. Jira/GitHub Issue 확인 또는 생성
2. develop 최신화
3. feat/fix/refactor 브랜치 생성
4. 해당 브랜치에서 작업
5. commit
6. push
7. develop 대상으로 PR 생성
8. 리뷰 및 수정
9. develop 최신 반영 후 충돌 해결
10. PR merge
11. 브랜치 삭제
```

