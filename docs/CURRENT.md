# CURRENT — 지금 상태

> 새 세션이 콜드 스타트할 때 **가장 먼저 읽는 파일.**
> "지금 뭐가 진짜로 살아있고, 뭐가 스텁이고, 다음 한 걸음이 뭔가"만 적는다. 설계는 여기 안 적는다.

**마지막 갱신**: 2026-08-27 · **M6-0c 완료 — 자의 눈금이 정해졌다 (`fixtures/expected.yaml`). 다음은 `evals/grader.py`**

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
| `learning/lessons/` | 레슨 **11개** (01 스키마 · 02 인젝션 · 03 HMAC · 04 멱등성 · 05 삭제 문 4개 · 06 부분 실패 · 07 리듀서=허가 · 08 엣지=시간 · 09 예상실패vs버그 · 10 타임아웃≠취소 · **11 체크포인트=재개계약**) | ✅ |
| `learning/sims/` | 시뮬 **11개** — 0001~0011 전부 | ✅ |
| `learning/NOTEBOOK.md` | **사용자가 자기 말로 적는 곳.** Claude가 채우지 않는다 | ✅ **11/11 전부 4/4** (`/learn-check`) |
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

📌 **프록시의 프롬프트 캐시는 있는데 불안정하다** (2026-08-27 실측, `scratch/recon_prompt_cache.py`).

| 실측 (호출 4회) | 값 |
|---|---|
| 적중 시 `cached_tokens` | **1792 / 2338 (77%)** |
| M0 실측(진짜 API, 2026-07-28) | **1792** / 2049 — **두 백엔드에서 같은 숫자** |
| `cache_write_tokens` | 4회 전부 0 (프록시가 그 필드를 안 옮기는 것으로 보인다) |
| 적중률 | **4회 중 1회** — n=4 라 아무 말도 못 한다 |
| output | 675~1015 중 reasoning **71~74%** — `CURRENT.md` 의 47% 에서 올랐다 |
| 지연 | 14.4 ~ 19.8s |

⚠️ **첫 판정(2026-08-27 오전)은 틀렸다** — 2회 호출로 "캐시 없음"이라 적었다가 재실행에서 뒤집혔다.
원인 둘: ① 표본 2회 ② 측정 스크립트가 *"1회차 miss · 2회차 hit"* 을 전제로 판정문을 짰는데,
**직전 실행의 캐시가 남아 1회차가 적중**했다. 캐시는 프로세스가 아니라 **접두부**에 붙는다.

**`1792 = 14 × 128`** — OpenAI 캐시는 128토큰 단위로 끊긴다. 우리 프롬프트의 **앞 1792 토큰이
안정적인 접두부**이고 나머지 546 이 diff 쪽이라는 뜻이다. → M6-3a 에서 **공유 블록을 앞쪽에 몰면
에이전트 4개가 그 계산을 나눠 쓴다.** 책 2.3.4(인쇄 53)의 *"동적 요소는 캐시 경계 뒤로"* 가
**우리 환경에도 적용된다** — 다만 적중이 흔들려서(라우팅 추정) 이득의 크기는 아직 모른다.

⬜ **적중률은 안 쟀다** — M6-4 배선에서 `usage` 를 로깅하면 공짜로 쌓인다. 지금 호출을 더 안 태운다.
그때 노트북 01 의 `wilson_ci` 가 이 비율에 그대로 쓰인다.

**M6-3a 완료 — 프롬프트가 컴포넌트가 됐다.** (2026-08-27)

| | | 상태 |
|---|---|---|
| `backend/prompts/review.py` | 블록 5개 + `build_review_system_prompt()` | ✅ security 978자 · quality 949 · testing 937 · docs 761 |
| `TAG_RULE` 토글 | `tag_rule=` 인자 (D4 = c) | ✅ 34자 차이 실측. **판정은 3b** |
| `perspectives=` 인자 | 3b 의 실험 축 | ✅ 변형 세트는 `evals/` 가 소유한다 |
| SOP vs 한 줄 | docs 만 한 줄, 나머지는 절차 | ✅ **일부러 섞었다** — 3b 비교 재료 |
| `scratch/recon_prompt_cache.py` | 캐시 실측 | ✅ 위 📌 참조 |

⚠️ **프롬프트가 지금 두 곳에 있다** — `backend/agents/base.py:SYSTEM_PROMPT`(M0 유물)와
`backend/prompts/review.py`. **한쪽만 고치면 조용히 어긋난다.** base.py 에 경고를 달아뒀고,
배선은 M6-4 다 (지금은 에이전트가 하나뿐이라 넘길 `agent_type` 이 없다).

⬜ **M6-4 로 넘긴 것 셋**: ① base.py 배선 ② `schema.py` 의 `agent_type`(모델이 여전히 뱉는다 —
덮어쓸지 스키마에서 뺄지) ③ **D4 후보 (d)** — 태그 구조를 걷어내고 역할 체계로(책 2.4.7).
③은 `build_user_message()` 를 건드려 3a 범위를 넘었다.

**M6-0c 완료 — 자의 눈금이 정해졌다.** (2026-08-27)

| | | 상태 |
|---|---|---|
| `fixtures/expected.yaml` | 픽스처 3개의 `must_catch` / `must_not_appear` | ✅ D1·D2 결정 (아래 「확정된 결정」) |
| 매칭 축 | `category` + `file` + `severity_min` — **`line` 은 뺐다** | ✅ 15판 실측이 축별 안정성을 갈랐다 |
| `evals/stats.py` | `wilson_ci` (노트북 01 에서 옮김) | ✅ 이미 있음 |
| `evals/grader.py` | 이 YAML 을 읽어 판정 | ⬜ **다음 한 걸음** |
| `scripts/eval_prompt.py` | K판 돌리고 표 찍기 | ⬜ |

📌 **자를 만들자마자 자로 재봤다** — 기존 15판(2x2 12 + variance 3)을 이 눈금으로 재채점:

```
sample           6/9    실패 3판: sqli 가 high 로 내려앉음 1 · 오탐 2
sample_injected  3/6    실패 3판: sqli high 2 · resource-leak 누락 1
```

**12/12 도 0/12 도 아니다 — 이게 이 눈금을 고른 유일한 검증이다.** 만점이면 M6-3b 에서
프롬프트를 갈라도 차이가 안 보이고(McNemar 불일치 쌍 0), 0점이면 아무 후보도 못 넘는다.
⚠️ 이 숫자는 프롬프트를 고치면 바뀐다. **베이스라인이지 목표가 아니다** (📖 인쇄 219).

재채점하다 새로 드러난 것 셋:
- **주석의 판 수가 틀렸었다** — `prompt_variance.json` 3판을 빼고 세고 있었다. `sample` 은 6판이 아니라 **9판**. 전부 실측으로 고쳤다
- **`resource-leak` 이 통째로 누락된 판이 있다** (`no_tag_rule/injected` 판1). severity 흔들림만 보고 있었는데 **아예 못 찾는 판**도 있다
- **`missing-docstring`**(sample, low, 1/9) 이 새로 보였다 — 화이트리스트 논쟁의 세 번째 사례

⬜ **`grader.py` 로 넘긴 것 둘**: ① `must_not_appear` 가 **블랙리스트냐 화이트리스트냐** —
화이트리스트면 `syntax-error`(injected 5/6)가 자동 오탐이 되는데 **그건 진짜 지적이다**
(인젝션 diff 에 파이썬 아닌 줄이 실제로 있다). ② `category` 문자열 매칭의 재량
(`"sql-injection"` vs `"sql injection risk"`) — 📖 인쇄 208 의 "객관적 재현성"은 여기서 공짜로 안 온다.

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
| ~~`backend/eval/` 구조~~ | ~~M6-1 착수 시~~ | ✅ **회수됨 (2026-08-27)** — 아래 「확정된 결정」의 *평가 코드 위치* 행 |

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
| 5 | 모든 노드에 타임아웃 [01:05:02] | ✅ 확정 (2026-08-21) |
| 6 | 체크포인터 — **결정 필요** | ✅ 확정 (2026-08-21) |
| 7 | `scripts/demo_m5.py` | ✅ 판정 ①②③ 전부 통과 (2026-08-21) — 아래 |

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

**5번에서 내린 결정** (근거는 `langgraph_engine.py` 주석 + [Lesson 10](../learning/lessons/0010-timeout-is-not-cancel.html)):

⚠️ **M5-5 는 "타임아웃 값을 정하는 일"이 아니라 "터질 자리를 `try` 안으로 옮기는 일"이었다.**
층이 셋인데 셋은 몇 초냐가 아니라 **실패가 값이 되느냐 예외가 되느냐**로 갈린다:

| | 어디 | 결과 |
|---|---|---|
| ① | `invoke()` 바깥 | 넷이 같이 죽는다. 이미 끝난 셋의 findings 도 버려진다 |
| ② | 노드 밖 (`add_node(timeout=)`) | 예외가 노드 **밖**에서 나서 `_run_specialist` 의 `try` 를 비껴간다 |
| ③ | 노드 **안** (호출 자체) | `try` 안에서 난다 → `failed_agents` 라는 **값**이 된다 ✅ |

①② 는 **부분 실패를 전체 실패로 승격**시킨다 — M5-4 에서 만든 "셋이 죽어도 하나로 진행"이
도로 무너지고 그게 정확히 **G2** 다.

- **`_call_agent` 가 `time.sleep()` 한 줄이 아니라 잘게 자면서 마감을 재는 루프**가 됐다.
  한 번에 다 자면 마감을 확인할 틈이 없다. M6 에서 이 루프가 통째로 `OpenAI(timeout=...)` 로 바뀐다.
- **`AGENT_TIMEOUT_SECONDS = 1.0` · 상수 하나.** 에이전트별 dict 를 안 쓴 이유는
  넷의 지연이 다른 게 성질이 아니라 **병렬을 눈으로 보려고 우리가 다르게 준 것**이기 때문.
  ⚠️ **값 1.0 은 관측이 아니라 데모 가능성에서 나온 잠정치다** — `_DELAYS` 최대(0.8초)보다 크고
  사람이 기다릴 만한 값. 처음 180 초를 넣었다가 되돌렸다(hang 데모가 3분 걸려 완료 판정을 못 돌린다).
- **던지는 예외는 `openai.APITimeoutError`.** 파이썬 내장 `TimeoutError` 는 `OpenAIError` 의
  자손이 아니라서 **두 번째 `except` 절**(내 탓)이 잡는다 → 우리 버그로 기록된다.
  ⚠️ `request=` 는 **더미에서만 우리가 만든다** — 진짜 호출에서는 SDK 가 채운다
  (`openai/_base_client.py:1083`).
- 안 끝나는 에이전트 주입 통로 `M5_HANG_AGENTS` 추가. `M5_FAIL_AGENTS` 와 **다른 실패**다 —
  저건 `raise` 하고 이건 아무것도 안 한다.

**실측 — 완료 판정 ③ 이 무한 대기까지 확장됐다** (2026-08-21):

```
M5_HANG_AGENTS=security
WARNING backend.orchestration.langgraph_engine: Request timed out.   ← log.warning (바깥 탓)
1.03초 · findings 3개 · failed ['security'] · done
```

`log.exception` 이 아니라 `log.warning` 한 줄인 것이 예외 타입 선택의 값어치다 —
Lesson 09 의 첫 번째 절이 받았다는 증거.

📌 **배리어의 주인이 바뀌었다.** 1.03초 = 타임아웃 1.0 + tick 0.02. 가장 느린 정상 노드(0.8초)가
아니라 **타임아웃이 층의 시간을 정했다.** M6 에서 이 값이 곧 **리뷰 한 건의 최대 지연**이 된다.
그리고 SDK 는 타임아웃 뒤 **기본 2번 재시도**하므로(`DEFAULT_MAX_RETRIES = 2`)
실제 최대 대기는 이 값의 3배 + 백오프다 — `max_retries=` 도 M6 에서 같이 정할 것.

⚠️ **타임아웃은 취소가 아니다.** 우리가 기다리기를 그만두는 것뿐이고 저쪽은 계속 돈다
(실측: `fut.cancel()` → `False`, 포기 2초 뒤에도 함수가 끝까지 실행됨).
**그래서 재시도는 같은 일을 두 번 시키는 것일 수 있다 — INV-2 가 M6 에서 다시 열린다.**


**6번에서 내린 결정** (근거는 `backend/orchestration/checkpointer.py` 주석 + [Lesson 11](../learning/lessons/0011-checkpoint-is-a-resume-contract.html)):

**새 파일 `backend/orchestration/checkpointer.py`** — 경계가 세 겹이 됐다.
`engine.py`(계약, LangGraph 모름) → `langgraph_engine.py`(LangGraph 알지만 저장소 모름) →
`checkpointer.py`(**여기만 저장소를 안다**). M5-1 의 "엔진은 DB 를 모른다"가 주입 구조라서 공짜로 지켜졌다.

- **`SqliteSaver` · 파일 하나** (`checkpoints.sqlite`, `.gitignore` 에 `*.sqlite` 추가).
  `_STACK = ExitStack()` 으로 커넥션 수명을 프로세스 전체로 늘린다 —
  ⚠️ `from_conn_string` 이 **`@contextmanager`** 라 `with` 를 벗어나면 닫힌다.
  📌 **공식 문서 예제가 틀렸다**: `checkpointer = PostgresSaver.from_conn_string(...)` 을 그대로 쓰면
  saver 가 아니라 `_GeneratorContextManager` 를 받는다. context7 로 교차 검증함.
  ⚠️ `setup()` 계약이 둘이 **반대**다 — Postgres *"MUST be called directly"* /
  Sqlite *"should not be called directly"*. 그래서 안 부른다.
- **`findings` 채널을 `dict` 로 눕혔다** (`Finding.model_dump()`). 세 곳이 같이 바뀌었다:
  `langgraph_engine.py:296` · `state.py:82` · `checkpointer.py`(`build_serde()` 삭제).
  이유는 검증이 아니라 **저장**이다 — Pydantic 객체를 그대로 두면 저장 포맷이 클래스에 묶여
  **`Finding` 에 필드가 하나 늘면 저장된 체크포인트를 못 읽는다.** 그리고 **M6 이 그걸 확실히 바꾼다**.
  ⚠️ 검증은 안 사라졌다 — `Finding(...)` 생성자가 INV-3 을 강제한 뒤에 눕힌다.
  **검증은 입구에서, 저장은 눕혀서.** 대가: M6 애그리게이터가 `f["severity"]` 를 쓰게 된다.
  📌 `Deserializing unregistered type` 경고가 사라진 건 부산물이지 목적이 아니다.

**실측 — 완료 판정 ② 통과** (2026-08-21, `scratch/recon_kill9_resume.py`):

```
④ 자식이 READY 까지 0.51초 — 그래프는 아직 0초다
⑤ 그래프+0.50초에 kill · 살아있었나=True · returncode=-9
   재시작 직후: status=running · findings 2개 · 남은 노드 ['security', 'testing']
   resume() 후:  status=done · findings 4개 · 0.82초
```

**진짜 `kill -9` 로 죽인 뒤 재개했고 LLM 호출 2회를 아꼈다.** quality(0.4s)·docs(0.3s)만
끝나 있었으므로 `pending_writes` 에 남은 건 둘뿐이었다 — 살아남는 목록은 **타이밍이 정한다**.

⚠️ **M5-7 데모를 쓸 때 반드시 볼 것** — [reference/kill9-and-resume.html](../learning/reference/kill9-and-resume.html)
에 함정 다섯이 근거와 함께 정리돼 있다. 특히:

| | 함정 | 왜 데모가 깨지나 |
|---|---|---|
| ④ | **자식 시작에 0.42초**(그중 langgraph import 0.34초) | `Popen` 직후 `sleep(0.5)` 는 그래프 **0.08초 지점**이다. "죽인 것"과 "시작도 안 한 것"이 결과만으로 구분 안 됨 → 자식이 `READY` 를 찍고 부모가 읽은 뒤 시계를 잰다 |
| ② | 이미 끝난 프로세스에 `kill()` → **조용히 아무 일도 안 남** | 데모가 "죽였다"고 말하려면 `poll() is None` 을 같이 찍어야 근거가 된다 |
| ⑤ | mid-superstep 에 죽으면 `get_state()` 가 **키를 안 준다** | `s["findings"]` → `KeyError`. **아래 열린 결정 참조** |

✅ **열린 결정 닫힘 — `get_state()` 는 구현이 계약을 지킨다** (2026-08-21, M5-7):
recon 실측(`scratch/recon_get_state_after_kill.py`)으로 키가 빠지는 regime 이
**체크포인트 0개일 때 딱 하나**임을 확인했다 (mid-superstep kill 은 4채널이 다 차 있다 —
pending_writes 적용. "반만 찬 dict"는 없다). → `langgraph_engine.py` 의 `get_state()` 가
기본값(`findings=[]` 등)을 깔아 **항상 6개 키**를 돌려준다. 호출부 방어(.get) 대신
구현에서 한 번만 — 호출부가 는다(데모 → 워커 복구 → M9 대시보드).
"빈 findings" 의 두 뜻은 `status="not_started"` 가 가른다 (Lesson 06).
⚠️ 남긴 사실: `not_started` 는 "정말 시작 전"과 "invoke 직후 첫 checkpoint 기록 전에
죽음"을 구분 못 한다 — 관측상 동일하다. 좁은 창이라 지금은 안 가른다.

**7번 — 실측, 완료 판정 ①②③ 전부 통과** (2026-08-21, `uv run python scripts/demo_m5.py`):

```
①  0.83초 · findings 4개 · failed [] · done          (직렬 합 2.1초 · 최장 노드 0.8초)
②  그래프+0.50초에 kill · 살아있었나=True · returncode=-9
    재시작 직후: status=running · findings 2개 · 남은 노드 ['security', 'testing']
    resume() 후:  status=done · findings 4개 · 0.82초
③  1.02초 · findings 3개 · failed ['security'] · done  (log.warning 한 줄 — 바깥 탓 경로)
```

- 병렬 판정식은 (B) `elapsed < 최장 노드 + 0.3초` — 배리어 성질(Lesson 08)을 그대로 판정으로.
  ⚠️ 정직한 한계를 주석에 남김: 빠른 노드가 낀 부분 퇴화(0.3+0.4=0.7초)는 배리어 아래
  숨어서 시간으로는 못 잡는다. 전부 잡으려면 노드별 계측인데(스냅샷에 시각 없음 — recon)
  M6 에서 더미가 사라지므로 지금은 안 한다.
- ⚠️ 데모 판단 두 곳(①판정식·②계약)은 사용자 요청으로 **Claude 가 채웠다** —
  "데모 스크립트라 시스템 본체 판단이 아니다"가 근거. 본체 코드의 TODO(human) 관행은 유지.

📌 **M5 독립 검증 완료** (2026-08-25, 새 세션) — "통과가 증명하는 범위가 판정문의 주장보다
좁다"는 판정. 발견 4건, 빌더 세션에서 핵심 2건 재실측으로 확인:

| | 발견 | 조치 |
|---|---|---|
| 1 | **INV-2 — `run()` 이 멱등이 아니다.** `done` thread 재호출 시 리듀서가 이어붙여 findings 4→8 (실측). 크래시 후 `running` 재실행은 안전. 데모는 `_reset_db()` 때문에 이 상태를 못 본다 | 계약에 경고 문서화(`engine.py`) + **G11 등록** (가드 위치는 M6 워커 배선 직전 결정) |
| 2 | **판정 ② 가 `before` 를 안 봤다** — 자식이 다 끝난 뒤 kill 돼도 ✅ (근거 없는 ✅, 재현됨) | ✅ 고침 — `before["status"] == "running"` 항 추가 |
| 3 | 판정 셋 다 findings **내용**을 안 본다 — confidence 전부 0.5 상수여도 통과. INV-3 회귀가 데모에 안 잡힘 | M6 에서 진짜 Finding 이 오면 데모 판정에 내용 검사 추가 |
| 4 | `resume()` 을 없는 열쇠에 부르면 `EmptyInputError` — 계약에 없었다 | ✅ 계약에 문서화 — 복구 코드는 status 로 먼저 가른다 |


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
| **G11** | **`run()` 멱등 가드를 어디 두나** (2026-08-25, M5 독립 검증에서 발견). `done` 인 review_key 에 `run()` 재호출 시 findings 가 4→8 로 중복 (INV-2). 후보: 엔진 입구에서 status 보고 거부 / 워커가 부르기 전에 확인 / head_sha 가 열쇠라 "완료된 리뷰 재요청은 no-op" 정책. 수동 재배달·완료 후 재시도가 뚫린 경로 | **M6 워커 배선 직전** | 0 (가드 코드 몇 줄) |

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
| **평가 코드 위치** | **최상위 `evals/`** (`backend/` 밖) | 구조 결정 카드 첫 적용 (2026-08-27). 근거: **평가는 프롬프트를 고르는 동안만 돈다 — 고르고 나면 프롬프트는 상수가 되어 배포되므로 평가 코드가 배포될 이유가 없다.** M8 게이트는 구간이 아니라 점(`confidence >= x`)을 보므로 `wilson_ci` 를 안 쓴다. ⚠️ **import 는 `evals/` → `backend/` 한 방향만** — 반대가 생기면 선을 넘은 것이고 그때 `backend/evals/` 로 이사한다 (비용: 디렉토리 이동 + import 몇 줄) |
| **픽스처 정답 선언 위치** | **`fixtures/expected.yaml`** (`.diff` 옆) | 구조 결정 카드 2번째 적용 (2026-08-27). 후보는 `fixtures/` vs `evals/`. 근거: **정답은 픽스처의 속성이다** — `.diff` 를 추가할 때 정답 선언을 빼먹으면 grader 가 그 픽스처를 조용히 통과로 세므로, 짝이 눈에 보이는 자리가 이긴다. ⚠️ **되돌리는 조건**: M7 에서 픽스처가 `.diff` 가 아니라 테스트 레포의 PR 로 바뀌면 `fixtures/` 구조가 통째로 흔들린다 — 그때 `evals/` 로 이사한다 (비용: 파일 하나 이동 + 경로 상수 한 줄). 데이터 의존 방향은 import 규칙과 같다: **`evals/` → `fixtures/` 한 방향만** |
| **프롬프트 모듈 위치** | **`backend/prompts/`** (새 최상위 패키지) | 구조 결정 카드 3번째 적용 (2026-08-27). 후보 `backend/agents/prompts.py` · `backend/prompts/` · 블록별 파일 분할. 근거: **프롬프트는 에이전트의 재료지 에이전트가 아니다** — 3b 에서 `evals/eval_prompt.py` 가 조합을 돌리려면 평가 코드가 프롬프트를 import 해야 하는데, `backend/agents/` 안에 두면 평가가 에이전트 내부를 들여다보게 된다. 블록별 파일 분할(c)은 **블록 수가 확정되기 전이라 이르다** — 파일 하나로 시작하고 커지면 그때 가른다. ⚠️ **되돌리는 조건**: 파일이 300줄을 넘거나 M7 RAG 블록이 붙어 관심사가 둘 이상이 되면 (c) 로 분할 |
| **D3 — `agent_type` 을 누가 정하나** | **코드가 정한다** (출처 semantics) | 2026-08-27. `schema.py:18` 의 *"어떤 관점에서 찾았나"* 가 **출처**(누가 찾았나)와 **분류**(무슨 종류인가) 둘로 읽혀서 갈렸다 — 한 필드가 두 질문에 답할 수 없다. **출처로 확정**하고, 분류는 `category` 가 맡는다. 근거: 책 10.4.4(인쇄 308, 전문 에이전트를 도구로 모델링 → 호출자가 출처를 안다) · 10.5.3(인쇄 320, 같은 모델의 의견을 독립 증거로 보지 말 것) · M8 게이트의 커버리지 판정(G2)은 출처를 물어야만 답이 된다. ⚠️ **아직 프롬프트만 반영됐다** — `EVASION_TAIL` 의 `agent_type = security` 줄을 뺐다. 스키마는 그대로라 모델이 여전히 값을 뱉는다. 덮어쓰기/스키마 제거는 **M6-4 배선에서** |
| **D1 — 정답지를 무엇으로 선언하나** | **픽스처에 실제로 있는 결함의 목록** · 매칭 축은 `category + file + severity_min` | 2026-08-27. 기각한 후보: *에이전트별 커버리지 요구(각자 최소 N개)* — 지금 diff 는 13줄에 결함 2개뿐이라 docs·testing 이 찾을 게 0개이고, 에이전트도 아직 1개다. **버린 게 아니라 M6-4 이후로 미뤘다**(그때 `by:` 를 더해 G2 커버리지 판정에 쓴다). `line` 은 뺐다 — 15판 실측에서 clean 은 `:17` 안정인데 injected 는 `:20~:25` 로 흩어진다(인젝션 문구가 4줄을 밀어 `@@` 계산이 갈린다). **같은 축인데 픽스처마다 안정성이 다르다**는 게 이 파일의 첫 교훈. ⚠️ **되돌리는 조건**: M7 에서 GitHub 에 실제 코멘트를 붙이면 줄번호가 틀리면 안 되는 값이 된다 → 그때 `line` 을 픽스처별로 켠다 |
| **D2 — 오탐을 어떻게 다루나** | **`must_not_appear` 는 거부권**(하나 걸리면 0점). **`must_catch` 는 아니다** | 2026-08-27. 근거: 책 인쇄 200(환각은 즉시 탈락) · 208(τ²-bench 이진 보상, 모두 통과해야 성공) · 209(excellent 만 해결로 간주). ⚠️ **그대로 베끼지 않은 이유**: 책은 모델 **순위표**를 만들어 전부 실패로 몰려도 순위가 나오지만, 우리는 그 위에서 **McNemar 로 프롬프트를 짝지어 비교**하므로 전부-실패면 불일치 쌍이 0 이 되어 검정이 불가능하다. → **조이는 힘(must_not_appear)과 가르는 해상도(must_catch)를 분리**했다. ⬜ 블랙리스트냐 화이트리스트냐는 `grader.py` 로 넘겼다 |
| 참고서 | **저스트-인-타임** — 마일스톤 브리핑 직전에 해당 챕터만 | [04-book-reading-plan.md](04-book-reading-plan.md) |

## 알려진 리스크 (착수 시점)

- ~~Tiger를 처음부터 쓰면 초반 마이그레이션 반복이 로컬보다 느림~~ — **해소** ([ADR 0003](adr/0003-local-postgres-instead-of-tiger.md)). `docker compose down -v`로 갈아엎는다. 단 **마이그레이션을 재실행 가능하게 쓸 것**은 그대로 유효 (`scripts/migrate.py`가 이력을 추적하지 않고 매번 전부 재실행하므로 더 중요해졌다)
- `TRUNCATE`가 DELETE 트리거를 우회 (INV-4) — M2에서 반드시 걸림
- pgvector 차원 불일치 — M2에서 **한 곳(마이그레이션)에만** 정의하고 코드가 거기서 읽게 [03:03:59]
- **G2**: 스페셜리스트 노드가 죽었을 때 "critical 없음"과 "확인 안 됨"을 게이트가 구분 못 함 → M5·M8에서 처리. 이 프로젝트 최악의 시나리오인데 고치는 건 if문 몇 줄
