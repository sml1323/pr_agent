# CURRENT — 지금 상태

> 새 세션이 콜드 스타트할 때 **가장 먼저 읽는 파일.**
> "지금 뭐가 진짜로 살아있고, 뭐가 스텁이고, 다음 한 걸음이 뭔가"만 적는다. 설계는 여기 안 적는다.

**마지막 갱신**: 2026-07-28 · 설계·하네스 완료, 코드 0줄

---

## 지금 살아있는 것

문서만. **코드 없음, DB 없음, 계정 없음.**

| | |
|---|---|
| 하네스 | `WORKFLOW.md` `DONE.md` `invariants.md` `PLAN.md` `adr/0001` `adr/0002` |
| 참조 | `01-chapter-map.md` `02-architecture.md` `03-build-plan.md` `04-book-reading-plan.md` |
| 원본 | `source/transcript.txt` `source/segment_map.json` |

## 다음 한 걸음

### 지금 — M0 착수

`python scripts/demo_m0.py fixtures/sample.diff`

M0에 필요한 건 **OpenAI 키 + 손으로 쓴 `fixtures/sample.diff`** 둘뿐. DB도 레포도 웹훅도 안 씀.

- ✅ OpenAI API 키 — `.env`에 넣음 (2026-07-28)
- ⬜ **하드 리밋** — 대시보드에서 월 상한. 비용은 1급 실패 모드 [01:21:42]
- ⬜ **`.gitignore`** — `.env`가 지금 untracked로 노출돼 있음

### 결정을 미룬 것 — 각 마일스톤 브리핑 직전에 (2026-07-28 재배치)

책 대조에서 나온 구멍 13개 중 4개는 "M2 전에"로 잡혀 있었는데, **필요해지기 직전**으로 옮김.
이유: 코드 0줄 상태에서 스키마 결정을 내리면 상상으로 만든 감으로 되돌릴 수 없는 걸 고르게 됨.
[`04-book-reading-plan.md`](04-book-reading-plan.md)가 정한 **저스트-인-타임** 원칙과 같은 근거.

| | 무엇 | 언제 | 되돌리기 |
|---|---|---|---|
| **G9** | `agent_events`에 증거 스니펫 원문을 넣을지 / 마스킹할지 / 해시+포인터만 남길지. 보존·압축 정책 | **M2 브리핑 직전** | ∞ (INV-4가 삭제 하드 거부) |
| **G8** | `code_chunks`에 `repo_id`·`commit_sha` 박기. `past_reviews`·`conventions`를 남길지 뺄지 | **M2 브리핑 직전** | 재인덱싱 = 돈 |
| **G6** | 애그리게이터 계약 — LLM인가 코드인가 / dedup 키 / severity 충돌 시 뭐가 남나 | **M5 브리핑 직전** (M5 state의 findings 모양이 여기 걸림) | 0 (문서 한 문단) |
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
