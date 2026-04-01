/**
 * LearnCraft Frontend Config
 *
 * API_BASE_URL: 현재 서버 origin을 자동 감지합니다.
 * - 로컬 개발: http://localhost:8000
 * - 스테이징/프로덕션: 배포된 도메인으로 자동 전환
 *
 * 이 파일은 const API 변수를 정의합니다. 모든 HTML 페이지가 이를 공유합니다.
 */
const API = window.location.origin;
