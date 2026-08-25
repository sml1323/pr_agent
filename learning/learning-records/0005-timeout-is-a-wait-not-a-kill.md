# 타임아웃은 기다림에 거는 것이지 실행에 거는 것이 아니다 — 그리고 층을 잘못 고르면 값이 예외가 된다

M5-5 를 앞두고 "안 끝나는 노드"를 다뤘다. [[0004-reducer-is-permission-not-merge]] 가 남긴 숙제의 뒷면이다 — 거기서 **예외를 값으로** 바꿨는데, 무한 대기는 예외가 아니라서 그 경로를 통째로 비껴간다.

**핵심**: `timeout` 은 *기다리는 쪽*의 인내심이지 *일하는 쪽*의 수명이 아니다. 파이썬에는 도는 스레드를 죽이는 수단이 없다. 그래서 "타임아웃을 걸었다"는 "그 일이 멈춘다"를 뜻하지 않는다 — **포기했을 뿐 저쪽은 계속 돈다.**

**Evidence** (넷 다 직접 돌림):
1. `fut.result(timeout=0.5)` → `TimeoutError` 는 0.50초에 났지만, 2.5초 시점에 그 함수의 마지막 줄이 실행돼 있었다. `fut.cancel()` 은 `False`.
2. 동기 노드에 `add_node(..., timeout=0.5)` → **compile 에서 거부**. `ValueError: Node timeouts are only supported for async nodes because sync Python execution cannot be safely cancelled in-process.`
3. `async` 노드 + `await asyncio.sleep(3)` + `timeout=0.5` → **0.51초에 `NodeTimeoutError`** ✅. 같은 노드의 안을 `time.sleep(3)` 으로만 바꾸면 → **3.02초에 그냥 성공** 💥. 에러도 경고도 없음.
4. ③의 성공 경로에서 `ainvoke()` 가 통째로 터졌다 — 함께 돌던 빠른 노드는 이미 끝났는데 결과를 못 받는다.

**갈라놓은 것 — 층이 실패의 모양을 정한다.** 타임아웃을 걸 자리가 셋인데, 셋은 "몇 초냐"가 아니라 **실패가 값이 되느냐 예외가 되느냐**로 갈린다.

| | 어디 | 결과 |
|---|---|---|
| ① | `invoke()` 바깥 | 넷이 같이 죽는다 |
| ② | 노드 밖 (LangGraph `timeout=`) | 예외가 밖에서 난다 → 노드 안의 `except` 가 못 받는다 |
| ③ | 노드 안 (호출 자체에) | `try` 안에서 난다 → `failed_agents` 로 간다 ✅ |

①②는 **부분 실패를 전체 실패로 승격**시킨다. M5-4 에서 어렵게 만든 "셋이 죽어도 하나로 진행"이 도로 무너지고, 그게 정확히 G2 다.

**Implications**:
- **M5-5 는 "타임아웃 값을 정하는 일"이 아니라 "타임아웃이 날 자리를 노드 안으로 옮기는 일"이다.** 숫자는 잠정치다 — 정상 응답의 지연 분포를 M6 전엔 관측할 수 없다.
- **[[0003-hmac-is-a-seal-not-a-lock]] 과 같은 모양**: 방어를 걸었다는 사실이 아니라 *무엇을 막는지*를 짚어야 한다. 동기 노드에 건 타임아웃은 "걸었으니 안전하다"는 착각만 만든다. LangGraph 가 compile 에서 거부하는 건 그 착각을 파는 걸 거절하는 것이다 — [Lesson 01](../lessons/0001-schema-not-prompt.html) 의 "부탁하지 말고 강제하라" 와 같은 사고방식.
- **M5-4 의 `except openai.OpenAIError` 가 이자를 낸다.** `APITimeoutError ◂ APIConnectionError ◂ APIError ◂ OpenAIError` 이므로 M6 에서 타임아웃이 실전에 들어와도 코드를 안 고친다. 층을 골라 잡은 것이 새 실패 종류를 공짜로 흡수했다.
- **기본값을 읽는 습관**: `openai/_constants.py` 의 `DEFAULT_TIMEOUT = 600s`(연결 5s), `DEFAULT_MAX_RETRIES = 2`. 10분은 사실상 "타임아웃 없음"이고, **우리가 재시도를 안 써도 이미 재시도가 2번 돌고 있다.**
- **타임아웃 후 재시도는 INV-2 문제다.** "포기했다"는 "안 일어났다"가 아니다 — 서버는 이미 처리를 끝냈을 수 있다. [Lesson 04](../lessons/0004-same-delivery-twice.html) 가 웹훅 입구에서 푼 문제가 LLM 호출 앞에서 다시 나온다. M6 브리핑에서 다시 열 것.
- 관련: [Lesson 10](../lessons/0010-timeout-is-not-cancel.html), [Lesson 08](../lessons/0008-edges-draw-time.html), [[0004-reducer-is-permission-not-merge]]
