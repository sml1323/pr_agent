# CURRENT — 지금 상태

> 새 세션이 콜드 스타트할 때 **가장 먼저 읽는 파일.**
> "지금 뭐가 진짜로 살아있고, 뭐가 스텁이고, 다음 한 걸음이 뭔가"만 적는다. 설계는 여기 안 적는다.

**마지막 갱신**: 2026-08-19 · **M5 — 노드 넷이 병렬로 돌고 실패를 값으로 바꾼다(1~4), 다음은 타임아웃 · M1 테스트 미작성 · M0 독립검증 대기**

---

## 지금 살아있는 것

**M0이 실제로 돈다.** DB·웹훅·큐는 아직 없음.

| | | 상태 |
|---|---|---|
| `backend/agents/schema.py` | `Finding`(7필드) + `ReviewResult` | ✅ 계약 확정. INV-3을 스키마가 강제 |
| `backend/agents/base.py` | system 프롬프트 + `responses.parse()` 호출 1회 | ✅ 동작. 모델 `gpt-5.6-luna` (2026-08-14 교체) |
| `scripts/demo_m0.py` | 데모 + 완료 판정 도우미 | ✅ |
| `fixtures/*.diff` | `sample`(정상) · `sample_injected`(인젝션) · `sample_emotional`(사회공학) | ✅ 정답을 아는 상태 |
| 하네스 | `WORKFLOW.md` `DONE.md` `invariants.md` `PLAN.md` `adr/0001` `adr/0002` `CLAUDE.md` | ✅ |
| 학습 | `learning/` — MISSION · RESOURCES · NOTES · NOTEBOOK · 레슨 5 · 시뮬 3 · 레퍼런스 2 | ✅ 아래 "학습 하네스" 절 |

**M1도 돈다 — 테스트만 빼고.** (브랜치 `m1-webhook`, 커밋 3개)

| | | 상태 |
|---|---|---|
| `backend/webhook/security.py` | HMAC 검증. secret 없으면 부팅 거부 | ✅ INV-1이 코드가 됨 |
| `backend/webhook/app.py` | 가드 절 5개 + 응답 계약(200/400) | ✅ |
| `backend/queue/router.py` | 인메모리 큐 + delivery ID dedup | ✅ INV-2. **스텁 — M4에서 Redis로 교체** |
| `scripts/demo_m1_*.py` | 서명 7케이스 · 인그레스 12케이스 | ✅ 전부 통과 |
| `tests/test_webhook.py` | 다섯 함수가 **이름만 있고 본문이 비었다** | ⬜ **의도적으로 미룸** |
| 도구 | ruff + basedpyright + pytest + debugpy | ✅ |
| 학습 | Lesson 03·04, reference/webhook-ingress.html(인터랙티브) | ✅ |

⬜ **M1 테스트 미작성 — 알고 미룬 것.** 뼈대(`conftest.py`)는 있고 케이스만 비었다.
`03-build-plan.md` M1 완료 판정에 테스트가 들어 있으므로 **M1은 아직 "완료"가 아니다.**
이걸 채우기 전엔 M1 독립 검증을 돌릴 근거가 데모 스크립트뿐이다.
**사람이 쓴다** — 구현한 쪽이 자기 시험지를 만들면 자기가 답할 수 있는 문제만 낸다 [01:57:46].

📌 **1차 출처가 영상 전제를 뒤집음** (2026-07-29): GitHub은 실패한 배달을
**자동 재시도하지 않는다**. 응답 제한은 **10초**로 확정. 늦으면 이벤트가 **영구 유실**된다.
→ 큐의 존재 이유가 "느려도 되게"가 아니라 **"유실을 막으려고"**로 바뀐다.
`docs/invariants.md` INV-2에 근거 정정을 반영했다(사용자 승인). **불변식 자체는 유효** —
수동 재배달·워커 재시도·연속 push가 중복 경로로 남는다. 출처는 `learning/RESOURCES.md`.

**M2 착수 — 판이 깔렸다.** (2026-07-30)

| | | 상태 |
|---|---|---|
| `docker-compose.yml` | `timescaledb-ha:pg17` · `127.0.0.1`만 바인드 · healthcheck | ✅ 확장 4개 확인 (timescaledb 2.29.0 · vector 0.8.5 · vectorscale 0.9.0 · toolkit 1.24.0) |
| `scripts/migrate.py` | `migrations/*.sql` 번호순 **전부 재실행**. 이력 추적 안 함 | ✅ 두 번 연속 실행해도 같은 결과 확인 |
| `migrations/001_extensions.sql` | `timescaledb` + `vector`. `vectorscale`은 M7까지 안 요구 | ✅ 적용됨 |
| `migrations/002_time.sql` | `agent_events` 하이퍼테이블 · `chunk_interval='1 day'` | ✅ 적용됨. 첫 INSERT 로 `chunks=1` 확인 |
| `migrations/003_immutable.sql` | append-only 트리거 3개 (UPDATE·DELETE·TRUNCATE) | ✅ **완료 판정 통과** — 아래 |
| `migrations/004_truth.sql` | `reviews` · `findings` · `hitl_decisions`. 평범한 테이블 | ✅ CHECK 5개 실측 통과 — 아래 |
| `.env` | `DATABASE_URL` 추가 (로컬이라 비밀 아님) | ✅ |

**INV-4 가 코드가 됐다** (2026-08-14). 실측:

```
① INSERT    INSERT 0 1                                    ✅ 살아있다
② UPDATE    ERROR: append-only 다 (INV-4). UPDATE 는 …     ✅ 막힘
③ DELETE    ERROR: append-only 다 (INV-4). DELETE 는 …     ✅ 막힘
④ TRUNCATE  ERROR: append-only 다 (INV-4). TRUNCATE 는 …   ✅ 막힘
```

⚠️ **①이 성공하는지도 같이 봐야 한다.** 넷 다 에러면 방어가 아니라 표가 죽은 것이고,
"전부 에러 남" 만 보면 두 경우가 구분되지 않는다. 행 1개가 남은 것이 그 증거다.

**`004_truth.sql` 도 실측으로 확인됐다** (2026-08-18):

```
① INSERT reviews    id=1 · status=queued · failed_agents={}        ✅ 살아있다
② INSERT findings   id=1 · confidence=0.950                        ✅ 살아있다
③ status='Posted'   ERROR: reviews_status_check                    ✅ 막힘
④ line=0            ERROR: findings_line_check                     ✅ 막힘
⑤ confidence=1.5    ERROR: findings_confidence_check               ✅ 막힘
```

004 에서 내린 설계 판단 셋 (근거는 파일 안 주석):
- **`status` 8개 + `failed_agents TEXT[]` 분리** — "어디쯤 있나"와 "누가 죽었나"는 다른 질문이다.
  한 컬럼에 겹치면 값이 곱해진다(에이전트 4개 → 실패 조합 15가지). **`partial` 과 `auto_posted`
  를 가르는 것이 이 컬럼의 존재 이유** — G2 리스크가 여기서 처음 표현된다
- **CHECK 를 건다** — Pydantic 과 중복이지만, 판단 기준은 "중복이냐"가 아니라
  "DB 에 쓰는 경로가 앱 하나뿐이냐"다. 아니다(psql·백필·INSERT 코드)
- **`hitl_decisions` 는 finding 단위 + `UNIQUE` 없음** — M9 의 "지적 중 몇 %가 맞았나"가
  이 표에서만 나온다. 번복도 UPDATE 가 아니라 append 로 남긴다(INV-4 의 사고방식을 빌림)

⬜ **아직 안 막힌 문 두 개** — `drop_chunks()` 와 `DROP TABLE`. 트리거로는 원리적으로 못 막는다
(Postgres 트리거 이벤트에 DROP 이 없다). `006_rbac.sql` 의 일이다.
지금 `DATABASE_URL` 이 `postgres` 슈퍼유저라 **저 둘은 그냥 통과한다.**

⚠️ **DB 컨테이너는 항상 떠 있지 않다.** 재부팅을 못 넘긴다 → `docker compose up -d` 부터.
포트는 **5434** (다른 Postgres 와 충돌해서 5432 에서 옮김. `docker-compose.yml` 과 `.env` 양쪽).

**학습 하네스가 커졌다.** (2026-07-30)

| | | 상태 |
|---|---|---|
| `learning/lessons/` | 레슨 **9개** (01 스키마 · 02 인젝션 · 03 HMAC · 04 멱등성 · 05 삭제 문 4개 · 06 부분 실패 · 07 리듀서=허가 · 08 엣지=시간 · **09 예상실패vs버그**) | ✅ |
| `learning/sims/` | 시뮬 **9개** — 0001~0009 전부 | ✅ |
| `learning/NOTEBOOK.md` | **사용자가 자기 말로 적는 곳.** Claude가 채우지 않는다 | ✅ **9/9 전부 4/4** (`/learn-check`) |
| `.claude/skills/learn-check/` | 학습 사이클을 **파일로** 판정하는 프로젝트 스킬 | ✅ `/learn-check` 또는 `python3 .claude/skills/learn-check/scripts/check.py` |

`CLAUDE.md`의 학습 사이클이 **읽기 → 만지기 → 적기 → 만들기** 4단계로 바뀌었다.
⚠️ `/mattpocock-skills:teach`는 **Claude의 스킬 목록에 뜨지 않는다** — 사용자가 직접 쳐야 한다.

**LLM 백엔드를 로컬 OAuth 프록시로 교체.** (2026-08-14)

ChatGPT 구독의 OAuth 토큰을 OpenAI 호환 엔드포인트로 노출하는 제3자 도구
[`openai-oauth`](https://github.com/EvanZhouDev/openai-oauth)(npm, 비공식)를 쓴다.
`npx openai-oauth` → `http://127.0.0.1:10531/v1`. 토큰은 `~/.codex/auth.json`을 읽으므로
**먼저 `npx @openai/codex login`이 필요**하다(1회). 프록시는 재부팅을 못 넘긴다 — 다시 띄울 것.

📌 **`/v1/chat/completions`를 쓰면 안 된다.** 실측(2026-08-14):

| 경로 | `response_format` / `text_format` | 결과 |
|---|---|---|
| `client.chat.completions.parse` | 무시됨 | ❌ 자유 텍스트가 와서 `ValidationError: Invalid JSON` |
| `client.responses.parse` | 지켜짐 | ✅ `[critical] sql-injection @ app.py:3 conf=0.99` |

프록시가 Codex 전용 엔드포인트를 감싸는 어댑터인데 Codex가 Responses API 네이티브라,
`/v1/chat/completions`는 모양만 맞춘 호환 계층이고 스키마가 상류까지 안 내려간다.
**에러가 아니라 조용한 무시**라서 위험하다 — `.parse()`가 터져준 게 운이 좋았던 것.

- `client = OpenAI()`는 안 고쳤다. SDK가 `OPENAI_BASE_URL`을 자동으로 읽는다 →
  진짜 API로 되돌리는 건 `.env` 두 줄 삭제. **코드는 어느 백엔드인지 몰라도 된다**
- `usage` 필드명이 바뀌었다: `prompt/completion_tokens` → **`input/output_tokens`**.
  M3에서 `record_event`에 붙일 때 걸린다
- `.env`의 진짜 API 키는 주석 처리했다 — 프록시는 `Authorization`을 무시하므로
  제3자 패키지에 키를 넘길 이유가 없다
- ⚠️ 비공식 커뮤니티 프로젝트다. 개인 로컬 학습용으로만. 남에게 보여줄 물건이 되면 진짜 키로 되돌린다

**아직 없는 것**: `agent_events` 하이퍼테이블 · append-only 트리거 · RBAC · 오케스트레이션 · 리트리버 · 게이트 · GitHub 게시 · 진짜 큐(Redis).

**환경**: `uv` · `OPENAI_BASE_URL`(로컬 프록시) + `WEBHOOK_SECRET` + `DATABASE_URL`(`.env`) ·
원격 https://github.com/sml1323/pr_agent (**public**).
영상 파생 문서 2개(`docs/source/segment_map.json`, `docs/01-chapter-map.md`)는 저작권 판단으로
**히스토리에서 제거**하고 `.gitignore`에 등록 — 로컬에는 남아 있다.
⬜ ~~**OpenAI 하드 리밋 미확인**~~ — 프록시로 가면서 **호출당 과금이 사라졌다**(구독).
새 예산은 비용이 아니라 **구독 한도와 지연**이다. 실측: diff 한 건에 output 344 토큰 중
reasoning 162(47%). M6에서 에이전트 4개로 갈리면 이게 4배고, 프록시가 무상태라
히스토리도 매번 다시 올라간다. 진짜 키로 되돌릴 때 월 상한 거는 건 그대로 유효 [01:21:42]

## 다음 한 걸음

### 0. M5 — 멀티에이전트 배선  ← **지금 여기**

⚠️ **M2 를 `004` 에서 멈춘다** — [ADR 0006](adr/0006-stop-m2-at-004.md) (2026-08-18 결정).
**알고 하는 순서 변경이다.** 근거와 되돌리는 조건은 ADR 에 있다 — 이 절은 덮어써지므로.

| 미룬 것 | 언제 회수 | 왜 지금 안 하나 |
|---|---|---|
| `005_memory.sql` | **M7 직전** | RAG 전엔 아무도 안 읽는다. G8 결정도 그때 |
| `006_rbac.sql` | **M8 직전** | 게이트 전엔 막을 게 없다. 문 ④⑤ 는 그때까지 뚫려 있다 |
| `record_event()` (M3) | M6 이후 | G9 결정 필요 (payload 에 뭘 넣나 — INV-4 때문에 영구적) |
| Redis 큐 (M4) | M8 직전 | M1 의 인메모리 큐가 이미 돈다. 데모엔 없어도 된다 |

**이유**: 포폴에 들어가는 건 돌아가는 데모지 스키마가 아니다. 그리고 미룬 넷은
전부 "필요해지는 자리"가 뒤에 있다 — `04-book-reading-plan.md` 의 저스트-인-타임과 같은 근거.
**`004` 는 안 버려진다** — M5 에서 에이전트가 뱉은 걸 저장할 때 그대로 쓴다.

⚠️ **그래서 `03-build-plan.md` 의 M2 완료 판정(RBAC 포함)은 아직 통과하지 못했다.**
M2 는 "완료"가 아니라 "004 까지"다. M1 테스트와 같은 종류의 미룸이다.

**M5 가 하는 것**: M0 의 `backend/agents/base.py`(에이전트 하나)를 **4개 병렬**로 늘린다 —
security / quality / testing / docs. 그림의 ④ 배선.
M3·M4 를 건너뛰어도 되는 이유: 로그가 없어도 돌고, M1 의 큐가 이미 있다.

**진행 현황** (2026-08-19):

| | 만들 것 | 상태 |
|---|---|---|
| 1 | `backend/orchestration/engine.py` — 추상 계약 | ✅ 세 메서드 확정 (2026-08-19) |
| 2 | `backend/orchestration/state.py` — state + 리듀서 | ✅ 확정 (2026-08-19) |
| 3 | `langgraph_engine.py` — 팬아웃/팬인 배선 | ✅ 확정 (2026-08-19) |
| 4 | 더미 노드 4개 (sleep + 실패 모드) | ✅ 확정 (2026-08-20) |
| 5 | 모든 노드에 타임아웃 [01:05:02] | ⬜ ← **다음 한 걸음** |
| 6 | 체크포인터 — **결정 필요** | ⬜ |
| 7 | `scripts/demo_m5.py` | ⬜ |

**1번에서 내린 결정** (코드에 들어감 — 근거는 `engine.py` 주석):
- 세 메서드가 **같은 식별자 하나**를 인자로 받는다. LangGraph 의 `thread_id` 이고
  **호출자가 준다** (1차 출처: "Pass a `thread_id` in graph config").
- ⚠️ **그 식별자를 `run()` 의 반환값으로 하면 안 된다.** 반환값은 함수가 끝나야 생기는데,
  대비하려는 상황이 정확히 "안 끝나는 것"이다. `kill -9` 되면 그 값이 존재한 적이 없다.
  → 이름은 **PR 정보(repo·pr_id·head_sha)로 계산**한다. 저장이 아니라 계산이라 몇 번이든 다시 얻는다.
  004 의 `reviews_unique_head` 와 같은 재료 — 저긴 중복 방지, 여긴 재개용 열쇠.
- ⚠️ **엔진은 DB 를 모른다.** M5 에 DB 가 안 들어오므로 식별자도 DB 와 무관하다.

**2번에서 내린 결정** (근거는 `state.py` 주석):

셈의 규칙 하나로 전부 갈렸다 — **한 superstep 안에서 몇 개 노드가 이 칸에 쓰나.**
둘 이상이면 리듀서, 하나거나 없으면 안 단다.

| 필드 | 쓰는 노드 | 리듀서 |
|---|---|---|
| `review_key` · `diff` | 0 (읽기만) | ❌ — **안 다는 것이 방어다.** 둘이 쓰면 터져서 잡힌다 |
| `findings` | 4 | ✅ `Annotated[list[Finding], operator.add]` |
| `failed_agents` | 4 | ✅ `Annotated[list[str], operator.add]` |

- **`context` 를 뺐다** — M7 RAG 전엔 아무도 안 채운다. "있는데 항상 빈 칸"은 거짓말이다.
  aggregate 산출물 자리도 같은 이유로 안 팠다(M6).
- **`failed_agents` 는 이름만** — 004 의 `TEXT[]` 가 착지점. M8 게이트가 묻는 건
  "누가 못 봤나"이지 "왜"가 아니다. 이유는 M3 `record_event` 의 몫.
- ⚠️ **`Annotated[str, operator.add]` 는 함정** — 문자열끼리 `+` 라
  `'docsqualitysecuritytesting'` 으로 붙는다. 타입 체커도 LangGraph 도 통과시킨다.

📌 **1차 출처 두 문장의 모순을 실측으로 갈랐다** ([Lesson 07](../learning/lessons/0007-permission-to-write-together.html)):
*"the entire superstep is transactional"* 과 *"successful nodes... don't repeat when resumed"* 는
**층이 다르다** — 채널(`channel_values`)에는 아무것도 커밋 안 되고, 이미 **끝난** 노드의 출력만
`pending_writes` 로 남는다. ⚠️ 누가 끝났는지는 **타이밍에 달렸다** — 같은 코드를 두 번 돌려 결과가 갈렸다.
→ **6번(체크포인터)이 선택 사항이 아님이 확정됐다.** `resume()` 이 INV-2 를 지키는 메커니즘이
per-task writes 인데, 체크포인터가 없으면 그게 존재하지 않는다.

**3번에서 내린 결정** (근거는 `langgraph_engine.py` 주석):

- **팬아웃·팬인 둘 다 평범한 `add_edge`**. `add_conditional_edges` 는 안 썼다 —
  갈 곳이 실행 시점에 정해지지 않는다(넷은 항상 돈다). 조건 없는 조건부 엣지는
  "항상 같은 값을 반환하는 라우터"를 만들고 읽는 사람이 없는 분기를 찾게 한다.
- ⚠️ **`START → aggregate` 를 그으면 안 된다** — aggregate 가 스페셜리스트와 같은 층에 서서
  findings 0개로 판정한다. **최종 state 는 4개라 결과만 보면 정상으로 보인다** (Sim 08 프리셋 ③).
- **`retrieve` 는 뺐다** — M7(RAG)의 노드다. 담을 `context` 채널도 없다.
  `state.py` 와 그래프가 같은 말을 하게 맞췄다.
- **`get_state()` 는 `status` 3값**(`not_started`/`running`/`done`)**을 담는다.**
  처음에 `is_done` boolean 으로 썼다가 **시작 전과 완료 후가 뭉개지는 걸 실측으로 발견**했다
  (둘 다 `snapshot.next` 가 비어 있다. 구분자는 `created_at`).
  004 의 `reviews.status` 를 8개로 나눈 것과 같은 이유다.
- `StateSnapshot` 을 그대로 안 돌려준다 — 돌려주면 호출부가 LangGraph 객체를 만지게 되어
  갈아탈 때 호출부까지 고쳐야 한다. 반환 키 6개:
  `review_key · diff · findings · failed_agents · next_nodes · status`

📌 **superstep 은 배리어다** ([Lesson 08](../learning/lessons/0008-edges-draw-time.html) 실측):
엣지는 "어느 층에 서나"를 정하지 **"누구를 기다리나"를 정하지 않는다.**
aggregate 와 엣지로 안 이어진 느린 노드까지 기다린다(0.11초가 아니라 0.51초에 시작).
→ **한 노드가 안 끝나면 그래프 전체가 멈춘다. M5-5 타임아웃이 선택 사항이 아닌 이유.**

⚠️ **`basedpyright` 를 같이 돌릴 것.** `ruff` 만 돌려서 타입 에러 4개를 놓쳤다
(`Literal` 불일치, `RunnableConfig` 불일치). ruff 는 문법·import 만 본다.

⬜ **경고 하나 적어둠**: 체크포인터가 `Finding`(Pydantic)을 저장할 때
`Deserializing unregistered type ... will be blocked in a future version` 이 뜬다.
**6번(체크포인터)에서 풀 문제** — state 에 Pydantic 객체를 둘지 dict 로 눕힐지.

**4번에서 내린 결정** (근거는 `langgraph_engine.py` 주석 + [Lesson 09](../learning/lessons/0009-expected-failure-vs-bug.html)):

- **`except` 절 둘, 좁은 것 → 넓은 것.** `OpenAIError`(바깥 탓) → `Exception`(내 탓 의심).
  절의 개수는 예외 종류가 아니라 **다르게 다룰 경우의 수**로 정해진다.
- **로그가 갈린다** — 바깥 탓은 `log.warning`(한 줄), 내 탓은 `log.exception`(스택트레이스).
  `failed_agents` 에는 **둘 다 이름만** 넣는다. 게이트(M8)는 "누가 커버 안 됐나"만 필요하고
  이유는 안 쓴다. 이유는 로그 → M3 `record_event` 로 간다.
- **노드는 state 를 편집하지 않는다.** `{"채널이름": [값]}` 이라는 **쪽지**를 돌려준다.
  ⚠️ `state["findings"] = ...` 는 **에러도 안 나고 아무 일도 안 일어난다**(복사본을 고치는 것).
  리듀서·체크포인터가 전부 반환값 경로에 걸려 있어서 직접 고치면 통째로 우회한다.
- 노드마다 **다른** 지연(0.3~0.8초). 같으면 병렬인지 직렬인지 구분이 안 된다.

**실측 — 완료 판정 ①③ 통과** (2026-08-20):

```
① 정상       0.81초 · findings 4개 · failed []            · done
② 하나 실패   0.81초 · findings 3개 · failed ['security']  · done
③ 셋 실패            findings 1개 · failed [셋]           · done
```

지연 합이 `0.6+0.4+0.8+0.3=2.1초` 인데 **0.81초**에 끝났다 → 가장 느린 노드 하나 = **병렬**.
그리고 ②③ 이 `done` 이다 → 예외가 밖으로 안 나갔다(완료 판정 ③).

⬜ **아직 못 막은 것: 안 끝나는 노드.** `raise` 는 잡았지만 **무한 대기**는 잡을 게 없다.
superstep 이 배리어라 한 노드가 안 끝나면 나머지 셋이 끝나도 전체가 멈춘다 —
**M5-5 타임아웃의 일**이다. Lesson 06 의 "빈 것의 뜻 셋" 중 ③(돌고 있는데 안 끝남)이 여기다.

**6번 결정**: 인메모리 체크포인터는 완료 판정 ②(`kill -9` 재개)를 **통과 못 한다.**
후보는 Sqlite(파일 하나) / Postgres(이미 떠 있음). 그 단계에서 정한다.

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

### 2. M1 테스트 — 미룬 것을 회수

`tests/test_webhook.py`의 다섯 함수. **`app.py`를 열지 말고** 계약만 보고 쓴다:
`invariants.md` INV-1·INV-2 / `03-build-plan.md` M1 "완료 판정" 4줄 /
`learning/reference/webhook-ingress.html` 응답 코드 표.

각 케이스에서 **상태 코드와 큐 깊이를 같이** 볼 것. 200이 두 사건(큐에 넣음 /
받았지만 아무것도 안 함)에서 나오므로, 코드만 보는 테스트는 dedup이 통째로 빠져도 통과한다.
자가 검사: **"구현을 `return Response(200)` 한 줄로 바꿔도 통과하는 테스트가 있나?"**

### 3. M1 독립 검증 — 새 세션에서 (테스트를 채운 뒤)

성공 기준: `uv run pytest` 통과 + `uv run python scripts/demo_m1_webhook.py` 12/12.
검증자에게 줄 질문은 "돌아가나"가 아니라 **"어떤 불변식이 위험한가"**.

### 4. 관측으로 메울 공백 — 실제 재배달 쏘기

재배달 시 `X-GitHub-Delivery` GUID가 유지되는지 **1차 출처에 문장이 없다.**
INV-2가 여기 걸려 있으므로 실제 웹훅을 등록하고 재배달을 눌러 눈으로 확인할 것.
로컬은 GitHub이 접근 못 하므로 터널(ngrok/cloudflared)이 필요하다.

### 5. M2 — 데이터 스파인

### 결정을 미룬 것 — 각 마일스톤 브리핑 직전에 (2026-07-28 재배치)

책 대조에서 나온 구멍 13개 중 4개는 "M2 전에"로 잡혀 있었는데, **필요해지기 직전**으로 옮김.
이유: 코드 0줄 상태에서 스키마 결정을 내리면 상상으로 만든 감으로 되돌릴 수 없는 걸 고르게 됨.
[`04-book-reading-plan.md`](04-book-reading-plan.md)가 정한 **저스트-인-타임** 원칙과 같은 근거.

| | 무엇 | 언제 | 되돌리기 |
|---|---|---|---|
| **G9** | `agent_events`에 증거 스니펫 원문을 넣을지 / 마스킹할지 / 해시+포인터만 남길지. 보존·압축 정책 | **M2 브리핑 직전** | ∞ (INV-4가 삭제 하드 거부) |
| **G8** | `code_chunks`에 `repo_id`·`commit_sha` 박기. `past_reviews`·`conventions`를 남길지 뺄지 | **M2 브리핑 직전** | 재인덱싱 = 돈 |
| **G6** | 애그리게이터 계약 — LLM인가 코드인가 / dedup 키 / severity 충돌 시 뭐가 남나 | ~~M5 브리핑 직전~~ → **M6 브리핑 직전** (2026-08-18 이동). M5 는 더미 Finding 이라 합칠 중복이 없다. 스캐폴드는 [ADR 0005](adr/0005-aggregator-contract.md) 에 이미 있음 | 0 (문서 한 문단) |
| ↳ | **M0에서 실측 근거가 나옴** — 같은 `(file, line, category)`에 `severity`만 다른 중복이 **에이전트 하나의 한 번 호출**에서 생성됨. dedup 키에 `category`가 필요하고, severity 충돌 시 **더 심각한 쪽을 남겨야** 한다(`critical`을 버리면 사람에게 갈 것이 자동 게시됨). 상세는 `PLAN.md` G-M0-3 | | |
| **G5** | 트러스트 바운더리를 diff + **검색 결과**로 확장 | **M7 브리핑 직전** | 0 (ADR 한 줄) |
| **G10** | **M8 을 어디까지 할 것인가** (2026-08-20 추가). 게이트(if 문 몇 줄, 반나절)는 이 프로젝트의 제1원칙이 코드가 되는 자리라 값어치가 크고, **GitHub 게시**(API·라인 앵커·멱등성, 2~3단계)가 비싸다. 게시를 로그로 대체해도 판정 로직은 증명된다 | **M6 끝난 직후** | 0 (ADR 한 줄) |
| ↳ | **왜 지금 안 정하나**: M6 에서 진짜 findings 를 봐야 "confidence 가 실제로 쓸만한 신호인가"를 안다. 죄다 0.8 을 뱉으면 게이트의 값어치 계산이 통째로 바뀐다. M7(RAG) 을 할지도 같은 자리에서 판단한다 — "맥락이 없어서 못 잡는 게 많나"를 보고 | | |

**M2 브리핑 직전에 같이 할 것** — 미루면 잊으니까 여기 묶어둠:
1. **Ch8 읽기** (3쪽, 25분) — `reference_books/Agentic_Design_Patterns.pdf` Memory Management. G9·G8의 재료
2. ~~**TigerData 계정 + Tiger CLI**~~ — **완료 후 무효** ([ADR 0003](adr/0003-local-postgres-instead-of-tiger.md)).
   실제로 해봤다: `tiger mcp install` → MCP 연결 → `service_create`로 서비스 프로비저닝 → 확장 조회.
   ADR 0001 D3이 노린 "에이전트가 인프라를 코드처럼 세팅한다" 경험은 얻었고, 서비스는 지웠다.
   **`tiger` MCP는 `.mcp.json`에 남겨둠** — `search_docs`가 TimescaleDB·Postgres 문서 검색에 유용.

**M7 직전에 할 것**: 테스트 레포 + 버그 심은 PR (SQL 인젝션 한 줄 + 테스트 없는 함수 하나). 작을수록 좋음. **정답을 내가 아는 것**이 핵심.

## 확정된 결정

| | 선택 | |
|---|---|---|
| **코드 작성** | **내가 직접 타이핑** | [ADR 0002](adr/0002-implementation-mode.md). Claude는 브리핑·힌트·독립검증·개념설명만 |
| 하네스 | **직접** (Genesis Kit 안 씀) | `DONE.md` 고정 / 마일스톤당 데모 명령 / 별도 세션 독립 검증 |
| 범위 | **M8까지** | 선별이 실제로 도는 지점 |
| DB | **로컬 Docker** (`timescaledb-ha:pg17`) | [ADR 0003](adr/0003-local-postgres-instead-of-tiger.md) — 2026-07-30에 Tiger Cloud에서 변경. 포폴 재현성 |
| 리뷰 대상 | 개인 토이 레포 + 심은 버그 | |
| 학습 비중 | 설계사고 60 / 완성 30 / 하네스 10 | |
| LLM | OpenAI 하나로 | [ADR 0004](adr/0004-local-oauth-proxy-for-llm.md) — 2026-08-14부터 **로컬 OAuth 프록시** 경유(`:10531`). Responses API만 스키마가 먹는다. **되돌리는 조건이 ADR에 있다** |
| 참고서 | **저스트-인-타임** — 마일스톤 브리핑 직전에 해당 챕터만 | [04-book-reading-plan.md](04-book-reading-plan.md) |

## 알려진 리스크 (착수 시점)

- ~~Tiger를 처음부터 쓰면 초반 마이그레이션 반복이 로컬보다 느림~~ — **해소** ([ADR 0003](adr/0003-local-postgres-instead-of-tiger.md)). `docker compose down -v`로 갈아엎는다. 단 **마이그레이션을 재실행 가능하게 쓸 것**은 그대로 유효 (`scripts/migrate.py`가 이력을 추적하지 않고 매번 전부 재실행하므로 더 중요해졌다)
- `TRUNCATE`가 DELETE 트리거를 우회 (INV-4) — M2에서 반드시 걸림
- pgvector 차원 불일치 — M2에서 **한 곳(마이그레이션)에만** 정의하고 코드가 거기서 읽게 [03:03:59]
- **G2**: 스페셜리스트 노드가 죽었을 때 "critical 없음"과 "확인 안 됨"을 게이트가 구분 못 함 → M5·M8에서 처리. 이 프로젝트 최악의 시나리오인데 고치는 건 if문 몇 줄
