# ADR 0004 — LLM 백엔드를 로컬 OAuth 프록시로 바꾼다

**날짜**: 2026-08-14
**상태**: 확정 (조건부 — 아래 "되돌리는 조건" 참조)
**영향받는 결정**: [ADR 0001](0001-project-setup.md) D5 (LLM 제공자는 OpenAI 하나)
**시점**: M2 진행 중. M0 호출은 이미 돌아가고 있었고, M6에서 호출이 4배가 되기 전

---

## 결정

`backend/agents/base.py` 가 붙는 엔드포인트를 OpenAI API 에서
**로컬 OAuth 프록시**(`http://127.0.0.1:10531/v1`)로 바꾼다.
ChatGPT 구독의 OAuth 토큰을 OpenAI 호환 인터페이스로 노출하는
제3자 npm 패키지 [`openai-oauth`](https://github.com/EvanZhouDev/openai-oauth) 를 쓴다.

**코드는 안 고쳤다.** SDK 가 `OPENAI_BASE_URL` 환경변수를 자동으로 읽으므로
`client = OpenAI()` 가 그대로다. 백엔드가 무엇인지 코드는 모른다.

## 왜 바꾸나

**비용.** M0 하나로도 호출이 반복되는데, M6 에서 에이전트가 4개로 갈리면
PR 하나당 호출이 4배가 된다. 학습 프로젝트에서 호출당 과금은 **실험을 망설이게 만든다** —
"이거 한 번 더 돌려볼까" 가 비용 계산이 되는 순간 학습 속도가 떨어진다.
구독은 이미 내고 있으므로 한계 비용이 0 이다.

`CURRENT.md` 에 "OpenAI 하드 리밋 미확인" 이 계속 미해결로 남아 있었던 것도 같은 압력이다.

## 실측으로 알게 된 것 — 이게 이 ADR 의 값어치다

**`/v1/chat/completions` 를 쓰면 안 된다.**

| 경로 | `response_format` / `text_format` | 결과 |
|---|---|---|
| `client.chat.completions.parse` | **무시됨** | ❌ 자유 텍스트 → `ValidationError: Invalid JSON` |
| `client.responses.parse` | 지켜짐 | ✅ `[critical] sql-injection @ app.py:3 conf=0.99` |

프록시가 Codex 전용 엔드포인트를 감싸는 어댑터인데 Codex 가 Responses API 네이티브라,
`/v1/chat/completions` 는 **모양만 맞춘 호환 계층**이고 스키마가 상류까지 안 내려간다.

**위험한 건 이게 에러가 아니라 조용한 무시라는 점이다.**
스키마를 넘겼는데 아무 경고 없이 무시되고, 모델은 그냥 평범한 텍스트를 뱉는다.
`.parse()` 가 파싱에 실패해서 터져준 게 운이 좋았던 것이다 —
`.create()` 를 썼다면 "돌아가는데 형식이 안 지켜지는" 상태로 한참 갔을 수 있다.

> 호환 계층은 **인터페이스가 같다는 것만 보장하고 의미가 같다는 건 보장하지 않는다.**
> 갈아끼운 뒤에는 "붙었나" 가 아니라 **"계약이 지켜지나"** 를 확인해야 한다.
> 우리 경우 그 계약은 INV-3 (모든 finding 에 confidence·rationale) 이고,
> 스키마가 무시되면 그게 통째로 무너진다.

## 무엇을 받아들이나

- **비공식 제3자 패키지가 신뢰 경로에 들어왔다.** 프롬프트와 diff 가 이 패키지를 통과한다.
  개인 로컬 학습용이라 감수하지만, 조건이 바뀌면 되돌린다(아래).
- **프록시는 재부팅을 못 넘긴다.** `npx openai-oauth` 를 다시 띄워야 한다.
  DB 컨테이너와 같은 성질의 마찰이고, 새 세션이 "왜 안 되지" 로 시간을 쓸 자리다.
- **`usage` 필드명이 다르다** — `prompt/completion_tokens` → **`input/output_tokens`**.
  M3 에서 `record_event(cost, latency, tokens)` 를 붙일 때 걸린다.
- **비용이 지연과 한도로 바뀌었다.** 실측: diff 한 건에 output 344 토큰 중 **reasoning 162 (47%)**.
  M6 에서 4배가 되고, 프록시가 무상태라 히스토리도 매번 다시 올라간다.
  즉 예산 관리가 사라진 게 아니라 **단위가 달러에서 시간·한도로 바뀐 것**이다.

## 되돌리는 조건

되돌리기는 싸다 — `.env` 두 줄(`OPENAI_BASE_URL` 삭제, 진짜 키 주석 해제)이다.
아래 중 하나라도 참이면 되돌린다:

1. **남에게 보여줄 물건이 된다** — 데모, 포트폴리오 시연, 다른 사람이 clone 해서 돌림
2. 프록시가 스키마를 조용히 무시하는 다른 경로가 발견된다
3. 패키지 유지보수가 끊기거나 신뢰할 수 없는 변경이 들어온다

`README` 나 `docker-compose` 로 남이 돌릴 수 있게 만드는 시점이 1번이고,
[ADR 0003](0003-local-postgres-instead-of-tiger.md) 이 포폴 재현성을 근거로 로컬 DB 를 골랐으므로
**그 시점은 생각보다 가깝다.** 그때 이 결정은 자동으로 만료된다고 봐야 한다.

## 따라오는 변경

- `backend/agents/base.py` — `chat.completions.parse` → **`responses.parse`**. 모델 `gpt-5.6-luna`
- `.env` — `OPENAI_BASE_URL` 추가. 진짜 키는 주석 처리, `OPENAI_API_KEY` 는 자리채움 값
  (SDK 가 키 없이 부팅을 거부하므로 필요하다. 프록시는 `Authorization` 을 보지 않는다)
- `docs/CURRENT.md` — "환경" 절과 "확정된 결정" 표
- ⬜ **M3 에서 `usage` 필드명 차이를 처리할 것** — 지금 적어두지 않으면 그때 원인을 못 찾는다
