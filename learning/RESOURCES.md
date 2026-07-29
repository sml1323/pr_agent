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

- **confidence 캘리브레이션** — LLM이 뱉는 확신도가 실제 정확도와 맞는지 재는 방법. M11이 범위 밖이라 지금은 공백으로 둔다.
