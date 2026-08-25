# 에이전트 시스템 설계 Resources

## Knowledge

- [OpenAI — Structured Outputs 가이드](https://platform.openai.com/docs/guides/structured-outputs)
  `response_format`에 JSON schema를 넘겨 출력을 강제하는 공식 문서. 지원 모델, 제약(모든 필드 required, `additionalProperties: false`), refusal 처리.
  Use for: `parse()` 동작 원리, 스키마가 거부되는 이유, 어떤 pydantic 타입이 변환 가능한지.

- [openai-python — `helpers.md` (Structured Outputs Parsing Helpers)](https://github.com/openai/openai-python/blob/main/helpers.md)
  SDK가 pydantic 모델을 JSON schema로 바꾸고 다시 파싱하는 헬퍼의 1차 출처. `client.chat.completions.parse()` / `client.responses.parse()`.
  Use for: 실제 호출 시그니처, `message.parsed` vs `message.refusal`.

- [Pydantic — Fields (`Field`)](https://docs.pydantic.dev/latest/concepts/fields/)
  `description`, `ge`/`le` 같은 제약이 JSON schema로 어떻게 나가는지.
  Use for: description이 왜 LLM에게 가는 프롬프트인지, 범위 제약을 스키마 레벨에서 거는 법.

- [OWASP Top 10 for LLM Applications — LLM01: Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
  프롬프트 인젝션의 표준 분류(직접/간접)와 완화책. **간접 인젝션**이 우리 케이스 — PR diff가 그 통로.
  Use for: 트러스트 바운더리 설계, 왜 delimiter만으로는 부족한지.

- [Simon Willison — Prompt injection 시리즈](https://simonwillison.net/tags/prompt-injection/)
  이 문제를 처음 명명한 사람의 지속 기록. "완전 방어는 아직 없다"는 입장의 근거.
  Use for: 방어의 한계를 정직하게 이해하기 → 그래서 왜 출력 측 게이트가 필요한지.

- [GitHub Docs — Validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
  `X-Hub-Signature-256` · HMAC-SHA256 · **raw payload**에 서명 · timing-safe 비교 요구. 파이썬 예제 포함.
  Use for: M1 `webhook/security.py`의 확정 출처. ⚠️ 공식 예제는 불일치에 **403**을 쓰는데 우리 INV-1은 **400** — 의도된 차이.

- [GitHub Docs — Handling failed webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries)
  **"GitHub does not automatically redeliver failed webhook deliveries."** 실패 판정은
  "서버가 죽었거나 **10초** 넘게 응답하지 않을 때". 수동 재배달 방법도 여기.
  Use for: INV-2의 실제 근거. ⚠️ 영상의 "GitHub이 재시도한다"는 전제를 정정한 출처다.
  그리고 [00:03:06] vs [01:31:39]로 흔들리던 ack 시간을 **10초로 확정**해준다.

- [GitHub REST API — Repository webhooks](https://docs.github.com/en/rest/repos/webhooks)
  delivery 객체의 `id`(시도) / `guid`(이벤트) / `redelivery` 필드.
  Use for: 멱등키를 무엇으로 잡을지, API로 재배달을 쏘는 법.

- [Python 표준 라이브러리 — `hmac`](https://docs.python.org/3/library/hmac.html)
  `hmac.new()` · `compare_digest()`. 의존성 추가 불필요.
  Use for: 서명 계산과 타이밍 안전 비교의 시그니처.

- 영상: *Designing & Building PR Review Multi Agent System* (Ayush Singh, 3h)
  이 프로젝트의 원본. 3시간 중 2시간 43분이 설계. `docs/source/transcript.txt`에 전문, `docs/01-chapter-map.md`에 타임스탬프 맵.
  Use for: "왜 이 설계인가"의 1차 출처. 코드는 없으니 구현 참고용으로는 쓸 수 없음.

- 책: *Agentic Design Patterns* (`reference_books/`)
  Use for: **저스트-인-타임으로만.** 마일스톤 직전 해당 챕터만. 읽는 법은 [`docs/04-book-reading-plan.md`](../docs/04-book-reading-plan.md).

- [Tiger Docs — Understand chunks](https://www.tigerdata.com/docs/learn/chunks/understanding-chunks)
  하이퍼테이블(논리) ↔ chunk(물리 테이블)의 관계. **"Inheritance is not supported for hypertables"** 주의문 포함.
  Use for: M2 `agent_events` 설계. 트리거를 거는 대상과 데이터가 실제로 든 테이블이 왜 다른지.

- [Tiger Docs — Automate tasks with triggers](https://www.tigerdata.com/docs/build/performance-optimization/automate-tasks-with-triggers)
  **"TimescaleDB propagates the change to every chunk."** 하이퍼테이블 트리거가 chunk까지 전파된다는 확정 근거.
  Limitations 절도 볼 것 — transition table을 쓰는 ROW 트리거와 DELETE 트리거는 미지원.
  Use for: `003_immutable.sql`이 chunk 레벨까지 유효한지의 근거.

- [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/17/sql-createtrigger.html) · [TRUNCATE](https://www.postgresql.org/docs/17/sql-truncate.html)
  **"TRUNCATE will not fire any ON DELETE triggers... But it will fire ON TRUNCATE triggers."**
  그리고 **"Triggers on TRUNCATE may only be defined at statement level, not per-row."**
  Use for: INV-4의 문 ③. DELETE 트리거만 걸면 뚫리는 이유와, TRUNCATE 트리거를 statement-level로 써야 하는 이유.

- [Tiger Docs — Understand data retention](https://www.tigerdata.com/docs/learn/data-lifecycle/data-retention/about-data-retention)
  **"dropping data by the chunk is faster, because it deletes an entire file from disk."**
  Use for: INV-4의 문 ④. `drop_chunks()`가 DDL이라 DML 트리거의 사정거리 밖인 근거 → RBAC이 별도로 필요한 이유.
  ⚠️ 보존 정책을 켜면 INV-4와 정면 충돌한다는 것도 여기서 나온다.

- [Python 표준 라이브러리 — `asyncio`: Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html)
  `gather()` 의 두 모드가 여기서 확정된다 — 기본값은 첫 예외를 즉시 위로 던지지만
  **"Other awaitables ... won't be cancelled and will continue to run."**
  `return_exceptions=True` 는 예외를 결과 리스트의 값으로 만든다.
  `TaskGroup` 은 반대로 **나머지를 취소**한다("the remaining tasks in the group are cancelled").
  `asyncio.timeout()` 은 `CancelledError` 를 `TimeoutError` 로 **번역**한다.
  Use for: M5 팬아웃/팬인의 실패 정책 선택. 고아 태스크가 토큰을 계속 태우는 이유.
  [Lesson 06](lessons/0006-nobody-looked.html)

- [LangChain Docs — Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
  **"the entire superstep is transactional. If any of these branches raises an exception,
  none of the updates are applied to the state."** — M5 설계를 바꾸는 문장이다.
  예외를 노드 밖으로 내보내면 성공한 브랜치의 결과까지 날아간다 → 노드 안에서 값으로 바꿔야 한다.
  리듀서(`Annotated[list, operator.add]`)와 노드별 retry policy 도 여기.
  ⚠️ 체크포인터가 있으면 **"results from successful nodes within a superstep are saved,
  and don't repeat when resumed"** — 재개 시 중복 호출을 막는 근거.
  📌 **두 인용은 모순이 아니다 — 층이 다르다** (2026-08-19 실측으로 확인):
  전자는 **채널**(정식 체크포인트) 층 — 실패하면 `channel_values` 가 비어 있다.
  후자는 **태스크**(pending writes) 층 — 터진 순간까지 **끝나 있던** 노드만 남는다.
  ⚠️ 누가 끝났는지는 **타이밍에 달렸다**. 같은 코드를 두 번 돌려 결과가 갈렸다 → **비결정적**.
  그래서 이 동작에 기대면 안 되고, 노드 안에서 예외를 값으로 바꾸는 게 유일하게 결정적이다.
  Use for: M5 `langgraph_engine.py`. G6(애그리게이터 계약)의 입력 모양.
  [Lesson 06](lessons/0006-nobody-looked.html) · [Lesson 07](lessons/0007-permission-to-write-together.html)

- [LangGraph — Graph API · Edges 절](https://docs.langchain.com/oss/python/langgraph/graph-api)
  **"If a node has multiple outgoing edges, all destination nodes execute in parallel
  during the next superstep."** `add_edge` · `add_conditional_edges` · `START`/`END` · entry point.
  📌 실측(2026-08-19): 같은 노드 넷을 **배선만** 바꿔 돌린 결과 —
  팬아웃+팬인 0.30초(aggregate 가 4개 봄) / 체인 1.22초(4개) / **팬인 빠뜨림 0.31초(0개)**.
  셋 다 에러 없고 최종 state 는 전부 4개다. **결과만 보면 구분이 안 된다.**
  Use for: M5-3 `_build()` 배선. 조건부 엣지를 언제 쓰나(갈 곳이 실행 시점에 정해질 때만).
  [Lesson 08](lessons/0008-edges-draw-time.html)

- [LangGraph — Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
  **"As each node finishes, its outputs are written as task entries... These per-task writes
  ensure successful nodes' outputs are durable and don't need re-running on resume."**
  `put_writes` 계약, superstep 체크포인트와 task write 의 차이.
  Use for: M5-6 체크포인터 선택(Sqlite / Postgres)의 근거. `resume()` 이 INV-2 를 지키는 메커니즘.
  [Lesson 07](lessons/0007-permission-to-write-together.html)

- [Python — `concurrent.futures`](https://docs.python.org/3/library/concurrent.futures.html)
  **"Attempt to cancel the call. If the call is currently being executed or finished running
  and cannot be cancelled then the method will return `False`."** (`Future.cancel`) ·
  **"Regardless of the value of *wait*, the entire Python program will not exit until all
  pending futures are done executing."** (`Executor.shutdown`)
  📌 실측(2026-08-20): `result(timeout=0.5)` 가 0.50초에 `TimeoutError` 를 냈지만
  그 함수는 2초를 다 채우고 마지막 줄까지 실행됐다. `cancel()` → `False`.
  Use for: M5-5. **타임아웃은 기다림에 거는 것이지 실행에 거는 것이 아니다.**
  [Lesson 10](lessons/0010-timeout-is-not-cancel.html)

- `langgraph.types.TimeoutPolicy` 독스트링 + `langgraph/graph/state.py::add_node` (설치된 패키지)
  **"Timeouts rely on asyncio cancellation. If your node uses synchronous `time.sleep()`
  or other CPU-bound work that blocks the GIL, the timeout will not be fired until after
  the event loop has been released."** ·
  **"Timeouts are supported only for async nodes; sync nodes cannot be safely cancelled in-process."**
  📌 실측(2026-08-20): 동기 노드에 `timeout=0.5` → **compile 에서 `ValueError`**.
  async 노드 + `await asyncio.sleep(3)` → 0.51초 `NodeTimeoutError`,
  같은 노드 안을 `time.sleep(3)` 으로 바꾸면 → **3.02초에 그냥 성공**(경고 없음).
  Use for: M5-5 에서 타임아웃을 **노드 밖이 아니라 노드 안**에 두는 근거.
  [Lesson 10](lessons/0010-timeout-is-not-cancel.html)

- `openai/_constants.py` (설치된 SDK 2.49.0)
  `DEFAULT_TIMEOUT = httpx.Timeout(timeout=600, connect=5.0)` · `DEFAULT_MAX_RETRIES = 2`
  예외 족보: `APITimeoutError ◂ APIConnectionError ◂ APIError ◂ OpenAIError`.
  📌 **600초 = 10분은 사실상 "타임아웃 없음"이다.** 그리고 우리가 안 써도 재시도가 이미 2번 돈다.
  Use for: M6 에서 `_call_agent` 에 꽂을 값. M5-4 의 `except OpenAIError` 가 타임아웃도 받는다는 근거.
  [Lesson 10](lessons/0010-timeout-is-not-cancel.html)


- `langgraph/checkpoint/serde/_msgpack.py` 모듈 독스트링 + `SAFE_MSGPACK_TYPES` (설치된 패키지)
  **"Msgpack deserialization safety controls. Set `LANGGRAPH_STRICT_MSGPACK=true` to restrict
  checkpoint deserialization to the types listed in `SAFE_MSGPACK_TYPES`. Without this,
  any Python callable stored in checkpoint data will be imported and executed on load."**
  📌 그래서 `Deserializing unregistered type ... Finding` 경고는 **정리 잔소리가 아니라 보안 경계**다 —
  체크포인트를 읽는다는 건 거기 적힌 타입을 import 한다는 뜻이다. 기본 허용 목록에는
  `datetime`·`UUID`·`Decimal`·`Path` 같은 것만 있고 우리 클래스는 없다.
  Use for: M5-6 결정 ③ (`Finding` 을 그대로 저장할지 dict 로 눕힐지).
  [Lesson 11](lessons/0011-checkpoint-is-a-resume-contract.html)

- `langgraph.checkpoint.memory.InMemorySaver` 독스트링 (설치된 패키지)
  **"Only use `InMemorySaver` for debugging or testing purposes. For production use cases
  we recommend installing `langgraph-checkpoint-postgres` and using `PostgresSaver`."**
  📌 실측(2026-08-21): 프로세스 A 에서 `run()` → `done · findings 4`,
  **프로세스 B 에서 같은 `thread_id` 로 `get_state()` → `not_started · findings 0`.**
  그리고 `langgraph.checkpoint.sqlite`/`.postgres` 는 **설치돼 있지 않다**(별도 패키지) —
  이 결정은 `uv add` 를 부른다.
  Use for: M5-6 결정 ① (Memory / Sqlite / Postgres). 완료 판정 ②를 못 넘는 이유.
  [Lesson 11](lessons/0011-checkpoint-is-a-resume-contract.html)


- `subprocess.Popen.send_signal` / `.kill` / `.__del__` (CPython 3.13.5 stdlib)
  **"Skip signalling a process that we know has already died."** (`send_signal`, `subprocess.py:2192`) ·
  **"Not reading subprocess exit status creates a zombie process which is only destroyed
  at the parent python process exit"** (`__del__`, `subprocess.py:1137`)
  📌 실측(2026-08-21): `p.kill()` → `returncode=-9`(SIGKILL). 이미 끝난 프로세스에 `kill()` 하면
  **예외도 없고 아무 일도 안 일어난다** → 데모가 "죽였다"고 말하려면 `poll() is None` 을 같이 찍어야 한다.
  `signal.signal(SIGKILL, ...)` → `OSError: [Errno 22]` — **가로챌 수 없다**(그래서 진짜 시험이 된다).
  Use for: M5-7 `demo_m5.py` 의 완료 판정 ②. [reference/kill9-and-resume.html](reference/kill9-and-resume.html)

- **자식 프로세스 시작 오버헤드** (실측, 이 레포 기준)
  📌 실측(2026-08-21, 3회): 자식 파이썬 시작 **0.42초**, 그중 `import langgraph` + 우리 모듈이 **0.34초**.
  우리 그래프 전체가 0.81초이므로 **오버헤드가 그래프 길이의 절반이다.**
  ⚠️ `Popen` 직후 `sleep(0.5)` 는 "그래프 0.5초 지점"이 아니라 **0.08초 지점**이고,
  그때는 체크포인트가 없어 `get_state()` 가 `not_started` 를 준다 —
  **"죽인 것"과 "시작도 안 한 것"이 결과만으로 구분 안 된다.**
  → 자식이 `READY` 를 찍고 부모가 그걸 읽은 뒤 시계를 잰다.
  Use for: M5-7 데모 · 앞으로 프로세스를 나누는 모든 실측.
  [reference/kill9-and-resume.html](reference/kill9-and-resume.html)

- `langgraph.pregel.main::Pregel._prepare_state_snapshot` (설치된 langgraph 1.2.11)
  **`if not saved: return StateSnapshot(values={}, next=(), ..., created_at=None, ...)`**
  📌 실측(2026-08-21, `scratch/recon_get_state_after_kill.py`): 키가 빠지는 regime 은
  **체크포인트 0개일 때뿐**이다 (values={} → 우리 `get_state()` 가 키 2개 · `not_started`).
  mid-superstep kill(0.5초)은 채널 4개가 **다 차 있다** (pending_writes 까지 적용, 키 6개 · `running`).
  "반만 찬 dict"라는 세 번째 regime 은 없다. ⚠️ 그래서 `not_started` 가 두 뜻이 된다 —
  "정말 시작 전"과 "invoke 직후 첫 put 전에 죽음"이 관측상 구분 불가.
  그리고 노드별 시작 시각은 스냅샷 어디에도 없다 (PregelTask 필드 · metadata 키에 시간 없음).
  Use for: M5-7 `demo_m5.py` TODO(human) ② (get_state 반환 계약) · TODO ① 후보 (C)의 비용.


## Wisdom (Communities)

- [r/LocalLLaMA](https://reddit.com/r/LocalLLaMA) · [r/LLMDevs](https://reddit.com/r/LLMDevs)
  Use for: 구조화 출력이 실무에서 깨지는 지점, 프롬프트 인젝션 사례 공유.

- [LangChain / LangGraph Discord](https://discord.gg/langchain)
  Use for: M5 오케스트레이션에서 막힐 때. 특히 병렬 팬인 reducer 문제(G7).

> 커뮤니티 참여 선호는 아직 확인 안 함. 원치 않으면 이 절은 지운다.

## Gaps

- **애그리게이터 병합 규칙의 1차 출처가 없음** — 영상이 "overall confidence를 계산한다"고만 하고 공식을 안 준다.
  G6 결정 시점(M5 직전)에 찾아야 함. 없으면 우리가 정하고 ADR로 남긴다.
- **재배달 시 `guid`가 유지되는지에 대한 명시 문장이 여전히 없음** — 공식 문서 다섯 곳을 봤다.
  다만 delivery 객체가 `id`(시도)와 `guid`(이벤트)를 나눠 갖고 `redelivery` 플래그가 따로 있다는
  **구조적 근거**는 확보했다. 추측을 사실로 승격시키지 말 것 — M1 끝나고 실제 재배달로 관측한다.
  [Lesson 04](lessons/0004-same-delivery-twice.html)

- **`CREATE RULE`이 하이퍼테이블에서 실패한다는 1차 출처가 없음** — 프로젝트 문서가
  "RULE은 쿼리 재작성 단계에서 돌고 하이퍼테이블은 재작성 규칙을 미지원" [03:00:45]이라 적었으나,
  Tiger 문서에서 확인된 건 **"Inheritance is not supported for hypertables"**까지다.
  어차피 트리거로 가므로 실무 영향은 없지만 근거 등급은 구분해 둔다.
  [Lesson 05](lessons/0005-four-doors-to-delete.html)

- **`kill -9` 후 체크포인트 재개의 구체적 메커니즘** — LangGraph 공식 문서는 "fault tolerance" 를
  용도로 나열하고 superstep 내 성공 노드가 재개 시 반복되지 않는다는 문장까지는 준다.
  그런데 **프로세스가 중간에 죽었을 때 어디서부터 이어지는지**를 명시한 문장은 못 찾았다.
  M5 완료 판정 ②가 정확히 이걸 요구하므로 **실측으로 확인한다** — 문서가 아니라 관측이 근거가 된다.
  [Lesson 06](lessons/0006-nobody-looked.html)

- **confidence 캘리브레이션** — LLM이 뱉는 확신도가 실제 정확도와 맞는지 재는 방법. M11이 범위 밖이라 지금은 공백으로 둔다.

- **정상 LLM 응답의 지연 분포** — M5-5 타임아웃 값을 정하려면 "느린 정상 호출이 몇 초까지 가나"가
  필요한데, 더미 노드의 `0.3~0.8초` 는 우리가 만든 숫자지 관측한 숫자가 아니다.
  **M6 에서 진짜 호출을 재고 다시 정한다.** 지금 고르는 값은 잠정치다.
  [Lesson 10](lessons/0010-timeout-is-not-cancel.html)

- **`durability="sync"` 가 언제 결과를 바꾸나** — 0.5·0.7초 kill 에서 `async`(기본)와 결과가 같았다.
  우리 그래프가 superstep 2개짜리로 짧아서일 수 있다. **긴 그래프에서 재검증 필요**.
  1차 출처는 확보: `Durability = Literal["sync","async","exit"]` · `'async'`는
  *"persisted asynchronously while the next step executes"* (`langgraph/types.py:89`).
  [reference/kill9-and-resume.html](reference/kill9-and-resume.html)
