"""diff 하나를 LLM에 넣고 구조화된 리뷰를 받는다.

전체 그림에서 ④의 조각 하나. M6에서 이게 넷(security/quality/testing/docs)으로
갈라지고 각자 다른 프롬프트와 모델을 갖는다. 지금은 하나다.

트러스트 바운더리 (docs/02-architecture.md:493):
    PR diff는 신뢰할 수 없는 입력이다. PR을 열 수 있는 누구나 내용을 정할 수 있으므로
    프롬프트 인젝션 벡터로 취급한다. 문서에 적힌 이 경계가 여기서 처음 코드가 된다.
"""

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.responses import ResponseUsage

from backend.agents.schema import AgentType, ReviewResult, SourcedFinding
from backend.prompts.review import build_review_system_prompt

load_dotenv()

# M6에서 backend/config/model_router.py 로 뺀다 — 에이전트마다 다른 모델을 쓰려고.
# 문서는 싼 모델, 보안은 제일 센 모델 [01:48:58]. M0에선 상수 하나로 충분하다.
#
# 원래는 nano 였고 근거는 비용이었다 — 에이전트 4개 × PR마다 호출이면 4배로 곱해지니까.
# 2026-08-14에 로컬 OAuth 프록시로 갈아타면서 그 전제가 죽었다. 호출당 과금이 없고,
# 애초에 nano 가 프록시 모델 목록에 없다 (sol / terra / luna / 5.5 / 5.4 / 5.4-mini).
#
# 새 예산은 비용이 아니라 한도와 지연이다. 실측: 이 diff 한 건에 output 475 토큰 중
# reasoning 이 291 (61%). 프록시는 무상태라 히스토리도 매번 다시 올라간다.
# M6에서 4개로 갈릴 때 무엇을 한 번만 계산해 나눠 쓸지가 여기서 결정된다.
MODEL = "gpt-5.6-luna"


# ─────────────────────────────────────────────────────────────────────
# TODO(human) ⑥ (계속) — 호출의 마감. **여기가 그 값이 사는 자리다** (2026-08-28, M6-4)
#
# `langgraph_engine.py` 의 TODO ⑥ 에서 "누가 소유하나"를 (B) 로 정했고, 그 (B) 가 여기다.
# 남은 건 **숫자 둘**이다.
#
# ── 관측 ────────────────────────────────────────────────────────────
#   n=12 (2026-08-25, security 한 관점):  min 10.09 · median 16.84 · max 41.40
#   n=4  (2026-08-28, 관점 넷 각 1판):    9.8 · 12.8 · 13.1 · 13.5
#   ⚠️ **p95 를 못 잰다** (📖 인쇄 217). n=3 일 때 최대 24.35 였는데 n=12 에서
#      41.40 으로 뛰었다 — 꼬리를 아직 못 봤고, 지금 고르는 값도 **잠정치**다.
#   ⚠️ 그리고 이건 **프록시** 지연이다. 진짜 API 로 되돌리면 분포가 통째로 바뀐다.
#
# ── ⚠️ 잠정 = 90초 · 재시도 1회. 네가 뒤집을 자리다 ─────────────────
#   **90 의 근거**: 관측 최대(41.4)의 두 배 조금 넘는다. "두 배"에 이론적 근거는 없고,
#   꼬리를 못 봤다는 사실에 대한 **여유**다. 짧게 잡을 때의 대가가 비대칭이라 넉넉히 뒀다 —
#   너무 짧으면 멀쩡한 응답을 끊고 `failed_agents` 에 이름을 올리는데, 게이트(M8)는
#   그걸 **"저 관점은 아무도 안 봤다"** 로 읽는다. 사실은 봤는데 우리가 끊은 것이다.
#   그건 이 프로젝트 최악의 시나리오(G2)와 같은 모양이다.
#
#   **재시도 1 의 근거**: SDK 기본이 **2** 다 (`openai/_constants.py:DEFAULT_MAX_RETRIES`).
#   그대로 두면 최악 대기가 `90 × 3 + 백오프` = **5분에 가깝다.** 노드 넷이 병렬이라
#   리뷰 한 건의 최대 지연이 그대로 그 값이 된다.
#   ⚠️ **재시도는 INV-2 를 다시 연다** — 타임아웃은 취소가 아니다 (Lesson 10).
#      우리가 기다리기를 그만두는 것뿐이고 저쪽 서버는 첫 요청을 계속 처리 중이다.
#      **같은 diff 를 두 번 리뷰하는 셈**이고, 한도도 두 번 쓴다.
#      지금 그게 안전한 이유는 **리뷰가 읽기 전용이라서**다 — 부작용이 없다.
#      ⬜ M8 에서 GitHub 게시가 붙으면 그 전제가 죽는다. 그때 이 값을 다시 본다.
#
# ── 후보 ────────────────────────────────────────────────────────────
#   시간:   (i) 45초 — 관측 최대에 붙인다. 꼬리를 만나면 거짓 실패가 난다
#           (ii) 90초 ← 잠정
#           (iii) 관측이 쌓이면 p95 × 여유 — **K판 데이터가 이미 `evals/runs/` 에 쌓인다**
#                 (`_usage_dict` 옆의 `elapsed`). 그걸로 다시 정하는 게 원래 계획이다
#   재시도: (i) 0 — INV-2 를 완전히 닫는다. 대신 일시적 장애에 그 관점이 통째로 빈다
#           (ii) 1 ← 잠정
#           (iii) 2 (SDK 기본) — 최악 5분
#
# ── 틀리면 뭐가 깨지나 ──────────────────────────────────────────────
#   짧으면: 멀쩡한 관점이 `failed_agents` 에 올라가고 게이트가 커버리지를 잘못 읽는다 (G2)
#   길면:   웹훅 → 큐 → 워커의 전체 지연이 늘어난다. GitHub 응답 제한(10초)과는 무관하다
#           (큐가 그걸 막는 게 존재 이유다) — 사람이 기다리는 시간이 늘 뿐이다
#   재시도 많으면: 한도를 태우고, 같은 리뷰가 여러 번 돈다
#
# 🔴 **잠정 (B) 의 전제가 깨졌다 — `timeout=90` 은 전체 대기의 상한이 아니다** (2026-08-28)
#
#    `OpenAI(timeout=90.0)` 은 httpx 에 **connect / read / write 각각 90초**로 들어간다.
#    `httpx.Timeout` 의 필드를 직접 확인하면 `['as_dict','connect','pool','read','write']` —
#    **`total` 이 없다.** `read` 는 *"한 번의 읽기"* 마감이라 서버가 조금씩 흘려보내면
#    **매번 갱신된다.** 목 서버로 실측: 마감 2.0초로 선언했는데 **77.5초** 매달렸다.
#    그리고 `max_retries=1` 이 그걸 **곱한다** (실측: 9.1초 → 18.1초).
#
#    ⚠️ **이게 `langgraph_engine.py` TODO ⑥ 이 (C)를 안 고른 근거를 정확히 깬다.**
#       거기 이렇게 적혀 있다: *"(C) 를 안 고른 이유는 바깥 마감을 재려면 스레드나
#       시그널이 필요한데 그 복잡도를 정당화할 관측이 아직 없다 —
#       **SDK 마감이 안 먹히는 걸 본 적이 없다.**"*  이제 봤다.
#
#    ⚠️ **정직하게 깎을 것 둘** (검증자가 스스로 깎았다):
#      · "38배"는 파라미터의 산물이다. 실제 값 90초로는 같은 응답이 다 들어와 **안 걸린다.**
#        **전형적 최악은 `90 × 2 + 백오프 ≈ 3분/에이전트`** 이고, 무한은 병리적 상대에서만.
#      · 그 병리적 상대는 **공격자 통제 입력이 아니다** — 열화·오작동하는 릴레이가 필요하다.
#        지금 호출부는 사람이 직접 돌리는 데모뿐이라 Ctrl-C 가 된다.
#        **피해는 M4(워커) 에 예약된 것이지 오늘의 것이 아니다.**
#
#    ⚠️ 그리고 **회귀 그물이 다른 코드를 재고 있다.** `demo_m5` 판정 ③(hang → 타임아웃)은
#       `M5_DUMMY_AGENTS=all` 이라 **진짜 `review_diff` 를 0번 부른다**(검증자 실측).
#       hang 주입 자체가 더미 분기에서만 가능하다 — 그물이 걸린 곳과 매달릴 수 있는 곳이 다르다.
#
#    ⏭ **그래서 후보 (C)(둘 다)의 값이 올라갔다.** 바깥 마감을 어디에 두나:
#       · `graph.compile(...)` 이 아니라 **`invoke(config={"step_timeout": ...})`**
#         — LangGraph 가 superstep 마감을 지원하는지 먼저 정찰할 것 (`/recon`)
#       · 노드 안에서 `concurrent.futures` 로 감싸 `future.result(timeout=)`
#       · `httpx.Timeout` 대신 총량을 재는 커스텀 트랜스포트
#       **이건 판단이고 코드도 는다 — 네가 고를 자리다.** M4 워커 배선 직전이 그 시점.
# ─────────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT_SECONDS: float = 90.0
MAX_RETRIES: int = 1


# ⚠️ **SYSTEM_PROMPT 상수가 여기 있었다. 지웠다** (2026-08-28, M6-4 배선).
#
#    M0 에서 한 덩어리 문자열이었고, M6-3a 에서 `backend/prompts/review.py` 로 옮겨
#    블록으로 갈렸다. 그런데 옮기기만 하고 **여기를 안 지워서 하루 동안 둘이 중복**이었고,
#    실제로 어긋나 있었다 — 여기엔 D3 로 뺐어야 할 `agent_type = security` 줄이
#    아직 살아 있었고, 관점도 한 덩어리 네 줄이었다(저쪽은 넷으로 갈린 SOP).
#
#    📌 그래서 `evals/runs/` 의 18판은 전부 **이 유물**을 잰 것이다.
#       `meta.prompt_source` 가 그걸 기록해 뒀다 — M6-3b 는 새 베이스라인부터 다시 뜬다.
#
#    교훈: 옮기는 커밋과 지우는 커밋을 나누면 그 사이에 "조용히 어긋난 창"이 생긴다.


def build_user_message(diff_text: str) -> str:
    """신뢰할 수 없는 diff 를 격리해서 user 메시지로 만든다."""
    # ─────────────────────────────────────────────────────────────────
    # TODO(human) ② diff 격리  — ✅ 채워짐 (M0)
    #
    # diff 를 그대로 반환하면 어디까지가 데이터인지 모델이 알 수 없다.
    # 시작과 끝을 표시해서 감쌀 것.
    #
    # 판단 두 개:
    #   (a) delimiter 를 뭘로 쓸까? 고르기 전에 반드시 물을 것 —
    #       "이 문자열이 diff 안에 나타날 수 있나?"
    #       코드 리뷰라는 게 무슨 뜻인지 생각하면 답이 불편해진다.
    #   (b) 나타날 수 있다면 어떻게 하나?
    #       그냥 두기 / 이스케이프 / 검사해서 거부 — 각각 뭘 잃나?
    #
    # 틀리면: diff 안에 닫는 delimiter 를 써넣어 격리를 깨고,
    #        그 뒤에 오는 글을 "지시"처럼 보이게 만들 수 있다.
    #        이 함수가 트러스트 바운더리의 실제 위치다.
    # ─────────────────────────────────────────────────────────────────
    built_message = f"<untrusted_diff> {diff_text} </untrusted_diff>"
    return built_message


def _refusal_text(response: object) -> str:
    """거부 응답에서 사람이 읽을 이유를 꺼낸다. 못 찾으면 상태값이라도 돌려준다."""
    for item in getattr(response, "output", []):
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "refusal":
                return getattr(content, "refusal", "")
    return f"이유 없음 (status={getattr(response, 'status', '?')})"


# ✅ **결정됨 (2026-08-28) — `agent_type` 은 필수 인자, `tag_rule` 은 토글로 연다.**
#
# 기각한 후보: 기본값을 주는 것(`agent_type="security"`). 그러면 `demo_m0.py` 와
# `eval_prompt.py` 가 **안 고쳐도 돌아간다** — 그게 문제다. `eval_prompt.py` 는
# 계속 security 만 재면서 파일명엔 그 사실을 안 남기고, 6개월 뒤 그 데이터를
# "넷을 잰 것"으로 읽게 된다. 조용히 틀린 데이터를 만드느니 시끄럽게 깨지는 게 낫다.
# 이 프로젝트가 같은 질문에 같은 답을 한 게 세 번째다 —
#   `security.py`  secret 없으면 부팅 거부
#   `base.py`      모델이 거부하면 빈 결과 대신 예외
#   여기           출처 없이 부르면 TypeError
#
# `tag_rule` 을 같이 연 이유: M6-3b 가 이 축을 실험해야 하는데
# `eval_prompt.py:192` 가 "변형을 넣을 구멍이 없다"고 적어둔 그 구멍이 여기였다.
# ⚠️ 아직 `eval_prompt.py` 가 이 인자를 안 넘긴다 — variant 슬롯 배선은 다음 조각.
def review_diff(
    diff_text: str, agent_type: AgentType, tag_rule: bool = True, model: str = MODEL
) -> tuple[list[SourcedFinding], ResponseUsage | None]:
    """diff 하나 → 출처가 붙은 finding 목록. (finding 들, 토큰 사용량) 을 돌려준다.

    usage 를 같이 돌려주는 이유: PLAN.md 의 '토큰 예산' 칸을 채워야 하고,
    M3에서 record_event(cost, latency, tokens) 를 붙일 때 여기가 그 자리가 된다.
    ⚠️ Responses API 라 필드명이 input_tokens / output_tokens 다
       (Chat Completions 의 prompt_tokens / completion_tokens 가 아니다).
       2026-08-28 에 `demo_m0.py` 가 옛 이름을 불러 실제로 터졌다 — 그래서 반환 타입을
       `object` 에서 진짜 타입으로 바꿨다. 이제 오타를 타입 검사기가 먼저 잡는다.
    ⚠️ `| None` 인 건 SDK 가 그렇게 선언해서다 (`Response.usage: Optional[...]`).
       여기서 임의로 0 을 채워 넣지 않는다 — "0 토큰 썼다"와 "모른다"는 다른 사실이고,
       M3 의 `record_event(tokens)` 가 그걸 구별해야 한다.
    """
    # base_url 은 OPENAI_BASE_URL 환경변수에서 SDK 가 알아서 읽는다.
    # 로컬 OAuth 프록시를 쓰는 동안엔 .env 가 거기를 가리키고, 진짜 API 로
    # 되돌리려면 .env 의 그 줄만 지우면 된다. 코드는 어느 쪽인지 몰라도 된다.
    client = OpenAI(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=MAX_RETRIES)

    # Chat Completions 가 아니라 Responses 를 쓰는 이유는 취향이 아니다.
    # 로컬 프록시의 /v1/chat/completions 는 response_format 을 조용히 무시하고
    # 자유 텍스트를 돌려준다 — 에러가 아니라 무시라서 더 위험하다.
    # /v1/responses 만 스키마를 실제로 강제한다. 실측 근거는 docs/CURRENT.md.
    # ⚠️ system 프롬프트가 상수가 아니라 **조립 결과**가 됐다 (M6-4).
    #    ⚠️ `tag_rule=` 로 이름을 대는 이유: 저쪽 시그니처가 `*` 로 키워드 전용을 강제한다.
    system_prompt = build_review_system_prompt(agent_type, tag_rule=tag_rule)

    # ⚠️ `model` 이 인자가 됐다 (2026-08-28, **M6-2** 모델 교체 실험).
    #    📖 책 인쇄 198 — *"'모델 역량 부족'과 '하네스 설계 결함'을 구분하는 일반적인 방법은
    #       **모델 교체 실험**입니다. **하네스를 고정한 채** 더 강하거나 약한 모델로 바꾸고
    #       점수가 얼마나 움직이는지 관찰합니다. **더 강한 모델로도 점수가 오르지 않으면
    #       병목은 하네스입니다.**"*
    #    기본값이 `MODEL` 이라 부르는 쪽은 안 고쳐도 된다 — 실험만 명시적으로 넘긴다.
    response = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_message(diff_text)},
        ],
        text_format=ReviewResult,
    )

    # ⚠️ **잘림을 먼저 본다** (2026-08-28, `PLAN.md` G-M0-2 를 메운다).
    #
    #    G-M0-2 는 M0 에서 관측됐고 *"어디서 메우나 = **M6**"* 로 배정돼 있었다:
    #    *"`finish_reason` 미체크. `length` 로 잘려도 `parsed` 가 채워져 통과.
    #     **잘린 rationale 이 완료 판정 ②를 PASS 로 통과한 사례 있음.**"*
    #
    #    Responses API 에서는 `finish_reason` 이 아니라 이 둘이다 (openai 2.49.0 확인):
    #        response.status              'completed' | 'incomplete' | 'failed' | …
    #        response.incomplete_details.reason   'max_output_tokens' | 'content_filter'
    #
    #    ⚠️ **`output_parsed` 검사보다 먼저** 와야 한다. 잘려도 파싱이 성공할 수 있고
    #       (구조가 우연히 닫히면), 그럼 **잘린 rationale 이 조용히 흘러간다.**
    #       그게 INV-3 을 형식적으로만 통과시키는 경로다 — 필드는 있는데 내용이 반쪽이다.
    #
    #    ⚠️ 거부와 **다른 예외로 안 나눈다.** `eval_prompt.py` 의 D7 은 `RuntimeError` 를
    #       `refused` 로 세는데, 잘림도 *"확인을 못 했다"* 라서 같은 통이 맞다.
    #       ⬜ 둘을 갈라야 할 이유가 생기면(예: 잘림률이 따로 봐야 할 숫자가 되면)
    #          그때 예외 타입을 나눈다 — 지금은 이유가 없다.
    if response.status == "incomplete":
        why = getattr(response.incomplete_details, "reason", None) or "이유 없음"
        raise RuntimeError(f"모델 응답이 잘렸다 (status=incomplete, reason={why})")

    # 모델이 거부하면 output_parsed 가 None 이다.
    # 여기서 빈 결과를 조용히 돌려주면 "문제가 없어서 비었다"와 구별이 안 된다.
    # 조용히 틀리는 게 시끄럽게 틀리는 것보다 나쁘다 — 터뜨린다.
    if response.output_parsed is None:
        raise RuntimeError(f"모델이 응답을 거부했다: {_refusal_text(response)}")

    # ✅ **결정됨 (2026-08-28) — 출처는 여기서 붙이고, 껍데기는 안 내보낸다.**
    #
    # 기각한 후보 둘:
    #   (i)  ReviewResult 를 그대로 주고 agent_type 을 따로 반환 — 호출자가 붙이게 되는데,
    #        `scripts/eval_prompt.py` 는 오케스트레이터를 안 지나가고 이 함수를 직접 부른다.
    #        붙이는 자리가 둘로 갈리면 한쪽을 잊고, 그럼 평가 데이터에 출처가 안 남는다.
    #   (iii) dict 로 눕혀서 반환 — `demo_m0.py` 의 속성 접근 8곳이 깨진다. 그건 감수할 수
    #        있는데, **타입이 오타를 못 잡게 된다.** `f["severty"]` 는 런타임에나 터진다.
    #        같은 세션에서 `agent_type: str` → `AgentType` 으로 고친 것과 반대 방향이다.
    #
    # `**f.model_dump()` 로 여섯 필드를 펼쳐 넣는다 — 손으로 옮겨 적지 않으므로
    # 나중에 `Finding` 에 필드가 늘어도 이 줄은 안 고쳐도 된다.
    # 📌 공짜 이득: dict 를 생성자에 다시 넣는 것이라 **검증이 한 번 더 돈다**
    #    (`line >= 1`, `0 <= confidence <= 1`). INV-3 이 여기서 재확인된다.
    #
    # ⚠️ `response.output_parsed`(= ReviewResult)를 반환하지 않는 이유는
    #    `schema.py` 의 `SourcedFinding` 독스트링에 실측과 함께 적어뒀다 —
    #    통째로 dump 하면 `agent_type` 이 조용히 사라진다.
    findings = [
        SourcedFinding(**f.model_dump(), agent_type=agent_type)
        for f in response.output_parsed.findings
    ]
    return findings, response.usage
