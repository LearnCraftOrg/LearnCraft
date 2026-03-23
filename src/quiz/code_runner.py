"""Judge0 공개 API를 통한 코드 실행 및 채점 서비스.

엔드포인트: https://ce.judge0.com  (인증 불필요)

실행 우선순위:
  1. Judge0 공개 API POST /submissions?wait=true 호출
  2. 요청 실패 or 타임아웃(10초) → 로컬 exec() fallback (Python만)
  3. exec() 도 실패 → {"stderr": "실행 실패", "is_correct": False} 반환
"""

import contextlib
import io

import requests

_JUDGE0_URL = "https://ce.judge0.com/submissions?wait=true"
_LANGUAGE_IDS = {
    "python": 71,  # Python 3.8
    "sql": 82,     # SQLite 3.31.1
}


def _exec_fallback(code: str, expected_output: str) -> dict:
    """로컬 exec()로 코드 실행 (Judge0 API 실패 시 fallback)."""
    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(code, {"__builtins__": __builtins__})  # noqa: S102
        stdout = stdout_buf.getvalue().strip()
        return {
            "stdout": stdout,
            "stderr": "",
            "status": "Accepted (local exec)",
            "is_correct": stdout == expected_output.strip(),
            "exec_time": "N/A",
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "status": "Runtime Error (local exec)",
            "is_correct": False,
            "exec_time": "N/A",
        }


def fill_and_run(
    code_template: str,
    user_inputs: list[str],
    expected_output: str,
    language: str = "python",
) -> dict:
    """code_template의 ___를 user_inputs로 치환 후 Judge0로 실행·채점.

    Args:
        code_template: ___가 포함된 코드 템플릿
        user_inputs: 빈칸 순서대로 채울 값 목록
        expected_output: 정답 코드의 기대 stdout 출력값
        language: 실행 언어 ("python" | "sql"), 기본값 "python"

    Returns:
        {
            "stdout": str,
            "stderr": str,
            "status": str,      # "Accepted", "Runtime Error" 등
            "is_correct": bool,
            "exec_time": str    # 예: "0.042s"
        }
    """
    # ___ 순서대로 치환
    code = code_template
    for value in user_inputs:
        code = code.replace("___", value, 1)

    language_id = _LANGUAGE_IDS.get(language, _LANGUAGE_IDS["python"])

    # Judge0 공개 API 호출
    try:
        response = requests.post(
            _JUDGE0_URL,
            json={"source_code": code, "language_id": language_id},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        stdout = (data.get("stdout") or "").strip()
        stderr = (data.get("stderr") or "").strip()
        status = data.get("status", {}).get("description", "Unknown")
        raw_time = data.get("time")
        exec_time = f"{raw_time}s" if raw_time else "N/A"

        return {
            "stdout": stdout,
            "stderr": stderr,
            "status": status,
            "is_correct": stdout == expected_output.strip(),
            "exec_time": exec_time,
        }

    except Exception:
        # Judge0 요청 실패 시 로컬 exec fallback (Python만 지원)
        if language == "python":
            return _exec_fallback(code, expected_output)
        return {
            "stdout": "",
            "stderr": "Judge0 API 연결 실패",
            "status": "API Error",
            "is_correct": False,
            "exec_time": "N/A",
        }
