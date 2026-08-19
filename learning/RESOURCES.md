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

- [LangGraph — Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
  **"As each node finishes, its outputs are written as task entries... These per-task writes
  ensure successful nodes' outputs are durable and don't need re-running on resume."**
  `put_writes` 계약, superstep 체크포인트와 task write 의 차이.
  Use for: M5-6 체크포인터 선택(Sqlite / Postgres)의 근거. `resume()` 이 INV-2 를 지키는 메커니즘.
  [Lesson 07](lessons/0007-permission-to-write-together.html)

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
