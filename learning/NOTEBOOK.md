# 학습 노트 — 내가 정리한 핵심

> 레슨과 시뮬을 끝낸 뒤 **내 말로** 적는 곳. Claude가 채우지 않는다.
> 규칙 하나: **레슨을 다시 보지 말고 먼저 쓴다.** 못 쓰겠으면 그게 아직 안 배운 부분이다.
> 다 쓰면 Claude가 검토한다 — 틀린 곳을 잡아주고, 빠진 자리를 짚어준다.

**왜 쓰나**: 읽으면 "아 맞다" 하고 넘어간다(유창성 착각). 쓰면 뭘 모르는지가 드러난다.
그리고 몇 주 뒤 돌아왔을 때 **레슨 5개를 다시 읽는 것보다 이 파일 한 장을 읽는 게 빠르다.**

**형식**: 앞 **세 칸을 사람이** 채운다. 길게 쓰지 않는다 — 짧을수록 다시 읽는다.
네 번째 **"우리 코드 어디에 있나"** 는 Claude 가 파일·행 번호를 찾아 적는다 (2026-08-14부터).
그건 판단이 아니라 사실 조회라서 — 사람이 꺼내야 하는 건 앞 세 칸이다.

---

## Lesson 01 — JSON을 부탁하지 말고 스키마로 강제하라

> 📄 [레슨](lessons/0001-schema-not-prompt.html) · 🎮 [시뮬](sims/0001-schema-gate.html)

**한 문장으로**: pydantic 모델을 `response_format` 으로 넘기면 토큰 디코딩 단계에서 형태가 강제된다.

**내 말로 (3줄 이내)**: `completions.parse` 함수의 `response_format` 에 pydantic 모델을 정의하여
넘기면, 토큰 디코딩 단계에서 모델 스키마 형태를 강제하여 원하는 형태의 결과를 얻을 수 있다.
`choices[0].message.parsed` 형태로 output 사용.

**시뮬에서 틀린 예측 / 놀란 것**: 없음.

**우리 코드 어디에 있나**: `backend/agents/schema.py` 의 `Finding(BaseModel)` —
필드는 agent_type, severity, category, file, line, confidence, rationale.
`str`·`float`·`ge`·`le` 가 값을 강제하고, `description` 은 모델에게 부탁하는 형태.
`ReviewResult` 는 최상위 객체 — 지적이 여러 개이고, structured output 은 최상위가 배열이면 거부한다.

<!-- Claude 검토 (2026-07-30) — 위는 사용자가 쓴 것, 아래는 검토 의견 -->
> **빠진 것**: "무엇이 강제되나" 는 맞는데 **"무엇이 강제 안 되나"** 가 없다.
> `description=` 은 모델에게 가는 부탁이고 파서는 안 본다. `ge`/`le` 는 JSON schema 의
> `minimum`/`maximum` 으로 나가 실제로 강제된다(파인튜닝 모델만 예외). 둘 다 `Field()` 안에
> 나란히 쓰는데 성질이 다르다 — 이 경계가 Lesson 01 의 나머지 절반이다.
>
> **추가**: `message.parsed` 는 항상 있지 않다. 모델이 거부하면 `None` 이고
> `message.refusal` 에 이유가 온다. 확인 없이 쓰면 터진다.

---

## Lesson 02 — PR diff는 공격자가 쓴 글이다

> 📄 [레슨](lessons/0002-untrusted-diff.html) · 🎮 [시뮬](sims/0002-injection-lab.html)

**한 문장으로**: 프롬프트 인젝션은 근본적으로 해결책이 없다. 방어는 확률을 낮추는 일이다.

**내 말로 (3줄 이내)**: 세 겹으로 막는다.
1. **역할 분리** — 지시는 system prompt, 신뢰할 수 없는 diff 는 user content 에 둔다.
2. **delimiter 격리** — diff 를 `<untrusted_diff>{diff}</untrusted_diff>` 로 감싸 데이터의
   시작과 끝을 명시하고, 신뢰할 수 없는 데이터일 뿐이라고 system 에서 못 박는다.
3. **출력 스키마** — Lesson 01 에서 정한 `ReviewResult` 로 출력 형식을 묶는다.

**시뮬에서 틀린 예측 / 놀란 것**:

**우리 코드 어디에 있나**: `backend/agents/base.py` — `SYSTEM_PROMPT`(방어 ①③)와
`build_user_message()`(방어 ②).

<!-- Claude 검토 (2026-08-14) — 위는 사용자가 쓴 것, 아래는 검토 의견 -->
> **표현 교정 2개**
> · 닫는 태그는 `</untrusted_diff>` — 슬래시 방향. delimiter 는 문자열이 전부라 한 글자가 곧 구멍이다.
> · 3번은 "이상한 출력 방지" 보다 **"출력의 형식을 공격자가 바꿀 수 없다"** 가 정확하다.
>   내용은 여전히 바뀐다 — `findings: []` 는 형식상 완벽하다.
>
> **빠진 것 — 이 레슨의 나머지 절반**
> 위는 *방어 목록*이고, 레슨·시뮬의 절반은 **"그래도 뚫린다"** 다.
>
> | 두 층위 | 예시 | 방어가 듣나 |
> |---|---|---|
> | 명령형 인젝션 | "Ignore previous instructions" | 잘 듣는다 |
> | **사실 조작** | "보안팀이 승인했다 (SEC-4821)" | **거의 안 듣는다** |
>
> · delimiter 는 **탈출 문자열 한 줄로 깨진다** (Sim L3)
> · 스키마는 자유 텍스트를 막지만 **빈 배열은 못 막는다** (Sim L4)
> · 그리고 `findings: []` 는 **"정말 문제 없음" 과 모양이 똑같다** → 게이트가 구별 못 한다
>
> 사실 조작이 핵심이다. severity 를 낮추라고 *명령*할 필요가 없다 — *안전하다고 주장*하면 된다.
> 지시를 무시하라고 시킨 적이 없으니 어떤 인젝션 필터에도 안 걸린다.

---

## Lesson 03 — 서명은 바이트에 대한 것이다

> 📄 [레슨](lessons/0003-signature-over-bytes.html) · 🎮 [시뮬](sims/0003-signature-bytes.html)

**한 문장으로**: GitHub PR 웹훅은 HMAC-SHA256 으로 검증하고, **바이트 단위로** 대조해야 하므로
`json()` 이 아니라 `body()` 로 받아야 한다.

**내 말로 (3줄 이내)**: 깃과 우리는 secret 을 공유한다. 깃이 HMAC-SHA256 으로 본문 바디의
지문을 만들어 헤더에 싣는다. 우리는 `body()` 로 본문을 받아 같은 함수·같은 secret 으로
다시 계산하고 헤더와 대조한다. 같으면 그때 body 를 처리한다.
`json()` 으로 안 받는 이유는 변환 중 바이트가 바뀌기 때문.

**시뮬에서 틀린 예측 / 놀란 것**: 없음.

**우리 코드 어디에 있나**: `backend/webhook/security.py:71` `verify_signature(raw_body, signature_header)`
— `hmac.new(key=WEBHOOK_SECRET, ...)` 로 계산하고 `hmac.compare_digest`(133행)로 대조.
`WEBHOOK_SECRET` 은 import 시점에 없으면 부팅을 거부한다(62~68행).
raw body 를 읽는 자리는 `backend/webhook/app.py:63` `body = await request.body()` — **파싱보다 먼저**.

<!-- Claude 검토 (2026-08-14) — 위는 사용자가 쓴 것, 아래는 검토 의견 -->
> **어휘 교정 — 이 레슨의 핵심이다**
> "암호화" 가 아니다. 두 개는 다른 물건이다:
>
> | | 방향 | 내용 | 목적 |
> |---|---|---|---|
> | 암호화 | 왕복 (복호화 가능) | **숨긴다** | 비밀 유지 |
> | HMAC | 편도 | **평문 그대로 간다** | 변조 탐지 |
>
> 헤더에 실리는 것은 본문이 아니라 **본문의 지문**이다. body 는 평문으로 가고 누구나 읽는다.
> 시뮬 L4 에서 secret 만 가려지고 body 는 그대로 보였던 게 그 뜻이다.
>
> 이 구분이 중요한 이유는 **다음 생각을 차단하기 때문**이다 —
> "암호화됐으니 body 는 안전하다" 로 이어진다. 서명 통과가 증명하는 건 **출처**뿐이고,
> body 안의 diff 는 여전히 공격자가 쓴 글이다. 그건 [Lesson 02] 가 따로 막는다.
> **두 경계가 막는 것이 다르다.**
> 관련: `learning-records/0003-hmac-is-a-seal-not-a-lock.md` (같은 자리를 이미 한 번 겪었다)
>
> **빠진 것 2개**
> · **타이밍 안전 비교** — `==` 가 아니라 `hmac.compare_digest`. `==` 는 첫 불일치에서 멈춰서
>   "몇 글자까지 맞았나" 를 시간으로 흘린다 (Sim L5). 우리 코드 `security.py:133`.
> · **응답 코드** — 우리는 400, GitHub 공식 예제는 403. 의도된 차이이고 INV-1 에 적혀 있다.

---

## Lesson 04 — 같은 배달이 두 번 왔을 때

> 📄 [레슨](lessons/0004-same-delivery-twice.html) · 🎮 [시뮬](sims/0004-idempotency-timeline.html)

**한 문장으로**: 웹훅 중복은 delivery ID 를 set 에 넣어보고 **크기 변화**로 판정한다.

**내 말로 (3줄 이내)**: 먼저 set 의 길이를 재서 `before` 에 저장한다. 그 set 에 delivery ID 를
`add` 해본다 — set 자료구조라 중복이면 크기가 증가하지 않는다.
`add` 후 길이와 `before` 를 비교해 동일하면 중복, 아니면 통과.

**시뮬에서 틀린 예측 / 놀란 것**: 없음.

**우리 코드 어디에 있나**: `backend/queue/router.py:51` `is_duplicate(delivery_id)` —
`before = len(_seen_deliveries)` → `.add()` → `return len(...) == before` (67~69행).
자료구조가 **둘**이다: `_queue`(list, 20행)는 처리할 잡, `_seen_deliveries`(set, 26행)는 본 ID 기억.
호출부는 `backend/webhook/app.py:109` — `is_duplicate()` 통과한 것만 `enqueue()`(112행).

<!-- Claude 검토 (2026-08-14) — 위는 사용자가 쓴 것, 아래는 검토 의견 -->
> **이름 교정** — 처음에 "큐를 set 으로 관리" 라고 했는데 둘은 별개다.
> `len()` 비교는 **`_seen_deliveries`(set)** 에서 일어나고, 큐(list)는 판정을 통과한 뒤 `append` 될 뿐이다.
>
> | | 무엇을 세나 | 줄어드나 |
> |---|---|---|
> | `len(_queue)` | 아직 처리 안 된 잡 | 워커가 꺼내면 줄어든다 |
> | `len(_seen_deliveries)` | 지금까지 본 배달 | **절대 안 줄어든다** ← 함정 ② |
>
> **왜 `add` 의 반환값을 안 쓰나**: `set.add()` 는 아무것도 돌려주지 않는다.
> 그래서 전후 `len()` 비교가 관용구가 된다. 핵심은 **확인과 기록이 한 동작**이라는 것 —
> `if x in seen` 과 `seen.add(x)` 를 따로 하면 그 사이에 틈이 생긴다 (Sim L2, 340ms 경계).
>
> **아직 안 적힌 두 함정**
> · **재시작을 못 넘는다** — `_seen_deliveries` 는 프로세스 메모리다. 껐다 켜면 통째로 사라진다.
>   버그가 아니라 **알고 미룬 타협**이고, M4 에서 Redis TTL 로 간다 (Sim L4).
> · **10초의 벽** — GitHub 은 실패한 배달을 **자동 재시도하지 않는다**. 10초를 넘기면 이벤트가
>   **영구 유실**된다. 그래서 큐는 "느려도 되게" 가 아니라 **"유실을 막으려고"** 있다 (Sim L5).

---

## Lesson 05 — 삭제로 가는 문은 네 개다

> 📄 [레슨](lessons/0005-four-doors-to-delete.html) · 🎮 [시뮬](sims/0005-four-doors.html)

**한 문장으로**: 감사 로그를 변경·삭제하지 못하게 하려면 **막아야 할 문이 여러 개**고,
문마다 자물쇠가 다르다.

**내 말로 (3줄 이내)**: 기본적으로 `UPDATE`·`DELETE` 에 트리거를 걸어 행 단위 변경·삭제를 막는다.
`TRUNCATE` 는 행 단위 연산이 아니라 별도의 TRUNCATE 트리거를 건다.
추가로 `drop` 은 또 다른 연산이라 트리거로 못 막고 RBAC 으로 제한한다.

**시뮬에서 틀린 예측 / 놀란 것**:

**우리 코드 어디에 있나**: `migrations/003_immutable.sql` — 거부 함수
`agent_events_append_only()`(23행)를 트리거 셋이 공유한다. UPDATE 트리거는 38행에 완성돼 있고
**DELETE·TRUNCATE 는 아직 `TODO(human)`(45행)**. RBAC 은 `006_rbac.sql` 로 **아직 없다**.

<!-- Claude 검토 (2026-08-14) — 위는 사용자가 쓴 것, 아래는 검토 의견 -->
> **미묘한 교정 — "DDL 이라서 못 막는다" 가 아니다**
> `TRUNCATE` 도 넓게는 DDL 인데 막을 수 있다. 진짜 기준은 **그 사건을 잡는 트리거가 존재하냐** 다.
>
> | 명령 | 대응 트리거 | 막히나 |
> |---|---|---|
> | UPDATE / DELETE | `BEFORE UPDATE/DELETE ... FOR EACH ROW` | ✅ |
> | TRUNCATE | `BEFORE TRUNCATE ... FOR EACH STATEMENT` | ✅ |
> | `drop_chunks()` / `DROP TABLE` | **없음** | ❌ 권한으로만 |
>
> Postgres 가 트리거를 걸 수 있는 사건은 INSERT/UPDATE/DELETE/TRUNCATE **넷뿐**이다.
> 테이블을 DROP 하는 건 그 목록에 없다. 그래서 남은 방어가 권한뿐이다.
>
> 그리고 `TRUNCATE` 가 별도 트리거를 요구하는 진짜 이유는 문서 문장이다 —
> *"TRUNCATE will not fire any ON DELETE triggers."* 행 단위가 아니라서가 아니라,
> **아예 다른 트리거 종류를 발동시키기 때문**이다. 그래서 `FOR EACH ROW` 로는 쓸 수조차 없다.
>
> **아직 안 적힌 것 — 왜 두 겹인가**
> 시뮬에서 접속 주체를 「소유자」로 바꾸면 **RBAC 이 통째로 무효**가 된다. 롤 제한은 앱 롤에게만 걸린다.
> 두 층이 막는 대상이 다르다:
> · **트리거** — "그 동작을 허용하지 않는다" (누가 접속하든)
> · **롤** — "그럴 자격이 없다" (앱 자격증명이 유출돼도 감사 로그는 남는다)
>
> ⚠️ 지금 우리 `.env` 의 `DATABASE_URL` 은 `postgres` 슈퍼유저다 — **소유자 상태**다.
>
> **프레임 한 줄**: "방법이 여러 가지" 보다 **"막아야 할 문이 여러 개"**. 방법을 고르는 게 아니라
> 문마다 다른 자물쇠가 필요하고, 하나라도 안 잠그면 나머지를 아무리 잘 잠가도 소용없다.

---

## 아직 모르겠는 것 (레슨 무관, 계속 쌓는다)

여기 적힌 게 다음 레슨의 재료가 된다. 부끄러워할 것 없다 — 안 적으면 안 배운다.

-
