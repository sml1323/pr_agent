# PR Review Multi-Agent System

GitHub에 PR이 올라오면 4개의 AI 에이전트가 각자 다른 관점으로 코드를 읽고,
**확신 있는 지적만 자동으로 코멘트를 달고, 애매한 건 사람에게 넘기는** 시스템.

영상 *Designing & Building PR Review Multi Agent System* (Ayush Singh)의 설계를 따라
직접 구현하며 **에이전트 시스템 설계 사고**를 익히는 학습 프로젝트다.

```
PR 열림 → ① 웹훅 수신 → ② Redis 큐 → ③ 워커
                                        ↓
              ④ security / quality / testing / docs  (4개 병렬)
                                        ↓
              ⑤ 애그리게이터 (중복 제거 + 전체 확신도)
                                        ↓
              ⑥ 게이트 ─ critical 있음    → 사람
                       ├ 확신 ≥ 0.6      → GitHub 자동 게시
                       └ 애매함           → 사람 큐
```

## 제1원칙 — 선별(selectivity)

많이 지적하는 게 목표가 아니라 **틀린 말을 안 하는 것**이 목표다.
지적을 20개 쏟아내는 리뷰어는 무시당하고, 무시당하는 순간 시스템은 죽는다.

그래서 모든 지적에 `confidence`와 `rationale`이 붙고, 마지막에 게이트가 선다.

## 상태

**M0 진행 중.** 지금 무엇이 살아있고 다음 한 걸음이 무엇인지는
[`docs/CURRENT.md`](docs/CURRENT.md)에 있다 — 새 세션이 콜드 스타트할 때 가장 먼저 읽는 파일.

| | 마일스톤 | 데모 명령 |
|---|---|---|
| M0 | diff → Finding JSON | `python scripts/demo_m0.py fixtures/sample.diff` |
| M1 | 웹훅 인그레스 (HMAC + 멱등성) | `bash scripts/demo_m1.sh` |
| M2 | 데이터 스파인 + RBAC + append-only | `psql -f scripts/demo_m2.sql` |
| M3 | 이벤트 스파인 배선 | `python scripts/trace.py <delivery_id>` |
| M4 | Redis + ARQ로 큐 교체 | `bash scripts/demo_m4.sh` |
| M5 | 오케스트레이션 (LangGraph 병렬 팬아웃) | `python scripts/demo_m5.py` |
| M6 | 스페셜리스트 4 + 애그리게이터 | `python scripts/demo_m6.py` |
| M7 | RAG 리트리버 | `python scripts/demo_m7.py` |
| M8 | 컨피던스 게이트 + HITL + GitHub 게시 | `bash scripts/demo_m8.sh` |

범위는 **M8까지**. M9~M12는 설계 문서로만 남긴다 ([ADR 0001](docs/adr/0001-project-setup.md) D2).
각 마일스톤은 **데모 명령 하나**로 증명한다 — "됐습니다"는 증거가 아니다.

## 불변식

깨면 안 되는 규칙 4개. 코드 규약이 아니라 **물리적으로 깨는 게 불가능하게** 만드는 게 목표다.
전문은 [`docs/invariants.md`](docs/invariants.md).

| | |
|---|---|
| **INV-1** | 모든 webhook payload는 서명 검증을 통과한다 |
| **INV-2** | 모든 delivery는 delivery ID를 멱등성 키로 중복 제거된다 |
| **INV-3** | 모든 finding은 `confidence`와 `rationale`을 갖는다 |
| **INV-4** | `agent_events`의 `UPDATE`/`DELETE`는 DB 레벨에서 하드 거부된다 |

## 문서

| | |
|---|---|
| [`docs/CURRENT.md`](docs/CURRENT.md) | **여기부터.** 지금 상태와 다음 한 걸음 |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | 세션 운영 방법 (브리핑 → 구현 → 검증 → 이해도) |
| [`docs/02-architecture.md`](docs/02-architecture.md) | 설계 근거 — "왜 이 모양인가" |
| [`docs/03-build-plan.md`](docs/03-build-plan.md) | 마일스톤별 만들 것과 완료 판정 |
| [`docs/adr/`](docs/adr/) | 되돌릴 수 있는 결정 기록 |
| [`learning/`](learning/) | 개념 레슨과 레퍼런스 (HTML) |

## 이 프로젝트의 방식

- **코드는 사람이 직접 타이핑한다.** 에이전트는 뼈대·배선만 주고 설계 판단 자리는 `TODO(human)`으로 비운다 ([ADR 0002](docs/adr/0002-implementation-mode.md))
- **상태는 컨텍스트 창이 아니라 디스크에 산다.** 세션이 끊겨도 `CURRENT.md` 한 장으로 이어받는다
- **독립 검증은 별도 세션에서.** 구현 세션의 대화를 물려주면 검증자가 같은 맹점을 물려받는다
- 질문은 *"돌아가나"*가 아니라 **"어떤 불변식이 위험한가"**로 던진다

## 실행

```bash
uv sync
uv run python scripts/demo_m0.py fixtures/sample.diff
```

`.env`에 `OPENAI_API_KEY`가 필요하다.
