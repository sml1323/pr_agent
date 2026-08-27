"""평가 도구 — PR 리뷰가 도는 동안에는 실행되지 않는다.

⚠️ import 방향은 한 방향이다:  evals/ ──→ backend/   (반대 금지)

`backend/` 안에서 `from evals ...` 가 나오면 선을 넘은 것이다.
그때는 이 패키지를 `backend/eval/` 로 이사한다.
근거: docs/CURRENT.md 「확정된 결정」 · 평가 코드 위치 (2026-08-27)
"""
