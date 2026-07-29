# CURRENT — 지금 상태

> 새 세션이 콜드 스타트할 때 **가장 먼저 읽는 파일.**
> "지금 뭐가 진짜로 살아있고, 뭐가 스텁이고, 다음 한 걸음이 뭔가"만 적는다. 설계는 여기 안 적는다.

**마지막 갱신**: 2026-07-28 · **M0 데모 통과, 독립검증 대기**

---

## 지금 살아있는 것

**M0이 실제로 돈다.** DB·웹훅·큐는 아직 없음.

| | | 상태 |
|---|---|---|
| `backend/agents/schema.py` | `Finding`(7필드) + `ReviewResult` | ✅ 계약 확정. INV-3을 스키마가 강제 |
| `backend/agents/base.py` | system 프롬프트 + `parse()` 호출 1회 | ✅ 동작. 모델 `gpt-5.4-nano` |
| `scripts/demo_m0.py` | 데모 + 완료 판정 도우미 | ✅ |
| `fixtures/*.diff` | `sample`(정상) · `sample_injected`(인젝션) · `sample_emotional`(사회공학) | ✅ 정답을 아는 상태 |
| 하네스 | `WORKFLOW.md` `DONE.md` `invariants.md` `PLAN.md` `adr/0001` `adr/0002` `CLAUDE.md` | ✅ |
| 학습 | `learning/` — MISSION · RESOURCES · 레슨 2개 · 레퍼런스 1개 | ✅ |

**아직 없는 것**: 웹훅 · DB · 큐 · 오케스트레이션 · 리트리버 · 게이트 · GitHub 게시.

**환경**: `uv` · OpenAI 키(`.env`) · 원격 저장소 없음(사용자가 삭제, 로컬 커밋 `1a822ed`만 존재).
⬜ **OpenAI 하드 리밋 미확인** — 대시보드에서 월 상한 걸 것. 비용은 1급 실패 모드 [01:21:42]

## 다음 한 걸음

### 1. M0 독립 검증 — **새 세션에서**

`WORKFLOW.md` ④. 구현 세션(이 대화)의 내용을 **절대 붙여넣지 않는다.**

```
너는 독립 리뷰어다. 코드를 쓰지 마라. 빌더의 주장을 참이라 가정하지 마라.

목표: .diff 하나를 넣으면 구조화된 Finding 배열이 나온다.
성공 기준: uv run python scripts/demo_m0.py fixtures/sample.diff
          → 모든 항목에 confidence(0~1)·rationale·file·line 이 채워짐.
            confidence 가 항상 같은 값이면 실패.
불변식: docs/invariants.md 를 읽어라.

직접 실행해서 확인하고, 어떤 불변식이 위험한지 말해라.
```

**질문을 "돌아가나"가 아니라 "어떤 불변식이 위험한가"로** 던질 것 [02:57:57].
`PLAN.md`의 M0 "알려진 구멍" 7개는 **주지 말 것** — 검증자가 스스로 찾는지가 이 단계의 값어치다.

### 2. M1 — 웹훅 인그레스

`03-build-plan.md` M1 절. 브랜치를 따서 갈 것 (`git checkout -b m1-webhook`).

### 결정을 미룬 것 — 각 마일스톤 브리핑 직전에 (2026-07-28 재배치)

책 대조에서 나온 구멍 13개 중 4개는 "M2 전에"로 잡혀 있었는데, **필요해지기 직전**으로 옮김.
이유: 코드 0줄 상태에서 스키마 결정을 내리면 상상으로 만든 감으로 되돌릴 수 없는 걸 고르게 됨.
[`04-book-reading-plan.md`](04-book-reading-plan.md)가 정한 **저스트-인-타임** 원칙과 같은 근거.

| | 무엇 | 언제 | 되돌리기 |
|---|---|---|---|
| **G9** | `agent_events`에 증거 스니펫 원문을 넣을지 / 마스킹할지 / 해시+포인터만 남길지. 보존·압축 정책 | **M2 브리핑 직전** | ∞ (INV-4가 삭제 하드 거부) |
| **G8** | `code_chunks`에 `repo_id`·`commit_sha` 박기. `past_reviews`·`conventions`를 남길지 뺄지 | **M2 브리핑 직전** | 재인덱싱 = 돈 |
| **G6** | 애그리게이터 계약 — LLM인가 코드인가 / dedup 키 / severity 충돌 시 뭐가 남나 | **M5 브리핑 직전** (M5 state의 findings 모양이 여기 걸림) | 0 (문서 한 문단) |
| ↳ | **M0에서 실측 근거가 나옴** — 같은 `(file, line, category)`에 `severity`만 다른 중복이 **에이전트 하나의 한 번 호출**에서 생성됨. dedup 키에 `category`가 필요하고, severity 충돌 시 **더 심각한 쪽을 남겨야** 한다(`critical`을 버리면 사람에게 갈 것이 자동 게시됨). 상세는 `PLAN.md` G-M0-3 | | |
| **G5** | 트러스트 바운더리를 diff + **검색 결과**로 확장 | **M7 브리핑 직전** | 0 (ADR 한 줄) |

**M2 브리핑 직전에 같이 할 것** — 미루면 잊으니까 여기 묶어둠:
1. **Ch8 읽기** (3쪽, 25분) — `reference_books/Agentic_Design_Patterns.pdf` Memory Management. G9·G8의 재료
2. **TigerData 계정 + Tiger CLI** — 영상 설명란 링크로 가입해야 신규 $1,000 크레딧 [02:48:27].
   ⚠️ 결제 실패로 **조용히 pause**되는 사고가 영상에서 실제로 남 — 크레딧 만료일 캘린더에.
   콘솔에서 **서비스는 만들지 말 것.** M2에서 에이전트가 Tiger MCP로 직접 프로비저닝함 ([ADR 0001](adr/0001-project-setup.md) D3).
   CLI를 설치하면 MCP 서버가 같이 들어옴 → `tiger auth login` → `tiger service list`(0개 나오면 정상)

**M7 직전에 할 것**: 테스트 레포 + 버그 심은 PR (SQL 인젝션 한 줄 + 테스트 없는 함수 하나). 작을수록 좋음. **정답을 내가 아는 것**이 핵심.

## 확정된 결정

| | 선택 | |
|---|---|---|
| **코드 작성** | **내가 직접 타이핑** | [ADR 0002](adr/0002-implementation-mode.md). Claude는 브리핑·힌트·독립검증·개념설명만 |
| 하네스 | **직접** (Genesis Kit 안 씀) | `DONE.md` 고정 / 마일스톤당 데모 명령 / 별도 세션 독립 검증 |
| 범위 | **M8까지** | 선별이 실제로 도는 지점 |
| DB | **처음부터 Tiger Cloud** | 로컬 Docker 안 씀 |
| 리뷰 대상 | 개인 토이 레포 + 심은 버그 | |
| 학습 비중 | 설계사고 60 / 완성 30 / 하네스 10 | |
| LLM | OpenAI 하나로 | |
| 참고서 | **저스트-인-타임** — 마일스톤 브리핑 직전에 해당 챕터만 | [04-book-reading-plan.md](04-book-reading-plan.md) |

## 알려진 리스크 (착수 시점)

- Tiger를 처음부터 쓰면 초반 마이그레이션 반복이 로컬보다 느림 — 갈아엎기 잦은 M2에서 체감. **마이그레이션을 재실행 가능하게 쓸 것**
- `TRUNCATE`가 DELETE 트리거를 우회 (INV-4) — M2에서 반드시 걸림
- pgvector 차원 불일치 — M2에서 **한 곳(마이그레이션)에만** 정의하고 코드가 거기서 읽게 [03:03:59]
- **G2**: 스페셜리스트 노드가 죽었을 때 "critical 없음"과 "확인 안 됨"을 게이트가 구분 못 함 → M5·M8에서 처리. 이 프로젝트 최악의 시나리오인데 고치는 건 if문 몇 줄
