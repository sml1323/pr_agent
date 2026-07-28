# PR Review Multi-Agent System — 학습 프로젝트

출처 영상: [Designing & Building PR Review Multi Agent System (3 Hours Build)](https://www.youtube.com/watch?v=RiN02OXjeeQ)
— Ayush Singh · 2026-07-22 공개 · 3:10:07

## 하네스 — 매 세션 여기서 시작

Genesis Kit을 쓰지 않고 핵심 3개만 직접 굴린다 ([ADR 0001](adr/0001-project-setup.md) D1).

| 파일 | 무엇 | |
|---|---|---|
| [**WORKFLOW.md**](WORKFLOW.md) | **세션 운영법** — 빌드/검증/마무리 3세션 + 복붙 프롬프트 | 🔴 작업 시작 전에 읽는 파일 |
| [**CURRENT.md**](CURRENT.md) | **지금 뭐가 살아있고 다음 한 걸음이 뭔가** | 🔴 새 세션이 가장 먼저 읽는 파일 |
| [DONE.md](DONE.md) | "완료"의 고정 정의 · 자율성 수준 · 3단 판정 절차 | ⛔ 에이전트 수정 금지 |
| [invariants.md](invariants.md) | 절대 깨면 안 되는 규칙 4개 (INV-1~4) | ⛔ 에이전트 수정 금지 |
| [PLAN.md](PLAN.md) | M0~M8 상태 트래커 + 마일스톤별 데모 명령 | 마일스톤 끝낼 때 갱신 |
| [adr/](adr/) | 되돌릴 수 있는 결정 기록 | 새 결정 내릴 때 추가 |

## 참조 문서 (영상에서 추출)

| 파일 | 무엇 | 언제 보나 |
|---|---|---|
| [01-chapter-map.md](01-chapter-map.md) | 영상 전체 챕터 맵 (9개 파트 · 타임스탬프별) | 영상의 특정 구간으로 점프하고 싶을 때 |
| [02-architecture.md](02-architecture.md) | 아키텍처 + **설계 근거** — 왜 그렇게 했는지의 복원 | 무엇을 만들지가 아니라 왜 그런 모양인지 이해할 때 |
| [03-build-plan.md](03-build-plan.md) | M0~M8 빌드 플랜 (완료 판정 · 리스크). M9~M12는 범위 밖 | 실제로 구현을 시작할 때 |
| [04-book-reading-plan.md](04-book-reading-plan.md) | 참고서(*Agentic Design Patterns*) 저스트-인-타임 읽기 계획 + 설계 구멍 13개 | 마일스톤 브리핑 직전 |

## 원본

| 파일 | 설명 |
|---|---|
| `source/transcript.txt` | 자동자막 → 30초 단위 타임스탬프 대본 (31,860 단어) |
| `source/transcript.en.json3` | yt-dlp 원본 자막 |
| `source/segment_map.json` | 대본을 8구간으로 나눠 구조화 추출한 것. **세 문서의 유일한 근거** |

## 이 문서들을 읽는 규칙

- `[HH:MM:SS]` = 영상 타임스탬프. 그대로 유튜브에서 점프 가능
- **(추정)** = 영상에 근거가 없고 실무 판단으로 채운 것. 그대로 믿지 말 것
- **소스 내 불일치** = 영상이 두 군데서 다르게 말한 것. 특히 마일스톤 번호(M3·M4·M6)가 구간마다 다름
- `M#` 표기: `01`은 **영상 번호**, `03`은 **플랜 자체 번호**. `03`은 영상 번호를 `[영상 M#]`으로 구분

## 재현

```bash
yt-dlp --skip-download --write-auto-subs --sub-langs "en" --sub-format json3 \
  -o "transcript.%(ext)s" "https://www.youtube.com/watch?v=RiN02OXjeeQ"
```
