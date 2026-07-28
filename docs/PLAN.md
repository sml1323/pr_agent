# PLAN — 마일스톤 트래커

범위: **M0 ~ M8** (`docs/DONE.md` 참조). M9~M12는 설계 문서로만 남기고 구현 안 함.
각 마일스톤은 **데모 명령 하나**로 증명한다. "됐습니다"는 증거가 아니다.

상태 표기: `⬜ 시작 전` / `🟡 진행 중` / `🔵 데모 통과, 검증 대기` / `✅ 완료(데모+독립검증+이해도 3단 통과)`

---

| # | 마일스톤 | 데모 명령 | 난이도 | 상태 |
|---|---|---|---|---|
| M0 | diff → Finding JSON | `python scripts/demo_m0.py fixtures/sample.diff` | 하 (2~3h) | ⬜ |
| M1 | 웹훅 인그레스 (HMAC + 멱등성) | `bash scripts/demo_m1.sh` | 중 (반나절) | ⬜ |
| M2 | 데이터 스파인 + RBAC + append-only | `psql -f scripts/demo_m2.sql` | 중상 (하루) | ⬜ |
| M3 | 이벤트 스파인 배선 | `bash scripts/demo_m1.sh && python scripts/trace.py <delivery_id>` | 하 (반나절) | ⬜ |
| M4 | Redis + ARQ로 큐 교체 | `bash scripts/demo_m4.sh` | 중 (반나절) | ⬜ |
| M5 | 오케스트레이션 (LangGraph 병렬 팬아웃) | `python scripts/demo_m5.py --pr fixtures/pr_opened.json` | 상 (하루) | ⬜ |
| M6 | 스페셜리스트 4 + 애그리게이터 | `python scripts/demo_m6.py fixtures/sample.diff` | 중상 (하루) | ⬜ |
| M7 | RAG 리트리버 (하이브리드 검색) | `python scripts/index_repo.py --repo ../my-test-repo && python scripts/demo_m7.py fixtures/sample.diff` | 상 (하루~하루반) | ⬜ |
| M8 | 컨피던스 게이트 + HITL + GitHub 게시 | `bash scripts/demo_m8.sh` | 상 (하루) | ⬜ |

상세 목표·만들 것·완료 판정은 [`03-build-plan.md`](03-build-plan.md) §2에 있다. 이 파일은 **상태 추적용**이다.

---

## 마일스톤별 기록

각 마일스톤을 끝낼 때 아래 형식으로 채운다. 빈 칸을 남기지 말 것 — 특히 "알려진 구멍".

### M0 — diff → Finding JSON

- **목표**: `.diff` 하나 → 구조화된 Finding 배열. 목적은 시스템 전체를 관통하는 **계약(Finding 스키마)을 손에 쥐는 것**.
- **토큰 예산**: (착수 시 기재)
- **데모 명령**: `python scripts/demo_m0.py fixtures/sample.diff`
- **통과 기준**: 모든 항목에 `confidence`(0~1)·`rationale`·`file`·`line`이 비어있지 않음. `rationale`이 "이거 좀 이상함"이 아니라 "40번 줄에서 user_input이 그대로 쿼리에 들어감" 수준. **`confidence`가 항상 같은 값이면 실패 취급.**
- **독립 검증 결과**: (미실시)
- **이해도 체크**: 설계근거 / 엣지케이스 / 변경영향 — (미실시)
- **알려진 구멍**: (기재)

> ⚠️ M0는 영상이 **최종 산출물로 삼는 걸 강하게 반대하는** 바로 그 형태다 [00:00:00]. 여기서는 결승선이 아니라 **비계**로만 쓴다. M1부터 이 조각들이 제자리로 흩어진다.

### M1 ~ M8

(각 마일스톤 착수 시 위 형식으로 추가)

---

## 완료 절차 (매 마일스톤 반복)

`docs/DONE.md`의 3단 판정을 그대로 따른다.

1. **데모 명령 실행** — 위 표의 명령을 그대로.
2. **독립 검증** — 새 세션 열고 이 프롬프트만 준다. **빌더 세션의 대화 내용은 절대 붙여넣지 않는다.**

   ```
   너는 독립 리뷰어다. 코드를 쓰지 마라. 빌더의 주장을 참이라 가정하지 마라.
   목표: <마일스톤 목표 한 문장>
   성공 기준: <데모 명령 + 통과 기준>
   불변식: docs/invariants.md
   직접 실행해서 확인하고, 무엇이 위험한지 말해라.
   ```

   성공 기준을 "돌아가나"가 아니라 **"어떤 불변식이 위험한가"**로 물을 것 [02:57:57].
3. **이해도 체크** — 세 질문에 내가 답한다. 답 못 하면 코드가 돌아도 미완료 [03:00:45].

## 마일스톤 종료 시 갱신할 파일

- `docs/PLAN.md` — 상태, 독립검증 결과, 알려진 구멍
- `docs/CURRENT.md` — 지금 뭐가 살아있고 뭐가 스텁인지
- `docs/adr/` — 되돌릴 수 있는 결정을 새로 내렸다면

이 셋을 갱신해야 다음 세션이 콜드 스타트할 수 있다. **상태는 컨텍스트 창이 아니라 디스크에 산다** [02:46:02].
