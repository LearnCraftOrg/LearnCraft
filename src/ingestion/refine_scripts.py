"""
강의 녹취록 → 정제된 마크다운 스크립트 변환기
사용법: python src/ingestion/refine_scripts.py [--all] [--file 날짜]
"""

import os
import sys
import time
import argparse
from openai import OpenAI

from config.settings import SCRIPTS_DIR, REFINED_DIR, LLM_MODEL, OPENAI_API_KEY

CHUNK_SIZE = 300   # 한 번에 읽을 줄 수

# ── 시스템 프롬프트 ────────────────────────────────────────
SYSTEM_PROMPT = """너는 기술 강의 스크립트를 정제하는 전문 편집자이자 백엔드 개발 지식을 갖춘 기술 문서 편집자다.
입력으로 제공되는 텍스트는 실시간 강의 녹취록이며, 아래 규칙에 따라 정제한다.

이 작업은 요약이 아니라 정제(editing)다.

## 정제 규칙

### 1. 메타데이터 제거
- 타임스탬프 제거 (예: <09:11:17>)
- 사용자 ID 제거 (예: b54f46b0:)
- 시스템 메시지 제거

### 2. 강의 외 발언 제거
삭제 대상: 인사, 수업 운영 발언(화면 보이시나요 / 마이크 들리시나요 / 잠시 쉬겠습니다 등), 잡담
단, 기술 설명과 연결되는 질문/답변은 유지

### 3. 불필요한 구어체 제거
추임새 삭제: 어, 음, 이제, 그, 그러니까, 뭐냐면, 사실은, 약간
의미 없는 반복 연결어도 제거

### 4. 문장 교정
끊긴 문장 연결 / 구어체→문어체 변환 / 주어·서술어 교정 / 중복 문장 제거
의미 변경 절대 금지

### 5. 기술 용어 정정
크루드→CRUD / 제네릭→Generic / 스트림→Stream / 쓰레드→Thread
스프링→Spring / 자바→Java / 레포지토리→Repository / 컨트롤러→Controller
서비스→Service / 엔티티→Entity / 어노테이션→Annotation / 인터페이스→Interface
트랜잭션→Transaction / 데이터베이스→Database / 쿼리→Query
디펜던시→Dependency / 인젝션→Injection
그 외 프로그래밍 용어도 올바른 영문 표기 사용

### 6. 코드 블록 처리
코드 내용·삭제 금지 / 코드 포맷 유지 (```언어 블록) / 필요시 코드 앞 간단한 설명 추가

### 7. 내용 구조화
논리적 주제 단위로 재구성하되, 반드시 아래 계층 구조를 따른다.
- # 강의 주제: 이 청크에서 다루는 내용을 대표하는 가장 상위의 단일 대주제. 반드시 출력의 첫 줄에 위치하며, 여러 주제를 나열하지 않고 하나의 대표 주제만 작성한다.
- ## 대주제: 강의 전체를 관통하는 큰 주제 단위 (예: ## OUTER JOIN)
- ### 소주제: 대주제 안에서 구분되는 세부 개념 단위 (예: ### LEFT OUTER JOIN, ### RIGHT OUTER JOIN)
모든 섹션은 ## 또는 ### 으로 시작해야 하며, ## 없이 ### 만 단독으로 존재할 수 없다.
소주제(###)를 반드시 사용하여 각 대주제 내 세부 내용을 분리하라.

## 출력 형식
- 출력의 첫 줄은 반드시 다음 형식으로 작성한다:
  # 강의 주제: {이 청크에서 다루는 가장 상위의 단일 대주제}
  여러 개의 주제를 나열하지 말고 반드시 하나의 대표 대주제만 작성한다.
  이 줄 바로 다음 줄부터 ## 헤딩을 시작한다.
- 대주제: ## 주제 제목
- 소주제: ### 세부 주제 제목
- 한 문단 최대 5~6문장
- 문단 사이 한 줄 공백
- 불필요한 리스트 사용 금지
- 코드는 ```코드블록``` 형식

## 엄격한 규칙
강의 내용 삭제 금지 / 요약 금지 / 설명 축약 금지 / 의미 변경 금지
기술 설명은 최대한 보존

정제된 마크다운 텍스트만 출력하라. 설명이나 머리말을 붙이지 말 것."""

# ── 청크 단위 정제 ─────────────────────────────────────────
def refine_chunk(client: OpenAI, chunk_text: str, is_first: bool) -> str:
    """하나의 청크를 GPT-4o API로 정제한다."""
    user_msg = chunk_text if is_first else (
        "앞 내용에서 이어지는 강의 녹취록 청크다. 동일한 규칙으로 정제하라.\n\n" + chunk_text
    )
    response = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )
    return response.choices[0].message.content


def refine_file(client: OpenAI, input_path: str, output_path: str) -> None:
    """파일 전체를 청크 단위로 읽어 정제 후 저장한다."""
    file_start = time.time()
    print(f"\n처리 중: {os.path.basename(input_path)}")

    with open(input_path, encoding="utf-8") as f:
        lines = f.readlines()

    total = len(lines)
    print(f"  총 {total}줄 / {(total + CHUNK_SIZE - 1) // CHUNK_SIZE}개 청크")

    refined_parts: list[str] = []
    for i, offset in enumerate(range(0, total, CHUNK_SIZE)):
        chunk = "".join(lines[offset : offset + CHUNK_SIZE])
        print(f"  청크 {i + 1} 처리 중 (줄 {offset + 1}~{min(offset + CHUNK_SIZE, total)})...", end=" ")
        part = refine_chunk(client, chunk, is_first=(i == 0))
        refined_parts.append(part)
        print("완료")

        # Rate limit 방지를 위한 짧은 대기
        if offset + CHUNK_SIZE < total:
            time.sleep(1)

    # # 강의 주제: 줄을 각 청크에서 수집하고 본문에서 제거
    topic_line = ""
    cleaned_parts: list[str] = []
    for part in refined_parts:
        lines = part.splitlines()
        body_lines = []
        for line in lines:
            if line.startswith("# 강의 주제:"):
                if not topic_line:          # 첫 번째 청크의 주제만 사용
                    topic_line = line.strip()
            else:
                body_lines.append(line)
        cleaned_parts.append("\n".join(body_lines))

    body = "\n\n".join(cleaned_parts)
    full_text = (topic_line + "\n\n" + body) if topic_line else body

    REFINED_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    elapsed = time.time() - file_start
    print(f"  저장 완료: {os.path.basename(output_path)} ({elapsed:.1f}초)")


# ── 파일 목록 수집 ─────────────────────────────────────────
def get_pending_files(force_all: bool) -> list[tuple[str, str]]:
    """처리가 필요한 (입력경로, 출력경로) 쌍을 반환한다."""
    result = []
    for fname in sorted(os.listdir(SCRIPTS_DIR)):
        if not fname.endswith(".txt"):
            continue
        date_part = fname.replace("_kdt-backendj-21th.txt", "")
        out_fname = f"{date_part}_refined.md"
        in_path   = str(SCRIPTS_DIR / fname)
        out_path  = str(REFINED_DIR / out_fname)

        if force_all or not os.path.exists(out_path):
            result.append((in_path, out_path))
        else:
            print(f"[건너뜀] {out_fname} (이미 존재)")
    return result


# ── 메인 ──────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="강의 녹취록 정제 스크립트")
    parser.add_argument("--all",  action="store_true", help="이미 존재하는 파일도 재처리")
    parser.add_argument("--file", type=str,            help="특정 날짜 파일만 처리 (예: 2026-02-13)")
    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print("오류: OPENAI_API_KEY 환경 변수가 설정되어 있지 않습니다.")
        sys.exit(1)

    client = OpenAI(api_key=OPENAI_API_KEY)

    if args.file:
        # 특정 파일만 처리
        in_path  = str(SCRIPTS_DIR / f"{args.file}_kdt-backendj-21th.txt")
        out_path = str(REFINED_DIR / f"{args.file}_refined.md")
        if not os.path.exists(in_path):
            print(f"오류: {in_path} 파일을 찾을 수 없습니다.")
            sys.exit(1)
        pending = [(in_path, out_path)]
    else:
        pending = get_pending_files(force_all=args.all)

    if not pending:
        print("처리할 파일이 없습니다.")
        return

    print(f"\n총 {len(pending)}개 파일 처리 시작\n" + "=" * 50)
    for idx, (in_path, out_path) in enumerate(pending, 1):
        print(f"[{idx}/{len(pending)}]", end="")
        try:
            refine_file(client, in_path, out_path)
        except Exception as e:
            if "rate_limit" in str(e).lower() or "rate limit" in str(e).lower():
                print(f"\n  API 한도 초과. {in_path} 처리 중단.")
                print("  잠시 후 다시 실행하거나 --file 옵션으로 개별 처리하세요.")
                break
            print(f"\n  오류 발생: {e}")
            continue

    print("\n" + "=" * 50)
    print("작업 완료")


if __name__ == "__main__":
    main()
