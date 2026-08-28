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
    diff_text: str, agent_type: AgentType, tag_rule: bool = True
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
    client = OpenAI()

    # Chat Completions 가 아니라 Responses 를 쓰는 이유는 취향이 아니다.
    # 로컬 프록시의 /v1/chat/completions 는 response_format 을 조용히 무시하고
    # 자유 텍스트를 돌려준다 — 에러가 아니라 무시라서 더 위험하다.
    # /v1/responses 만 스키마를 실제로 강제한다. 실측 근거는 docs/CURRENT.md.
    # ⚠️ system 프롬프트가 상수가 아니라 **조립 결과**가 됐다 (M6-4).
    #    ⚠️ `tag_rule=` 로 이름을 대는 이유: 저쪽 시그니처가 `*` 로 키워드 전용을 강제한다.
    system_prompt = build_review_system_prompt(agent_type, tag_rule=tag_rule)

    response = client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_message(diff_text)},
        ],
        text_format=ReviewResult,
    )

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
